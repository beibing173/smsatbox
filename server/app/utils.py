"""通用工具函数。"""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any

# 验证码提取：优先“验证码/校验码/动态码”等关键词后面的 4~8 位数字
_CODE_KEYWORDS = re.compile(
    r"(?:验证码|校验码|动态码|确认码|激活码|code|Code|CODE|OTP)\s*(?:为|是|:|：)?\s*(\d{4,8})"
)
_CODE_ANY = re.compile(r"(?<!\d)(\d{4,8})(?!\d)")


def utcnow_iso() -> str:
    """统一使用带 Z 的 UTC ISO8601 时间戳存储。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def generate_device_token() -> str:
    """ESP32 唯一的设备绑定码（Device_Token）。"""
    return "smsat_" + secrets.token_urlsafe(24)


def extract_verification_code(text: str | None) -> str | None:
    if not text:
        return None
    match = _CODE_KEYWORDS.search(text)
    if match:
        return match.group(1)
    match = _CODE_ANY.search(text)
    if match:
        return match.group(1)
    return None


def loads(raw: str | None, default: Any = None) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_to_list(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def audit(
    conn: sqlite3.Connection,
    action: str,
    *,
    user_id: int | None = None,
    target: str = "",
    detail: str = "",
    ip: str = "",
) -> None:
    """写入审计日志；失败不影响主流程。"""
    try:
        conn.execute(
            "INSERT INTO audit_logs (user_id, action, target, detail, ip, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, action, target, detail[:2000], ip, utcnow_iso()),
        )
        conn.commit()
    except sqlite3.Error:
        pass


def client_ip(request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host or ""
    return ""
