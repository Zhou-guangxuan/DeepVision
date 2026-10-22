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

    - 输入节点按 `input_slices` 从特征维切出自己的那一份；
    - 其余节点为 Linear（隐藏层后接激活函数），多前驱节点先 concat 再线性变换；
    - 多个输出节点时，按逐元素均值合并成一个输出。
    """

    def __init__(
        self,
        plan: dict,
        nodes: dict[str, dict],
        input_dim: int,
        input_slices: dict[str, tuple[int, int]] | None = None,
    ) -> None:
        super().__init__()

        self.steps: list[dict] = plan["steps"]
        self.merge: str = plan.get("merge", "concat")
        self.output_ids: list[str] = list(
            plan.get("output_ids")
            or [nid for nid in plan["order"] if nodes[nid]["type"] == "output"]
        )
        self.input_ids: list[str] = list(
            plan.get("input_ids")
            or [nid for nid in plan["order"] if nodes[nid]["type"] == "input"]
        )
        if not self.output_ids:
            raise ValueError("拓扑缺少输出层")
        self.output_id: str = self.output_ids[0]
        self.input_slices = input_slices or self._default_slices(input_dim)
        self.ops = nn.ModuleDict()

        dims: dict[str, int] = {}

        for step in self.steps:
            node_id = step["node_id"]
            node = nodes[node_id]

            if node["type"] == "input":
                start, end = self.input_slices[node_id]
                dims[node_id] = end - start
                continue

            in_dim = sum(dims[source] for source in step["inputs"])
            if in_dim <= 0:
                raise ValueError(f"节点 {node_id} 没有有效输入维度")

            units = int(node.get("params", {}).get("units", 16))
            if units <= 0:
                raise ValueError(f"节点 {node_id} 的单元数必须为正整数")

            if node["type"] == "hidden":
                activation = str(node.get("params", {}).get("activation", "relu"))
                activation_cls = ACTIVATIONS.get(activation, nn.ReLU)
                self.ops[node_id] = nn.Sequential(
                    nn.Linear(in_dim, units),
                    activation_cls(),
                )
            else:
                self.ops[node_id] = nn.Linear(in_dim, units)

            dims[node_id] = units

    def _default_slices(self, input_dim: int) -> dict[str, tuple[int, int]]:
        """未显式指定切分时：单输入取全部，多输入均分。"""
        if len(self.input_ids) == 1:
            return {self.input_ids[0]: (0, input_dim)}

        count = max(1, len(self.input_ids))
        base = max(1, input_dim // count)
        slices: dict[str, tuple[int, int]] = {}
        cursor = 0
        for index, node_id in enumerate(self.input_ids):
            end = input_dim if index == count - 1 else min(cursor + base, input_dim)
            slices[node_id] = (cursor, end)
            cursor = end
        return slices

    def forward_intermediates(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        """返回拓扑序中每个节点的输出，供可视化使用。"""
        outputs: dict[str, torch.Tensor] = {}

        for step in self.steps:
            node_id = step["node_id"]

            if node_id not in self.ops:
                start, end = self.input_slices[node_id]
                outputs[node_id] = x[:, start:end]
                continue

            parts = [outputs[source] for source in step["inputs"]]
            merged = parts[0] if len(parts) == 1 else torch.cat(parts, dim=1)
            outputs[node_id] = self.ops[node_id](merged)

        return outputs

    def profile(self, x: torch.Tensor) -> list[dict]:
        """做一次前向并记录每个节点的张量形状、dtype、参数量与前向耗时。

        耗时是单次前向的粗略测量（毫秒），用于教学展示相对开销，
        不等同于 CUDA / 算子级 profiler。
        """
        import time

        outputs: dict[str, torch.Tensor] = {}
        records: list[dict] = []

        with torch.no_grad():
            for step in self.steps:
                node_id = step["node_id"]

                if node_id not in self.ops:
                    start, end = self.input_slices[node_id]
                    tensor = x[:, start:end]
                    outputs[node_id] = tensor
                    records.append(
                        {
                            "node_id": node_id,
                            "kind": "input",
                            "in_dim": int(tensor.shape[1]),
                            "out_dim": int(tensor.shape[1]),
                            "dtype": str(tensor.dtype).replace("torch.", ""),
                            "param_count": 0,
                            "time_ms": 0.0,
                        }
                    )
                    continue

                parts = [outputs[source] for source in step["inputs"]]
                merged = parts[0] if len(parts) == 1 else torch.cat(parts, dim=1)

                module = self.ops[node_id]
                begin = time.perf_counter()
                tensor = module(merged)
                elapsed = (time.perf_counter() - begin) * 1000

                outputs[node_id] = tensor
                records.append(
                    {
                        "node_id": node_id,
                        "kind": "layer",
                        "in_dim": int(merged.shape[1]),
                        "out_dim": int(tensor.shape[1]),
                        "dtype": str(tensor.dtype).replace("torch.", ""),
                        "param_count": sum(
                            parameter.numel() for parameter in module.parameters()
                        ),
                        "time_ms": round(elapsed, 4),
                    }
                )

        return records

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        outputs = self.forward_intermediates(x)

        if len(self.output_ids) == 1:
            return outputs[self.output_ids[0]]

        # 多输出：逐元素取均值，等价于把多个头的预测做平均集成
        stacked = torch.stack([outputs[nid] for nid in self.output_ids], dim=0)
        return stacked.mean(dim=0)


def build_dag_net(
    plan: dict,
    nodes: dict[str, dict],
    input_dim: int,
    input_slices: dict[str, tuple[int, int]] | None = None,
) -> DagNet:
    return DagNet(
        plan=plan,
        nodes=nodes,
        input_dim=input_dim,
        input_slices=input_slices,
    )
