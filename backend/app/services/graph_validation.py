"""网络拓扑结构校验。

前端在保存草稿与开始训练前调用；阶段四的训练引擎复用同一套规则，
保证「画布能搭出来的结构」与「后端能构建的模型」始终一致。

校验分两级：

- errors   —— 结构非法，无法训练（成环、孤立引用、自连、重复连线等）
- warnings —— 结构合法，但当前版本（MLP）无法直接训练，例如分支 / 汇合
"""

from __future__ import annotations

from collections import defaultdict

from app.schemas.graph import ModelConfigIn

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


def _has_cycle(node_ids: list[str], adjacency: dict[str, list[str]]) -> bool:
    """迭代式 DFS 检测有向环（避免深层网络触发递归上限）。"""
    white, gray, black = 0, 1, 2
    color = {node_id: white for node_id in node_ids}

    def visit(start: str) -> bool:
        stack: list[tuple[str, int]] = [(start, 0)]
        color[start] = gray
        while stack:
            node, index = stack[-1]
            neighbours = adjacency.get(node, [])
            if index < len(neighbours):
                stack[-1] = (node, index + 1)
                nxt = neighbours[index]
                if color.get(nxt) == gray:
                    return True
                if color.get(nxt) == white:
                    color[nxt] = gray
                    stack.append((nxt, 0))
            else:
                color[node] = black
                stack.pop()
        return False

    for node_id in node_ids:
        if color[node_id] == white and visit(node_id):
            return True
    return False


def validate_model_config(payload: ModelConfigIn) -> dict:
    """校验拓扑结构，返回 {valid, errors, warnings}。"""
    errors: list[str] = []
    warnings: list[str] = []

    if not payload.nodes:
        return {"valid": False, "errors": ["拓扑为空，至少需要一个输入层与一个输出层"], "warnings": []}

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
    indegree: dict[str, int] = defaultdict(int)
    for edge in payload.edges:
        if edge.source in node_map and edge.target in node_map:
            adjacency[edge.source].append(edge.target)
            indegree[edge.target] += 1

    if _has_cycle(ids, adjacency):
        errors.append("拓扑中存在环，神经网络必须是有向无环图")

    inputs = [n for n in payload.nodes if n.type == "input"]
    outputs = [n for n in payload.nodes if n.type == "output"]
    if not inputs:
        errors.append("缺少输入层节点")
    if not outputs:
        errors.append("缺少输出层节点")
    if len(inputs) > 1:
        warnings.append("存在多个输入层，首版仅支持单输入")
    if len(outputs) > 1:
        warnings.append("存在多个输出层，首版仅支持单输出")

    # 链式约束：后端训练器（阶段四）按顺序层构建 MLP，无法处理分支与汇合
    outdegree = {node_id: len(adjacency.get(node_id, [])) for node_id in ids}
    for node_id in ids:
        if indegree.get(node_id, 0) > 1 or outdegree.get(node_id, 0) > 1:
            warnings.append("拓扑存在分支或汇合，当前版本训练仅支持链式结构")
            break

    # 孤立节点
    if len(payload.nodes) > 1:
        connected = {e.source for e in payload.edges} | {e.target for e in payload.edges}
        for node in payload.nodes:
            if node.id not in connected:
                warnings.append(f"节点 {node.id} 未连接其他节点")

    return {
        "valid": not errors,
        "errors": _dedupe(errors),
        "warnings": _dedupe(warnings),
    }
