"""训练接口：创建任务、停止任务。

真正的训练在 WebSocket 连接建立后启动，便于客户端先订阅再接收事件。
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.errors import APIError
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.dataset import Dataset
from app.models.user import User
from app.schemas.graph import ModelConfigIn
from app.schemas.train import (
    ImageTrainRequest,
    StopResponse,
    TrainRequest,
    TrainStartResponse,
)
from app.services import codegen, training
from app.services.graph_validation import validate_model_config

router = APIRouter(prefix="/train", tags=["train"])


@router.post(
    "",
    response_model=TrainStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="创建训练任务",
)
def create_training(
    payload: TrainRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TrainStartResponse:
    dataset = db.get(Dataset, payload.dataset_id)
    if dataset is None:
        raise APIError(status.HTTP_404_NOT_FOUND, "DATASET_NOT_FOUND", "数据集不存在")
    if dataset.user_id != current_user.id:
        raise APIError(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "无权访问该数据集")

    config = ModelConfigIn(**payload.network_config)
    result = validate_model_config(config)
    if not result["valid"]:
        raise APIError(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_MODEL_CONFIG",
            result["errors"][0] if result["errors"] else "拓扑结构非法",
        )

    hyper = payload.hyperparameters.model_dump()
    task = training.create_task(
        user_id=current_user.id,
        dataset_id=payload.dataset_id,
        config=payload.network_config,
        plan=result["execution_plan"],
        hyper=hyper,
    )

    return TrainStartResponse(task_id=task.task_id, total_epochs=int(hyper["epochs"]))


@router.post(
    "/image",
    response_model=TrainStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="创建图像分类训练任务（固定小 CNN）",
)
def create_image_training(
    payload: ImageTrainRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TrainStartResponse:
    dataset = db.get(Dataset, payload.dataset_id)
    if dataset is None:
        raise APIError(status.HTTP_404_NOT_FOUND, "DATASET_NOT_FOUND", "数据集不存在")
    if dataset.user_id != current_user.id:
        raise APIError(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "无权访问该数据集")
    if dataset.kind != "image":
        raise APIError(
            status.HTTP_400_BAD_REQUEST,
            "NOT_IMAGE_DATASET",
            "该数据集不是图像数据集",
        )

    hyper = payload.hyperparameters.model_dump()
    task = training.create_image_task(
        user_id=current_user.id,
        dataset_id=payload.dataset_id,
        hyper=hyper,
    )
    return TrainStartResponse(task_id=task.task_id, total_epochs=int(hyper["epochs"]))


@router.post("/{task_id}/stop", response_model=StopResponse, summary="停止训练")
def stop_training(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> StopResponse:
    task = training.get_task(task_id)
    if task is None:
        raise APIError(
            status.HTTP_404_NOT_FOUND, "TRAIN_TASK_NOT_FOUND", "训练任务不存在"
        )
    if task.user_id != current_user.id:
        raise APIError(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "无权操作该任务")

    training.request_stop(task)
    return StopResponse(task_id=task_id, stopped=True)


@router.get("/{task_id}/code", summary="生成等效 PyTorch 代码与行号映射")
def get_task_code(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    task = training.get_task(task_id)
    if task is None:
        raise APIError(
            status.HTTP_404_NOT_FOUND, "TRAIN_TASK_NOT_FOUND", "训练任务不存在"
        )
    if task.user_id != current_user.id:
        raise APIError(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "无权访问该任务")

    try:
        return codegen.generate_code(task.config)
    except ValueError as exc:
        raise APIError(status.HTTP_400_BAD_REQUEST, "CODEGEN_FAILED", str(exc)) from exc
