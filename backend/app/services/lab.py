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

from app.db.session import SessionLocal

ACTIVATIONS = {
    "relu": nn.ReLU,
    "tanh": nn.Tanh,
    "sigmoid": nn.Sigmoid,
}

BOUNDARY_SIZE = 48
BOUNDARY_RANGE = 1.6
HISTOGRAM_BINS = 20
BOUNDARY_EVERY = 3

_TASKS: dict[str, LabTask] = {}
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
    # 训练结束后保留模型与数据，供「前向/反向传播」「注意力」「降维投影」使用
    model: nn.Module | None = None
    features: np.ndarray | None = None
    labels: np.ndarray | None = None
    record_id: int | None = None
    # 快照回放：按间隔保存 state_dict（小模型只有几 KB）
    snapshots: list[dict] = field(default_factory=list)


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


def build_dataset(
    input_dim: int = 2, num_classes: int = 2, seed: int = 42
) -> tuple[np.ndarray, np.ndarray]:
    """生成教学数据集。

    - 2 类：标准双螺旋（两类各 1000 点，旋转 180° 交错）；
    - 多类：各类中心均匀分布在一个圆上，便于观察多分类决策边界；
    - 输入维度 > 2 时，额外维度用噪声填充（不影响前两维的可视化）。
    """
    rng = np.random.default_rng(seed)

    input_dim = max(1, min(int(input_dim), 16))
    num_classes = max(2, min(int(num_classes), 8))
    per_class = max(80, 2000 // num_classes)

    if num_classes == 2:
        theta = np.linspace(0, 4 * np.pi, per_class)
        radius = theta / (4 * np.pi)
        base0 = np.stack([radius * np.cos(theta), radius * np.sin(theta)], axis=1)
        base1 = -base0
        base = np.vstack([base0, base1]) + rng.normal(0, 0.05, size=(2 * per_class, 2))
    else:
        arms: list[np.ndarray] = []
        for index in range(num_classes):
            angle = 2 * np.pi * index / num_classes
            center = np.array([np.cos(angle), np.sin(angle)]) * 0.65
            arms.append(center + rng.normal(0, 0.16, size=(per_class, 2)))
        base = np.vstack(arms)

    labels = np.repeat(np.arange(num_classes, dtype=np.int64), per_class)

    # 前两维缩放到约 [-1, 1]
    scale = float(np.abs(base).max()) or 1.0
    base = base / scale

    if input_dim <= 2:
        features = base[:, :input_dim]
    else:
        extra = rng.normal(0, 0.35, size=(len(base), input_dim - 2))
        features = np.hstack([base, extra])

    order = rng.permutation(len(features))
    return features[order].astype("float32"), labels[order]


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
    input_units = max(1, min(int(config.get("input_units", 2)), 16))
    output_units = max(2, min(int(config.get("output_units", 2)), 8))
    previous = input_units

    for units in config.get("hidden_layers", [8, 8]):
        size = max(1, min(int(units), 256))
        layers.append(nn.Linear(previous, size))
        layers.append(activation())
        if dropout > 0:
            layers.append(nn.Dropout(dropout))
        previous = size

    layers.append(nn.Linear(previous, output_units))
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
    input_dim: int = 2,
    sample: int = 320,
) -> dict:
    axis = np.linspace(-BOUNDARY_RANGE, BOUNDARY_RANGE, BOUNDARY_SIZE)
    grid_x, grid_y = np.meshgrid(axis, axis)
    flat = np.stack([grid_x.ravel(), grid_y.ravel()], axis=1).astype("float32")

    # 输入维度大于 2 时，其余维度补 0（只看前两维的切面）
    if input_dim > 2:
        points = np.zeros((len(flat), input_dim), dtype="float32")
        points[:, :2] = flat
    else:
        points = flat[:, :input_dim]

    model.eval()
    with torch.no_grad():
        logits = model(torch.from_numpy(points))
        probabilities = torch.softmax(logits, dim=1).numpy()

    # 多分类时前端按「每个格子的预测类别 + 置信度」着色
    predicted = probabilities.argmax(axis=1)
    confidence = probabilities.max(axis=1)

    step = max(1, len(features) // sample)
    sampled = features[::step][:sample]
    sampled_labels = labels[::step][:sample]

    return {
        "type": "boundary",
        "size": BOUNDARY_SIZE,
        "min": -BOUNDARY_RANGE,
        "max": BOUNDARY_RANGE,
        "classes": [int(value) for value in predicted],
        "confidence": [round(float(value), 4) for value in confidence],
        "points": [
            {
                "x": round(float(point[0]), 4),
                "y": round(float(point[1]), 4),
                "label": int(label),
            }
            for point, label in zip(sampled, sampled_labels, strict=True)
        ],
    }


def _run(task: LabTask) -> None:
    config = task.config
    epochs = max(1, min(int(config.get("epochs", 60)), 500))
    snapshot_every = max(1, epochs // 20)
    batch_size = max(1, int(config.get("batch_size", 32)))
    learning_rate = float(config.get("learning_rate", 0.05))
    l2 = float(config.get("l2", 0.0))

    try:
        # 固定种子：教学任务与快照回放需要可复现的结果
        torch.manual_seed(42)

        input_units = max(1, min(int(config.get("input_units", 2)), 16))
        output_units = max(2, min(int(config.get("output_units", 2)), 8))

        features, labels = build_dataset(input_units, output_units)
        split = min(1400, max(100, len(features) - 100))
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
                "input_units": input_units,
                "output_units": output_units,
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

            # 注意力随 epoch 变化：取验证集前 32 条，按 |∂loss/∂x × x| 求特征均值
            attention = _sample_attention(model, x_val[:32], y_val[:32])

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
                    "attention": attention,
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                },
            )

            if epoch == 1 or epoch % BOUNDARY_EVERY == 0 or epoch == epochs:
                emit(task, _weight_histogram(model))
                emit(
                    task,
                    _decision_boundary(model, features, labels, input_dim=input_units),
                )

            # 快照回放：最多保留约 20 份参数
            if (epoch == 1 or epoch % snapshot_every == 0 or epoch == epochs) and (
                not task.snapshots or task.snapshots[-1]["epoch"] != epoch
            ):
                task.snapshots.append(
                    {
                        "epoch": epoch,
                        "accuracy": round(accuracy, 4),
                        "val_loss": round(val_loss, 4),
                        "state": {
                            key: value.detach().clone()
                            for key, value in model.state_dict().items()
                        },
                    }
                )

        # 训练结束（含中止）都保留模型与数据，供传播演示 / 降维投影使用
        model.eval()
        task.model = model
        task.features = features
        task.labels = labels
        _save_record(task, epochs=len(task.history), stopped=task.stop_event.is_set())

        if task.stop_event.is_set():
            task.status = "stopped"
            emit(task, {"type": "stopped", "epoch": len(task.history)})
        else:
            task.status = "completed"
            emit(task, {"type": "completed", "epochs": epochs})

    except Exception as exc:  # noqa: BLE001
        task.status = "failed"
        emit(task, {"type": "failed", "reason": str(exc)})


