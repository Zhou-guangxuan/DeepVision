"""拓扑诊断：规则引擎产出结构化的 score / issues / suggestions。

只对**已有节点的参数**给出建议（features / units / activation / task），
这样前端的「一键应用」才能可靠地修改画布且可撤销。

结构性问题（如缺少隐藏层）只作为 issue 提示，不生成不可应用的 suggestion。
"""

from __future__ import annotations

from app.models.dataset import Dataset
from app.schemas.graph import ModelConfigIn
from app.services.graph_validation import validate_model_config

MIN_LEARNING_RATE = 1e-5
MAX_LEARNING_RATE = 0.1


def _clamp_score(score: int) -> int:
    return max(0, min(100, score))


def diagnose(
    config: ModelConfigIn,
    dataset: Dataset | None = None,
    hyperparameters: dict | None = None,
) -> dict:
    issues: list[dict] = []
    suggestions: list[dict] = []
    score = 100

    validation = validate_model_config(config)
    for message in validation["errors"]:
        issues.append({"node_id": None, "severity": "error", "message": message})
        score -= 25
    for message in validation["warnings"]:
        issues.append({"node_id": None, "severity": "warning", "message": message})
        score -= 8

    inputs = [n for n in config.nodes if n.type == "input"]
    hiddens = [n for n in config.nodes if n.type == "hidden"]
    outputs = [n for n in config.nodes if n.type == "output"]

    if inputs and outputs and not hiddens:
        issues.append(
            {
                "node_id": None,
                "severity": "warning",
                "message": "当前网络没有隐藏层，只有线性映射，难以拟合非线性关系",
            }
        )
        score -= 10

    if len(hiddens) > 5:
        issues.append(
            {
                "node_id": None,
                "severity": "warning",
                "message": f"隐藏层数量为 {len(hiddens)}，表格数据通常 1~3 层已足够",
            }
        )
        score -= 6

    # 隐藏层过窄：宽度不足输入维度的一半
    if inputs:
        input_features = int(inputs[0].params.get("features", 0) or 0)
        if input_features > 0:
            for hidden in hiddens:
                units = int(hidden.params.get("units", 0) or 0)
                if units > 0 and units * 2 < input_features:
                    suggestions.append(
                        {
                            "node_id": hidden.id,
                            "field": "units",
                            "from": units,
                            "to": input_features,
                            "reason": (
                                f"隐藏层宽度 {units} 不足输入维度 {input_features} 的一半，"
                                "容易欠拟合"
                            ),
                        }
                    )
                    issues.append(
                        {
                            "node_id": hidden.id,
                            "severity": "warning",
                            "message": f"隐藏层「{hidden.id}」神经元数偏少",
                        }
                    )
                    score -= 8

    # 与数据集的输入维度对齐
    if dataset is not None and inputs:
        declared = int(inputs[0].params.get("features", 0) or 0)
        if (
            declared > 0
            and dataset.feature_count > 0
            and declared != dataset.feature_count
        ):
            suggestions.append(
                {
                    "node_id": inputs[0].id,
                    "field": "features",
                    "from": declared,
                    "to": dataset.feature_count,
                    "reason": (
                        f"数据集有 {dataset.feature_count} 个原始特征列"
                        "（类别特征独热编码后维度会更大，请以训练报错的实际维度为准）"
                    ),
                }
            )
            issues.append(
                {
                    "node_id": inputs[0].id,
                    "severity": "warning",
                    "message": (
                        f"输入层特征数 {declared} 与数据集原始特征数 "
                        f"{dataset.feature_count} 不一致"
                    ),
                }
            )
            score -= 6

    # 分类类别数与输出单元对齐
    if dataset is not None and outputs:
        distribution = (dataset.stats or {}).get("target_distribution") or {}
        classes = len(distribution)
        units = int(outputs[0].params.get("units", 0) or 0)
        task = str(outputs[0].params.get("task", "classification"))
        if task == "classification" and classes > 0 and units != classes:
            suggestions.append(
                {
                    "node_id": outputs[0].id,
                    "field": "units",
                    "from": units,
                    "to": classes,
                    "reason": f"目标列共有 {classes} 个类别",
                }
            )
            issues.append(
                {
                    "node_id": outputs[0].id,
                    "severity": "warning",
                    "message": f"输出层单元数 {units} 与类别数 {classes} 不一致，训练会报维度错误",
                }
            )
            score -= 10

    # 超参检查
    if hyperparameters:
        learning_rate = float(hyperparameters.get("learning_rate", 0) or 0)
        if learning_rate > MAX_LEARNING_RATE:
            issues.append(
                {
                    "node_id": None,
                    "severity": "warning",
                    "message": f"学习率 {learning_rate} 偏大，容易震荡或发散",
                }
            )
            score -= 8
        elif 0 < learning_rate < MIN_LEARNING_RATE:
            issues.append(
                {
                    "node_id": None,
                    "severity": "warning",
                    "message": f"学习率 {learning_rate} 偏小，收敛会很慢",
                }
            )
            score -= 5

        epochs = int(hyperparameters.get("epochs", 0) or 0)
        if epochs and epochs < 5:
            issues.append(
                {
                    "node_id": None,
                    "severity": "info",
                    "message": f"仅训练 {epochs} 个 epoch，可能不足以收敛",
                }
            )

    return {
        "score": _clamp_score(score),
        "mode": "rules",
        "issues": issues,
        "suggestions": suggestions,
    }
