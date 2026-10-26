"""训练记录 CRUD。

所有接口均要求登录，且强制校验资源归属，防止 ID 越权。
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.errors import APIError
from app.core.config import get_settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.dataset import Dataset
from app.models.record import TrainingRecord
from app.models.user import User
from app.schemas.common import Page
from app.schemas.graph import ModelConfigIn
from app.schemas.record import RecordCreate, RecordResponse
from app.schemas.train import TrainStartResponse
from app.services import codegen, curve_diagnosis, training
from app.services.graph_validation import validate_model_config

router = APIRouter(prefix="/records", tags=["records"])


def _ensure_owned(record: TrainingRecord, user: User) -> None:
    if record.user_id != user.id:
        raise APIError(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "无权访问该记录")


@router.get(
    "",
    response_model=Page[RecordResponse],
    summary="训练记录列表（按时间倒序）",
)
def list_records(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Page[RecordResponse]:
    base = select(TrainingRecord).where(TrainingRecord.user_id == current_user.id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    rows = db.scalars(
        base.order_by(TrainingRecord.created_at.desc(), TrainingRecord.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return Page[RecordResponse](
        items=[RecordResponse.model_validate(row) for row in rows],
        total=int(total),
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="保存训练记录",
)
def create_record(
    payload: RecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RecordResponse:
    if db.scalar(
        select(TrainingRecord).where(TrainingRecord.task_id == payload.task_id)
    ):
        raise APIError(status.HTTP_409_CONFLICT, "TASK_ID_TAKEN", "task_id 已存在")

    if payload.dataset_id is not None:
        dataset = db.get(Dataset, payload.dataset_id)
        if dataset is None:
            raise APIError(
                status.HTTP_404_NOT_FOUND, "DATASET_NOT_FOUND", "数据集不存在"
            )
        if dataset.user_id != current_user.id:
            raise APIError(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "无权访问该数据集")

    record = TrainingRecord(
        user_id=current_user.id,
        dataset_id=payload.dataset_id,
        task_id=payload.task_id,
        network_config=payload.network_config,
        hyperparameters=payload.hyperparameters,
        result_metrics=payload.result_metrics,
        model_file_url=payload.model_file_url,
        status=payload.status,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return RecordResponse.model_validate(record)


@router.get("/compare", summary="多实验曲线对比（2–4 条）")
def compare_records(
    ids: str = Query(description="逗号分隔的记录 ID，例如 3,5,8"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    id_list = [int(item) for item in ids.split(",") if item.strip().isdigit()]
    if not 2 <= len(id_list) <= 4:
        raise APIError(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_SELECTION",
            "请选择 2–4 条记录进行对比",
        )

    rows = db.scalars(
        select(TrainingRecord).where(
            TrainingRecord.id.in_(id_list),
            TrainingRecord.user_id == current_user.id,
        )
    ).all()
    if len(rows) != len(set(id_list)):
        raise APIError(
            status.HTTP_404_NOT_FOUND, "RECORD_NOT_FOUND", "部分训练记录不存在"
        )

    order = {record_id: index for index, record_id in enumerate(id_list)}
    rows.sort(key=lambda row: order.get(row.id, 0))

    runs = []
    for row in rows:
        metrics = row.result_metrics or {}
        history = metrics.get("history") or []
        runs.append(
            {
                "id": row.id,
                "task_id": row.task_id,
                "source": row.source,
                "status": row.status,
                "created_at": row.created_at.isoformat(),
                "epochs": len(history),
                "final_accuracy": metrics.get("final_accuracy"),
                "history": [
                    {
                        "epoch": item.get("epoch"),
                        "train_loss": item.get("train_loss"),
                        "val_loss": item.get("val_loss"),
                        "accuracy": item.get("accuracy"),
                        # 用于「按实际耗时」对齐；历史记录可能没有该字段
                        "elapsed_ms": item.get("elapsed_ms"),
                    }
                    for item in history
                ],
            }
        )

    return {"runs": runs}


@router.get("/{record_id}/diagnosis", summary="训练曲线诊断")
def diagnose_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    record = db.get(TrainingRecord, record_id)
    if record is None:
        raise APIError(status.HTTP_404_NOT_FOUND, "RECORD_NOT_FOUND", "训练记录不存在")
    _ensure_owned(record, current_user)

    history = (record.result_metrics or {}).get("history") or []
    return curve_diagnosis.diagnose_curve(history)


@router.post(
    "/{record_id}/rerun",
    response_model=TrainStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="按原配置重跑（可复现）",
)
def rerun_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TrainStartResponse:
    record = db.get(TrainingRecord, record_id)
    if record is None:
        raise APIError(status.HTTP_404_NOT_FOUND, "RECORD_NOT_FOUND", "训练记录不存在")
    _ensure_owned(record, current_user)

    if record.dataset_id is None:
        raise APIError(
            status.HTTP_400_BAD_REQUEST,
            "RERUN_UNAVAILABLE",
            "该记录没有关联数据集（例如教学实验室记录），无法重跑",
        )

    dataset = db.get(Dataset, record.dataset_id)
    if dataset is None or dataset.user_id != current_user.id:
        raise APIError(
            status.HTTP_404_NOT_FOUND, "DATASET_NOT_FOUND", "数据集不存在或无权访问"
        )

    hyper = dict(record.hyperparameters or {})
    hyper.setdefault("epochs", 10)
    hyper.setdefault("batch_size", 32)
    hyper.setdefault("learning_rate", 0.001)

    # 图像 / 多模态实验线不走 DAG 校验：用同一份数据集与超参重新创建固定模型任务
    if dataset.kind == "image":
        image_task = training.create_image_task(
            user_id=current_user.id,
            dataset_id=record.dataset_id,
            hyper=hyper,
        )
        return TrainStartResponse(
            task_id=image_task.task_id, total_epochs=int(hyper["epochs"])
        )

    if dataset.kind == "multimodal":
        multimodal_task = training.create_multimodal_task(
            user_id=current_user.id,
            dataset_id=record.dataset_id,
            hyper=hyper,
        )
        return TrainStartResponse(
            task_id=multimodal_task.task_id, total_epochs=int(hyper["epochs"])
        )

    config = ModelConfigIn(**record.network_config)
    result = validate_model_config(config)
    if not result["valid"]:
        raise APIError(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_MODEL_CONFIG",
            result["errors"][0] if result["errors"] else "拓扑结构非法",
        )

    task = training.create_task(
        user_id=current_user.id,
        dataset_id=record.dataset_id,
        config=record.network_config,
        plan=result["execution_plan"],
        hyper=hyper,
    )

    return TrainStartResponse(task_id=task.task_id, total_epochs=int(hyper["epochs"]))


@router.get("/{record_id}/code", summary="生成等效 PyTorch 代码与行号映射")
def get_record_code(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    record = db.get(TrainingRecord, record_id)
    if record is None:
        raise APIError(status.HTTP_404_NOT_FOUND, "RECORD_NOT_FOUND", "训练记录不存在")
    _ensure_owned(record, current_user)

    config = record.network_config or {}
    if not config.get("nodes"):
        raise APIError(
            status.HTTP_400_BAD_REQUEST,
            "CODEGEN_UNAVAILABLE",
            "该记录没有保存拓扑（例如教学实验室记录），无法生成代码",
        )

    try:
        return codegen.generate_code(config)
    except ValueError as exc:
        raise APIError(status.HTTP_400_BAD_REQUEST, "CODEGEN_FAILED", str(exc)) from exc


@router.get("/{record_id}/image-eval", summary="图像训练的混淆矩阵与样本预测")
def get_image_eval(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    record = db.get(TrainingRecord, record_id)
    if record is None:
        raise APIError(status.HTTP_404_NOT_FOUND, "RECORD_NOT_FOUND", "训练记录不存在")
    _ensure_owned(record, current_user)

    image_eval = (record.result_metrics or {}).get("image_eval")
    if not image_eval:
        raise APIError(
            status.HTTP_400_BAD_REQUEST,
            "NOT_IMAGE_RECORD",
            "该记录不是图像训练，或未保存图像评估",
        )
    return image_eval


@router.get("/{record_id}/model", summary="下载训练好的模型权重")
def download_model(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    record = db.get(TrainingRecord, record_id)
    if record is None:
        raise APIError(status.HTTP_404_NOT_FOUND, "RECORD_NOT_FOUND", "训练记录不存在")
    _ensure_owned(record, current_user)

    if not record.model_file_url:
        raise APIError(
            status.HTTP_400_BAD_REQUEST,
            "MODEL_NOT_AVAILABLE",
            "该记录没有保存模型文件（例如图像实验线不落盘权重）",
        )

    storage = Path(get_settings().storage_dir).resolve()
    path = Path(record.model_file_url).resolve()
    if storage != path and storage not in path.parents:
        raise APIError(
            status.HTTP_400_BAD_REQUEST,
            "MODEL_PATH_INVALID",
            "模型文件路径非法",
        )
    if not path.is_file():
        raise APIError(
            status.HTTP_404_NOT_FOUND,
            "MODEL_FILE_MISSING",
            "模型文件已丢失，请重新训练",
        )

    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=f"deepvision-record-{record_id}.pt",
    )


@router.get("/{record_id}", response_model=RecordResponse, summary="训练记录详情")
def get_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RecordResponse:
    record = db.get(TrainingRecord, record_id)
    if record is None:
        raise APIError(status.HTTP_404_NOT_FOUND, "RECORD_NOT_FOUND", "训练记录不存在")
    _ensure_owned(record, current_user)
    return RecordResponse.model_validate(record)


@router.delete(
    "/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除训练记录",
)
def delete_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    record = db.get(TrainingRecord, record_id)
    if record is None:
        raise APIError(status.HTTP_404_NOT_FOUND, "RECORD_NOT_FOUND", "训练记录不存在")
    _ensure_owned(record, current_user)
    db.delete(record)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
