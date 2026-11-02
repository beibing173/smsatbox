"""编排与工具：设备握手、OTA、Server 协同升级。"""

from __future__ import annotations

import sqlite3
from typing import Any

from ..config import settings
from ..utils import parse_iso, utcnow_iso


def is_device_online(row: sqlite3.Row | dict[str, Any]) -> bool:
    """以最后一次心跳时间判定在线；阈值可由 DEVICE_OFFLINE_SECONDS 配置。"""
    last = parse_iso(dict(row).get("last_seen_at"))
    if last is None:
        return False
    delta = (parse_iso(utcnow_iso()) - last).total_seconds()
    return delta <= settings.device_offline_seconds


def server_info() -> dict[str, Any]:
    return {
        "product": settings.app_name,
        "version": settings.version,
        "server_image": settings.server_image,
        "upgrade_enabled": settings.server_upgrade_enabled,
    }