def _save_record(task: LabTask, epochs: int, stopped: bool = False) -> None:
    """把实验室训练结果写入 training_records（source = lab）。失败不影响训练结果。"""
    from app.models.record import STATUS_INTERRUPTED, STATUS_SUCCESS, TrainingRecord

    last = task.history[-1] if task.history else {}
    metrics = {
        "epochs": epochs,
        "final_loss": last.get("val_loss"),
        "final_accuracy": last.get("accuracy"),
        "grad_norm": last.get("grad_norm"),
        "history": task.history[-200:],
        "dataset": "spiral",
    }

    session = SessionLocal()
    try:
        record = TrainingRecord(
            user_id=task.user_id,
            dataset_id=None,
            task_id=task.task_id,
            network_config={
                "source": "lab",
                "hidden_layers": task.config.get("hidden_layers"),
                "activation": task.config.get("activation"),
                "init": task.config.get("init"),
            },
            hyperparameters={
                key: task.config.get(key)
                for key in (
                    "optimizer",
                    "learning_rate",
                    "batch_size",
                    "epochs",
                    "l2",
                    "dropout",
                )
            },
            result_metrics=metrics,
            status=STATUS_INTERRUPTED if stopped else STATUS_SUCCESS,
            source="lab",
        )
        session.add(record)
        session.commit()
        task.record_id = record.id
    except Exception:  # noqa: BLE001
        session.rollback()
    finally:
        session.close()


