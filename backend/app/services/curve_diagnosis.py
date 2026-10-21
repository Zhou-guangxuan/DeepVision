"""训练曲线诊断（规则引擎）。

只依赖 epoch 事件里的 `train_loss` / `val_loss` / `accuracy`，不引入额外依赖。
阈值针对「教学场景的小模型 + 合成/小数据集」设定，属于启发式判断，
用于给学习者即时提示，不作为严格的统计结论。
"""

from __future__ import annotations

from typing import Any

# 少于这个轮次不足以判断趋势
MIN_POINTS = 6
# 教学数据集上，验证 loss 高于此值通常意味着「还没学会」
HIGH_LOSS = 0.5
# 后半程改进不足 5% 视为平台期
FLAT_RATIO = 0.05
# 相邻 epoch 的 loss 波动幅度超过这个比例，视为震荡
OSCILLATION_AMPLITUDE = 0.15

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def _series(history: list[dict], key: str) -> list[float]:
    values: list[float] = []
    for item in history:
        value = item.get(key)
        if value is None:
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    return values


def _slope(values: list[float]) -> float:
    """最小二乘斜率（每 epoch 的变化量）。"""
    count = len(values)
    if count < 2:
        return 0.0

    mean_x = (count - 1) / 2
    mean_y = sum(values) / count
    numerator = sum(
        (index - mean_x) * (value - mean_y) for index, value in enumerate(values)
    )
    denominator = sum((index - mean_x) ** 2 for index in range(count))
    return numerator / denominator if denominator else 0.0


def _improvement(values: list[float]) -> float:
    """相对下降比例（正数表示下降）。"""
    if len(values) < 2:
        return 0.0
    start = max(abs(values[0]), 1e-9)
    return (values[0] - values[-1]) / start


def _issue(
    code: str,
    severity: str,
    title: str,
    detail: str,
    suggestion: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "title": title,
        "detail": detail,
        "suggestion": suggestion,
        "evidence": evidence,
    }


def diagnose_curve(history: list[dict]) -> dict[str, Any]:
    """分析训练曲线，返回健康状态与问题列表。"""
    train = _series(history, "train_loss")
    val = _series(history, "val_loss")
    accuracy = _series(history, "accuracy")

    count = min(len(train), len(val))
    if count < MIN_POINTS:
        return {
            "healthy": None,
            "summary": f"训练轮次不足 {MIN_POINTS}，暂不诊断",
            "issues": [],
            "stats": {"epochs": count},
        }

    train = train[:count]
    val = val[:count]
    issues: list[dict[str, Any]] = []

    window = min(8, max(4, count // 3))
    tail_val = val[-window:]
    tail_train = train[-window:]

    # 1. 发散：验证 loss 超过历史最低点的 2 倍
    lowest = min(val)
    if val[-1] > max(lowest * 2, 1.0):
        issues.append(
            _issue(
                "diverged",
                "error",
                "训练发散",
                f"验证 loss 从最低 {lowest:.4f} 升到 {val[-1]:.4f}，已超过两倍",
                "先降低学习率（例如除以 10）或减小批大小，确认 loss 能稳定下降",
                {"min_val_loss": round(lowest, 6), "last_val_loss": round(val[-1], 6)},
            )
        )

    # 2. 过拟合：训练 loss 继续下降，但验证 loss 回升、gap 扩大
    gap_start = tail_val[0] - tail_train[0]
    gap_end = tail_val[-1] - tail_train[-1]
    if (
        _slope(tail_val) > 0.002
        and _slope(tail_train) < 0
        and gap_end > gap_start + 0.02
    ):
        issues.append(
            _issue(
                "overfitting",
                "warning",
                "出现过拟合迹象",
                f"最近 {window} 个 epoch 训练 loss 仍在下降，验证 loss 却上升，"
                f"train/val 差距从 {gap_start:.3f} 扩大到 {gap_end:.3f}",
                "加入 Dropout / L2 正则，或减少训练轮数、扩大数据集",
                {
                    "window": window,
                    "gap_start": round(gap_start, 6),
                    "gap_end": round(gap_end, 6),
                },
            )
        )

    # 3. 学习率过大：loss 反复震荡
    diffs = [val[index + 1] - val[index] for index in range(count - 1)]
    tail_diffs = diffs[-min(10, len(diffs)) :]
    flips = sum(
        1
        for left, right in zip(tail_diffs, tail_diffs[1:], strict=False)
        if left * right < 0
    )
    span = max(tail_diffs) - min(tail_diffs)
    base = abs(sum(tail_val) / len(tail_val)) + 1e-9
    if flips >= 4 and span / base > OSCILLATION_AMPLITUDE:
        issues.append(
            _issue(
                "lr_too_high",
                "warning",
                "学习率可能过大",
                f"最近 {len(tail_diffs)} 步里 loss 方向反转 {flips} 次，波动幅度约 {span / base:.0%}",
                "把学习率调小一个数量级，观察曲线是否变平滑",
                {"flips": flips, "amplitude": round(span / base, 4)},
            )
        )

    # 4. 学习率过小：几乎不下降
    tail_improvement = _improvement(val[-min(10, count) :])
    if tail_improvement < 0.01 and val[-1] > 0.3 and _slope(val) < 0:
        issues.append(
            _issue(
                "lr_too_low",
                "info",
                "学习率可能过小",
                f"最近 {min(10, count)} 个 epoch 验证 loss 只下降 {tail_improvement:.2%}，仍在 {val[-1]:.3f}",
                "尝试把学习率放大 2–5 倍，或增加训练轮数",
                {"tail_improvement": round(tail_improvement, 6)},
            )
        )

    # 5. 欠拟合：训练与验证 loss 都高，且几乎不再下降（或始终远高于可接受水平）
    high_loss = train[-1] > HIGH_LOSS and val[-1] > HIGH_LOSS
    stagnated = _improvement(val) < FLAT_RATIO or val[-1] > HIGH_LOSS * 1.5
    if high_loss and stagnated:
        issues.append(
            _issue(
                "underfitting",
                "warning",
                "模型欠拟合",
                f"训练 loss {train[-1]:.3f}、验证 loss {val[-1]:.3f} 都偏高，整体只下降 {_improvement(val):.1%}",
                "增加隐藏层宽度/层数、换用 ReLU、提高学习率，或检查特征是否有效",
                {
                    "last_train_loss": round(train[-1], 6),
                    "last_val_loss": round(val[-1], 6),
                    "improvement": round(_improvement(val), 6),
                },
            )
        )

    issues.sort(key=lambda item: SEVERITY_ORDER.get(item["severity"], 9))
    has_problem = any(item["severity"] in {"error", "warning"} for item in issues)

    if has_problem:
        summary = "；".join(item["title"] for item in issues[:3])
    elif issues:
        summary = "曲线基本健康，但有可优化点：" + issues[0]["title"]
    else:
        summary = "曲线健康：loss 稳定下降，train/val 差距合理"

    stats: dict[str, Any] = {
        "epochs": count,
        "last_train_loss": round(train[-1], 6),
        "last_val_loss": round(val[-1], 6),
        "gap": round(val[-1] - train[-1], 6),
        "min_val_loss": round(min(val), 6),
    }
    if accuracy:
        stats["last_accuracy"] = round(accuracy[-1], 6)

    return {
        "healthy": not has_problem,
        "summary": summary,
        "issues": issues,
        "stats": stats,
    }
