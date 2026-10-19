"""前馈 DAG 的拓扑执行计划。

阶段四的训练引擎据此把 `model_config` 物化为 PyTorch 模块。放在这里的好处：
「结构是否可执行」在阶段二就能验证，不必等到训练时才报错。

汇合语义：一个节点有多个前驱时，按前驱声明顺序在**特征维**拼接（concat）。
"""

from __future__ import annotations

from collections import defaultdict, deque

from app.schemas.graph import ModelConfigIn

# 目前只实现 concat；add / multiply 留作后续扩展
MERGE_STRATEGY = "concat"


def topological_order(
    node_ids: list[str],
    edges: list[tuple[str, str]],
) -> list[str] | None:
    """Kahn 算法求拓扑序；存在环时返回 None。

    同一层内按节点 id 排序，保证结果稳定可复现。
    """
    indegree = {node_id: 0 for node_id in node_ids}
    adjacency: dict[str, list[str]] = defaultdict(list)

    for source, target in edges:
        if source in indegree and target in indegree:
            adjacency[source].append(target)
            indegree[target] += 1

    queue: deque[str] = deque(sorted(nid for nid in node_ids if indegree[nid] == 0))
    order: list[str] = []

    while queue:
        node_id = queue.popleft()
        order.append(node_id)
        for nxt in adjacency.get(node_id, []):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)

    return order if len(order) == len(node_ids) else None


def build_execution_plan(config: ModelConfigIn) -> dict | None:
    """生成执行计划；结构不可执行（成环）时返回 None。"""
    node_ids = [node.id for node in config.nodes]
    edges = [(edge.source, edge.target) for edge in config.edges]

    order = topological_order(node_ids, edges)
    if order is None:
        return None

    predecessors: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for source, target in edges:
        if target in predecessors:
            predecessors[target].append(source)

    node_map = {node.id: node for node in config.nodes}

    steps = [
        {
            "node_id": nid,
            "type": node_map[nid].type,
            "inputs": predecessors[nid],
        }
        for nid in order
    ]

    return {
        "merge": MERGE_STRATEGY,
        "order": order,
        "steps": steps,
        # 多输入按特征切分、多输出按均值合并，均依赖这两个顺序
        "input_ids": [nid for nid in order if node_map[nid].type == "input"],
        "output_ids": [nid for nid in order if node_map[nid].type == "output"],
    }
