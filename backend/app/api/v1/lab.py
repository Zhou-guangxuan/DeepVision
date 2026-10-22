"""教学实验室接口：创建训练任务与暂停 / 恢复 / 停止。"""

from fastapi import APIRouter, Depends, Query, status

from app.api.errors import APIError
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.lab import (
    LabControlResponse,
    LabStartRequest,
    LabStartResponse,
    TuneStartRequest,
)
from app.services import curve_diagnosis, lab, tuning

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
    return LabStartResponse(task_id=task.task_id, parameter_count=parameter_count)


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


def _ready_task(task_id: str, user: User):
    task = _owned_task(task_id, user)
    if task.model is None:
        raise APIError(
            status.HTTP_409_CONFLICT,
            "LAB_NOT_READY",
            "训练开始后才能查看传播过程",
        )
    return task


@router.get("/{task_id}/inspect", summary="前向 / 反向传播与特征注意力")
def inspect_task(
    task_id: str,
    index: int = Query(default=0, ge=0, description="样本序号"),
    current_user: User = Depends(get_current_user),
) -> dict:
    task = _ready_task(task_id, current_user)
    try:
        return lab.inspect(task, index)
    except ValueError as exc:
        raise APIError(
            status.HTTP_400_BAD_REQUEST, "LAB_INSPECT_FAILED", str(exc)
        ) from exc


@router.get("/{task_id}/projection", summary="指定层的降维投影（PCA / t-SNE）")
def project_task(
    task_id: str,
    layer: int = Query(default=0, ge=0, description="第几个 Linear 层"),
    method: str = Query(default="pca", pattern="^(pca|tsne)$"),
    current_user: User = Depends(get_current_user),
) -> dict:
    task = _ready_task(task_id, current_user)
    try:
        return lab.project(task, layer, method=method)
    except ValueError as exc:
        raise APIError(
            status.HTTP_400_BAD_REQUEST, "LAB_PROJECTION_FAILED", str(exc)
        ) from exc


@router.get("/{task_id}/attention", summary="逐 epoch 的输入特征注意力")
def attention_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    task = _ready_task(task_id, current_user)
    try:
        return lab.attention_history(task)
    except ValueError as exc:
        raise APIError(
            status.HTTP_400_BAD_REQUEST, "LAB_ATTENTION_FAILED", str(exc)
        ) from exc


@router.get("/{task_id}/diagnosis", summary="教学任务的曲线诊断")
def lab_diagnosis(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """复用记录级的规则引擎，直接分析当前任务的历史曲线。"""
    task = _owned_task(task_id, current_user)
    return curve_diagnosis.diagnose_curve(task.history)


@router.post("/tune", summary="启动自动调参（随机搜索 + 早停）")
def start_tune(
    payload: TuneStartRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    tune = tuning.create_tune(
        user_id=current_user.id,
        base=payload.config.model_dump(),
        trials=payload.trials,
        epochs=payload.epochs,
    )
    return tune.snapshot()


@router.get("/tune/{tune_id}", summary="查询自动调参进度")
def get_tune(
    tune_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    tune = tuning.get_tune(tune_id)
    if tune is None or tune.user_id != current_user.id:
        raise APIError(
            status.HTTP_404_NOT_FOUND, "TUNE_NOT_FOUND", "自动调参任务不存在"
        )
    return tune.snapshot()
