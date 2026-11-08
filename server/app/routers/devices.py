"""设备管理、卡槽配置、固件 OTA 下发。"""

from __future__ import annotations

import hashlib
import sqlite3
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse

from ..config import settings
from ..db import get_db
from ..realtime import manager
from ..schemas import DeviceCreate, DeviceUpdate, SimCardUpdate
from ..security import get_current_user, get_superadmin
from ..services import devices as device_service
from ..utils import audit, utcnow_iso

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("")
def list_devices(
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = conn.execute("SELECT * FROM devices ORDER BY id").fetchall()
    items = []
    for row in rows:
        detail = device_service.device_detail(conn, row["id"]) or {}
        if user["role"] != "superadmin":
            allowed = conn.execute(
                "SELECT DISTINCT s.device_id FROM permissions p"
                " JOIN sim_cards s ON s.id = p.slot_id"
                " WHERE p.user_id = ? AND p.can_read = 1",
                (user["id"],),
            ).fetchall()
            if row["id"] not in {r["device_id"] for r in allowed}:
                continue
            allowed_slots = {
                r["slot_id"]
                for r in conn.execute(
                    "SELECT slot_id FROM permissions WHERE user_id = ? AND can_read = 1",
                    (user["id"],),
                ).fetchall()
            }
            detail["slots"] = [
                s for s in detail.get("slots", []) if s["id"] in allowed_slots
            ]
        items.append(detail)
    return {"version": settings.version, "items": items}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_device(
    payload: DeviceCreate,
    admin: dict[str, Any] = Depends(get_superadmin),
    conn: sqlite3.Connection = Depends(get_db),
):
    detail = device_service.create_device(
        conn,
        device_name=payload.device_name,
        hardware_model=payload.hardware_model,
        slot_count=payload.slots,
        remark=payload.remark,
    )
    audit(conn, "device_create", user_id=admin["id"], target=str(detail.get("id")))
    return {"version": settings.version, "device": detail}


@router.get("/{device_id}")
def get_device(
    device_id: int,
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    detail = device_service.device_detail(conn, device_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "设备不存在")
    if user["role"] != "superadmin":
        allowed = {
            r["slot_id"]
            for r in conn.execute(
                "SELECT slot_id FROM permissions WHERE user_id = ? AND can_read = 1",
                (user["id"],),
            ).fetchall()
        }
        detail["slots"] = [s for s in detail["slots"] if s["id"] in allowed]
        if not detail["slots"]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该设备")
    detail["ws_connections"] = manager.device_online_sockets(device_id)
    return {"version": settings.version, "device": detail}


@router.patch("/{device_id}")
def update_device(
    device_id: int,
    payload: DeviceUpdate,
    admin: dict[str, Any] = Depends(get_superadmin),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "设备不存在")
    fields: list[str] = []
    params: list[Any] = []
    if payload.device_name is not None:
        fields.append("device_name = ?")
        params.append(payload.device_name)
    if payload.remark is not None:
        fields.append("remark = ?")
        params.append(payload.remark)
    if fields:
        params.append(device_id)
        conn.execute(f"UPDATE devices SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
    return {"version": settings.version, "device": device_service.device_detail(conn, device_id)}


@router.delete("/{device_id}")
def delete_device(
    device_id: int,
    admin: dict[str, Any] = Depends(get_superadmin),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "设备不存在")
    conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    conn.commit()
    audit(conn, "device_delete", user_id=admin["id"], target=str(device_id))
    return {"ok": True, "version": settings.version}


@router.post("/{device_id}/rotate-token")
def rotate_token(
    device_id: int,
    admin: dict[str, Any] = Depends(get_superadmin),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "设备不存在")
    from ..utils import generate_device_token

    token = generate_device_token()
    conn.execute(
        "UPDATE devices SET device_token = ? WHERE id = ?", (token, device_id)
    )
    conn.commit()
    audit(conn, "device_rotate_token", user_id=admin["id"], target=str(device_id))
    return {"version": settings.version, "device_token": token}


# --------------------------------------------------------------------------- #
# 卡槽（含套餐到期日）
# --------------------------------------------------------------------------- #
@router.patch("/slots/{slot_id}")
def update_slot(
    slot_id: int,
    payload: SimCardUpdate,
    admin: dict[str, Any] = Depends(get_superadmin),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute("SELECT * FROM sim_cards WHERE id = ?", (slot_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "卡槽不存在")
    fields: list[str] = []
    params: list[Any] = []
    for field in (
        "phone_number",
        "provider",
        "plan_name",
        "plan_expire_at",
        "carrier",
        "remark",
    ):
        value = getattr(payload, field)
        if value is not None:
            fields.append(f"{field} = ?")
            params.append(value)
    if payload.is_active is not None:
        fields.append("is_active = ?")
        params.append(1 if payload.is_active else 0)
    if fields:
        params.append(slot_id)
        conn.execute(f"UPDATE sim_cards SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
    audit(conn, "slot_update", user_id=admin["id"], target=str(slot_id))
    updated = conn.execute("SELECT * FROM sim_cards WHERE id = ?", (slot_id,)).fetchone()
    return {
        "version": settings.version,
        "slot": device_service_slot(updated),
    }


def device_service_slot(row: sqlite3.Row) -> dict[str, Any]:
    """把卡槽行转成前端结构（含 module 详情与 visible）。"""
    from ..services.devices import _decorate_slot

    return _decorate_slot(row)


# --------------------------------------------------------------------------- #
# OTA：上传 .bin 并下发到 ESP32
# --------------------------------------------------------------------------- #
@router.get("/{device_id}/ota")
def list_ota(
    device_id: int,
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = conn.execute(
        "SELECT * FROM ota_tasks WHERE device_id = ? ORDER BY id DESC LIMIT 20",
        (device_id,),
    ).fetchall()
    return {"version": settings.version, "items": [dict(r) for r in rows]}


@router.post("/{device_id}/ota", status_code=status.HTTP_201_CREATED)
async def upload_and_push_ota(
    device_id: int,
    version: str = Form(...),
    file: UploadFile = File(...),
    admin: dict[str, Any] = Depends(get_superadmin),
    conn: sqlite3.Connection = Depends(get_db),
):
    device = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "设备不存在")
    if not (file.filename or "").lower().endswith(".bin"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "只允许上传 .bin 固件文件")

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "固件内容为空")
    if len(data) > settings.max_firmware_mb * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"固件超过 {settings.max_firmware_mb}MB 限制",
        )

    md5 = hashlib.md5(data).hexdigest()
    safe_version = "".join(c for c in version if c.isalnum() or c in ".-_") or "1.0.1"
    filename = f"esp32-{safe_version}-{md5[:8]}.bin"
    target = settings.firmware_dir / filename
    target.write_bytes(data)

    now = utcnow_iso()
    cur = conn.execute(
        "INSERT INTO ota_tasks (device_id, version, filename, md5, size, status,"
        " created_by, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)",
        (device_id, safe_version, filename, md5, len(data), admin["id"], now, now),
    )
    conn.commit()
    task_id = int(cur.lastrowid)
    audit(
        conn,
        "ota_upload",
        user_id=admin["id"],
        target=f"device:{device_id}",
        detail=f"{filename} md5={md5}",
    )

    pushed = await manager.push_command(
        device_id,
        {
            "type": "ota",
            "task_id": task_id,
            "version": safe_version,
            "url": f"/api/v1/ota/download/{filename}",
            "md5": md5,
            "size": len(data),
        },
    )
    return {
        "version": settings.version,
        "task_id": task_id,
        "md5": md5,
        "size": len(data),
        "pushed": pushed,
        "note": "" if pushed else "设备当前不在线，已排队，设备上线后自动下发",
    }


@router.get("/{device_id}/ota/pending")
def pending_ota(
    device_id: int,
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute(
        "SELECT * FROM ota_tasks WHERE device_id = ? AND status = 'pending'"
        " ORDER BY id ASC LIMIT 1",
        (device_id,),
    ).fetchone()
    return {"version": settings.version, "task": dict(row) if row else None}


@router.delete("/ota/{task_id}")
def cancel_ota(
    task_id: int,
    admin: dict[str, Any] = Depends(get_superadmin),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute("SELECT * FROM ota_tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    conn.execute(
        "UPDATE ota_tasks SET status = 'canceled', updated_at = ? WHERE id = ?",
        (utcnow_iso(), task_id),
    )
    conn.commit()
    return {"ok": True, "version": settings.version}


@router.get("/ota/{task_id}/file")
def download_ota_file(
    task_id: int,
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """带鉴权的固件下载（供 Web 端校验/重下）。"""
    row = conn.execute("SELECT * FROM ota_tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    path = settings.firmware_dir / row["filename"]
    if not path.exists():
        raise HTTPException(status.HTTP_410_GONE, "固件文件已被清理")
    return FileResponse(path, media_type="application/octet-stream", filename=row["filename"])
