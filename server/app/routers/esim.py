"""eUICC / eSIM 管理 API。

设计要点
- 设备侧（Device_Token 鉴权）：上报卡片状态、拉取操作指令、回写执行结果
- 用户侧（JWT 鉴权）：查看卡片与 profile、下发切卡/删卡/改名、开关功能

为什么指令要排队而不是直接下发？
    eUICC 的切卡会触发 REFRESH 让模组重新读卡，执行期间可能短暂断网。
    用「指令表 + 设备轮询」的方式，能保证：
      1) 断网时指令不丢，设备恢复后自动补执行
      2) 同一张卡同时只有一个操作在跑，避免 APDU 会话冲突
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..config import settings
from ..db import get_db
from ..realtime import manager
from ..schemas import (
    EsimCommandCreate,
    EsimCommandResult,
    EuiccReport,
    EuiccToggle,
)
from ..security import device_auth, get_current_user
from ..utils import audit, dumps, utcnow_iso

router = APIRouter(tags=["esim"])


# --------------------------------------------------------------------------- #
# 内部工具
# --------------------------------------------------------------------------- #
def _euicc_public(row: sqlite3.Row, profiles: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "device_id": row["device_id"],
        "slot_index": row["slot_index"],
        "eid": row["eid"] or "",
        "installed_apps": row["installed_apps"] or 0,
        "free_nonvolatile": row["free_nonvolatile"]
        if row["free_nonvolatile"] is not None
        else -1,
        "free_volatile": row["free_volatile"]
        if row["free_volatile"] is not None
        else -1,
        "user_enabled": bool(row["user_enabled"]),
        "probed_at": row["probed_at"] or "",
        "updated_at": row["updated_at"],
        "profiles": profiles,
        "version": settings.version,
    }


def _profiles_for(conn: sqlite3.Connection, euicc_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM euicc_profile WHERE euicc_id = ? ORDER BY state DESC, id ASC",
        (euicc_id,),
    ).fetchall()
    return [
        {
            "iccid": r["iccid"],
            "state": r["state"],
            "nickname": r["nickname"],
            "provider": r["provider"],
            "profile_name": r["profile_name"],
        }
        for r in rows
    ]


def _visible_device_ids(conn: sqlite3.Connection, user: dict[str, Any]) -> list[int]:
    """当前用户能看到的设备 id。超级管理员看全部，普通成员看被授权的。"""
    if user["role"] == "superadmin":
        rows = conn.execute("SELECT id FROM devices ORDER BY id").fetchall()
        return [r["id"] for r in rows]

    rows = conn.execute(
        """
        SELECT DISTINCT sc.device_id AS id
        FROM permissions p
        JOIN sim_cards sc ON sc.id = p.slot_id
        WHERE p.user_id = ?
        """,
        (user["id"],),
    ).fetchall()
    return [r["id"] for r in rows]


# =========================================================================== #
# 设备侧 API
# =========================================================================== #
@router.post("/device/esim/report")
def device_report_euicc(
    payload: EuiccReport,
    request: Request,
    device: sqlite3.Row = Depends(device_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    """设备上报某卡槽的 eUICC 状态与 profile 列表。"""
    now = utcnow_iso()
    device_id = device["id"]

    if not payload.present:
        # 未检测到 eUICC：清掉该槽记录（保留用户开关偏好）
        conn.execute(
            "DELETE FROM euicc WHERE device_id = ? AND slot_index = ?",
            (device_id, payload.slot_index),
        )
        conn.commit()
        return {"ok": True, "present": False, "version": settings.version}

    row = conn.execute(
        "SELECT * FROM euicc WHERE device_id = ? AND slot_index = ?",
        (device_id, payload.slot_index),
    ).fetchone()

    if row is None:
        cur = conn.execute(
            """
            INSERT INTO euicc (device_id, slot_index, eid, installed_apps,
                               free_nonvolatile, free_volatile, user_enabled,
                               probed_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                device_id,
                payload.slot_index,
                payload.eid,
                payload.installed_apps,
                payload.free_nonvolatile,
                payload.free_volatile,
                1 if payload.user_enabled else 0,
                now,
                now,
            ),
        )
        euicc_id = int(cur.lastrowid or 0)
    else:
        euicc_id = int(row["id"])
        conn.execute(
            """
            UPDATE euicc
               SET eid = ?, installed_apps = ?, free_nonvolatile = ?,
                   free_volatile = ?, probed_at = ?, updated_at = ?
             WHERE id = ?
            """,
            (
                payload.eid,
                payload.installed_apps,
                payload.free_nonvolatile,
                payload.free_volatile,
                now,
                now,
                euicc_id,
            ),
        )

    # profile 全量同步：先删后插，保证与服务端一致
    conn.execute("DELETE FROM euicc_profile WHERE euicc_id = ?", (euicc_id,))
    for p in payload.profiles:
        if not p.iccid:
            continue
        conn.execute(
            """
            INSERT INTO euicc_profile
                (euicc_id, iccid, state, nickname, provider, profile_name, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                euicc_id,
                p.iccid,
                p.state,
                p.nickname,
                p.provider,
                p.profile_name,
                now,
            ),
        )
    conn.commit()

    return {"ok": True, "euicc_id": euicc_id, "version": settings.version}


@router.get("/device/esim/commands")
def device_poll_esim_commands(
    device: sqlite3.Row = Depends(device_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    """设备拉取待执行的 eSIM 指令（一次最多 1 条，避免并发改卡）。"""
    row = conn.execute(
        """
        SELECT c.*, d.device_name
          FROM esim_command c
          JOIN devices d ON d.id = c.device_id
         WHERE c.device_id = ? AND c.status = 'pending'
         ORDER BY c.id ASC
         LIMIT 1
        """,
        (device["id"],),
    ).fetchone()

    if row is None:
        return {"items": [], "version": settings.version}

    return {
        "items": [
            {
                "id": row["id"],
                "slot_index": row["slot_index"],
                "operation": row["command_type"],
                "iccid": row["iccid"],
                "nickname": row["nickname"],
            }
        ],
        "version": settings.version,
    }


@router.post("/device/esim/commands/{command_id}")
async def device_report_esim_result(
    command_id: int,
    payload: EsimCommandResult,
    request: Request,
    device: sqlite3.Row = Depends(device_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute(
        "SELECT * FROM esim_command WHERE id = ? AND device_id = ?",
        (command_id, device["id"]),
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "指令不存在")

    conn.execute(
        "UPDATE esim_command SET status = ?, error = ?, finished_at = ? WHERE id = ?",
        (payload.status, payload.error, utcnow_iso(), command_id),
    )
    conn.commit()

    await manager.broadcast_clients(
        "esim_command_result",
        {
            "command_id": command_id,
            "status": payload.status,
            "error": payload.error,
            "version": settings.version,
        },
    )
    return {"ok": True, "version": settings.version}


# =========================================================================== #
# 用户侧 API
# =========================================================================== #
@router.get("/esim")
def list_euicc(
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """列出当前用户可见的所有 eUICC 卡片及其 profile。"""
    ids = _visible_device_ids(conn, user)
    if not ids:
        return {"items": [], "version": settings.version}

    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        SELECT e.*, d.device_name, d.online
          FROM euicc e
          JOIN devices d ON d.id = e.device_id
         WHERE e.device_id IN ({placeholders})
         ORDER BY e.device_id, e.slot_index
        """,
        ids,
    ).fetchall()

    items = []
    for r in rows:
        item = _euicc_public(r, _profiles_for(conn, r["id"]))
        item["device_name"] = r["device_name"]
        item["online"] = bool(r["online"])
        items.append(item)

    return {"items": items, "version": settings.version}


