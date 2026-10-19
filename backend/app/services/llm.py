"""LLM 适配层。

两种模式：

- `llm_provider != none` 且配置了 `llm_api_key`：调用 OpenAI 兼容的
  `/chat/completions` 流式接口（GLM 等兼容服务改 `llm_base_url` 即可）；
- 未配置、或调用失败：退化为内置知识库的规则式回答，保证功能可用。

统一向调用方产出 `meta` / `delta` / `done` 三类事件。
"""

from __future__ import annotations

import json
import logging
import ssl
from collections.abc import AsyncIterator

import httpx

from app.core.config import get_settings
from app.services import knowledge_base
from app.services.ai_guard import sanitize_output

CHUNK_SIZE = 24

logger = logging.getLogger(__name__)


def _ssl_verify() -> ssl.SSLContext | bool:
    """返回 httpx 的 verify 参数。

    默认使用**系统证书库**：企业代理或安全软件常会注入自签根证书，
    这类根证书在 Windows 证书库里可信，但不在 certifi 里，直接用 certifi
    会报 `CERTIFICATE_VERIFY_FAILED`。用户也可以显式关闭校验。
    """
    settings = get_settings()
    if not settings.llm_verify_ssl:
        return False
    return ssl.create_default_context()


def is_llm_enabled() -> bool:
    settings = get_settings()
    return settings.llm_provider != "none" and bool(settings.llm_api_key)


def _fallback_answer(question: str) -> tuple[str, list[str]]:
    entries = knowledge_base.search(question)
    sections = [f"### {entry.title}\n{entry.content}" for entry in entries]
    answer = "当前未配置大模型，以下回答来自内置知识库。\n\n" + "\n\n".join(sections)
    sources = [f"{knowledge_base.SOURCE_LABEL} · {entry.title}" for entry in entries]
    return answer, sources


def _split(text: str, size: int = CHUNK_SIZE) -> list[str]:
    return [text[index : index + size] for index in range(0, len(text), size)]


async def stream_answer(
    question: str, mode_preference: str = "auto"
) -> AsyncIterator[dict]:
    """产出事件流：meta → delta* → done。

    mode_preference：
    - auto：有 Key 走大模型，否则内置知识库；
    - offline：强制内置知识库；
    - llm：强制大模型（未配置或调用失败时仍降级，并说明原因）。
    """
    use_llm = is_llm_enabled() and mode_preference != "offline"
    if mode_preference == "llm" and not is_llm_enabled():
        yield {
            "type": "meta",
            "mode": "fallback",
            "reason": "未配置大模型 Key，无法使用大模型引擎",
        }
        answer, sources = _fallback_answer(question)
        for piece in _split(answer):
            yield {"type": "delta", "text": sanitize_output(piece)}
        yield {"type": "done", "sources": sources}
        return

    mode = "llm" if use_llm else "fallback"
    yield {"type": "meta", "mode": mode}

    if mode == "llm":
        try:
            async for event in _stream_llm(question):
                yield event
            return
        except Exception as exc:  # noqa: BLE001 - 任何失败都降级，不阻塞用户
            logger.warning(
                "大模型调用失败，已降级为内置知识库：%s: %s",
                type(exc).__name__,
                exc,
            )
            yield {
                "type": "meta",
                "mode": "fallback",
                "reason": "大模型暂不可用，已切换为内置知识库",
            }

    answer, sources = _fallback_answer(question)
    for piece in _split(answer):
        yield {"type": "delta", "text": sanitize_output(piece)}
    yield {"type": "done", "sources": sources}


async def _stream_llm(question: str) -> AsyncIterator[dict]:
    settings = get_settings()
    entries = knowledge_base.search(question, limit=3)
    context = "\n\n".join(f"【{entry.title}】{entry.content}" for entry in entries)
    sources = [f"{knowledge_base.SOURCE_LABEL} · {entry.title}" for entry in entries]

    payload = {
        "model": settings.llm_model,
        "stream": True,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是 DeepVision 的深度学习助教。用简洁中文回答初学者的问题，"
                    "不要编造引用来源。"
                ),
            },
            {
                "role": "user",
                "content": f"参考资料：\n{context}\n\n问题：{question}",
            },
        ],
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"

    async with (
        httpx.AsyncClient(
            timeout=settings.llm_timeout_seconds,
            trust_env=False,
            verify=_ssl_verify(),
        ) as client,
        client.stream("POST", url, json=payload, headers=headers) as response,
    ):
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = line[6:].strip()
            if data == "[DONE]":
                break
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = parsed.get("choices") or [{}]
            delta = (choices[0].get("delta") or {}).get("content")
            if delta:
                yield {"type": "delta", "text": sanitize_output(delta)}

    yield {"type": "done", "sources": sources}