def inspect(task: LabTask, index: int) -> dict:
    """取一条样本做一次前向 + 反向，返回逐层激活与梯度，以及输入注意力。"""
    if task.model is None or task.features is None or task.labels is None:
        raise ValueError("训练尚未开始，无法查看传播过程")

    total = int(len(task.features))
    if not 0 <= index < total:
        raise ValueError(f"样本序号需在 0 到 {total - 1} 之间")

    model = task.model
    model.eval()
    model.zero_grad(set_to_none=True)

    x = torch.from_numpy(task.features[index : index + 1]).clone().requires_grad_(True)
    target = int(task.labels[index])

    tensors: list[torch.Tensor] = []

    hidden = x
    for module in model:
        hidden = module(hidden)
        if isinstance(module, nn.Linear):
            hidden.retain_grad()
            tensors.append(hidden)

    logits = hidden
    loss = nn.CrossEntropyLoss()(logits, torch.tensor([target]))
    loss.backward()

    layers = []
    for order, tensor in enumerate(tensors):
        gradient = tensor.grad
        size = int(tensor.shape[1])
        layers.append(
            {
                "index": order,
                "size": size,
                "activation": [
                    round(float(value), 5)
                    for value in tensor.detach().flatten().tolist()
                ],
                "gradient": [
                    round(float(value), 5)
                    for value in (
                        gradient.detach().flatten().tolist()
                        if gradient is not None
                        else [0.0] * size
                    )
                ],
            }
        )

    # 注意力：输入梯度的绝对值 × 输入值，衡量该特征对本次预测的贡献
    input_vector = task.features[index]
    if x.grad is not None:
        grad_vector = x.grad.detach().flatten().numpy()
    else:
        grad_vector = np.zeros_like(input_vector)
    saliency = np.abs(grad_vector * input_vector)

    probabilities = torch.softmax(logits.detach(), dim=1).flatten().tolist()
    result = {
        "sample_index": index,
        "total_samples": total,
        "true_label": target,
        "prediction": int(logits.detach().argmax(dim=1).item()),
        "probabilities": [round(float(value), 5) for value in probabilities],
        "input": [round(float(value), 5) for value in input_vector],
        "saliency": [round(float(value), 5) for value in saliency],
        "layers": layers,
        "loss": round(float(loss.item()), 6),
    }

    model.zero_grad(set_to_none=True)
    return result


def _sample_attention(
    model: nn.Module, x_sample: torch.Tensor, y_sample: torch.Tensor
) -> list[float]:
    """一批样本的平均输入注意力：|∂loss/∂x × x| 在样本维取均值。"""
    model.zero_grad(set_to_none=True)
    x = x_sample.clone().requires_grad_(True)

    logits = model(x)
    loss = nn.CrossEntropyLoss()(logits, y_sample)
    loss.backward()

    if x.grad is None:
        model.zero_grad(set_to_none=True)
        return [0.0] * int(x_sample.shape[1])

    values = (x.grad * x).abs().mean(dim=0).detach().numpy()
    model.zero_grad(set_to_none=True)
    return [round(float(value), 6) for value in values]


def _pca_coords(matrix: np.ndarray) -> tuple[np.ndarray, list[float]]:
    """主成分分析：返回前两个主成分上的坐标与各自解释方差占比。"""
    centered = matrix - matrix.mean(axis=0, keepdims=True)
    left, singular, _ = np.linalg.svd(centered, full_matrices=False)
    coords = left[:, :2] * singular[:2]

    variance = singular**2
    total = float(variance.sum()) or 1.0
    explained = [round(float(value / total), 4) for value in variance[:2]]
    return coords, explained


