"""训练记录模型。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.types import IDType

if TYPE_CHECKING:
    from app.models.dataset import Dataset
    from app.models.user import User

# 训练任务状态机
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_INTERRUPTED = "interrupted"
STATUSES = (
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SUCCESS,
    STATUS_FAILED,
    STATUS_INTERRUPTED,
)


class TrainingRecord(Base):
    __tablename__ = "training_records"

    id: Mapped[int] = mapped_column(IDType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    dataset_id: Mapped[int | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="SET NULL"), index=True, nullable=True
    )
    task_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    # 列名为 model_config（对齐设计文档 §6.2）；
    # 属性名用 network_config，避免与 SQLAlchemy / Pydantic 的保留名冲突。
    network_config: Mapped[dict] = mapped_column("model_config", JSON, nullable=False)
    hyperparameters: Mapped[dict] = mapped_column(JSON, nullable=False)
    result_metrics: Mapped[dict] = mapped_column(JSON, nullable=False)
    model_file_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), index=True, nullable=False, default=STATUS_PENDING
    )
    # 记录来源：platform（第一阶段工作台） / lab（第三阶段教学实验室）
    source: Mapped[str] = mapped_column(
        String(16), index=True, nullable=False, default="platform"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    user: Mapped[User] = relationship(back_populates="records")
    dataset: Mapped[Dataset | None] = relationship(back_populates="records")
