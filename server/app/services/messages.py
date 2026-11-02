"""消息业务逻辑：入库、过滤、验证码提取、实时推送。"""

from __future__ import annotations

import sqlite3
from typing import Any

from ..utils import dumps, extract_verification_code, utcnow_iso

MESSAGE_SQL = """
SELECT m.*, s.slot_index, s.phone_number AS slot_number, d.device_name
FROM messages m
LEFT JOIN sim_cards s ON s.id = m.slot_id
LEFT JOIN devices d ON d.id = m.device_id
"""


def insert_message(
    conn: sqlite3.Connection,
    *,
    device_id: int,
    slot_id: int | None,
    kind: str,
    sender: str,
    content: str,
    received_at: str | None,
    raw: str | None,
) -> dict[str, Any]:
    now = utcnow_iso()
    code = extract_verification_code(content) if kind == "sms" else None
    cur = conn.execute(
        "INSERT INTO messages (device_id, slot_id, kind, sender, content, code,"
        " received_at, created_at, is_read, raw) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
        (
            device_id,
            slot_id,
            kind,
            sender[:64],
            content[:2000],
            code,
            received_at or now,
            now,
            raw,
        ),
    )
    conn.commit()
    row = conn.execute(MESSAGE_SQL + " WHERE m.id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


def list_messages(
    conn: sqlite3.Connection,
    *,
    allowed_slot_ids: set[int] | None,
    slot_id: int | None = None,
    kind: str | None = None,
    keyword: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    where: list[str] = []
    params: list[Any] = []
    if allowed_slot_ids is not None:
        if not allowed_slot_ids:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}
        placeholders = ",".join("?" * len(allowed_slot_ids))
        where.append(f"m.slot_id IN ({placeholders})")
        params.extend(sorted(allowed_slot_ids))
    if slot_id is not None:
        where.append("m.slot_id = ?")
        params.append(slot_id)
    if kind:
        where.append("m.kind = ?")
        params.append(kind)
    if keyword:
        where.append("(m.content LIKE ? OR m.sender LIKE ? OR m.code LIKE ?)")
        like = f"%{keyword}%"
        params.extend([like, like, like])
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    total = conn.execute(
        "SELECT COUNT(*) AS c FROM messages m" + clause, params
    ).fetchone()["c"]
    rows = conn.execute(
        MESSAGE_SQL + clause + " ORDER BY m.received_at DESC, m.id DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return {
        "items": [dict(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def mark_read(conn: sqlite3.Connection, message_id: int, is_read: bool) -> bool:
    cur = conn.execute(
        "UPDATE messages SET is_read = ? WHERE id = ?", (1 if is_read else 0, message_id)
    )
    conn.commit()
    return cur.rowcount > 0


def mark_all_read(conn: sqlite3.Connection, allowed_slot_ids: set[int] | None) -> int:
    if allowed_slot_ids is None:
        cur = conn.execute("UPDATE messages SET is_read = 1 WHERE is_read = 0")
    else:
        if not allowed_slot_ids:
            return 0
        placeholders = ",".join("?" * len(allowed_slot_ids))
        cur = conn.execute(
            f"UPDATE messages SET is_read = 1 WHERE is_read = 0"
            f" AND slot_id IN ({placeholders})",
            sorted(allowed_slot_ids),
        )
    conn.commit()
    return cur.rowcount


def message_to_client(row: dict[str, Any]) -> dict[str, Any]:
    """统一的客户端消息结构（Web / APK / EXE 三端共用）。"""
    return {
        "id": row["id"],
        "device_id": row["device_id"],
        "device_name": row.get("device_name") or "",
        "slot_id": row["slot_id"],
        "slot_index": row.get("slot_index"),
        "slot_number": row.get("slot_number") or "",
        "kind": row["kind"],
        "sender": row["sender"],
        "content": row["content"],
        "code": row["code"],
        "received_at": row["received_at"],
        "is_read": bool(row["is_read"]),
        "raw": row.get("raw"),
    }


def stats(conn: sqlite3.Connection, allowed_slot_ids: set[int] | None) -> dict[str, Any]:
    where = ""
    params: list[Any] = []
    if allowed_slot_ids is not None:
        if not allowed_slot_ids:
            return {"total": 0, "unread": 0, "today": 0, "codes": 0, "unread_calls": 0}
        placeholders = ",".join("?" * len(allowed_slot_ids))
        where = f" WHERE slot_id IN ({placeholders})"
        params = sorted(allowed_slot_ids)

    def scalar(sql: str, extra: list[Any] | None = None) -> int:
        merged = list(params) + list(extra or [])
        return int(conn.execute(sql, merged).fetchone()["c"])

    today_prefix = utcnow_iso()[:10] + "%"
    cond_today = " AND received_at LIKE ?" if where else " WHERE received_at LIKE ?"
    return {
        "total": scalar(f"SELECT COUNT(*) AS c FROM messages{where}"),
        "unread": scalar(f"SELECT COUNT(*) AS c FROM messages{where}{' AND' if where else ' WHERE'} is_read = 0"),
        "today": scalar(
            f"SELECT COUNT(*) AS c FROM messages{where}{cond_today}", [today_prefix]
        ),
        "codes": scalar(
            f"SELECT COUNT(*) AS c FROM messages{where}{' AND' if where else ' WHERE'} code IS NOT NULL"
        ),
        "unread_calls": scalar(
            f"SELECT COUNT(*) AS c FROM messages{where}{' AND' if where else ' WHERE'} kind = 'call' AND is_read = 0"
        ),
    }


def dumps_raw(raw: dict[str, Any]) -> str:
    return dumps(raw)
