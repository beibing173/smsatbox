"""系统信息、健康检查、全局配置。"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends

from ..config import settings
from ..db import get_db
from ..realtime import manager
from ..security import get_current_user, get_superadmin
from ..utils import utcnow_iso

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    return {"ok": True, "product": settings.app_name, "version": settings.version}


@router.get("/version")
def version():
    return {
        "product": settings.app_name,
        "version": settings.version,
        "api_prefix": settings.api_prefix,
        "server_image": settings.server_image,
        "server_upgrade_enabled": settings.server_upgrade_enabled,
        "timestamp": utcnow_iso(),
    }


@router.get("/system/overview")
def overview(
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    devices_total = conn.execute("SELECT COUNT(*) AS c FROM devices").fetchone()["c"]
    devices_online = len(manager.online_device_ids())
    slots_total = conn.execute("SELECT COUNT(*) AS c FROM sim_cards").fetchone()["c"]
    msgs = conn.execute("SELECT COUNT(*) AS c FROM messages").fetchone()["c"]
    unread = conn.execute(
        "SELECT COUNT(*) AS c FROM messages WHERE is_read = 0"
    ).fetchone()["c"]
    users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    if user["role"] != "superadmin":
        allowed = [
            r["slot_id"]
            for r in conn.execute(
                "SELECT slot_id FROM permissions WHERE user_id = ? AND can_read = 1",
                (user["id"],),
            ).fetchall()
        ]
        if allowed:
            ph = ",".join("?" * len(allowed))
            msgs = conn.execute(
                f"SELECT COUNT(*) AS c FROM messages WHERE slot_id IN ({ph})", allowed
            ).fetchone()["c"]
            unread = conn.execute(
                f"SELECT COUNT(*) AS c FROM messages WHERE is_read = 0 AND slot_id IN ({ph})",
                allowed,
            ).fetchone()["c"]
        else:
            msgs = unread = 0
        slots_total = len(allowed)
    return {
        "version": settings.version,
        "stats": {
            "devices_total": devices_total,
            "devices_online": devices_online,
            "slots_total": slots_total,
            "messages_total": msgs,
            "messages_unread": unread,
            "users_total": users if user["role"] == "superadmin" else None,
            "ws_clients": len(manager.online_user_ids()),
        },
    }


@router.get("/audit")
def list_audit(
    limit: int = 100,
    admin: dict[str, Any] = Depends(get_superadmin),
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = conn.execute(
        "SELECT a.*, u.username FROM audit_logs a LEFT JOIN users u ON u.id = a.user_id"
        " ORDER BY a.id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return {"version": settings.version, "items": [dict(r) for r in rows]}
