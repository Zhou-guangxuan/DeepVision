"""网络拓扑结构的请求 / 响应模型。

对应设计文档 §6.3 的 `model_config` 契约。
"""

from typing import Literal

from pydantic import BaseModel, Field

NodeType = Literal["input", "hidden", "output"]


class GraphNodeIn(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    type: NodeType
    params: dict = Field(default_factory=dict)


class GraphEdgeIn(BaseModel):
    source: str = Field(min_length=1, max_length=64)
    target: str = Field(min_length=1, max_length=64)


class ModelConfigIn(BaseModel):
    version: int = 1
    nodes: list[GraphNodeIn] = Field(default_factory=list)
    edges: list[GraphEdgeIn] = Field(default_factory=list)


class GraphValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
