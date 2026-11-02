"""消息总览、详情、已读、验证码、统计。"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ..config import settings
from ..db import get_db
from ..realtime import manager
from ..schemas import MessageStatusUpdate, SendSmsRequest
from ..security import (
    accessible_slot_ids,
    ensure_slot_readable,
    ensure_slot_sendable,
    get_current_user,
)
from ..services import commands as command_service
from ..services import messages as message_service
from ..utils import audit, client_ip

router = APIRouter(prefix="/messages", tags=["messages"])


@router.get("")
def list_messages(
    slot_id: int | None = None,
    kind: str | None = None,
    keyword: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    allowed = accessible_slot_ids(conn, user)
    if slot_id is not None:
        ensure_slot_readable(conn, user, slot_id)
    result = message_service.list_messages(
        conn,
        allowed_slot_ids=allowed,
        slot_id=slot_id,
        kind=kind,
        keyword=keyword,
        limit=limit,
        offset=offset,
    )
    result["items"] = [
        message_service.message_to_client(m) for m in result["items"]
    ]
    result["version"] = settings.version
    return result


@router.get("/stats")
def message_stats(
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    allowed = accessible_slot_ids(conn, user)
    data = message_service.stats(conn, allowed)
    data["version"] = settings.version
    return data


@router.get("/codes")
def recent_codes(
    limit: int = Query(default=10, ge=1, le=50),
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """最近验证码，供一键复制。"""
    allowed = accessible_slot_ids(conn, user)
    where = ["code IS NOT NULL"]
    params: list[Any] = []
    if allowed is not None:
        if not allowed:
            return {"version": settings.version, "items": []}
        placeholders = ",".join("?" * len(allowed))
        where.append(f"slot_id IN ({placeholders})")
        params.extend(sorted(allowed))
    rows = conn.execute(
        "SELECT id, slot_id, sender, code, received_at FROM messages WHERE "
        + " AND ".join(where)
        + " ORDER BY received_at DESC LIMIT ?",
        [*params, limit],
    ).fetchall()
    return {"version": settings.version, "items": [dict(r) for r in rows]}


@router.get("/{message_id}")
def get_message(
    message_id: int,
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute(
        message_service.MESSAGE_SQL + " WHERE m.id = ?", (message_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "消息不存在")
    ensure_slot_readable(conn, user, row["slot_id"])
    return {"version": settings.version, "message": message_service.message_to_client(dict(row))}


@router.patch("/{message_id}")
def update_message(
    message_id: int,
    payload: MessageStatusUpdate,
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "消息不存在")
    ensure_slot_readable(conn, user, row["slot_id"])
    message_service.mark_read(conn, message_id, payload.is_read)
    return {"ok": True, "version": settings.version}


@router.post("/read-all")
def read_all(
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    allowed = accessible_slot_ids(conn, user)
    count = message_service.mark_all_read(conn, allowed)
    return {"ok": True, "updated": count, "version": settings.version}


# --------------------------------------------------------------------------- #
# 反向控制：Web 下发“发送短信”
# --------------------------------------------------------------------------- #
@router.post("/send", status_code=status.HTTP_201_CREATED)
async def send_sms(
    payload: SendSmsRequest,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    slot_id = payload.slot_id
    if slot_id is not None:
        ensure_slot_sendable(conn, user, slot_id)
        slot = conn.execute("SELECT * FROM sim_cards WHERE id = ?", (slot_id,)).fetchone()
        if slot is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "卡槽不存在")
        device_id = slot["device_id"]
    else:
        if user["role"] != "superadmin":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "普通成员必须指定卡槽")
        if payload.device_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "缺少 device_id 或 slot_id")
        device = conn.execute(
            "SELECT * FROM devices WHERE id = ?", (payload.device_id,)
        ).fetchone()
        if device is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "设备不存在")
        device_id = device["id"]
        first = conn.execute(
            "SELECT * FROM sim_cards WHERE device_id = ? ORDER BY slot_index LIMIT 1",
            (device_id,),
        ).fetchone()
        slot_id = first["id"] if first else None

    command = command_service.create_command(
        conn,
        device_id=device_id,
        slot_id=slot_id,
        target_number=payload.target_number,
        content=payload.content,
        created_by=user["id"],
    )
    await manager.broadcast_clients(
        "command_created",
        {"command": command, "version": settings.version},
    )
    pushed = await manager.push_command(
        device_id, command_service.build_payload(conn, command)
    )
    audit(
        conn,
        "send_sms",
        user_id=user["id"],
        target=payload.target_number,
        detail=f"slot={slot_id} pushed={pushed}",
        ip=client_ip(request),
    )
    return {
        "version": settings.version,
        "command": command,
        "pushed": pushed,
        "note": "" if pushed else "设备离线，指令已入库，设备上线后自动补发",
    }


@router.get("/commands/list")
def list_commands(
    limit: int = Query(default=30, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    items = command_service.list_commands(conn, limit=limit, status=status_filter)
    if user["role"] != "superadmin":
        allowed = accessible_slot_ids(conn, user) or set()
        items = [c for c in items if c["slot_id"] in allowed]
    return {"version": settings.version, "items": items}