@router.post("/esim/command", status_code=status.HTTP_201_CREATED)
def create_esim_command(
    payload: EsimCommandCreate,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """下发一条 eSIM 操作（切卡/删卡/改名/刷新）。"""
    visible = _visible_device_ids(conn, user)
    if payload.device_id not in visible:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作该设备")

    device = conn.execute(
        "SELECT * FROM devices WHERE id = ?", (payload.device_id,)
    ).fetchone()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "设备不存在")

    # 同一张卡不允许有重叠操作（APDU 会话必须串行）
    busy = conn.execute(
        """
        SELECT id FROM esim_command
         WHERE device_id = ? AND slot_index = ? AND status = 'pending'
        """,
        (payload.device_id, payload.slot_index),
    ).fetchone()
    if busy is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "该卡槽已有 eSIM 操作在排队")

    if payload.operation in ("enable", "disable", "delete") and len(payload.iccid) < 19:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "需要完整的 19/20 位 ICCID")
    if payload.operation == "nickname" and len(payload.nickname) > 64:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "名称过长（最多 64 字符）")

    cur = conn.execute(
        """
        INSERT INTO esim_command
            (device_id, slot_index, command_type, iccid, nickname,
             status, error, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, 'pending', '', ?, ?)
        """,
        (
            payload.device_id,
            payload.slot_index,
            payload.operation,
            payload.iccid,
            payload.nickname,
            user["id"],
            utcnow_iso(),
        ),
    )
    command_id = int(cur.lastrowid or 0)
    conn.commit()

    audit(
        conn,
        "esim_command",
        user_id=user["id"],
        target=str(payload.device_id),
        detail=f"{payload.operation} iccid={payload.iccid}",
    )

    return {
        "ok": True,
        "command_id": command_id,
        "status": "pending",
        "version": settings.version,
    }


