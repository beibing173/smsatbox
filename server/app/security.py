"""安全：密码哈希、JWT 签发校验、设备 Token 校验、鉴权依赖。"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from datetime import timedelta
from typing import Any

from fastapi import Depends, HTTPException, Request, status

from .config import settings
from .db import get_db
from .utils import now_utc, utcnow_iso

PBKDF2_ROUNDS = 260_000
TOKEN_PREFIX = "Bearer"


# --------------------------------------------------------------------------- #
# 密码
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ROUNDS
    ).hex()
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt, digest = stored.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    calc = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(rounds)
    ).hex()
    return hmac.compare_digest(calc, digest)


# --------------------------------------------------------------------------- #
# 轻量 JWT (HS256)，仅为减少依赖而手写；签名为标准实现
# --------------------------------------------------------------------------- #
def _b64url(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    import base64

    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def create_access_token(user_id: int, role: str, username: str) -> tuple[str, int]:
    expires_in = settings.token_ttl_minutes * 60
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user_id),
        "role": role,
        "username": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in,
    }
    head = _b64url(json.dumps(header, separators=(",", ":")).encode())
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{head}.{body}".encode()
    sig = hmac.new(settings.secret_key.encode(), signing_input, hashlib.sha256).digest()
    return f"{head}.{body}.{_b64url(sig)}", expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        head, body, sig = token.split(".")
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "令牌格式错误")
    signing_input = f"{head}.{body}".encode()
    expected = hmac.new(
        settings.secret_key.encode(), signing_input, hashlib.sha256
    ).digest()
    try:
        provided = _b64url_decode(sig)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "令牌签名解析失败")
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "令牌签名无效")
    try:
        payload = json.loads(_b64url_decode(body))
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "令牌内容损坏")
    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "登录已过期，请重新登录")
    return payload


def token_fingerprint(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# 通用工具
# --------------------------------------------------------------------------- #
def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    token = request.headers.get("x-auth-token")
    return token.strip() if token else None


def authenticate_request(request: Request, conn: sqlite3.Connection) -> dict[str, Any]:
    """同时支持 JWT 与长效客户端 Token。"""
    raw = _bearer(request)
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "缺少访问令牌")
    user_row = None
    if raw.count(".") == 2:
        payload = decode_access_token(raw)
        user_row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (int(payload["sub"]),)
        ).fetchone()
    else:
        fp = token_fingerprint(raw)
        row = conn.execute(
            "SELECT * FROM user_tokens WHERE token_hash = ?", (fp,)
        ).fetchone()
        if row:
            now = utcnow_iso()
            conn.execute(
                "UPDATE user_tokens SET last_used_at = ? WHERE id = ?", (now, row["id"])
            )
            conn.commit()
            user_row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (row["user_id"],)
            ).fetchone()
    if user_row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "账号不存在或令牌已失效")
    if not user_row["is_active"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "账号已被禁用")
    return dict(user_row)


def get_current_user(
    request: Request, conn: sqlite3.Connection = Depends(get_db)
) -> dict[str, Any]:
    return authenticate_request(request, conn)


def get_superadmin(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if user["role"] != "superadmin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要超级管理员权限")
    return user


def device_token_from_request(request: Request) -> str:
    """提取设备令牌：优先级 X-Device-Token 头 > ?token= 查询参数。"""
    header = (request.headers.get("x-device-token") or "").strip()
    if header:
        return header
    return (request.query_params.get("token") or "").strip()


def get_device_by_token(conn: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    """ESP32 鉴权：仅凭唯一 Device_Token。"""
    if not token:
        return None
    return conn.execute(
        "SELECT * FROM devices WHERE device_token = ?", (token,)
    ).fetchone()


def device_auth(request: Request, conn: sqlite3.Connection = Depends(get_db)) -> sqlite3.Row:
    """设备专用鉴权依赖：仅凭 Device_Token。"""
    row = get_device_by_token(conn, device_token_from_request(request))
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "设备未授权：Device_Token 无效")
    return row


def accessible_slot_ids(conn: sqlite3.Connection, user: dict[str, Any]) -> set[int] | None:
    """返回可访问的卡槽 id 集合；None 表示不限（超级管理员）。"""
    if user["role"] == "superadmin":
        return None
    rows = conn.execute(
        "SELECT slot_id FROM permissions WHERE user_id = ? AND can_read = 1",
        (user["id"],),
    ).fetchall()
    return {row["slot_id"] for row in rows}


def ensure_slot_readable(
    conn: sqlite3.Connection, user: dict[str, Any], slot_id: int | None
) -> None:
    if slot_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "缺少卡槽参数")
    if user["role"] == "superadmin":
        return
    row = conn.execute(
        "SELECT 1 FROM permissions WHERE user_id = ? AND slot_id = ? AND can_read = 1",
        (user["id"], slot_id),
    ).fetchone()
    if not row:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该卡槽")


def ensure_slot_sendable(
    conn: sqlite3.Connection, user: dict[str, Any], slot_id: int | None
) -> None:
    if slot_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "缺少卡槽参数")
    if user["role"] == "superadmin":
        return
    row = conn.execute(
        "SELECT 1 FROM permissions WHERE user_id = ? AND slot_id = ? AND can_send_sms = 1",
        (user["id"], slot_id),
    ).fetchone()
    if not row:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权通过该卡槽发送短信")


def new_raw_token() -> str:
    return "u_" + secrets.token_urlsafe(32)


def ttl_delta() -> timedelta:
    return timedelta(minutes=settings.token_ttl_minutes)


def unix_now() -> int:
    return int(now_utc().timestamp())
