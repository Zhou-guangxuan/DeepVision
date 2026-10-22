"""把拓扑配置生成等效 PyTorch 代码，并维护「节点 → 行号」映射。

生成结果是**只读展示**，用于教学解释与定位；训练真正执行的是 `DagNet`，
两者由同一份配置驱动，但 codegen 不是训练引擎的真相源。
"""

from __future__ import annotations

from app.schemas.graph import ModelConfigIn
from app.services.dag import build_execution_plan

ACTIVATIONS = {"relu": "ReLU", "tanh": "Tanh", "sigmoid": "Sigmoid"}


def _safe(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)
    return cleaned or "layer"


def _var(node_id: str) -> str:
    return f"v_{_safe(node_id)}"


def generate_code(config: dict) -> dict:
    """返回 {code, lines, total_lines}；lines 为 node_id → 定义行 / 前向行区间。"""
    model = ModelConfigIn(**config)
    plan = build_execution_plan(model)
    if plan is None:
        raise ValueError("拓扑中存在环，无法生成代码")

    nodes = {node.id: node for node in model.nodes}
    order = plan["order"]
    steps = {step["node_id"]: step for step in plan["steps"]}
    input_ids = plan["input_ids"]
    output_ids = plan["output_ids"]

    lines: list[str] = []
    mapping: dict[str, dict[str, list[int]]] = {}

    def emit(text: str = "") -> None:
        lines.append(text)

    emit("import torch")
    emit("from torch import nn")
    emit()
    emit()
    emit("class GeneratedNet(nn.Module):")
    emit('    """由 DeepVision 拓扑自动生成，便于对照阅读。"""')
    emit()
    emit("    def __init__(self) -> None:")
    emit("        super().__init__()")

    dims: dict[str, int] = {}

    for node_id in order:
        node = nodes[node_id]
        if node.type == "input":
            dims[node_id] = int(node.params.get("features", 2) or 2)
            continue

        in_dim = sum(dims[source] for source in steps[node_id]["inputs"])
        units = int(node.params.get("units", 16) or 16)
        dims[node_id] = units

        start = len(lines) + 1
        emit(f"        self.{_safe(node_id)} = nn.Linear({in_dim}, {units})")
        if node.type == "hidden":
            activation = str(node.params.get("activation", "relu"))
            emit(
                f"        self.{_safe(node_id)}_act = "
                f"nn.{ACTIVATIONS.get(activation, 'ReLU')}()"
            )
        mapping[node_id] = {
            "definition": [start, len(lines)],
            "forward": [],
        }

    emit()
    emit("    def forward(self, x: torch.Tensor) -> torch.Tensor:")

    # 输入层：按声明顺序切分特征维
    cursor = 0
    for node_id in input_ids:
        size = dims[node_id]
        start = len(lines) + 1
        emit(f"        {_var(node_id)} = x[:, {cursor}:{cursor + size}]")
        cursor += size
        mapping.setdefault(node_id, {"definition": [], "forward": []})
        mapping[node_id]["forward"] = [start, len(lines)]

    for node_id in order:
        node = nodes[node_id]
        if node.type == "input":
            continue

        sources = steps[node_id]["inputs"]
        start = len(lines) + 1

        if len(sources) == 1:
            argument = _var(sources[0])
        else:
            argument = f"merged_{_safe(node_id)}"
            joined = ", ".join(_var(source) for source in sources)
            emit(f"        {argument} = torch.cat([{joined}], dim=1)")

        call = f"self.{_safe(node_id)}({argument})"
        if node.type == "hidden":
            call = f"self.{_safe(node_id)}_act({call})"
        emit(f"        {_var(node_id)} = {call}")

        mapping[node_id]["forward"] = [start, len(lines)]

    if len(output_ids) == 1:
        emit(f"        return {_var(output_ids[0])}")
    else:
        joined = ", ".join(_var(node_id) for node_id in output_ids)
        emit(f"        return torch.stack([{joined}]).mean(dim=0)")

    return {
        "code": "\n".join(lines),
        "lines": mapping,
        "total_lines": len(lines),
    }