@router.get("/esim/commands")
def list_esim_commands(
    device_id: int | None = None,
    limit: int = 20,
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """最近 eSIM 指令历史。"""
    visible = _visible_device_ids(conn, user)
    if not visible:
        return {"items": [], "version": settings.version}

    limit = max(1, min(limit, 100))
    placeholders = ",".join("?" for _ in visible)
    sql = f"""
        SELECT c.*, d.device_name
          FROM esim_command c
          JOIN devices d ON d.id = c.device_id
         WHERE c.device_id IN ({placeholders})
    """
    args: list[Any] = list(visible)
    if device_id is not None:
        sql += " AND c.device_id = ?"
        args.append(device_id)
    sql += " ORDER BY c.id DESC LIMIT ?"
    args.append(limit)

    rows = conn.execute(sql, args).fetchall()
    items = [
        {
            "id": r["id"],
            "device_id": r["device_id"],
            "device_name": r["device_name"],
            "slot_index": r["slot_index"],
            "operation": r["command_type"],
            "iccid": r["iccid"],
            "nickname": r["nickname"],
            "status": r["status"],
            "error": r["error"],
            "created_at": r["created_at"],
            "finished_at": r["finished_at"] or "",
        }
        for r in rows
    ]
    return {"items": items, "version": settings.version}


@router.patch("/esim/{euicc_id}/toggle")
def toggle_euicc(
    euicc_id: int,
    payload: EuiccToggle,
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """手动开关某张 eUICC 的管理功能。"""
    row = conn.execute("SELECT * FROM euicc WHERE id = ?", (euicc_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "eUICC 不存在")

    visible = _visible_device_ids(conn, user)
    if row["device_id"] not in visible:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作该设备")

    conn.execute(
        "UPDATE euicc SET user_enabled = ?, updated_at = ? WHERE id = ?",
        (1 if payload.user_enabled else 0, utcnow_iso(), euicc_id),
    )
    conn.commit()

    audit(
        conn,
        "esim_toggle",
        user_id=user["id"],
        target=str(row["device_id"]),
        detail=f"euicc={euicc_id} enabled={payload.user_enabled}",
    )
    return {"ok": True, "user_enabled": payload.user_enabled, "version": settings.version}
