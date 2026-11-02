"""固件下载（设备静默下载通道）。"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from ..config import settings
from ..db import get_db
from ..security import get_device_by_token

router = APIRouter(prefix="/ota", tags=["ota"])


@router.get("/download/{filename}")
def download_firmware(
    filename: str,
    request: Request,
    token: str | None = Query(default=None),
    conn: sqlite3.Connection = Depends(get_db),
):
    """ESP32 静默下载固件。

    鉴权：优先 X-Device-Token 头，其次 ?token= 查询参数（便于设备端简化实现）。
    """
    device_token = (request.headers.get("x-device-token") or token or "").strip()
    if not device_token or get_device_by_token(conn, device_token) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "设备未授权")

    safe_name = filename.replace("\\", "/").split("/")[-1]
    if not safe_name.endswith(".bin") or ".." in safe_name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "非法的固件文件名")
    path = settings.firmware_dir / safe_name
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "固件不存在或已被清理")
    return FileResponse(
        path, media_type="application/octet-stream", filename=safe_name
    )
