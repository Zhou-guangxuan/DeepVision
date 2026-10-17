"""认证相关请求 / 响应模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

USERNAME_PATTERN = r"^[A-Za-z0-9_-]+$"


class RegisterRequest(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=64,
        pattern=USERNAME_PATTERN,
        description="3-64 位，仅允许字母、数字、下划线与连字符",
    )
    password: str = Field(
        min_length=6,
        max_length=128,
        description="6-128 位",
    )


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse
