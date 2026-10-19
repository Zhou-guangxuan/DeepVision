"""训练记录 CRUD。

所有接口均要求登录，且强制校验资源归属，防止 ID 越权。
"""

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.errors import APIError
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.dataset import Dataset
from app.models.record import TrainingRecord
from app.models.user import User
from app.schemas.common import Page
from app.schemas.record import RecordCreate, RecordResponse

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
