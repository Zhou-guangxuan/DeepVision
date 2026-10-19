"""数据集模型。

说明：设计文档将 datasets 归入阶段三，但 training_records.dataset_id 是外键，
阶段一必须先建表，否则该外键无从引用。故此处一并落地表结构，
阶段三只需补充上传、解析与统计的业务逻辑。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.types import IDType

if TYPE_CHECKING:
    from app.models.record import TrainingRecord
    from app.models.user import User


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(IDType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    columns_meta: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    feature_columns: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    target_column: Mapped[str | None] = mapped_column(String(255), nullable=True)
    missing_strategy: Mapped[str] = mapped_column(
        String(16), nullable=False, default="mean"
    )
    stats: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    sample_count: Mapped[int] = mapped_column(nullable=False, default=0)
    feature_count: Mapped[int] = mapped_column(nullable=False, default=0)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="datasets")
    records: Mapped[list[TrainingRecord]] = relationship(back_populates="dataset")
