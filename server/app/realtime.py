"""WebSocket 实时推送中心。

- `/ws?token=...`  供 Web / APK / EXE 订阅实时消息
- `/ws/device?token=<Device_Token>` 供 ESP32 长连接接收反向控制与 OTA 指令
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: dict[int, set[WebSocket]] = {}     # user_id -> sockets
        self._devices: dict[int, set[WebSocket]] = {}     # device_id -> sockets
        self._lock = asyncio.Lock()

    # ---------------- 客户端（Web/APK/EXE） ---------------- #
    async def connect_client(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._clients.setdefault(user_id, set()).add(websocket)

    async def disconnect_client(self, user_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._clients.get(user_id)
            if conns:
                conns.discard(websocket)
                if not conns:
                    self._clients.pop(user_id, None)

    # ---------------- 设备（ESP32） ---------------- #
    async def connect_device(self, device_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._devices.setdefault(device_id, set()).add(websocket)

    async def disconnect_device(self, device_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._devices.get(device_id)
            if conns:
                conns.discard(websocket)
                if not conns:
                    self._devices.pop(device_id, None)

    # ---------------- 广播 ---------------- #
    async def _send_many(self, sockets: set[WebSocket], payload: str) -> None:
        dead: list[WebSocket] = []
        for ws in list(sockets):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            sockets.discard(ws)

    async def broadcast_clients(self, event: str, data: dict[str, Any]) -> None:
        payload = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        async with self._lock:
            targets = [set(s) for s in self._clients.values()]
        for sockets in targets:
            await self._send_many(sockets, payload)

    async def send_to_clients(
        self, user_ids: list[int], event: str, data: dict[str, Any]
    ) -> None:
        payload = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        async with self._lock:
            targets = [set(self._clients.get(uid, set())) for uid in user_ids]
        for sockets in targets:
            await self._send_many(sockets, payload)

    async def push_command(self, device_id: int, command: dict[str, Any]) -> bool:
        """向指定设备下发指令，返回是否有在线连接接收。"""
        payload = json.dumps({"event": "command", "data": command}, ensure_ascii=False)
        async with self._lock:
            sockets = set(self._devices.get(device_id, set()))
        if not sockets:
            return False
        await self._send_many(sockets, payload)
        return True

    def device_online_sockets(self, device_id: int) -> int:
        return len(self._devices.get(device_id, set()))

    def online_device_ids(self) -> set[int]:
        return set(self._devices.keys())

    def online_user_ids(self) -> set[int]:
        return set(self._clients.keys())


manager = ConnectionManager()
