"""创建或重置本地测试账号。

用法（在任意目录执行均可，脚本会自行切换工作目录）：

    python backend/scripts/seed_test_user.py
    python backend/scripts/seed_test_user.py --username admin --password 123456

说明：

- 直接写入数据库创建账号，不经过注册接口；密码仍使用 argon2id 哈希存储，不会出现明文。
- 仅用于本地开发 / 演示；生产环境请勿使用弱口令账号。
- 数据库地址取自应用配置，默认 `backend/deepvision.db`（相对路径，依赖工作目录），
  因此脚本会先 chdir 到 backend 目录，确保与 `uvicorn` 运行时使用同一个库文件。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]

# 必须在导入 app.* 之前切换目录：
# 配置里的 database_url 是相对路径 sqlite:///./deepvision.db，引擎在导入时创建。
os.chdir(BACKEND_ROOT)
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

from app.core.security import hash_password, verify_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402


def upsert_user(username: str, password: str) -> tuple[User, bool]:
    """创建用户；若已存在则重置其密码。返回 (用户, 是否新建)。"""
    session = SessionLocal()
    try:
        user = session.scalar(select(User).where(User.username == username))
        created = user is None
        if created:
            user = User(username=username, password_hash=hash_password(password))
            session.add(user)
        else:
            user.password_hash = hash_password(password)
        session.commit()
        session.refresh(user)
        return user, created
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="创建或重置 DeepVision 测试账号")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="123456")
    args = parser.parse_args()

    user, created = upsert_user(args.username, args.password)
    verified = verify_password(args.password, user.password_hash)

    # 故意使用 ASCII 输出：Windows 控制台默认 GBK，中文容易乱码
    print(f"database    : {BACKEND_ROOT / 'deepvision.db'}")
    print(f"action      : {'created' if created else 'password reset'}")
    print(f"account     : id={user.id} username={user.username}")
    print(f"verify      : {'OK' if verified else 'FAILED'}")
    print(f"hash prefix : {user.password_hash[:24]}...")
    print(
        "plaintext   : "
        + (
            "NO (argon2id hash)"
            if args.password not in user.password_hash
            else "YES (BUG!)"
        )
    )
    return 0 if verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
