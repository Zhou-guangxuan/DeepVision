"""数据集相关的请求 / 响应模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ColumnMeta(BaseModel):
    name: str
    dtype: str
    missing: int = 0


class FeatureStats(BaseModel):
    name: str
    mean: float | None = None
    variance: float | None = None


class DatasetStats(BaseModel):
    features: list[FeatureStats] = Field(default_factory=list)
    target: FeatureStats | None = None
    target_distribution: dict[str, int] = Field(default_factory=dict)


class DatasetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    columns_meta: list[ColumnMeta]
    target_column: str | None
    missing_strategy: str
    stats: DatasetStats
    sample_count: int
    feature_count: int
    created_at: datetime


class DatasetSummary(BaseModel):
    """列表页用的精简结构，不返回逐列统计。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    target_column: str | None
    missing_strategy: str
    sample_count: int
    feature_count: int
    created_at: datetime
