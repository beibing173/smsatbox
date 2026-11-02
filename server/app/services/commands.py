"""反向控制：发送短信指令的创建、下发与状态回写。"""

from __future__ import annotations

import sqlite3
from typing import Any

from ..utils import utcnow_iso


def create_command(
    conn: sqlite3.Connection,
    *,
    device_id: int,
    slot_id: int | None,
    target_number: str,
    content: str,
    created_by: int,
) -> dict[str, Any]:
    now = utcnow_iso()
    cur = conn.execute(
        "INSERT INTO sms_commands (device_id, slot_id, target_number, content, status,"
        " created_by, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)",
        (device_id, slot_id, target_number, content, created_by, now, now),
    )
    conn.commit()
    return dict(
        conn.execute("SELECT * FROM sms_commands WHERE id = ?", (cur.lastrowid,)).fetchone()
    )


def build_payload(
    conn: sqlite3.Connection, command: dict[str, Any]
) -> dict[str, Any]:
    """下发给 ESP32 的指令结构。"""
    slot_index = 1
    if command.get("slot_id"):
        row = conn.execute(
            "SELECT slot_index FROM sim_cards WHERE id = ?", (command["slot_id"],)
        ).fetchone()
        if row:
            slot_index = row["slot_index"]
    return {
        "type": "send_sms",
        "command_id": command["id"],
        "slot_index": slot_index,
        "target_number": command["target_number"],
        "content": command["content"],
        "version": "1.0.0",
    }


def set_status(
    conn: sqlite3.Connection,
    command_id: int,
    status: str,
    error: str = "",
) -> dict[str, Any] | None:
    conn.execute(
        "UPDATE sms_commands SET status = ?, error = ?, updated_at = ? WHERE id = ?",
        (status, error[:500], utcnow_iso(), command_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM sms_commands WHERE id = ?", (command_id,)).fetchone()
    return dict(row) if row else None


def list_commands(
    conn: sqlite3.Connection, limit: int = 50, status: str | None = None
) -> list[dict[str, Any]]:
    if status:
        rows = conn.execute(
            "SELECT * FROM sms_commands WHERE status = ? ORDER BY id DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sms_commands ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def pending_for_device(conn: sqlite3.Connection, device_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM sms_commands WHERE device_id = ? AND status = 'pending'"
        " ORDER BY id ASC",
        (device_id,),
    ).fetchall()
    return [dict(row) for row in rows]
