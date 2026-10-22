"""实验室自动调参：随机搜索 + 早停。

在后台线程里跑有限次试验，每次用不同的超参组合训练一个小 MLP，
记录验证准确率与提前停止的轮次。结果保存在内存里，供前端轮询。
"""

from __future__ import annotations

import random
import threading
import uuid
from dataclasses import dataclass, field

import numpy as np
import torch
from torch import nn

from app.services import lab

MAX_TRIALS = 12
MAX_EPOCHS = 60
PATIENCE = 4

SPACE_LAYERS = [[8], [8, 8], [16], [16, 16], [32, 16]]
SPACE_ACTIVATION = ["relu", "tanh"]
SPACE_L2 = [0.0, 1e-4, 1e-3]
SPACE_DROPOUT = [0.0, 0.1]
SPACE_BATCH = [16, 32, 64]
LR_MIN, LR_MAX = 1e-3, 1e-1


@dataclass
class TuneTask:
    tune_id: str
    user_id: int
    total: int
    status: str = "pending"
    trials: list[dict] = field(default_factory=list)
    best_index: int | None = None
    error: str | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)

    def snapshot(self) -> dict:
        best = self.trials[self.best_index] if self.best_index is not None else None
        return {
            "tune_id": self.tune_id,
            "status": self.status,
            "total": self.total,
            "done": len(self.trials),
            "trials": list(self.trials),
            "best": best,
            "error": self.error,
        }


_TASKS: dict[str, TuneTask] = {}
_LOCK = threading.Lock()


def get_tune(tune_id: str) -> TuneTask | None:
    with _LOCK:
        return _TASKS.get(tune_id)


def create_tune(*, user_id: int, base: dict, trials: int, epochs: int) -> TuneTask:
    task = TuneTask(
        tune_id=uuid.uuid4().hex,
        user_id=user_id,
        total=max(1, min(int(trials), MAX_TRIALS)),
    )
    with _LOCK:
        _TASKS[task.tune_id] = task

    thread = threading.Thread(
        target=_run,
        args=(task, base, max(2, min(int(epochs), MAX_EPOCHS))),
        daemon=True,
    )
    thread.start()
    return task


def _sample(rng: random.Random) -> dict:
    return {
        "learning_rate": round(
            float(np.exp(rng.uniform(np.log(LR_MIN), np.log(LR_MAX)))), 5
        ),
        "hidden_layers": list(rng.choice(SPACE_LAYERS)),
        "activation": rng.choice(SPACE_ACTIVATION),
        "l2": rng.choice(SPACE_L2),
        "dropout": rng.choice(SPACE_DROPOUT),
        "batch_size": rng.choice(SPACE_BATCH),
    }


def _evaluate(
    model: nn.Module, x: torch.Tensor, y: torch.Tensor
) -> tuple[float, float]:
    model.eval()
    with torch.no_grad():
        logits = model(x)
        accuracy = float((logits.argmax(dim=1) == y).float().mean().item())
        loss = float(nn.CrossEntropyLoss()(logits, y).item())
    return accuracy, loss


def _run_trial(
    index: int,
    params: dict,
    features: np.ndarray,
    labels: np.ndarray,
    input_dim: int,
    num_classes: int,
    epochs: int,
) -> dict:
    torch.manual_seed(42 + index)
    rng = np.random.default_rng(1000 + index)

    order = rng.permutation(len(features))
    split = int(len(features) * 0.8)
    train_index, val_index = order[:split], order[split:]

    x_train = torch.from_numpy(features[train_index])
    y_train = torch.from_numpy(labels[train_index])
    x_val = torch.from_numpy(features[val_index])
    y_val = torch.from_numpy(labels[val_index])

    model = lab.build_model(
        {
            **params,
            "input_units": input_dim,
            "output_units": num_classes,
            "init": "he",
        }
    )
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=params["learning_rate"],
        weight_decay=params["l2"],
    )
    loss_fn = nn.CrossEntropyLoss()

    best_accuracy = -1.0
    best_loss = 0.0
    best_epoch = 0
    stale = 0
    ran = 0

    for epoch in range(1, epochs + 1):
        ran = epoch
        model.train()
        permutation = torch.randperm(len(x_train))
        for start in range(0, len(x_train), params["batch_size"]):
            batch_index = permutation[start : start + params["batch_size"]]
            optimizer.zero_grad()
            loss = loss_fn(model(x_train[batch_index]), y_train[batch_index])
            loss.backward()
            optimizer.step()

        accuracy, val_loss = _evaluate(model, x_val, y_val)
        if accuracy > best_accuracy + 1e-6:
            best_accuracy = accuracy
            best_loss = val_loss
            best_epoch = epoch
            stale = 0
        else:
            stale += 1
            if stale >= PATIENCE:
                break

    return {
        "index": index,
        "learning_rate": params["learning_rate"],
        "hidden_layers": params["hidden_layers"],
        "activation": params["activation"],
        "l2": params["l2"],
        "dropout": params["dropout"],
        "batch_size": params["batch_size"],
        "accuracy": round(best_accuracy, 4),
        "loss": round(best_loss, 4),
        "epochs_run": ran,
        "best_epoch": best_epoch,
        "early_stopped": ran < epochs,
    }


def _run(task: TuneTask, base: dict, epochs: int) -> None:
    task.status = "running"
    try:
        input_dim = max(1, min(int(base.get("input_units", 2)), 16))
        num_classes = max(2, min(int(base.get("output_units", 2)), 8))
        features, labels = lab.build_dataset(input_dim, num_classes)

        rng = random.Random(2026)
        for index in range(1, task.total + 1):
            if task.stop_event.is_set():
                task.status = "stopped"
                return

            params = _sample(rng)
            trial = _run_trial(
                index, params, features, labels, input_dim, num_classes, epochs
            )
            task.trials.append(trial)

            if (
                task.best_index is None
                or trial["accuracy"] > task.trials[task.best_index]["accuracy"]
            ):
                task.best_index = len(task.trials) - 1

        task.status = "completed"
    except Exception as exc:  # noqa: BLE001
        task.status = "failed"
        task.error = str(exc)
