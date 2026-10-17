"""用户模型。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.types import IDType

if TYPE_CHECKING:
    from app.models.dataset import Dataset
    from app.models.record import TrainingRecord


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(IDType, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    records: Mapped[list[TrainingRecord]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    datasets: Mapped[list[Dataset]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
