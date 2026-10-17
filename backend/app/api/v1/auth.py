"""认证接口：注册、登录、当前用户。"""

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import APIError
from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _build_token_response(user: User) -> TokenResponse:
    token, expires_in = create_access_token(user.id)
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="注册新用户",
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> UserResponse:
    exists = db.scalar(select(User).where(User.username == payload.username))
    if exists is not None:
        raise APIError(
            status.HTTP_409_CONFLICT, "USERNAME_TAKEN", "用户名已被占用"
        )

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse, summary="登录并获取 JWT")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.username == payload.username))
    # 用户不存在与密码错误返回同一错误，避免用户名枚举
    if user is None or not verify_password(payload.password, user.password_hash):
        raise APIError(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_CREDENTIALS",
            "用户名或密码错误",
        )
    return _build_token_response(user)


@router.get("/me", response_model=UserResponse, summary="当前登录用户")
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)
