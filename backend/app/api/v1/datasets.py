"""数据集接口：上传解析与查询。"""

import json

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.errors import APIError
from app.core.config import get_settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.dataset import Dataset
from app.models.user import User
from app.schemas.common import Page
from app.schemas.dataset import DatasetResponse, DatasetSummary
from app.services import csv_service

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post(
    "",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="上传并解析 CSV 数据集",
)
async def create_dataset(
    file: UploadFile = File(...),
    feature_columns: str = Form(..., description="JSON 字符串数组"),
    target_column: str = Form(...),
    missing_strategy: str = Form("mean"),
    name: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DatasetResponse:
    settings = get_settings()

    filename = (file.filename or "").strip()
    if not filename.lower().endswith(".csv"):
        raise APIError(
            status.HTTP_400_BAD_REQUEST, "INVALID_FILE_TYPE", "仅支持 .csv 文件"
        )

    raw = await file.read()
    if not raw:
        raise APIError(status.HTTP_400_BAD_REQUEST, "EMPTY_FILE", "文件内容为空")
    if len(raw) > settings.max_upload_bytes:
        raise APIError(
            413,
            "FILE_TOO_LARGE",
            "文件超过 50MB 限制",
        )

    try:
        parsed_features = json.loads(feature_columns)
    except json.JSONDecodeError as exc:
        raise APIError(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_FEATURE_COLUMNS",
            "feature_columns 必须是 JSON 数组",
        ) from exc

    if not isinstance(parsed_features, list) or not all(
        isinstance(item, str) for item in parsed_features
    ):
        raise APIError(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_FEATURE_COLUMNS",
            "feature_columns 必须是字符串数组",
        )

    try:
        result = csv_service.preprocess(
            raw, parsed_features, target_column, missing_strategy
        )
    except csv_service.CsvParseError as exc:
        raise APIError(
            status.HTTP_400_BAD_REQUEST, "CSV_PARSE_ERROR", str(exc)
        ) from exc

    file_path = csv_service.save_dataset_file(
        settings.storage_dir, current_user.id, raw
    )

    dataset = Dataset(
        user_id=current_user.id,
        name=name or filename,
        columns_meta=result["columns_meta"],
        target_column=target_column,
        missing_strategy=missing_strategy,
        stats=result["stats"].model_dump(),
        sample_count=result["sample_count"],
        feature_count=result["feature_count"],
        file_path=file_path,
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    return DatasetResponse.model_validate(dataset)


@router.get("", response_model=Page[DatasetSummary], summary="数据集列表")
def list_datasets(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Page[DatasetSummary]:
    base = select(Dataset).where(Dataset.user_id == current_user.id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    rows = db.scalars(
        base.order_by(Dataset.created_at.desc(), Dataset.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return Page[DatasetSummary](
        items=[DatasetSummary.model_validate(row) for row in rows],
        total=int(total),
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{dataset_id}", response_model=DatasetResponse, summary="数据集详情与统计"
)
def get_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DatasetResponse:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise APIError(
            status.HTTP_404_NOT_FOUND, "DATASET_NOT_FOUND", "数据集不存在"
        )
    if dataset.user_id != current_user.id:
        raise APIError(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "无权访问该数据集")
    return DatasetResponse.model_validate(dataset)
