"""教学实验室的 WebSocket 实时通道：`/ws/lab/{task_id}?token=<jwt>`。"""

from __future__ import annotations

import asyncio

import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models.user import User
from app.services import lab

router = APIRouter()

TERMINAL_EVENTS = {"completed", "failed", "stopped"}
TERMINAL_STATUSES = {"completed", "failed", "stopped"}


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


@router.websocket("/ws/lab/{task_id}")
async def lab_websocket(
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

    task = lab.get_task(task_id)
    if task is None or task.user_id != user.id:
        await websocket.send_json({"type": "failed", "reason": "训练任务不存在"})
        await websocket.close(code=4404)
        return

    queue = lab.subscribe(task)

    try:
        for event in task.lifecycle:
            await websocket.send_json(event)
        for event in task.history:
            await websocket.send_json(event)
        for key in ("weights", "boundary"):
            if key in task.latest:
                await websocket.send_json(task.latest[key])

        if task.status in TERMINAL_STATUSES:
            return

        if task.status == "idle":
            lab.start(task)

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
        _, pending = await asyncio.wait(
            tasks, return_when=asyncio.FIRST_COMPLETED
        )
        for item in pending:
            item.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    except WebSocketDisconnect:
        pass
    finally:
        lab.unsubscribe(task, queue)
        try:
            await websocket.close()
        except RuntimeError:
            pass
