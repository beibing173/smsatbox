"""设备与卡槽业务逻辑。"""

from __future__ import annotations

import sqlite3
from typing import Any

from ..config import settings
from ..utils import generate_device_token, parse_iso, utcnow_iso


def device_public(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    last_seen = parse_iso(data.get("last_seen_at"))
    online = False
    if last_seen is not None:
        delta = (parse_iso(utcnow_iso()) - last_seen).total_seconds()
        online = delta <= settings.device_offline_seconds
    data["online"] = bool(data.get("online")) or online
    data["version"] = settings.version
    data.pop("device_token", None)
    return data


def slots_for_device(conn: sqlite3.Connection, device_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM sim_cards WHERE device_id = ? ORDER BY slot_index",
        (device_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def device_detail(conn: sqlite3.Connection, device_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    if row is None:
        return None
    detail = device_public(row)
    detail["slots"] = slots_for_device(conn, device_id)
    return detail


def create_device(
    conn: sqlite3.Connection,
    *,
    device_name: str,
    hardware_model: str,
    slot_count: int,
    remark: str,
) -> dict[str, Any]:
    token = generate_device_token()
    now = utcnow_iso()
    cur = conn.execute(
        "INSERT INTO devices (device_token, device_name, hardware_model, firmware_version,"
        " net_mode, online, remark, created_at)"
        " VALUES (?, ?, ?, '1.0.0', 'wifi', 0, ?, ?)",
        (token, device_name or "未命名设备", hardware_model, remark, now),
    )
    device_id = int(cur.lastrowid)
    for slot in range(1, slot_count + 1):
        conn.execute(
            "INSERT INTO sim_cards (device_id, slot_index, plan_name, created_at)"
            " VALUES (?, ?, '默认套餐', ?)",
            (device_id, slot, now),
        )
    conn.commit()
    detail = device_detail(conn, device_id) or {}
    detail["device_token"] = token  # 仅创建时返回一次
    return detail


def get_or_create_slot(
    conn: sqlite3.Connection, device_id: int, slot_index: int
) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM sim_cards WHERE device_id = ? AND slot_index = ?",
        (device_id, slot_index),
    ).fetchone()
    if row is not None:
        return row
    now = utcnow_iso()
    conn.execute(
        "INSERT INTO sim_cards (device_id, slot_index, plan_name, created_at)"
        " VALUES (?, ?, '默认套餐', ?)",
        (device_id, slot_index, now),
    )
    conn.commit()
    return conn.execute(
        "SELECT * FROM sim_cards WHERE device_id = ? AND slot_index = ?",
        (device_id, slot_index),
    ).fetchone()


def touch_device(
    conn: sqlite3.Connection,
    device_id: int,
    *,
    firmware_version: str | None = None,
    server_version: str | None = None,
    local_ip: str | None = None,
    wifi_rssi: int | None = None,
    net_mode: str | None = None,
) -> None:
    fields: list[str] = ["online = 1", "last_seen_at = ?"]
    params: list[Any] = [utcnow_iso()]
    if firmware_version:
        fields.append("firmware_version = ?")
        params.append(firmware_version)
    if server_version:
        fields.append("server_version = ?")
        params.append(server_version)
    if local_ip:
        fields.append("local_ip = ?")
        params.append(local_ip)
    if wifi_rssi is not None:
        fields.append("wifi_rssi = ?")
        params.append(int(wifi_rssi))
    if net_mode:
        fields.append("net_mode = ?")
        params.append(net_mode)
    params.append(device_id)
    conn.execute(f"UPDATE devices SET {', '.join(fields)} WHERE id = ?", params)
    conn.commit()


def mark_offline(conn: sqlite3.Connection, device_id: int) -> None:
    conn.execute("UPDATE devices SET online = 0 WHERE id = ?", (device_id,))
    conn.commit()


def slot_owner_user_ids(conn: sqlite3.Connection, slot_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT user_id FROM permissions WHERE slot_id = ? AND can_read = 1", (slot_id,)
    ).fetchall()
    return [row["user_id"] for row in rows]
