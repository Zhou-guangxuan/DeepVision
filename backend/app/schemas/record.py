"""训练记录请求 / 响应模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RecordStatus = Literal["pending", "running", "success", "failed", "interrupted"]


class RecordCreate(BaseModel):
    """创建训练记录。

    请求体中的 `model_config` 对应 ORM 属性 `network_config`：
    Pydantic v2 保留 `model_config` 作为配置名，不能直接用作字段名，
    因此通过 alias 保持对外契约与设计文档 §6.3 一致。
    """

    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())

    task_id: str = Field(min_length=1, max_length=64)
    network_config: dict = Field(default_factory=dict, alias="model_config")
    hyperparameters: dict = Field(default_factory=dict)
    result_metrics: dict = Field(default_factory=dict)
    dataset_id: int | None = None
    model_file_url: str | None = Field(default=None, max_length=512)
    status: RecordStatus = "pending"
    source: Literal["platform", "lab"] = "platform"


class RecordResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        protected_namespaces=(),
    )

    id: int
    dataset_id: int | None
    task_id: str
    network_config: dict = Field(serialization_alias="model_config")
    hyperparameters: dict
    result_metrics: dict
    model_file_url: str | None
    status: RecordStatus
    source: str = "platform"
    created_at: datetime


class RecordListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
