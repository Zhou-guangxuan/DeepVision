"""训练曲线诊断规则引擎测试。"""

from app.services.curve_diagnosis import diagnose_curve


def _history(
    train: list[float], val: list[float], accuracy: list[float] | None = None
) -> list[dict]:
    history = []
    for index, (train_loss, val_loss) in enumerate(zip(train, val, strict=True)):
        history.append(
            {
                "type": "epoch",
                "epoch": index + 1,
                "train_loss": train_loss,
                "val_loss": val_loss,
                "accuracy": None if accuracy is None else accuracy[index],
            }
        )
    return history


def test_too_few_epochs_skips_diagnosis() -> None:
    result = diagnose_curve(_history([0.9, 0.8], [0.95, 0.9]))
    assert result["healthy"] is None
    assert result["issues"] == []


def test_healthy_curve_reports_no_problem() -> None:
    train = [0.9 - 0.06 * step for step in range(12)]
    val = [0.95 - 0.055 * step for step in range(12)]
    result = diagnose_curve(_history(train, val))

    assert result["healthy"] is True
    assert result["issues"] == []
    assert result["stats"]["epochs"] == 12


def test_detects_overfitting() -> None:
    # 训练 loss 继续下降，验证 loss 后段回升
    train = [0.9 - 0.07 * step for step in range(12)]
    val = [0.9 - 0.06 * step for step in range(8)] + [0.62, 0.68, 0.75, 0.83]
    result = diagnose_curve(_history(train, val))

    codes = {issue["code"] for issue in result["issues"]}
    assert "overfitting" in codes
    assert result["healthy"] is False


def test_detects_divergence() -> None:
    train = [0.8, 0.75, 0.7, 0.72, 0.8, 0.9, 1.1, 1.4]
    val = [0.82, 0.78, 0.74, 0.8, 0.95, 1.2, 1.6, 2.2]
    result = diagnose_curve(_history(train, val))

    codes = {issue["code"] for issue in result["issues"]}
    assert "diverged" in codes
    assert result["issues"][0]["severity"] == "error"


def test_detects_oscillation_from_large_learning_rate() -> None:
    val = [0.9, 0.55, 0.95, 0.5, 0.98, 0.52, 1.0, 0.54, 0.97]
    train = [0.88, 0.52, 0.9, 0.48, 0.92, 0.5, 0.95, 0.51, 0.9]
    result = diagnose_curve(_history(train, val))

    codes = {issue["code"] for issue in result["issues"]}
    assert "lr_too_high" in codes


def test_detects_underfitting() -> None:
    # 一直很高且几乎不降
    train = [1.05, 1.02, 1.0, 0.99, 0.985, 0.98, 0.978, 0.976]
    val = [1.08, 1.05, 1.03, 1.02, 1.015, 1.012, 1.01, 1.009]
    result = diagnose_curve(_history(train, val))

    codes = {issue["code"] for issue in result["issues"]}
    assert "underfitting" in codes