def _tsne_coords(
    matrix: np.ndarray,
    perplexity: float = 25.0,
    iterations: int = 300,
    learning_rate: float = 200.0,
    seed: int = 42,
) -> np.ndarray:
    """精简版精确 t-SNE（O(n²)），适合教学场景的几百个样本。

    没有引入 scikit-learn：先按困惑度二分搜索每点的 σ 得到条件概率，
    再对称化为联合概率 P，最后对低维坐标做带动量的梯度下降拟合 Q。
    """
    n = int(matrix.shape[0])
    if n < 10:
        raise ValueError("样本太少，无法做 t-SNE")

    perplexity = min(perplexity, max(2.0, (n - 1) / 3.0))
    target_entropy = np.log(perplexity)

    squared = (matrix**2).sum(axis=1)
    distances = squared[:, None] + squared[None, :] - 2 * matrix @ matrix.T
    np.maximum(distances, 0, out=distances)
    np.fill_diagonal(distances, 0.0)

    conditional = np.zeros((n, n))
    for i in range(n):
        row = distances[i].copy()
        row[i] = np.inf

        beta = 1.0
        beta_min, beta_max = 1e-20, 1e20
        probabilities = np.full(n, 1.0 / n)

        for _ in range(60):
            weights = np.exp(-row * beta)
            total = float(weights.sum())
            if total <= 0:
                probabilities = np.full(n, 1.0 / n)
                break

            probabilities = weights / total
            entropy = float(-(probabilities * np.log(probabilities + 1e-12)).sum())
            if abs(entropy - target_entropy) < 1e-5:
                break

            if entropy > target_entropy:
                beta_min = beta
                beta = beta * 2 if beta_max >= 1e20 else (beta + beta_max) / 2
            else:
                beta_max = beta
                beta = beta / 2 if beta_min <= 1e-20 else (beta + beta_min) / 2

        conditional[i] = probabilities

    p = (conditional + conditional.T) / (2 * n)
    p = np.maximum(p, 1e-12)

    rng = np.random.default_rng(seed)
    y = rng.normal(0, 1e-4, size=(n, 2))
    velocity = np.zeros_like(y)
    gains = np.ones_like(y)

    for _ in range(iterations):
        sum_y = (y**2).sum(axis=1)
        similarities = 1.0 / (1.0 + sum_y[:, None] + sum_y[None, :] - 2 * y @ y.T)
        np.fill_diagonal(similarities, 0.0)

        total = float(similarities.sum()) or 1.0
        q = similarities / total
        weighted = (p - q) * similarities

        gradient = 4 * (weighted.sum(axis=1)[:, None] * y - weighted @ y)
        gains = np.where(
            np.sign(gradient) != np.sign(velocity), gains + 0.2, gains * 0.8
        )
        np.maximum(gains, 0.01, out=gains)

        velocity = 0.8 * velocity - learning_rate * gains * gradient
        y += velocity
        y -= y.mean(axis=0)

    return y


def project(
    task: LabTask, layer_index: int, max_points: int = 600, method: str = "pca"
) -> dict:
    """对指定层的输出降维到二维：pca（线性）或 tsne（非线性）。"""
    if task.model is None or task.features is None or task.labels is None:
        raise ValueError("训练尚未开始，无法做降维投影")

    if method not in {"pca", "tsne"}:
        raise ValueError("不支持的投影方法")

    # t-SNE 复杂度较高，限制点数以保证响应时间
    if method == "tsne":
        max_points = min(max_points, 300)
    if task.model is None or task.features is None or task.labels is None:
        raise ValueError("训练尚未开始，无法做降维投影")

    model = task.model
    model.eval()

    features = task.features[:max_points]
    labels = task.labels[:max_points]

    with torch.no_grad():
        hidden = torch.from_numpy(features)
        cursor = 0
        found = False
        for module in model:
            hidden = module(hidden)
            if isinstance(module, nn.Linear):
                if cursor == layer_index:
                    found = True
                    break
                cursor += 1

    if not found:
        raise ValueError("层序号超出范围")

    matrix = hidden.detach().numpy().astype("float64")

    if method == "tsne":
        coords, explained = _tsne_coords(matrix), []
    else:
        coords, explained = _pca_coords(matrix)

    scale = float(np.abs(coords).max()) or 1.0
    coords = coords / scale

    return {
        "layer_index": layer_index,
        "layer_count": sum(1 for module in model if isinstance(module, nn.Linear)),
        "method": method,
        "explained": explained,
        "points": [
            {
                "x": round(float(point[0]), 4),
                "y": round(float(point[1]), 4),
                "label": int(label),
            }
            for point, label in zip(coords, labels, strict=True)
        ],
    }


