"""训练相关的请求 / 响应模型。"""

from pydantic import BaseModel, ConfigDict, Field


class Hyperparameters(BaseModel):
    epochs: int = Field(default=20, ge=1, le=500)
    batch_size: int = Field(default=32, ge=1, le=1024)
    learning_rate: float = Field(default=0.001, gt=0, le=1)


class TrainRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())

    dataset_id: int
    network_config: dict = Field(alias="model_config")
    hyperparameters: Hyperparameters = Field(default_factory=Hyperparameters)


class TrainStartResponse(BaseModel):
    task_id: str
    total_epochs: int


class StopResponse(BaseModel):
    task_id: str
    stopped: bool
