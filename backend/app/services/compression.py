"""模型压缩对比：magnitude 剪枝与动态 int8 量化。

只针对教学实验室的小 MLP（`nn.Linear`），用于演示「压缩会付出什么代价」：
- 剪枝：按权重绝对值zero掉最小的比例，稀疏度上升，但稠密存储体积不变；
- 量化：线性层权重转 int8，体积明显变小，精度通常小幅下降。

体积用 `torch.save(state_dict)` 的实际字节数测量，避免估算口径不一致。
"""

from __future__ import annotations

import copy
import io

import numpy as np
import torch
from torch import nn

from app.services.lab import LabTask


def _size_bytes(model: nn.Module) -> int:
    buffer = io.BytesIO()
    torch.save(model.state_dict(), buffer)
    return len(buffer.getvalue())


def _param_count(model: nn.Module) -> int:
    return sum(parameter.numel() for parameter in model.parameters())


def _nonzero_count(model: nn.Module) -> int:
    return sum(
        int((parameter.detach() != 0).sum().item()) for parameter in model.parameters()
    )


def _weight_bytes(model: nn.Module) -> int:
    """参数本身占的字节（不含序列化开销）。"""
    return sum(
        parameter.numel() * parameter.element_size() for parameter in model.parameters()
    )


def _quantized_weight_bytes(model: nn.Module) -> int:
    """量化模型的实际权重大小：int8 权重 1 字节 + 量化参数开销。"""
    total = 0
    for module in model.modules():
        if not isinstance(module, nn.quantized.dynamic.Linear):
            continue
        weight = module.weight()
        total += int(weight.int_repr().numel())

        # 动态量化默认是 per-tensor；per-channel 时还需 scales / zero_points
        if weight.qscheme() in {
            torch.per_channel_affine,
            torch.per_channel_affine_float_qparams,
        }:
            total += int(weight.q_per_channel_scales().numel()) * 4
            total += int(weight.q_per_channel_zero_points().numel()) * 4
        else:
            total += 8
    return total


def _accuracy(model: nn.Module, x_val: torch.Tensor, y_val: torch.Tensor) -> float:
    model.eval()
    with torch.no_grad():
        logits = model(x_val)
        return float((logits.argmax(dim=1) == y_val).float().mean().item())


def prune_model(model: nn.Module, sparsity: float) -> nn.Module:
    """按权重绝对值剪掉最小的 `sparsity` 比例（永久置零）。"""
    pruned = copy.deepcopy(model)
    for module in pruned.modules():
        if not isinstance(module, nn.Linear):
            continue
        weight = module.weight.detach()
        threshold = torch.quantile(weight.abs().flatten(), sparsity)
        mask = weight.abs() > threshold
        with torch.no_grad():
            module.weight.mul_(mask)
    return pruned


def quantize_model(model: nn.Module) -> nn.Module:
    """动态量化：Linear 权重转 int8，激活在运行时量化。"""
    model.eval()
    return torch.ao.quantization.quantize_dynamic(
        copy.deepcopy(model), {nn.Linear}, dtype=torch.qint8
    )


def compare(task: LabTask, sparsity: float = 0.3) -> dict:
    if task.model is None or task.features is None or task.labels is None:
        raise ValueError("模型尚未训练完成")

    sparsity = min(max(float(sparsity), 0.05), 0.9)

    features = torch.from_numpy(task.features)
    labels = torch.from_numpy(task.labels)

    # 固定 20% 子集做评估，保证三种方案用同一批样本
    rng = np.random.default_rng(7)
    order = rng.permutation(len(features))
    val_index = order[: max(1, len(features) // 5)]
    x_val, y_val = features[val_index], labels[val_index]

    baseline = {
        "params": _param_count(task.model),
        "nonzero": _nonzero_count(task.model),
        "size_bytes": _size_bytes(task.model),
        "weight_bytes": _weight_bytes(task.model),
        "accuracy": round(_accuracy(task.model, x_val, y_val), 4),
    }

    pruned = prune_model(task.model, sparsity)
    pruned_nonzero = _nonzero_count(pruned)
    pruned_result = {
        "sparsity": round(sparsity, 2),
        "params": _param_count(pruned),
        "nonzero": pruned_nonzero,
        "size_bytes": _size_bytes(pruned),
        # 稠密存储体积与原始一致（置零不减少字节数）
        "weight_bytes": _weight_bytes(pruned),
        # 稀疏存储的理论体积：非零值 4 字节 + 索引 4 字节
        "sparse_bytes": pruned_nonzero * 8,
        "accuracy": round(_accuracy(pruned, x_val, y_val), 4),
    }

    quantized = quantize_model(task.model)
    quantized_bytes = _quantized_weight_bytes(quantized)
    quantized_result = {
        "dtype": "int8",
        # 序列化体积：极小模型会被量化元数据（scale / zero_point）反超
        "size_bytes": _size_bytes(quantized),
        "weight_bytes": quantized_bytes,
        "compression_ratio": round(
            baseline["weight_bytes"] / max(quantized_bytes, 1), 2
        ),
        "accuracy": round(_accuracy(quantized, x_val, y_val), 4),
    }

    return {
        "baseline": baseline,
        "pruned": pruned_result,
        "quantized": quantized_result,
        "samples": int(len(val_index)),
    }
