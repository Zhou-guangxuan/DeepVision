"""AI 助教相关的请求 / 响应模型。"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class DiagnoseRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())

    network_config: dict = Field(alias="model_config")
    dataset_id: int | None = None
    hyperparameters: dict | None = None


class DiagnoseIssue(BaseModel):
    node_id: str | None = None
    severity: Literal["error", "warning", "info"]
    message: str


class DiagnoseSuggestion(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    node_id: str
    field: Literal["features", "units", "activation", "task"]
    from_value: Any = Field(alias="from")
    to_value: Any = Field(alias="to")
    reason: str


class DiagnoseResponse(BaseModel):
    score: int
    mode: str
    issues: list[DiagnoseIssue] = Field(default_factory=list)
    suggestions: list[DiagnoseSuggestion] = Field(default_factory=list)
