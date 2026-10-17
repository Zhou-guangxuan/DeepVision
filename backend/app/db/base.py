"""声明式基类与通用工具。"""

from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


def utcnow() -> datetime:
    """统一使用带时区的 UTC 时间。"""
    return datetime.now(timezone.utc)
