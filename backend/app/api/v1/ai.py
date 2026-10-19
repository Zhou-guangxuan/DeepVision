"""AI 助教接口：流式问答与拓扑诊断。"""

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.errors import APIError
from app.core.config import get_settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.dataset import Dataset
from app.models.user import User
from app.schemas.ai import ChatRequest, DiagnoseRequest, DiagnoseResponse
from app.schemas.graph import ModelConfigIn
from app.services import llm
from app.services.ai_guard import RateLimiter, check_input, sanitize_output
from app.services.diagnosis import diagnose

router = APIRouter(prefix="/ai", tags=["ai"])

_limiter = RateLimiter(get_settings().ai_rate_limit_per_minute)


def enforce_rate_limit(
    current_user: User = Depends(get_current_user),
) -> User:
    if not _limiter.allow(current_user.id):
        raise APIError(
            429,
            "RATE_LIMITED",
            f"请求过于频繁，请稍后再试（每分钟 {_limiter.limit} 次）",
        )
    return current_user


@router.post("/chat", summary="AI 助教问答（SSE 流式）")
async def chat(
    payload: ChatRequest,
    current_user: User = Depends(enforce_rate_limit),
) -> StreamingResponse:
    reason = check_input(payload.message)
    if reason:
        raise APIError(400, "INPUT_REJECTED", reason)

    async def generate():
        async for event in llm.stream_answer(payload.message, payload.mode):
            if event.get("type") == "delta":
                event["text"] = sanitize_output(str(event.get("text", "")))
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/diagnose", response_model=DiagnoseResponse, summary="拓扑诊断与调参建议"
)
def diagnose_graph(
    payload: DiagnoseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(enforce_rate_limit),
) -> DiagnoseResponse:
    config = ModelConfigIn(**payload.network_config)

    dataset = None
    if payload.dataset_id is not None:
        dataset = db.get(Dataset, payload.dataset_id)
        if dataset is None:
            raise APIError(404, "DATASET_NOT_FOUND", "数据集不存在")
        if dataset.user_id != current_user.id:
            raise APIError(403, "FORBIDDEN", "无权访问该数据集")

    result = diagnose(config, dataset, payload.hyperparameters)
    return DiagnoseResponse(**result)
