"""密码哈希与 JWT 签发 / 校验。

密码使用 argon2id（argon2-cffi 默认算法），不接受明文入库。
"""

from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

_settings = get_settings()
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """生成 argon2 哈希。"""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """校验明文密码与存储的哈希是否匹配。"""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_access_token(subject: str | int) -> tuple[str, int]:
    """签发访问令牌，返回 (token, 有效秒数)。"""
    expires_delta = timedelta(minutes=_settings.access_token_expire_minutes)
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "iat": now,
        "exp": now + expires_delta,
    }
    token = jwt.encode(payload, _settings.secret_key, algorithm=_settings.algorithm)
    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str) -> dict:
    """解码并校验令牌，失败时抛出 jwt 异常。"""
    return jwt.decode(token, _settings.secret_key, algorithms=[_settings.algorithm])