def attention_history(task: LabTask) -> dict:
    """逐 epoch 的输入注意力，用于观察「模型在关注哪些特征」如何变化。"""
    events = [event for event in task.history if "attention" in event]
    if not events:
        raise ValueError("暂无训练数据，请先完成一次训练")

    size = len(events[0]["attention"])
    return {
        "epochs": [event["epoch"] for event in events],
        "series": [
            {
                "feature": index,
                "values": [
                    float(event["attention"][index])
                    if index < len(event["attention"])
                    else 0.0
                    for event in events
                ],
            }
            for index in range(size)
        ],
    }


def list_snapshots(task: LabTask) -> dict:
    """列出可回放的快照（只给元信息，不含参数）。"""
    return {
        "snapshots": [
            {
                "epoch": item["epoch"],
                "accuracy": item["accuracy"],
                "val_loss": item["val_loss"],
            }
            for item in task.snapshots
        ],
        "total_epochs": len(task.history),
    }


def snapshot_detail(task: LabTask, epoch: int) -> dict:
    """恢复指定 epoch 的参数，返回该时刻的准确率与决策边界。"""
    if task.model is None or task.features is None or task.labels is None:
        raise ValueError("模型尚未训练完成")

    snapshot = next((item for item in task.snapshots if item["epoch"] == epoch), None)
    if snapshot is None:
        raise ValueError(f"epoch {epoch} 没有快照")

    model = build_model(task.config)
    model.load_state_dict(snapshot["state"])
    model.eval()

    input_units = max(1, min(int(task.config.get("input_units", 2)), 16))
    features = torch.from_numpy(task.features)
    labels = torch.from_numpy(task.labels)

    with torch.no_grad():
        logits = model(features)
        accuracy = float((logits.argmax(dim=1) == labels).float().mean().item())
        loss = float(nn.CrossEntropyLoss()(logits, labels).item())

    return {
        "epoch": epoch,
        "accuracy": round(accuracy, 4),
        "loss": round(loss, 4),
        "boundary": _decision_boundary(
            model,
            task.features,
            task.labels,
            input_dim=input_units,
        ),
    }


def integrated_gradients(task: LabTask, index: int = 0, steps: int = 32) -> dict:
    """Integrated Gradients：把预测归因到每个输入特征。

    基线取全零，沿「基线 → 样本」的直线积分梯度；
    结果表示「该特征把预测从基线推到当前类别」的贡献，正负号代表方向。
    """
    if task.model is None or task.features is None or task.labels is None:
        raise ValueError("模型尚未训练完成")
    if not 0 <= index < len(task.features):
        raise ValueError("样本下标超出范围")

    model = task.model
    model.eval()

    features = torch.from_numpy(task.features[index : index + 1])
    label = int(task.labels[index])

    with torch.no_grad():
        logits = model(features)
        probabilities = torch.softmax(logits, dim=1)[0]
        target = int(logits.argmax(dim=1).item())

    baseline = torch.zeros_like(features)
    steps = max(8, min(int(steps), 128))
    accumulated = torch.zeros_like(features)

    for step in range(1, steps + 1):
        alpha = step / steps
        interpolated = (baseline + alpha * (features - baseline)).requires_grad_(True)
        output = model(interpolated)[0, target]
        (gradient,) = torch.autograd.grad(output, interpolated)
        accumulated += gradient

    average = accumulated / steps
    attributions = ((features - baseline) * average)[0]

    return {
        "index": index,
        "label": label,
        "prediction": target,
        "probability": round(float(probabilities[target].item()), 4),
        "steps": steps,
        "features": [round(float(value), 4) for value in features[0]],
        "attributions": [round(float(value), 6) for value in attributions],
        "baseline": "zeros",
    }
