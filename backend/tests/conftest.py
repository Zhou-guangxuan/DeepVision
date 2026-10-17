"""测试公共夹具：内存 SQLite + 依赖覆盖。"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  确保模型注册到 metadata
from app.db.base import Base
from app.db.session import get_db
from app.main import app

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


@pytest.fixture(autouse=True)
def _schema() -> Iterator[None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db() -> Iterator[Session]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client() -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def user_payload() -> dict[str, str]:
    return {"username": "alice", "password": "Str0ng!pass"}


@pytest.fixture()
def auth_headers(
    client: TestClient, user_payload: dict[str, str]
) -> dict[str, str]:
    client.post("/api/auth/register", json=user_payload)
    resp = client.post("/api/auth/login", json=user_payload)
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}
