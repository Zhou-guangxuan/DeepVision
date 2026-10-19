"""FastAPI 应用入口。

启动方式（在 backend 目录下）：
    uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.lab_ws import router as lab_ws_router
from app.api.realtime import router as realtime_router
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.schemas.common import HealthResponse

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="DeepVision 可视化深度学习实验平台 API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router, prefix=settings.api_prefix)
# WebSocket 走独立路径 /ws/train/{task_id}，不加 /api 前缀
app.include_router(realtime_router)
# 教学实验室 WebSocket：/ws/lab/{task_id}
app.include_router(lab_ws_router)


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")
