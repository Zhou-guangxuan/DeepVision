"""按执行计划把网络拓扑物化为 PyTorch 模块。

支持任意前馈 DAG：汇合节点按前驱声明顺序在特征维做 `concat`。
"""

from __future__ import annotations

import torch
from torch import nn

ACTIVATIONS = {
    "relu": nn.ReLU,
    "sigmoid": nn.Sigmoid,
    "tanh": nn.Tanh,
}


class DagNet(nn.Module):
    """按拓扑序执行的前馈网络。

    输入节点直接返回输入张量；其余节点为 Linear（隐藏层后接激活函数），
    多前驱节点先 concat 再线性变换。
    """

    def __init__(
        self,
        plan: dict,
        nodes: dict[str, dict],
        input_dim: int,
    ) -> None:
        super().__init__()

        self.steps: list[dict] = plan["steps"]
        self.merge: str = plan.get("merge", "concat")
        self.output_id: str = plan["order"][-1]
        self.ops = nn.ModuleDict()

        dims: dict[str, int] = {}

        for step in self.steps:
            node_id = step["node_id"]
            node = nodes[node_id]

            if node["type"] == "input":
                dims[node_id] = input_dim
                continue

            in_dim = sum(dims[source] for source in step["inputs"])
            if in_dim <= 0:
                raise ValueError(f"节点 {node_id} 没有有效输入维度")

            units = int(node.get("params", {}).get("units", 16))
            if units <= 0:
                raise ValueError(f"节点 {node_id} 的单元数必须为正整数")

            if node["type"] == "hidden":
                activation = str(
                    node.get("params", {}).get("activation", "relu")
                )
                activation_cls = ACTIVATIONS.get(activation, nn.ReLU)
                self.ops[node_id] = nn.Sequential(
                    nn.Linear(in_dim, units),
                    activation_cls(),
                )
            else:
                self.ops[node_id] = nn.Linear(in_dim, units)

            dims[node_id] = units

    def forward_intermediates(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        """返回拓扑序中每个节点的输出，供可视化使用。"""
        outputs: dict[str, torch.Tensor] = {}

        for step in self.steps:
            node_id = step["node_id"]

            if node_id not in self.ops:
                outputs[node_id] = x
                continue

            parts = [outputs[source] for source in step["inputs"]]
            merged = parts[0] if len(parts) == 1 else torch.cat(parts, dim=1)
            outputs[node_id] = self.ops[node_id](merged)

        return outputs

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.forward_intermediates(x)[self.output_id]


def build_dag_net(
    plan: dict,
    nodes: dict[str, dict],
    input_dim: int,
) -> DagNet:
    return DagNet(plan=plan, nodes=nodes, input_dim=input_dim)
