from __future__ import annotations

import asyncio
import json
import logging
import os
from asyncio import wait_for

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from config.shutdown import register_connection, unregister_connection
from app.api.runtime import _subscribe_realtime_queue, _unsubscribe_realtime_queue
from app.core.database import SessionLocal, User

router = APIRouter(prefix="/api/v1")
legacy_router = APIRouter()
logger = logging.getLogger("realtime")


async def _realtime_socket(ws: WebSocket) -> None:
    auth = ws.headers.get("authorization", "")
    token = auth.replace("Bearer ", "").strip() if auth.startswith("Bearer ") else ""
    secret = os.getenv("JWT_SECRET_KEY")
    if not token or not secret:
        await ws.close(code=1008, reason="Authentication required")
        return
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except JWTError:
        await ws.close(code=1008, reason="Invalid token")
        return

    if payload.get("type") != "access":
        await ws.close(code=1008, reason="Access token required")
        return

    async with SessionLocal() as db:
        user = await db.get(User, payload.get("sub"))
        if user is None or not user.is_active:
            await ws.close(code=1008, reason="Invalid token")
            return

    org_id = payload.get("org_id")
    if not org_id:
        await ws.close(code=1008, reason="Organization scope required")
        return

    queue = _subscribe_realtime_queue(org_id)
    await ws.accept()
    register_connection(ws)
    try:
        while True:
            try:
                event = await wait_for(queue.get(), timeout=5)
            except asyncio.TimeoutError:
                await wait_for(ws.send_text("ping"), timeout=5)
                continue
            try:
                await wait_for(ws.send_text(json.dumps(event)), timeout=5)
            except asyncio.TimeoutError:
                logger.warning("slow client - event dropped")
                await ws.close(code=1013, reason="slow client")
                return
    except WebSocketDisconnect:
        return
    finally:
        _unsubscribe_realtime_queue(org_id, queue)
        unregister_connection(ws)


router.add_api_websocket_route("/ws", _realtime_socket)
legacy_router.add_api_websocket_route("/ws", _realtime_socket)