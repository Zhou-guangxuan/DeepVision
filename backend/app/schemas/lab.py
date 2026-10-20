"""教学实验室的请求 / 响应模型。"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LabConfig(BaseModel):
    input_units: int = Field(default=2, ge=1, le=16, description="输入神经元数")
    output_units: int = Field(default=2, ge=2, le=8, description="输出类别数")
    hidden_layers: list[int] = Field(
        default_factory=lambda: [8, 8], min_length=1, max_length=6
    )
    activation: Literal["relu", "tanh", "sigmoid"] = "relu"
    init: Literal["he", "xavier", "uniform"] = "he"
    optimizer: Literal["adam", "sgd"] = "adam"
    learning_rate: float = Field(default=0.05, gt=0, le=1)
    batch_size: int = Field(default=32, ge=1, le=512)
    epochs: int = Field(default=60, ge=1, le=500)
    l2: float = Field(default=0.0, ge=0, le=0.5)
    dropout: float = Field(default=0.0, ge=0, le=0.9)

    @field_validator("hidden_layers")
    @classmethod
    def _check_units(cls, value: list[int]) -> list[int]:
        for units in value:
            if not 1 <= units <= 256:
                raise ValueError("每层神经元数需在 1-256 之间")
        return value


class LabStartRequest(BaseModel):
    config: LabConfig = Field(default_factory=LabConfig)


class LabStartResponse(BaseModel):
    task_id: str
    parameter_count: int


class LabControlResponse(BaseModel):
    task_id: str
    status: str
