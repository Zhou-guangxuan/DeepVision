"""第二大阶段：3D 教学实验室的训练服务。

与第一阶段的训练不同，实验室使用**内置双螺旋数据集**（2 维、2 类，
1400 训练 / 600 验证），结构由左侧面板实时决定，支持暂停 / 恢复，
逐 epoch 推送指标、权重分布直方图与决策边界网格。
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from uuid import uuid4

import numpy as np
import torch
from torch import nn

ACTIVATIONS = {
    "relu": nn.ReLU,
    "tanh": nn.Tanh,
    "sigmoid": nn.Sigmoid,
}

BOUNDARY_SIZE = 48
BOUNDARY_RANGE = 1.6
HISTOGRAM_BINS = 20
BOUNDARY_EVERY = 3

_TASKS: dict[str, "LabTask"] = {}
_LOCK = threading.Lock()


@dataclass
class LabTask:
    task_id: str
    user_id: int
    config: dict
    status: str = "idle"
    history: list[dict] = field(default_factory=list)
    lifecycle: list[dict] = field(default_factory=list)
    latest: dict = field(default_factory=dict)
    subscribers: list[asyncio.Queue] = field(default_factory=list)
    loop: asyncio.AbstractEventLoop | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    pause_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None


def create_task(*, user_id: int, config: dict) -> LabTask:
    task = LabTask(task_id=uuid4().hex, user_id=user_id, config=config)
    with _LOCK:
        _TASKS[task.task_id] = task
    return task


def get_task(task_id: str) -> LabTask | None:
    with _LOCK:
        return _TASKS.get(task_id)


def subscribe(task: LabTask) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue()
    if task.loop is None:
        task.loop = asyncio.get_running_loop()
    task.subscribers.append(queue)
    return queue


def unsubscribe(task: LabTask, queue: asyncio.Queue) -> None:
    if queue in task.subscribers:
        task.subscribers.remove(queue)


def emit(task: LabTask, event: dict) -> None:
    if event["type"] == "epoch":
        task.history.append(event)
    elif event["type"] in {"boundary", "weights"}:
        task.latest[event["type"]] = event
    else:
        task.lifecycle.append(event)

    loop = task.loop
    if loop is None:
        return
    for queue in list(task.subscribers):
        try:
            loop.call_soon_threadsafe(queue.put_nowait, event)
        except RuntimeError:
            continue


def pause(task: LabTask) -> None:
    task.pause_event.set()


def resume(task: LabTask) -> None:
    task.pause_event.clear()


def stop(task: LabTask) -> None:
    task.stop_event.set()
    task.pause_event.clear()


def start(task: LabTask) -> None:
    if task.thread is not None:
        return
    task.status = "running"
    task.thread = threading.Thread(target=_run, args=(task,), daemon=True)
    task.thread.start()


def build_spiral_dataset(seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    """标准双螺旋：两类各 1000 点，旋转 180° 交错。"""
    rng = np.random.default_rng(seed)
    per_class = 1000

    theta = np.linspace(0, 4 * np.pi, per_class)
    radius = theta / (4 * np.pi)

    x0 = np.stack([radius * np.cos(theta), radius * np.sin(theta)], axis=1)
    x1 = np.stack([-radius * np.cos(theta), -radius * np.sin(theta)], axis=1)

    features = np.vstack([x0, x1]) + rng.normal(0, 0.05, size=(2 * per_class, 2))
    labels = np.concatenate(
        [np.zeros(per_class, dtype=np.int64), np.ones(per_class, dtype=np.int64)]
    )

    order = rng.permutation(len(features))
    features = features[order]
    labels = labels[order]

    # 缩放到约 [-1, 1]
    features = features / (np.abs(features).max() + 1e-9)
    return features.astype("float32"), labels


def _apply_init(model: nn.Module, init: str) -> None:
    for module in model.modules():
        if not isinstance(module, nn.Linear):
            continue
        if init == "he":
            nn.init.kaiming_normal_(module.weight, nonlinearity="relu")
        elif init == "xavier":
            nn.init.xavier_uniform_(module.weight)
        else:
            nn.init.uniform_(module.weight, -0.1, 0.1)
        nn.init.zeros_(module.bias)


def build_model(config: dict) -> nn.Sequential:
    activation_name = str(config.get("activation", "relu"))
    activation = ACTIVATIONS.get(activation_name, nn.ReLU)
    dropout = float(config.get("dropout", 0.0))

    layers: list[nn.Module] = []
    previous = 2

    for units in config.get("hidden_layers", [8, 8]):
        size = max(1, min(int(units), 256))
        layers.append(nn.Linear(previous, size))
        layers.append(activation())
        if dropout > 0:
            layers.append(nn.Dropout(dropout))
        previous = size

    layers.append(nn.Linear(previous, 2))
    model = nn.Sequential(*layers)
    _apply_init(model, str(config.get("init", "he")))
    return model


def _weight_histogram(model: nn.Module) -> dict:
    weights = torch.cat(
        [
            module.weight.detach().flatten()
            for module in model.modules()
            if isinstance(module, nn.Linear)
        ]
    )
    values = weights.cpu().numpy()
    counts, edges = np.histogram(values, bins=HISTOGRAM_BINS)
    return {
        "type": "weights",
        "counts": [int(item) for item in counts],
        "edges": [round(float(item), 4) for item in edges],
        "min": round(float(values.min()), 4),
        "max": round(float(values.max()), 4),
        "total": int(values.size),
    }


def _decision_boundary(
    model: nn.Module,
    features: np.ndarray,
    labels: np.ndarray,
    sample: int = 320,
) -> dict:
    axis = np.linspace(-BOUNDARY_RANGE, BOUNDARY_RANGE, BOUNDARY_SIZE)
    grid_x, grid_y = np.meshgrid(axis, axis)
    points = np.stack([grid_x.ravel(), grid_y.ravel()], axis=1).astype("float32")

    model.eval()
    with torch.no_grad():
        logits = model(torch.from_numpy(points))
        probabilities = torch.softmax(logits, dim=1)[:, 1].numpy()

    step = max(1, len(features) // sample)
    sampled = features[::step][:sample]
    sampled_labels = labels[::step][:sample]

    return {
        "type": "boundary",
        "size": BOUNDARY_SIZE,
        "min": -BOUNDARY_RANGE,
        "max": BOUNDARY_RANGE,
        "values": [round(float(value), 4) for value in probabilities],
        "points": [
            {
                "x": round(float(point[0]), 4),
                "y": round(float(point[1]), 4),
                "label": int(label),
            }
            for point, label in zip(sampled, sampled_labels)
        ],
    }


def _run(task: LabTask) -> None:
    config = task.config
    epochs = max(1, min(int(config.get("epochs", 60)), 500))
    batch_size = max(1, int(config.get("batch_size", 32)))
    learning_rate = float(config.get("learning_rate", 0.05))
    l2 = float(config.get("l2", 0.0))

    try:
        features, labels = build_spiral_dataset()
        split = 1400
        x_train = torch.from_numpy(features[:split])
        y_train = torch.from_numpy(labels[:split])
        x_val = torch.from_numpy(features[split:])
        y_val = torch.from_numpy(labels[split:])

        model = build_model(config)
        parameter_count = sum(p.numel() for p in model.parameters())

        if str(config.get("optimizer", "adam")) == "sgd":
            optimizer = torch.optim.SGD(
                model.parameters(), lr=learning_rate, weight_decay=l2
            )
        else:
            optimizer = torch.optim.Adam(
                model.parameters(), lr=learning_rate, weight_decay=l2
            )

        loss_fn = nn.CrossEntropyLoss()
        started = time.perf_counter()

        emit(
            task,
            {
                "type": "started",
                "task_id": task.task_id,
                "total_epochs": epochs,
                "parameter_count": parameter_count,
                "train_size": int(x_train.shape[0]),
                "val_size": int(x_val.shape[0]),
            },
        )

        for epoch in range(1, epochs + 1):
            if task.stop_event.is_set():
                break

            while task.pause_event.is_set():
                if task.stop_event.is_set():
                    break
                time.sleep(0.05)

            if task.stop_event.is_set():
                break

            model.train()
            permutation = torch.randperm(x_train.shape[0])
            total_loss = 0.0
            batches = 0

            for offset in range(0, x_train.shape[0], batch_size):
                indices = permutation[offset : offset + batch_size]
                optimizer.zero_grad()
                output = model(x_train[indices])
                loss = loss_fn(output, y_train[indices])
                loss.backward()
                optimizer.step()
                total_loss += float(loss.item())
                batches += 1

            model.eval()
            with torch.no_grad():
                val_logits = model(x_val)
                val_loss = float(loss_fn(val_logits, y_val).item())
                accuracy = float(
                    (val_logits.argmax(dim=1) == y_val).float().mean().item()
                )

            grad_norm = sum(
                float(parameter.grad.detach().abs().sum())
                for parameter in model.parameters()
                if parameter.grad is not None
            )

            emit(
                task,
                {
                    "type": "epoch",
                    "epoch": epoch,
                    "total_epochs": epochs,
                    "train_loss": round(total_loss / max(batches, 1), 6),
                    "val_loss": round(val_loss, 6),
                    "accuracy": round(accuracy, 6),
                    "grad_norm": round(grad_norm, 6),
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                },
            )

            if epoch == 1 or epoch % BOUNDARY_EVERY == 0 or epoch == epochs:
                emit(task, _weight_histogram(model))
                emit(task, _decision_boundary(model, features, labels))

        if task.stop_event.is_set():
            task.status = "stopped"
            emit(task, {"type": "stopped", "epoch": len(task.history)})
        else:
            task.status = "completed"
            emit(task, {"type": "completed", "epochs": epochs})

    except Exception as exc:  # noqa: BLE001
        task.status = "failed"
        emit(task, {"type": "failed", "reason": str(exc)})
