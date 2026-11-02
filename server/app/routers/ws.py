"""WebSocket 路由。

- `/api/v1/ws?token=<JWT 或客户端令牌>`  客户端订阅实时事件
- `/api/v1/ws/device?token=<Device_Token>`  ESP32 长连接接收指令
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import settings
from ..db import connect
from ..realtime import manager
from ..security import decode_access_token, get_device_by_token, token_fingerprint
from ..services import commands as command_service
from ..services import devices as device_service
from ..utils import utcnow_iso

router = APIRouter(tags=["websocket"])


def _auth_user(conn: sqlite3.Connection, token: str) -> dict[str, Any] | None:
    if not token:
        return None
    row = None
    if token.count(".") == 2:
        try:
            payload = decode_access_token(token)
        except Exception:
            return None
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (int(payload.get("sub", 0)),)
        ).fetchone()
    else:
        found = conn.execute(
            "SELECT * FROM user_tokens WHERE token_hash = ?", (token_fingerprint(token),)
        ).fetchone()
        if found:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (found["user_id"],)
            ).fetchone()
    if row is None or not row["is_active"]:
        return None
    return dict(row)


@router.websocket("/ws")
async def client_ws(websocket: WebSocket, token: str = ""):
    conn = connect()
    try:
        user = _auth_user(conn, token)
        if user is None:
            await websocket.close(code=4401, reason="unauthorized")
            return

        await manager.connect_client(user["id"], websocket)
        await websocket.send_text(
            json.dumps(
                {
                    "event": "connected",
                    "data": {
                        "user_id": user["id"],
                        "role": user["role"],
                        "version": settings.version,
                    },
                },
                ensure_ascii=False,
            )
        )
        try:
            while True:
                message = await websocket.receive_text()
                if message.strip() in {"ping", '{"type":"ping"}'}:
                    await websocket.send_text(
                        json.dumps({"event": "pong", "data": {"ts": utcnow_iso()}})
                    )
        except WebSocketDisconnect:
            pass
        finally:
            await manager.disconnect_client(user["id"], websocket)
    finally:
        conn.close()


@router.websocket("/ws/device")
async def device_ws(websocket: WebSocket, token: str = ""):
    conn = connect()
    device_id: int | None = None
    try:
        device = get_device_by_token(conn, token) if token else None
        if device is None:
            await websocket.close(code=4401, reason="unauthorized")
            return
        device_id = device["id"]

        device_service.touch_device(conn, device_id)
        await manager.connect_device(device_id, websocket)
        await manager.broadcast_clients(
            "device_status",
            {
                "device": device_service.device_detail(conn, device_id),
                "version": settings.version,
            },
        )
        await websocket.send_text(
            json.dumps(
                {
                    "event": "connected",
                    "data": {
                        "device_id": device_id,
                        "server_version": settings.version,
                    },
                },
                ensure_ascii=False,
            )
        )
        # 上线即补发积压指令
        for command in command_service.pending_for_device(conn, device_id):
            await websocket.send_text(
                json.dumps(
                    {
                        "event": "command",
                        "data": command_service.build_payload(conn, command),
                    },
                    ensure_ascii=False,
                )
            )

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    payload = json.loads(raw)
                except ValueError:
                    continue
                event = payload.get("event") or payload.get("type")
                if event in {"ping", "heartbeat"}:
                    device_service.touch_device(conn, device_id)
                    await websocket.send_text(
                        json.dumps(
                            {
                                "event": "pong",
                                "data": {
                                    "ts": utcnow_iso(),
                                    "server_version": settings.version,
                                },
                            }
                        )
                    )
                elif event == "result":
                    data = payload.get("data") or {}
                    command_id = data.get("command_id")
                    if command_id:
                        command_service.set_status(
                            conn,
                            int(command_id),
                            data.get("status", "failed"),
                            data.get("error", ""),
                        )
                        await manager.broadcast_clients(
                            "command_result",
                            {
                                "command_id": command_id,
                                "status": data.get("status"),
                                "version": settings.version,
                            },
                        )
        except WebSocketDisconnect:
            pass
    finally:
        if device_id is not None:
            await manager.disconnect_device(device_id, websocket)
            try:
                device_service.mark_offline(conn, device_id)
                await manager.broadcast_clients(
                    "device_status",
                    {
                        "device": device_service.device_detail(conn, device_id),
                        "version": settings.version,
                    },
                )
            except Exception:
                pass
        conn.close()
