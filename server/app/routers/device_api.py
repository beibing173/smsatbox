"""设备侧 API：ESP32 专用（仅凭 Device_Token 鉴权）。

路由前缀 /api/v1/device
- POST /report        设备心跳与状态上报
- POST /messages      上报短信 / 来电
- GET  /commands      拉取待执行指令（离线补发）
- POST /commands/{id} 回写指令执行结果
- GET  /ota           拉取待执行的 OTA 任务
- POST /ota/{id}      OTA 进度回写
- POST /server-upgrade 请求 Server 拉取最新镜像并重启
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..config import settings
from ..db import get_db
from ..realtime import manager
from ..schemas import (
    CommandResult,
    DeviceReport,
    InboundMessage,
    OtaUpdate,
    ServerUpgradeRequest,
)
from ..security import device_auth
from ..services import commands as command_service
from ..services import devices as device_service
from ..services import messages as message_service
from ..utils import audit, client_ip, dumps, utcnow_iso

router = APIRouter(prefix="/device", tags=["device"])


def _slot_payload(conn: sqlite3.Connection, device_id: int) -> list[dict[str, Any]]:
    return device_service.slots_for_device(conn, device_id)


@router.get("/bootstrap")
def bootstrap(
    device: sqlite3.Row = Depends(device_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    """设备开机首包：拿到自己的卡槽、版本要求与待办。"""
    device_service.touch_device(conn, device["id"])
    slots = _slot_payload(conn, device["id"])
    pending_ota = conn.execute(
        "SELECT * FROM ota_tasks WHERE device_id = ? AND status = 'pending'"
        " ORDER BY id ASC LIMIT 1",
        (device["id"],),
    ).fetchone()
    return {
        "version": settings.version,
        "server_version": settings.version,
        "device": device_service.device_public(device),
        "slots": slots,
        "pending_ota": dict(pending_ota) if pending_ota else None,
        "poll_interval": 15,
    }


@router.post("/report")
async def report(
    payload: DeviceReport,
    request: Request,
    device: sqlite3.Row = Depends(device_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    device_service.touch_device(
        conn,
        device["id"],
        firmware_version=payload.firmware_version,
        server_version=payload.server_version,
        local_ip=payload.local_ip,
        wifi_rssi=payload.wifi_rssi,
        net_mode=payload.net_mode,
    )
    for slot_report in payload.slots:
        slot = device_service.get_or_create_slot(conn, device["id"], slot_report.slot_index)

        # 基础字段（信号 / 号码 / 运营商）
        fields = ["signal_dbm = ?"]
        params: list[Any] = [
            slot_report.signal_dbm if slot_report.signal_dbm is not None else 99
        ]
        if slot_report.phone_number:
            fields.append("phone_number = ?")
            params.append(slot_report.phone_number)
        if slot_report.carrier:
            fields.append("carrier = ?")
            params.append(slot_report.carrier)

        # 模组详细状态以 JSON 快照形式整块存，便于原样回传前端
        detail = slot_report.model_dump(exclude_none=True)
        if detail:
            fields.append("module_json = ?")
            params.append(dumps(detail))

        params.append(slot["id"])
        conn.execute(f"UPDATE sim_cards SET {', '.join(fields)} WHERE id = ?", params)

    # 整台设备的模组列表快照（前端设备详情用）
    if payload.slots:
        snapshot = [s.model_dump(exclude_none=True) for s in payload.slots]
        conn.execute(
            "UPDATE devices SET modules_json = ? WHERE id = ?",
            (dumps(snapshot), device["id"]),
        )

    conn.commit()
    await manager.broadcast_clients(
        "device_status",
        {"device": device_service.device_detail(conn, device["id"]), "version": settings.version},
    )
    return {"ok": True, "version": settings.version, "server_version": settings.version}


@router.post("/messages", status_code=status.HTTP_201_CREATED)
async def inbound_message(
    payload: InboundMessage,
    request: Request,
    device: sqlite3.Row = Depends(device_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    slot = device_service.get_or_create_slot(conn, device["id"], payload.slot_index)
    raw = dumps(payload.model_dump()) if payload.raw else payload.raw
    row = message_service.insert_message(
        conn,
        device_id=device["id"],
        slot_id=slot["id"],
        kind=payload.kind,
        sender=payload.sender,
        content=payload.content,
        received_at=payload.received_at,
        raw=raw,
    )
    device_service.touch_device(conn, device["id"])
    client_msg = message_service.message_to_client(row)
    await manager.broadcast_clients(
        "new_message", {"message": client_msg, "version": settings.version}
    )
    return {
        "ok": True,
        "version": settings.version,
        "message_id": row["id"],
        "code": row["code"],
    }


@router.get("/commands")
def poll_commands(
    device: sqlite3.Row = Depends(device_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    """HTTP 轮询兜底通道（WebSocket 断开时设备也能拿到指令）。"""
    pending = command_service.pending_for_device(conn, device["id"])
    device_service.touch_device(conn, device["id"])
    return {
        "version": settings.version,
        "items": [command_service.build_payload(conn, c) for c in pending],
    }


@router.post("/commands/{command_id}")
async def command_result(
    command_id: int,
    payload: CommandResult,
    device: sqlite3.Row = Depends(device_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute(
        "SELECT * FROM sms_commands WHERE id = ? AND device_id = ?",
        (command_id, device["id"]),
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "指令不存在")
    updated = command_service.set_status(
        conn, command_id, payload.status, payload.error
    )
    await manager.broadcast_clients(
        "command_result",
        {"command": updated, "version": settings.version},
    )
    return {"ok": True, "version": settings.version}


# --------------------------------------------------------------------------- #
# OTA
# --------------------------------------------------------------------------- #
@router.get("/ota")
def poll_ota(
    device: sqlite3.Row = Depends(device_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute(
        "SELECT * FROM ota_tasks WHERE device_id = ? AND status IN ('pending','downloading')"
        " ORDER BY id ASC LIMIT 1",
        (device["id"],),
    ).fetchone()
    if row is None:
        return {"version": settings.version, "task": None}
    task = dict(row)
    task["url"] = f"/api/v1/ota/download/{task['filename']}"
    return {"version": settings.version, "task": task}


@router.post("/ota/{task_id}")
async def ota_progress(
    task_id: int,
    payload: OtaUpdate,
    device: sqlite3.Row = Depends(device_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute(
        "SELECT * FROM ota_tasks WHERE id = ? AND device_id = ?",
        (task_id, device["id"]),
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "OTA 任务不存在")
    conn.execute(
        "UPDATE ota_tasks SET status = ?, error = ?, updated_at = ? WHERE id = ?",
        (payload.status, payload.error[:500], utcnow_iso(), task_id),
    )
    if payload.status == "success":
        conn.execute(
            "UPDATE devices SET firmware_version = ? WHERE id = ?",
            (row["version"], device["id"]),
        )
    conn.commit()
    await manager.broadcast_clients(
        "ota_update",
        {
            "task_id": task_id,
            "status": payload.status,
            "version": settings.version,
        },
    )
    return {"ok": True, "version": settings.version}


# --------------------------------------------------------------------------- #
# 协同升级：ESP32 触发 Server 升级
# --------------------------------------------------------------------------- #
@router.post("/server-upgrade")
async def trigger_server_upgrade(
    payload: ServerUpgradeRequest,
    request: Request,
    device: sqlite3.Row = Depends(device_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    """设备发现 Server 版本落后时，可请求 Server 拉取 Docker Hub 最新镜像并重启容器。

    出于安全考虑，默认关闭；需在服务端设置 SERVER_UPGRADE_ENABLED=true，
    且 SERVER_UPGRADE_COMMAND 指向一个受控的升级脚本。
    """
    audit(
        conn,
        "server_upgrade_request",
        target=f"device:{device['id']}",
        detail=f"target={payload.target_version} reason={payload.reason}",
        ip=client_ip(request),
    )
    accepted = bool(
        settings.server_upgrade_enabled and settings.server_upgrade_command
    )
    result: dict[str, Any] = {
        "version": settings.version,
        "accepted": accepted,
        "current_version": settings.version,
        "target_version": payload.target_version or settings.version,
        "image": settings.server_image,
    }
    if not accepted:
        result["message"] = (
            "服务端未启用自动升级（SERVER_UPGRADE_ENABLED=false），"
            "请管理员手动执行 docker compose pull && up -d"
        )
        return result

    import asyncio

    try:
        in_container = settings.server_upgrade_command
        proc = await asyncio.create_subprocess_shell(
            in_container,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        result["accepted"] = proc.returncode == 0
        result["output"] = out.decode("utf-8", errors="replace")[-2000:]
    except Exception as exc:  # noqa: BLE001
        result["accepted"] = False
        result["message"] = f"升级命令执行失败：{exc}"
    await manager.broadcast_clients("server_upgrade", result)
    return result
