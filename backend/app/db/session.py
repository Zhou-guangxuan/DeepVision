"""数据库引擎与会话。"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()

# SQLite 需要放开线程检查（FastAPI 在线程池中执行同步依赖）
_connect_args = (
    {"check_same_thread": False}
    if _settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(
    _settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：每个请求一个会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
