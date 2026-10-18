"""WebSocket 实时通道：训练指标推送。

路径为 `/ws/train/{task_id}?token=<jwt>`，不属于 `/api` 前缀。
"""

from __future__ import annotations

import asyncio

import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models.user import User
from app.services import training

router = APIRouter()

TERMINAL_EVENTS = {"completed", "failed", "stopped"}
TERMINAL_STATUSES = {"success", "failed", "interrupted"}


def _authenticate(token: str | None) -> User | None:
    if not token:
        return None

    try:
        payload = decode_access_token(token)
    except jwt.InvalidTokenError:
        return None

    subject = payload.get("sub")
    if not subject or not str(subject).isdigit():
        return None

    session = SessionLocal()
    try:
        return session.get(User, int(subject))
    finally:
        session.close()


@router.websocket("/ws/train/{task_id}")
async def train_websocket(
    websocket: WebSocket,
    task_id: str,
    token: str | None = Query(default=None),
) -> None:
    await websocket.accept()

    user = _authenticate(token)
    if user is None:
        await websocket.send_json({"type": "failed", "reason": "认证失败"})
        await websocket.close(code=4401)
        return

    task = training.get_task(task_id)
    if task is None or task.user_id != user.id:
        await websocket.send_json({"type": "failed", "reason": "训练任务不存在"})
        await websocket.close(code=4404)
        return

    queue = training.subscribe(task)

    try:
        # 先回放已有事件：断线重连不丢数据
        for event in [*task.lifecycle, *task.history]:
            await websocket.send_json(event)

        if task.status in TERMINAL_STATUSES:
            return

        if task.status == "pending":
            training.start(task)

        async def send_events() -> None:
            while True:
                event = await queue.get()
                await websocket.send_json(event)
                if event["type"] in TERMINAL_EVENTS:
                    return

        async def receive_messages() -> None:
            while True:
                message = await websocket.receive_json()
                if isinstance(message, dict) and message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})

        tasks = {
            asyncio.create_task(send_events()),
            asyncio.create_task(receive_messages()),
        }
        done, pending = await asyncio.wait(
            tasks, return_when=asyncio.FIRST_COMPLETED
        )
        for item in pending:
            item.cancel()
        # 让取消真正生效，避免 "Task was destroyed but it is pending"
        await asyncio.gather(*pending, return_exceptions=True)

    except WebSocketDisconnect:
        pass
    finally:
        training.unsubscribe(task, queue)
        try:
            await websocket.close()
        except RuntimeError:
            pass
