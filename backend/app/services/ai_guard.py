"""AI 助教的输入过滤与限流。

- 输入：命中敏感词直接拒绝，不送进模型；
- 输出：命中敏感词做脱敏替换；
- 限流：单用户滑动窗口计数，默认 20 次/分钟。
"""

from __future__ import annotations

import threading
import time
from collections import deque

BLOCKED_TERMS: tuple[str, ...] = (
    "制造炸弹",
    "制作炸弹",
    "自制枪支",
    "毒品配方",
    "如何自杀",
    "hack 银行",
    "盗取密码",
)

REDACTED = "[已过滤]"


class RateLimiter:
    """滑动窗口限流器（进程内，够用于单机部署）。"""

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[int, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: int) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits.setdefault(key, deque())
            while bucket and now - bucket[0] > self.window:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True

    def remaining(self, key: int) -> int:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits.get(key)
            if not bucket:
                return self.limit
            while bucket and now - bucket[0] > self.window:
                bucket.popleft()
            return max(0, self.limit - len(bucket))


def check_input(text: str) -> str | None:
    """返回 None 表示通过，否则返回拒绝原因。"""
    lowered = text.lower()
    for term in BLOCKED_TERMS:
        if term.lower() in lowered:
            return "提问包含不适合处理的内容，请换一个与深度学习相关的问题。"
    return None


def sanitize_output(text: str) -> str:
    sanitized = text
    for term in BLOCKED_TERMS:
        sanitized = sanitized.replace(term, REDACTED)
    return sanitized
