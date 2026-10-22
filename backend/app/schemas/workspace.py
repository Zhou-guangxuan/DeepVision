"""工作台草稿的请求 / 响应模型。"""

from datetime import datetime

from pydantic import BaseModel, Field


class DraftSaveRequest(BaseModel):
    nodes: list[dict] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)
    saved_at: str | None = None


class DraftResponse(BaseModel):
    graph: dict | None = None
    updated_at: datetime | None = None
