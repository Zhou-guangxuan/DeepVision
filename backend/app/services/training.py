"""训练任务管理与执行。

设计要点：

- 训练在**线程**中执行，通过 asyncio.Queue 把事件推送给 WebSocket 客户端；
- 事件先写入任务内的历史列表再广播；客户端断线重连时先回放历史，避免丢数据；
- 训练结束后（无论成功、失败还是中断）都会写入 `training_records`。
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import torch
from torch import nn

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.dataset import Dataset
from app.models.record import (
    STATUS_FAILED,
    STATUS_INTERRUPTED,
    STATUS_SUCCESS,
    TrainingRecord,
)
from app.services.dag_model import build_dag_net
from app.services.preprocessing import prepare_dataset

MAX_HISTORY_EVENTS = 2000


@dataclass
class TrainingTask:
    task_id: str
    user_id: int
    dataset_id: int
    config: dict
    plan: dict
    hyper: dict
    total_epochs: int
    status: str = "pending"
    history: list[dict] = field(default_factory=list)
    lifecycle: list[dict] = field(default_factory=list)
    subscribers: list[asyncio.Queue] = field(default_factory=list)
    loop: asyncio.AbstractEventLoop | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None


_TASKS: dict[str, TrainingTask] = {}
_LOCK = threading.Lock()


def create_task(
    *,
    user_id: int,
    dataset_id: int,
    config: dict,
    plan: dict,
    hyper: dict,
) -> TrainingTask:
    task = TrainingTask(
        task_id=uuid4().hex,
        user_id=user_id,
        dataset_id=dataset_id,
        config=config,
        plan=plan,
        hyper=hyper,
        total_epochs=int(hyper.get("epochs", 20)),
    )
    with _LOCK:
        _TASKS[task.task_id] = task
    return task


def get_task(task_id: str) -> TrainingTask | None:
    with _LOCK:
        return _TASKS.get(task_id)


def subscribe(task: TrainingTask) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue()
    if task.loop is None:
        task.loop = asyncio.get_running_loop()
    task.subscribers.append(queue)
    return queue


def unsubscribe(task: TrainingTask, queue: asyncio.Queue) -> None:
    if queue in task.subscribers:
        task.subscribers.remove(queue)


def request_stop(task: TrainingTask) -> None:
    task.stop_event.set()


def start(task: TrainingTask) -> None:
    if task.thread is not None:
        return
    task.status = "running"
    task.thread = threading.Thread(
        target=_run_training, args=(task,), daemon=True
    )
    task.thread.start()


def _emit(task: TrainingTask, event: dict) -> None:
    if event.get("type") == "epoch":
        task.history.append(event)
        if len(task.history) > MAX_HISTORY_EVENTS:
            task.history.pop(0)
    else:
        task.lifecycle.append(event)

    loop = task.loop
    if loop is None:
        return
    for queue in list(task.subscribers):
        try:
            loop.call_soon_threadsafe(queue.put_nowait, event)
        except RuntimeError:
            # 事件循环已关闭（例如客户端已断开）
            continue


def _finalize(
    session,
    task: TrainingTask,
    status: str,
    metrics: dict,
    model_path: str | None,
    failure: str | None,
    duration: float,
    last_epoch: int,
) -> TrainingRecord:
    record = TrainingRecord(
        user_id=task.user_id,
        dataset_id=task.dataset_id,
        task_id=task.task_id,
        network_config=task.config,
        hyperparameters=task.hyper,
        result_metrics={
            "final_loss": metrics.get("val_loss"),
            "final_accuracy": metrics.get("accuracy"),
            "duration_sec": duration,
            "epochs": last_epoch,
            "history": list(task.history),
            "error": failure,
        },
        model_file_url=model_path,
        status=status,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _run_training(task: TrainingTask) -> None:
    settings = get_settings()
    session = SessionLocal()

    started = time.perf_counter()
    metrics: dict = {}
    model_path: str | None = None
    failure: str | None = None
    last_epoch = 0
    result_status = STATUS_FAILED

    try:
        dataset = session.get(Dataset, task.dataset_id)
        if dataset is None:
            raise RuntimeError("数据集不存在")
        if dataset.user_id != task.user_id:
            raise RuntimeError("无权访问该数据集")

        nodes = {node["id"]: node for node in task.config["nodes"]}
        input_node = next(
            node for node in task.config["nodes"] if node["type"] == "input"
        )
        output_node = next(
            node for node in task.config["nodes"] if node["type"] == "output"
        )

        task_type = str(output_node.get("params", {}).get("task", "classification"))
        prepared = prepare_dataset(dataset, task_type)

        declared = int(
            input_node.get("params", {}).get("features", prepared.input_dim)
        )
        if declared != prepared.input_dim:
            raise RuntimeError(
                f"输入层特征数 {declared} 与预处理后的实际特征数 "
                f"{prepared.input_dim} 不一致（类别特征会做独热编码，请按实际维度调整输入层）"
            )

        if task_type == "classification":
            units = int(
                output_node.get("params", {}).get(
                    "units", prepared.num_classes or 2
                )
            )
            if units != (prepared.num_classes or 0):
                raise RuntimeError(
                    f"输出层单元数 {units} 与类别数 {prepared.num_classes} 不一致"
                )

        net = build_dag_net(task.plan, nodes, prepared.input_dim)

        x_train = torch.from_numpy(prepared.x_train)
        y_train = torch.from_numpy(prepared.y_train)
        x_val = torch.from_numpy(prepared.x_val)
        y_val = torch.from_numpy(prepared.y_val)

        batch_size = int(task.hyper.get("batch_size", 32))
        learning_rate = float(task.hyper.get("learning_rate", 0.001))
        epochs = int(task.hyper.get("epochs", task.total_epochs))

        optimizer = torch.optim.Adam(net.parameters(), lr=learning_rate)
        loss_fn = (
            nn.CrossEntropyLoss()
            if task_type == "classification"
            else nn.MSELoss()
        )

        _emit(
            task,
            {
                "type": "started",
                "task_id": task.task_id,
                "total_epochs": epochs,
                "input_dim": prepared.input_dim,
                "task": task_type,
                "classes": prepared.classes,
            },
        )

        for epoch in range(1, epochs + 1):
            if task.stop_event.is_set():
                result_status = STATUS_INTERRUPTED
                break

            net.train()
            permutation = torch.randperm(x_train.shape[0])
            total_loss = 0.0
            batches = 0

            for offset in range(0, x_train.shape[0], batch_size):
                indices = permutation[offset : offset + batch_size]
                batch_x = x_train[indices]
                batch_y = y_train[indices]

                optimizer.zero_grad()
                output = net(batch_x)
                if task_type == "classification":
                    loss = loss_fn(output, batch_y)
                else:
                    loss = loss_fn(output.squeeze(-1), batch_y)
                loss.backward()
                optimizer.step()

                total_loss += float(loss.item())
                batches += 1

            net.eval()
            with torch.no_grad():
                val_output = net(x_val)
                if task_type == "classification":
                    val_loss = float(loss_fn(val_output, y_val).item())
                    accuracy = float(
                        (val_output.argmax(dim=1) == y_val).float().mean().item()
                    )
                else:
                    val_loss = float(loss_fn(val_output.squeeze(-1), y_val).item())
                    accuracy = None

            last_epoch = epoch
            metrics = {
                "train_loss": round(total_loss / max(batches, 1), 6),
                "val_loss": round(val_loss, 6),
                "accuracy": None if accuracy is None else round(accuracy, 6),
            }

            _emit(
                task,
                {
                    "type": "epoch",
                    "epoch": epoch,
                    "total_epochs": epochs,
                    **metrics,
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                },
            )

        if result_status != STATUS_INTERRUPTED:
            model_dir = Path(settings.storage_dir) / "models" / str(task.user_id)
            model_dir.mkdir(parents=True, exist_ok=True)
            model_file = model_dir / f"{task.task_id}.pt"
            torch.save(net.state_dict(), model_file)
            model_path = str(model_file)
            result_status = STATUS_SUCCESS

    except Exception as exc:  # noqa: BLE001
        failure = str(exc)
        result_status = STATUS_FAILED
    finally:
        duration = round(time.perf_counter() - started, 3)
        try:
            record = _finalize(
                session,
                task,
                result_status,
                metrics,
                model_path,
                failure,
                duration,
                last_epoch,
            )
            record_id = record.id
        except Exception as exc:  # noqa: BLE001
            record_id = None
            failure = failure or str(exc)
        finally:
            session.close()

        task.status = "success" if result_status == STATUS_SUCCESS else result_status

        if result_status == STATUS_SUCCESS:
            _emit(
                task,
                {
                    "type": "completed",
                    "record_id": record_id,
                    "final_loss": metrics.get("val_loss"),
                    "final_accuracy": metrics.get("accuracy"),
                    "duration_sec": duration,
                },
            )
        elif result_status == STATUS_INTERRUPTED:
            _emit(
                task,
                {"type": "stopped", "epoch": last_epoch, "record_id": record_id},
            )
        else:
            _emit(
                task,
                {
                    "type": "failed",
                    "reason": failure or "训练失败",
                    "record_id": record_id,
                },
            )
