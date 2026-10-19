"""应用配置。

所有配置均可用环境变量覆盖，也可写在 backend/.env 中。
环境变量名不区分大小写，例如 `DATABASE_URL` 对应 `database_url`。
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "DeepVision API"
    api_prefix: str = "/api"
    debug: bool = False

    # 认证
    secret_key: str = Field(default="dev-secret-change-me-in-production", min_length=8)
    algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=120, ge=1)

    # 数据集存储
    storage_dir: str = "./storage"
    max_upload_bytes: int = Field(default=50 * 1024 * 1024, ge=1)

    # AI 助教（未配置 Key 时自动降级为内置知识库）
    llm_provider: str = "none"  # none | openai（兼容 GLM 等 OpenAI 协议服务）
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 30.0
    # 用系统证书库校验 TLS（企业代理/安全软件注入根证书时 certifi 会失败）；
    # 确实无法通过时可设为 false 跳过校验，但会降低安全性。
    llm_verify_ssl: bool = True
    ai_rate_limit_per_minute: int = Field(default=20, ge=1)

    # 数据库
    database_url: str = "sqlite:///./deepvision.db"

    # CORS 白名单
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


@lru_cache
def get_settings() -> Settings:
    """返回进程内缓存的配置实例。"""
    return Settings()
