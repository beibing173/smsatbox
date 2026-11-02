"""用户管理（仅超级管理员）与权限分配（RBAC）。"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ..config import settings
from ..db import get_db
from ..schemas import PermissionUpdate, UserCreate, UserUpdate
from ..security import get_superadmin, hash_password
from ..utils import audit, utcnow_iso

router = APIRouter(prefix="/users", tags=["users"])


def _public(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    data.pop("password_hash", None)
    data["is_active"] = bool(data.get("is_active", 1))
    return data


@router.get("")
def list_users(
    admin: dict[str, Any] = Depends(get_superadmin),
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    items = []
    for row in rows:
        item = _public(row)
        granted = conn.execute(
            "SELECT slot_id, can_read, can_send_sms FROM permissions WHERE user_id = ?",
            (row["id"],),
        ).fetchall()
        item["permissions"] = [dict(g) for g in granted]
        items.append(item)
    return {"version": settings.version, "items": items}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    admin: dict[str, Any] = Depends(get_superadmin),
    conn: sqlite3.Connection = Depends(get_db),
):
    exists = conn.execute(
        "SELECT 1 FROM users WHERE username = ?", (payload.username.strip(),)
    ).fetchone()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "用户名已存在")
    now = utcnow_iso()
    cur = conn.execute(
        "INSERT INTO users (username, display_name, password_hash, role, is_active,"
        " created_at, updated_at) VALUES (?, ?, ?, ?, 1, ?, ?)",
        (
            payload.username.strip(),
            payload.display_name or payload.username.strip(),
            hash_password(payload.password),
            payload.role,
            now,
            now,
        ),
    )
    conn.commit()
    audit(conn, "user_create", user_id=admin["id"], target=payload.username)
    row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    return {"version": settings.version, "user": _public(row)}


@router.patch("/{user_id}")
def update_user(
    user_id: int,
    payload: UserUpdate,
    admin: dict[str, Any] = Depends(get_superadmin),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    fields: list[str] = []
    params: list[Any] = []
    if payload.display_name is not None:
        fields.append("display_name = ?")
        params.append(payload.display_name)
    if payload.is_active is not None:
        if row["role"] == "superadmin" and not payload.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能禁用超级管理员")
        fields.append("is_active = ?")
        params.append(1 if payload.is_active else 0)
    if payload.role is not None and payload.role != row["role"]:
        if row["role"] == "superadmin":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "超级管理员角色不可变更")
        fields.append("role = ?")
        params.append(payload.role)
    if payload.password:
        fields.append("password_hash = ?")
        params.append(hash_password(payload.password))
    if not fields:
        return {"ok": True, "version": settings.version}
    fields.append("updated_at = ?")
    params.extend([utcnow_iso(), user_id])
    conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", params)
    conn.commit()
    audit(conn, "user_update", user_id=admin["id"], target=row["username"])
    updated = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return {"version": settings.version, "user": _public(updated)}


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    admin: dict[str, Any] = Depends(get_superadmin),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    if row["role"] == "superadmin":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能删除超级管理员")
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    audit(conn, "user_delete", user_id=admin["id"], target=row["username"])
    return {"ok": True, "version": settings.version}


# --------------------------------------------------------------------------- #
# 权限（卡槽可见性）
# --------------------------------------------------------------------------- #
@router.get("/{user_id}/permissions")
def get_permissions(
    user_id: int,
    admin: dict[str, Any] = Depends(get_superadmin),
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = conn.execute(
        "SELECT p.*, s.slot_index, s.phone_number, s.device_id, d.device_name"
        " FROM permissions p JOIN sim_cards s ON s.id = p.slot_id"
        " JOIN devices d ON d.id = s.device_id WHERE p.user_id = ?",
        (user_id,),
    ).fetchall()
    return {"version": settings.version, "items": [dict(r) for r in rows]}


@router.put("/{user_id}/permissions")
def set_permissions(
    user_id: int,
    payload: PermissionUpdate,
    admin: dict[str, Any] = Depends(get_superadmin),
    conn: sqlite3.Connection = Depends(get_db),
):
    target = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    if target["role"] == "superadmin":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "超级管理员默认拥有全部卡槽权限，无需分配"
        )
    valid_slots = {row["id"] for row in conn.execute("SELECT id FROM sim_cards").fetchall()}
    for item in payload.items:
        if item.slot_id not in valid_slots:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"卡槽 {item.slot_id} 不存在"
            )
    now = utcnow_iso()
    conn.execute("DELETE FROM permissions WHERE user_id = ?", (user_id,))
    for item in payload.items:
        conn.execute(
            "INSERT INTO permissions (user_id, slot_id, can_read, can_send_sms, granted_by,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                user_id,
                item.slot_id,
                1 if item.can_read else 0,
                1 if item.can_send_sms else 0,
                admin["id"],
                now,
            ),
        )
    conn.commit()
    audit(conn, "permission_update", user_id=admin["id"], target=target["username"])
    return {
        "ok": True,
        "version": settings.version,
        "granted": len(payload.items),
    }
