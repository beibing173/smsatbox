"""鉴权路由：登录、当前用户、客户端长效令牌、改密。"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..config import settings
from ..db import get_db
from ..schemas import (
    ClientTokenCreate,
    LoginRequest,
    PasswordChange,
    TokenResponse,
)
from ..security import (
    authenticate_request,
    create_access_token,
    get_current_user,
    hash_password,
    new_raw_token,
    token_fingerprint,
    verify_password,
)
from ..utils import audit, client_ip, utcnow_iso

router = APIRouter(prefix="/auth", tags=["auth"])


def _public_user(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    data.pop("password_hash", None)
    data["is_active"] = bool(data.get("is_active", 1))
    return data


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, conn: sqlite3.Connection = Depends(get_db)):
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?", (payload.username.strip(),)
    ).fetchone()
    if row is None or not verify_password(payload.password, row["password_hash"]):
        audit(
            conn,
            "login_failed",
            target=payload.username,
            ip=client_ip(request),
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    if not row["is_active"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "账号已被禁用")
    token, expires_in = create_access_token(row["id"], row["role"], row["username"])
    conn.execute(
        "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?",
        (utcnow_iso(), utcnow_iso(), row["id"]),
    )
    conn.commit()
    audit(conn, "login", user_id=row["id"], target=row["username"], ip=client_ip(request))
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        version=settings.version,
        user=_public_user(row),
    )


@router.get("/me")
def me(user: dict[str, Any] = Depends(get_current_user)):
    return {"version": settings.version, "user": _public_user(user)}


@router.post("/logout")
def logout(request: Request, user: dict[str, Any] = Depends(get_current_user), conn: sqlite3.Connection = Depends(get_db)):
    """JWT 无状态，这里只记录审计；客户端 Token 会被吊销。"""
    raw = (request.headers.get("authorization", "")[7:]).strip()
    revoked = 0
    if raw and raw.count(".") != 2:
        cur = conn.execute(
            "DELETE FROM user_tokens WHERE token_hash = ?", (token_fingerprint(raw),)
        )
        conn.commit()
        revoked = cur.rowcount
    audit(conn, "logout", user_id=user["id"], target=user["username"])
    return {"ok": True, "revoked_client_tokens": revoked, "version": settings.version}


@router.post("/password")
def change_password(
    payload: PasswordChange,
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    if row is None or not verify_password(payload.old_password, row["password_hash"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "原密码不正确")
    conn.execute(
        "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
        (hash_password(payload.new_password), utcnow_iso(), user["id"]),
    )
    conn.commit()
    audit(conn, "password_change", user_id=user["id"], target=user["username"])
    return {"ok": True, "version": settings.version}


# --------------------------------------------------------------------------- #
# 客户端长效令牌（APK / EXE 用，避免频繁重登）
# --------------------------------------------------------------------------- #
@router.get("/client-tokens")
def list_client_tokens(
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = conn.execute(
        "SELECT id, name, created_at, last_used_at FROM user_tokens"
        " WHERE user_id = ? ORDER BY id DESC",
        (user["id"],),
    ).fetchall()
    return {"version": settings.version, "items": [dict(r) for r in rows]}


@router.post("/client-tokens")
def create_client_token(
    payload: ClientTokenCreate,
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    raw = new_raw_token()
    conn.execute(
        "INSERT INTO user_tokens (user_id, name, token_hash, created_at)"
        " VALUES (?, ?, ?, ?)",
        (user["id"], payload.name or "client", token_fingerprint(raw), utcnow_iso()),
    )
    conn.commit()
    return {
        "version": settings.version,
        "token": raw,
        "note": "该 Token 仅显示一次，请妥善保存到客户端",
    }


@router.delete("/client-tokens/{token_id}")
def delete_client_token(
    token_id: int,
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    cur = conn.execute(
        "DELETE FROM user_tokens WHERE id = ? AND user_id = ?", (token_id, user["id"])
    )
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "令牌不存在")
    return {"ok": True, "version": settings.version}


@router.get("/verify")
def verify(request: Request, conn: sqlite3.Connection = Depends(get_db)):
    """供 APK / EXE 探测服务器地址与令牌是否有效。"""
    user = authenticate_request(request, conn)
    return {
        "ok": True,
        "version": settings.version,
        "server": settings.app_name,
        "user": _public_user(user),
    }
