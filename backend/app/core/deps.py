"""FastAPI 依赖：当前用户等。"""

from fastapi import Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

import jwt

from app.api.errors import APIError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

# auto_error=False：未携带凭证时由我们返回统一的错误体，而不是 FastAPI 默认的 {"detail": ...}
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """解析 Bearer Token 并返回当前用户；任何失败均返回 401。"""
    if credentials is None or not credentials.credentials:
        raise APIError(
            status.HTTP_401_UNAUTHORIZED, "NOT_AUTHENTICATED", "未提供认证凭证"
        )

    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError as exc:
        raise APIError(
            status.HTTP_401_UNAUTHORIZED, "TOKEN_EXPIRED", "登录已过期，请重新登录"
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise APIError(
            status.HTTP_401_UNAUTHORIZED, "TOKEN_INVALID", "认证凭证无效"
        ) from exc

    subject = payload.get("sub")
    if not subject or not str(subject).isdigit():
        raise APIError(
            status.HTTP_401_UNAUTHORIZED, "TOKEN_INVALID", "认证凭证无效"
        )

    user = db.get(User, int(subject))
    if user is None:
        raise APIError(
            status.HTTP_401_UNAUTHORIZED, "USER_NOT_FOUND", "用户不存在"
        )
    return user
