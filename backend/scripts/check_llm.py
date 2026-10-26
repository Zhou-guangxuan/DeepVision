"""检查大模型接入配置是否可用。

用法（在 backend 目录下）：

    .venv\\Scripts\\python.exe scripts/check_llm.py

脚本会读取 `backend/.env`：
- 未配置 Key：提示当前为离线模式，退出码 0
- 已配置：向 `LLM_BASE_URL` 发一次非流式请求，打印状态码与模型返回
- 常见错误（401 / 402 / 404 / 429）会给出对应排查建议
"""

from __future__ import annotations

import ssl
import sys
from pathlib import Path

import httpx

# 允许用 `python scripts/check_llm.py` 直接运行
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402


def _mask(key: str) -> str:
    if len(key) <= 8:
        return "已配置"
    return f"{key[:4]}…{key[-4:]}"


def main() -> int:
    settings = get_settings()
    key = settings.llm_api_key or ""

    print(f"LLM_PROVIDER = {settings.llm_provider}")
    print(f"LLM_BASE_URL = {settings.llm_base_url}")
    print(f"LLM_MODEL    = {settings.llm_model}")
    print(f"LLM_API_KEY  = {_mask(key) if key else '未配置'}")

    if settings.llm_provider == "none" or not key:
        print("\n当前为离线模式：AI 助教使用内置知识库，不需要 API Key。")
        print("要接入大模型，请在 backend/.env 设置：")
        print("  LLM_PROVIDER=openai")
        print("  LLM_API_KEY=sk-...")
        print("  LLM_BASE_URL=https://api.deepseek.com/v1")
        print("  LLM_MODEL=<服务商控制台里的准确模型 id>")
        return 0

    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.llm_model,
        "messages": [{"role": "user", "content": "只回复 pong"}],
        "max_tokens": 8,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    # 与后端一致：用系统证书库，而不是 certifi
    verify: bool | ssl.SSLContext = (
        ssl.create_default_context() if settings.llm_verify_ssl else False
    )

    print(f"\nPOST {url}")

    try:
        with httpx.Client(
            timeout=settings.llm_timeout_seconds,
            trust_env=False,
            verify=verify,
        ) as client:
            response = client.post(url, json=payload, headers=headers)
    except Exception as exc:  # noqa: BLE001
        print(f"请求失败：{type(exc).__name__}: {exc}")
        print("排查：")
        print("  1) 脚本不使用系统代理（trust_env=False），确认能直连该地址")
        print(
            "  2) 公司代理注入自签证书导致 TLS 失败时，可临时设 LLM_VERIFY_SSL=false 测试"
        )
        return 2

    print(f"HTTP {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content", "")
        print(f"模型返回：{data.get('model')} / {content!r}")
        print("接入成功。")
        return 0

    print(f"响应体：{response.text[:400]}")
    hints = {
        400: "模型名不被支持：响应体会列出 supported names，把 LLM_MODEL 改成其中之一。",
        401: "API Key 无效或已过期：去控制台重新生成，注意不要带多余空格。",
        402: "余额不足：充值后重试。",
        403: "账号无权限调用该模型：确认已开通。",
        404: "模型名或地址不对：确认 LLM_MODEL 是控制台里的准确 id，且 LLM_BASE_URL 带 /v1。",
        429: "触发限流：稍后重试，或降低 AI_RATE_LIMIT_PER_MINUTE。",
    }
    print("提示：" + hints.get(response.status_code, "查看服务商文档。"))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
