"""网络拓扑结构校验。

前端在保存草稿与开始训练前调用；阶段四的训练引擎复用同一套规则与执行计划，
保证「画布能搭出来的结构」与「后端能构建的模型」始终一致。

支持的拓扑：任意前馈有向无环图（DAG），允许分支与汇合。
汇合语义：多前驱节点在特征维按前驱声明顺序拼接（concat）。

校验分两级：

- errors   —— 结构非法，无法生成执行计划（成环、悬浮引用、自连、重复连线、
              多输入/多输出、存在无法从输入层到达的节点等）
- warnings —— 结构合法但存在可疑之处（例如某节点的输出不会影响最终结果）
"""

from __future__ import annotations

from collections import defaultdict

from app.schemas.graph import ModelConfigIn
from app.services.dag import build_execution_plan

NODE_TYPES = {"input", "hidden", "output"}


def _dedupe(items: list[str]) -> list[str]:
    """去重但保持原有顺序。"""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _reachable(start: str, adjacency: dict[str, list[str]]) -> set[str]:
    """从 start 出发能到达的所有节点（含 start）。"""
    visited: set[str] = set()
    stack = [start]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        for nxt in adjacency.get(current, []):
            stack.append(nxt)
    return visited


def validate_model_config(payload: ModelConfigIn) -> dict:
    """校验拓扑结构，返回 {valid, errors, warnings, execution_plan}。"""
    errors: list[str] = []
    warnings: list[str] = []

    if not payload.nodes:
        return {
            "valid": False,
            "errors": ["拓扑为空，至少需要一个输入层与一个输出层"],
            "warnings": [],
            "execution_plan": None,
        }

    ids = [node.id for node in payload.nodes]
    if len(ids) != len(set(ids)):
        errors.append("节点 id 存在重复")

    node_map = {node.id: node for node in payload.nodes}

    for node in payload.nodes:
        if node.type not in NODE_TYPES:
            errors.append(f"节点 {node.id} 的类型「{node.type}」不受支持")

    seen_edges: set[tuple[str, str]] = set()
    for edge in payload.edges:
        if edge.source not in node_map or edge.target not in node_map:
            errors.append(f"连线 {edge.source} → {edge.target} 引用了不存在的节点")
            continue
        if edge.source == edge.target:
            errors.append(f"节点 {edge.source} 不能连接到自身")
        if (edge.source, edge.target) in seen_edges:
            errors.append(f"重复连线 {edge.source} → {edge.target}")
        seen_edges.add((edge.source, edge.target))

        if node_map[edge.source].type == "output":
            errors.append(f"输出层 {edge.source} 之后不能再连接其他层")
        if node_map[edge.target].type == "input":
            errors.append(f"输入层 {edge.target} 不能作为连线的终点")

    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in payload.edges:
        if edge.source in node_map and edge.target in node_map:
            adjacency[edge.source].append(edge.target)

    inputs = [n for n in payload.nodes if n.type == "input"]
    outputs = [n for n in payload.nodes if n.type == "output"]

    if not inputs:
        errors.append("缺少输入层节点")
    if not outputs:
        errors.append("缺少输出层节点")
    if len(inputs) > 1:
        errors.append("存在多个输入层，首版仅支持单输入")
    if len(outputs) > 1:
        errors.append("存在多个输出层，首版仅支持单输出")

    # 成环检测：独立于其他校验执行，尽量一次把所有问题报全
    plan = None
    acyclic = False
    if all(
        edge.source in node_map and edge.target in node_map
        for edge in payload.edges
    ):
        plan = build_execution_plan(payload)
        acyclic = plan is not None
        if not acyclic:
            errors.append("拓扑中存在环，神经网络必须是有向无环图")

    # 可达性：所有节点都必须从输入层可达，否则无法计算
    if acyclic and len(inputs) == 1:
        reachable = _reachable(inputs[0].id, adjacency)
        for nid in [item for item in ids if item not in reachable]:
            errors.append(f"节点 {nid} 无法从输入层到达")

    # 反向可达：节点输出应能影响最终结果，否则是死分支
    if acyclic and len(outputs) == 1:
        reverse: dict[str, list[str]] = defaultdict(list)
        for edge in payload.edges:
            reverse[edge.target].append(edge.source)
        useful = _reachable(outputs[0].id, reverse)
        for nid in ids:
            if nid not in useful:
                warnings.append(f"节点 {nid} 的输出不会影响最终结果")

    if errors:
        plan = None

    return {
        "valid": not errors,
        "errors": _dedupe(errors),
        "warnings": _dedupe(warnings),
        "execution_plan": plan,
    }
