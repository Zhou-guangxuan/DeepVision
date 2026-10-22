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

import numpy as np
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
from app.services import image_dataset
from app.services.dag_model import build_dag_net
from app.services.preprocessing import prepare_dataset

MAX_HISTORY_EVENTS = 2000


class ImageCNN(nn.Module):
    """图像实验线的固定小卷积网络（两条卷积 + 池化 + 全连接）。"""

    def __init__(self, num_classes: int, size: int) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1, 8, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(8, 16, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )
        reduced = max(1, size // 4)
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(16 * reduced * reduced, num_classes),
        )

    def forward(self, tensor: torch.Tensor) -> torch.Tensor:
        return self.classifier(self.features(tensor))


@dataclass
class TrainingTask:
    task_id: str
    user_id: int
    dataset_id: int
    config: dict
    plan: dict
    hyper: dict
    total_epochs: int
    # graph：按拓扑执行；image：固定 CNN 的图像实验线
    mode: str = "graph"
    status: str = "pending"
    history: list[dict] = field(default_factory=list)
    lifecycle: list[dict] = field(default_factory=list)
    layer_stats: list[dict] = field(default_factory=list)
    graph_profile: list[dict] = field(default_factory=list)
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


def create_image_task(*, user_id: int, dataset_id: int, hyper: dict) -> TrainingTask:
    task = TrainingTask(
        task_id=uuid4().hex,
        user_id=user_id,
        dataset_id=dataset_id,
        config={"kind": "image"},
        plan={},
        hyper=hyper,
        total_epochs=int(hyper.get("epochs", 20)),
        mode="image",
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
    target = _run_image_training if task.mode == "image" else _run_training
    task.thread = threading.Thread(target=target, args=(task,), daemon=True)
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
            "seed": int(task.hyper.get("seed", 42)),
            "history": list(task.history),
            "layer_stats": list(task.layer_stats),
            "graph_profile": list(task.graph_profile),
            "error": failure,
        },
        model_file_url=model_path,
        status=status,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _collect_layer_stats(
    net,
    sample_x: torch.Tensor,
    plan_order: list[str],
) -> list[dict]:
    """收集逐层可视化数据：权重绝对值之和、梯度范数、激活均值。

    由顶栏的「权重 / 梯度 / 激活」视图消费。
    """
    with torch.no_grad():
        outputs = net.forward_intermediates(sample_x)

    stats: list[dict] = []
    for node_id in plan_order:
        # nn.ModuleDict 没有 get()，只能先判断成员再取值
        if node_id not in net.ops:
            continue
        module = net.ops[node_id]

        parameters = list(module.parameters())
        weight_norm = sum(
            float(parameter.detach().abs().sum()) for parameter in parameters
        )
        grad_norm = sum(
            float(parameter.grad.detach().abs().sum())
            for parameter in parameters
            if parameter.grad is not None
        )

        # 权重分布统计：用于「张量演化」曲线（均值 / 标准差）
        if parameters:
            flat = torch.cat([parameter.detach().flatten() for parameter in parameters])
            weight_mean = float(flat.mean().item())
            weight_std = float(flat.std().item()) if flat.numel() > 1 else 0.0
        else:
            weight_mean = 0.0
            weight_std = 0.0

        activation = outputs.get(node_id)
        activation_mean = (
            float(activation.abs().mean().item()) if activation is not None else 0.0
        )

        stats.append(
            {
                "node_id": node_id,
                "weight_norm": round(weight_norm, 6),
                "weight_mean": round(weight_mean, 6),
                "weight_std": round(weight_std, 6),
                "grad_norm": round(grad_norm, 6),
                "activation_mean": round(activation_mean, 6),
            }
        )

    return stats


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
        # 固定随机种子，配合记录里的配置快照保证结果可复现
        seed = int(task.hyper.get("seed", 42))
        torch.manual_seed(seed)

        dataset = session.get(Dataset, task.dataset_id)
        if dataset is None:
            raise RuntimeError("数据集不存在")
        if dataset.user_id != task.user_id:
            raise RuntimeError("无权访问该数据集")

        nodes = {node["id"]: node for node in task.config["nodes"]}
        order = task.plan["order"]
        input_ids = list(
            task.plan.get("input_ids")
            or [nid for nid in order if nodes[nid]["type"] == "input"]
        )
        output_ids = list(
            task.plan.get("output_ids")
            or [nid for nid in order if nodes[nid]["type"] == "output"]
        )
        if not input_ids or not output_ids:
            raise RuntimeError("拓扑缺少输入层或输出层")

        task_type = str(
            nodes[output_ids[0]].get("params", {}).get("task", "classification")
        )
        prepared = prepare_dataset(dataset, task_type)

        # 多输入：按各输入层声明的特征数依次切分特征维
        declared_sizes = [
            int(nodes[nid].get("params", {}).get("features", 0) or 0)
            for nid in input_ids
        ]
        if any(size <= 0 for size in declared_sizes):
            if len(input_ids) == 1:
                declared_sizes = [prepared.input_dim]
            else:
                raise RuntimeError("存在多个输入层时，每个输入层都必须填写特征数")

        total_declared = sum(declared_sizes)
        if total_declared != prepared.input_dim:
            detail = "、".join(
                f"{nid}:{size}"
                for nid, size in zip(input_ids, declared_sizes, strict=True)
            )
            raise RuntimeError(
                f"输入层特征数之和 {total_declared}（{detail}）与预处理后的实际特征数 "
                f"{prepared.input_dim} 不一致（类别特征会做独热编码，请按实际维度分配）"
            )

        input_slices: dict[str, tuple[int, int]] = {}
        cursor = 0
        for nid, size in zip(input_ids, declared_sizes, strict=True):
            input_slices[nid] = (cursor, cursor + size)
            cursor += size

        # 多输出：按均值合并，因此每个输出层的单元数必须与类别数一致
        if task_type == "classification":
            for nid in output_ids:
                units = int(
                    nodes[nid].get("params", {}).get("units", 0)
                    or (prepared.num_classes or 2)
                )
                if units != (prepared.num_classes or 0):
                    raise RuntimeError(
                        f"输出层 {nid} 的单元数 {units} 与类别数 "
                        f"{prepared.num_classes} 不一致"
                    )
        elif len(output_ids) > 1:
            shapes = {
                int(nodes[nid].get("params", {}).get("units", 1) or 1)
                for nid in output_ids
            }
            if len(shapes) > 1:
                raise RuntimeError("多个输出层的单元数必须一致（训练时按均值合并输出）")

        net = build_dag_net(
            task.plan, nodes, prepared.input_dim, input_slices=input_slices
        )

        x_train = torch.from_numpy(prepared.x_train)
        y_train = torch.from_numpy(prepared.y_train)
        x_val = torch.from_numpy(prepared.x_val)
        y_val = torch.from_numpy(prepared.y_val)

        # 训练运行时剖析：一次前向记录每层形状、dtype、参数量与耗时
        profile_batch = x_train[: min(32, int(x_train.shape[0]))]
        task.graph_profile = net.profile(profile_batch)

        batch_size = int(task.hyper.get("batch_size", 32))
        learning_rate = float(task.hyper.get("learning_rate", 0.001))
        epochs = int(task.hyper.get("epochs", task.total_epochs))

        optimizer = torch.optim.Adam(net.parameters(), lr=learning_rate)
        loss_fn = (
            nn.CrossEntropyLoss() if task_type == "classification" else nn.MSELoss()
        )

        _emit(
            task,
            {
                "type": "started",
                "task_id": task.task_id,
                "total_epochs": epochs,
                "input_dim": prepared.input_dim,
                "input_layers": len(input_ids),
                "output_layers": len(output_ids),
                "task": task_type,
                "classes": prepared.classes,
            },
        )

        # 计算图剖析结果在训练一开始就推给前端，重连时会随历史事件回放
        _emit(
            task,
            {
                "type": "graph_profile",
                "nodes": task.graph_profile,
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
            layer_stats = _collect_layer_stats(net, x_val[:32], task.plan["order"])
            task.layer_stats = layer_stats
            metrics = {
                "train_loss": round(total_loss / max(batches, 1), 6),
                "val_loss": round(val_loss, 6),
                "accuracy": None if accuracy is None else round(accuracy, 6),
                "grad_norm": round(sum(item["grad_norm"] for item in layer_stats), 6),
            }

            _emit(
                task,
                {
                    "type": "epoch",
                    "epoch": epoch,
                    "total_epochs": epochs,
                    **metrics,
                    "layer_stats": layer_stats,
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


def _run_image_training(task: TrainingTask) -> None:
    """图像实验线：内置合成数据集 + 固定小 CNN。

    事件结构与表格训练保持一致，前端训练页无需区分来源。
    """
    session = SessionLocal()
    started = time.perf_counter()
    metrics: dict = {}
    failure: str | None = None
    last_epoch = 0
    result_status = STATUS_FAILED

    try:
        dataset = session.get(Dataset, task.dataset_id)
        if dataset is None:
            raise RuntimeError("数据集不存在")
        if dataset.user_id != task.user_id:
            raise RuntimeError("无权访问该数据集")
        if dataset.kind != "image":
            raise RuntimeError("该数据集不是图像数据集")

        x, y = image_dataset.load(dataset.file_path)
        num_classes = len(dataset.stats.get("classes", [])) or 2
        size = int(dataset.stats.get("size", x.shape[2]))

        seed = int(task.hyper.get("seed", 42))
        torch.manual_seed(seed)

        rng = np.random.default_rng(42)
        order = rng.permutation(len(x))
        split = int(len(x) * 0.8)
        train_index, val_index = order[:split], order[split:]

        x_train = torch.from_numpy(x[train_index])
        y_train = torch.from_numpy(y[train_index])
        x_val = torch.from_numpy(x[val_index])
        y_val = torch.from_numpy(y[val_index])

        model = ImageCNN(num_classes, size)
        optimizer = torch.optim.Adam(
            model.parameters(),
            lr=float(task.hyper.get("learning_rate", 0.001)),
        )
        loss_fn = nn.CrossEntropyLoss()

        batch_size = int(task.hyper.get("batch_size", 32))
        epochs = int(task.hyper.get("epochs", task.total_epochs))

        _emit(
            task,
            {
                "type": "started",
                "task_id": task.task_id,
                "total_epochs": epochs,
                "input_dim": size * size,
                "input_layers": 1,
                "output_layers": 1,
                "task": "classification",
                "classes": list(dataset.stats.get("classes", [])),
                "mode": "image",
            },
        )

        for epoch in range(1, epochs + 1):
            if task.stop_event.is_set():
                result_status = STATUS_INTERRUPTED
                break

            model.train()
            permutation = torch.randperm(len(x_train))
            total_loss = 0.0
            batches = 0

            for offset in range(0, len(x_train), batch_size):
                indices = permutation[offset : offset + batch_size]
                optimizer.zero_grad()
                loss = loss_fn(model(x_train[indices]), y_train[indices])
                loss.backward()
                optimizer.step()
                total_loss += float(loss.item())
                batches += 1

            model.eval()
            with torch.no_grad():
                logits = model(x_val)
                val_loss = float(loss_fn(logits, y_val).item())
                accuracy = float((logits.argmax(dim=1) == y_val).float().mean().item())

            last_epoch = epoch
            _emit(
                task,
                {
                    "type": "epoch",
                    "epoch": epoch,
                    "total_epochs": epochs,
                    "train_loss": round(total_loss / max(batches, 1), 6),
                    "val_loss": round(val_loss, 6),
                    "accuracy": round(accuracy, 6),
                    "grad_norm": 0.0,
                    "layer_stats": [],
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                },
            )

        if result_status != STATUS_INTERRUPTED:
            result_status = STATUS_SUCCESS
        metrics = {
            "val_loss": round(val_loss, 6) if last_epoch else None,
            "accuracy": round(accuracy, 6) if last_epoch else None,
        }
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
                None,
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
                    "final_loss": metrics.get("val_loss"),
                    "final_accuracy": metrics.get("accuracy"),
                    "record_id": record_id,
                    "epochs": last_epoch,
                },
            )
        elif result_status == STATUS_INTERRUPTED:
            _emit(task, {"type": "stopped", "epoch": last_epoch})
        else:
            _emit(task, {"type": "failed", "reason": failure or "训练失败"})
