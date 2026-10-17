"""认证相关测试，对应设计文档阶段一验收标准。"""

from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User


def test_register_returns_created_user(
    client: TestClient, user_payload: dict[str, str]
) -> None:
    resp = client.post("/api/auth/register", json=user_payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["username"] == "alice"
    assert "password" not in body
    assert "password_hash" not in body


def test_password_is_argon2_hashed(
    client: TestClient, db: Session, user_payload: dict[str, str]
) -> None:
    client.post("/api/auth/register", json=user_payload)
    user = db.scalar(select(User).where(User.username == "alice"))
    assert user is not None
    # 不得出现明文
    assert user.password_hash != user_payload["password"]
    assert user_payload["password"] not in user.password_hash
    # argon2id 哈希以 $argon2id$ 开头
    assert user.password_hash.startswith("$argon2")


def test_duplicate_username_conflicts(
    client: TestClient, user_payload: dict[str, str]
) -> None:
    assert client.post("/api/auth/register", json=user_payload).status_code == 201
    resp = client.post("/api/auth/register", json=user_payload)
    assert resp.status_code == 409
    assert resp.json()["code"] == "USERNAME_TAKEN"


def test_login_returns_token(
    client: TestClient, user_payload: dict[str, str]
) -> None:
    client.post("/api/auth/register", json=user_payload)
    resp = client.post("/api/auth/login", json=user_payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_in"] == get_settings().access_token_expire_minutes * 60
    assert body["user"]["username"] == "alice"


def test_login_wrong_password_returns_401(
    client: TestClient, user_payload: dict[str, str]
) -> None:
    client.post("/api/auth/register", json=user_payload)
    resp = client.post(
        "/api/auth/login",
        json={"username": user_payload["username"], "password": "wrong-password"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "INVALID_CREDENTIALS"


def test_me_requires_token(client: TestClient) -> None:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401
    assert resp.json()["code"] == "NOT_AUTHENTICATED"


def test_me_with_token(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == "alice"


def test_invalid_token_returns_401(client: TestClient) -> None:
    resp = client.get(
        "/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "TOKEN_INVALID"


def test_expired_token_returns_401(
    client: TestClient, user_payload: dict[str, str]
) -> None:
    client.post("/api/auth/register", json=user_payload)
    login = client.post("/api/auth/login", json=user_payload).json()
    user_id = login["user"]["id"]

    settings = get_settings()
    now = datetime.now(timezone.utc)
    expired = jwt.encode(
        {
            "sub": str(user_id),
            "iat": now - timedelta(hours=3),
            "exp": now - timedelta(hours=1),
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )

    resp = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {expired}"}
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "TOKEN_EXPIRED"


def test_short_password_rejected(
    client: TestClient, user_payload: dict[str, str]
) -> None:
    resp = client.post(
        "/api/auth/register",
        json={"username": user_payload["username"], "password": "short"},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_invalid_username_pattern_rejected(
    client: TestClient, user_payload: dict[str, str]
) -> None:
    resp = client.post(
        "/api/auth/register",
        json={"username": "bad name!", "password": user_payload["password"]},
    )
    assert resp.status_code == 422
