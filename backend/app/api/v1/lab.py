"""教学实验室接口：创建训练任务与暂停 / 恢复 / 停止。"""

from fastapi import APIRouter, Depends, status

from app.api.errors import APIError
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.lab import (
    LabControlResponse,
    LabStartRequest,
    LabStartResponse,
)
from app.services import lab

router = APIRouter(prefix="/lab", tags=["lab"])


def _owned_task(task_id: str, user: User):
    task = lab.get_task(task_id)
    if task is None:
        raise APIError(
            status.HTTP_404_NOT_FOUND, "LAB_TASK_NOT_FOUND", "训练任务不存在"
        )
    if task.user_id != user.id:
        raise APIError(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "无权操作该任务")
    return task


@router.post(
    "/train",
    response_model=LabStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="创建实验室训练任务",
)
def start_training(
    payload: LabStartRequest,
    current_user: User = Depends(get_current_user),
) -> LabStartResponse:
    config = payload.config.model_dump()
    model = lab.build_model(config)
    parameter_count = sum(parameter.numel() for parameter in model.parameters())

    task = lab.create_task(user_id=current_user.id, config=config)
    return LabStartResponse(
        task_id=task.task_id, parameter_count=parameter_count
    )


@router.post(
    "/{task_id}/pause",
    response_model=LabControlResponse,
    summary="暂停训练",
)
def pause_training(
    task_id: str, current_user: User = Depends(get_current_user)
) -> LabControlResponse:
    task = _owned_task(task_id, current_user)
    lab.pause(task)
    lab.emit(task, {"type": "paused"})
    return LabControlResponse(task_id=task_id, status="paused")


@router.post(
    "/{task_id}/resume",
    response_model=LabControlResponse,
    summary="恢复训练",
)
def resume_training(
    task_id: str, current_user: User = Depends(get_current_user)
) -> LabControlResponse:
    task = _owned_task(task_id, current_user)
    lab.resume(task)
    lab.emit(task, {"type": "resumed"})
    return LabControlResponse(task_id=task_id, status="running")


@router.post(
    "/{task_id}/stop",
    response_model=LabControlResponse,
    summary="停止训练",
)
def stop_training(
    task_id: str, current_user: User = Depends(get_current_user)
) -> LabControlResponse:
    task = _owned_task(task_id, current_user)
    lab.stop(task)
    lab.emit(task, {"type": "stopping"})
    return LabControlResponse(task_id=task_id, status="stopping")
