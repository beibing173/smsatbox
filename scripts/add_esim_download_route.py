# -*- coding: utf-8 -*-
"""给 esim.py 追加写卡相关路由"""
from pathlib import Path

P = Path(r"D:\SMSATBOX\server\app\routers\esim.py")
c = P.read_text(encoding="utf-8")

if "esim/download" in c:
    print("已有写卡路由，跳过")
    raise SystemExit(0)

# 更新 import
old_imp = """from ..schemas import (
    EsimCommandCreate,
    EsimCommandResult,
    EuiccReport,
    EuiccToggle,
)"""
new_imp = """from ..schemas import (
    EsimCommandCreate,
    EsimCommandResult,
    EsimDownloadCreate,
    EsimDownloadProgress,
    EuiccReport,
    EuiccToggle,
)"""
c = c.replace(old_imp, new_imp, 1)

ROUTES = '''

# =========================================================================== #
# eSIM 写卡（RSP 远程配置）
# =========================================================================== #
import re as _re

# RSP 引擎是否可用。
# 完整实现需要：与 SM-DP+ 做 ES9+ 双向认证（证书链 + ECIES），
# 再通过 ES10b 把 Bound Profile Package 分片写入 eUICC。
# 因为卡在本地 ESP32、服务端在云端，还需要一条 APDU 隧道，
# 因此这里先用开关控制，引擎接入后置 True 即可。
RSP_ENGINE_READY = False


def _parse_lpa(code: str) -> tuple[str, str] | None:
    """解析 LPA 激活码：LPA:1$smdp.example.com$MATCHING_ID"""
    m = _re.match(r"^LPA:?\\d*\\$([^\\$]+)\\$(.+)$", (code or "").strip(), _re.I)
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip()


@router.post("/esim/download", status_code=status.HTTP_201_CREATED)
async def create_download_task(
    payload: EsimDownloadCreate,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """受理写卡请求：校验激活码 -> 建任务 -> 交给 RSP 引擎执行。"""
    visible = _visible_device_ids(conn, user)
    if payload.device_id not in visible:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作该设备")

    parsed = _parse_lpa(payload.activation_code)
    if parsed is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "激活码格式不对，应为 LPA:1$服务器域名$匹配ID",
        )
    smdp, matching_id = parsed

    # 同一槽位不允许并发下卡（RSP 会话必须独占卡片）
    busy = conn.execute(
        """
        SELECT id FROM esim_download_task
         WHERE device_id = ? AND slot_index = ?
           AND state IN ('pending','authenticating','downloading')
        """,
        (payload.device_id, payload.slot_index),
    ).fetchone()
    if busy is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "该卡槽已有写卡任务在进行中")

    now = utcnow_iso()
    cur = conn.execute(
        """
        INSERT INTO esim_download_task
            (device_id, slot_index, activation_code, smdp_address, matching_id,
             confirmation_code, state, progress, error, created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'pending', '', '', ?, ?, ?)
        """,
        (
            payload.device_id,
            payload.slot_index,
            payload.activation_code.strip(),
            smdp,
            matching_id,
            payload.confirmation_code,
            user["id"],
            now,
            now,
        ),
    )
    task_id = int(cur.lastrowid or 0)
    conn.commit()

    audit(
        conn,
        "esim_download",
        user_id=user["id"],
        target=str(payload.device_id),
        detail=f"smdp={smdp}",
    )

    if RSP_ENGINE_READY:
        message = "任务已排队，正在与 SM-DP+ 建立会话"
    else:
        message = (
            "任务已受理并保存。写卡引擎（SGP.22 RSP）尚未接入，"
            "当前不会真正下发配置；可先用手机上的 9eSIM / 5ber 官方 App 完成写卡。"
        )

    return {
        "ok": True,
        "task_id": task_id,
        "supported": RSP_ENGINE_READY,
        "smdp_address": smdp,
        "matching_id": matching_id,
        "message": message,
        "version": settings.version,
    }


@router.get("/esim/download/{task_id}")
def get_download_task(
    task_id: int,
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute(
        "SELECT * FROM esim_download_task WHERE id = ?", (task_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")

    visible = _visible_device_ids(conn, user)
    if row["device_id"] not in visible:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权查看该任务")

    return {
        "id": row["id"],
        "device_id": row["device_id"],
        "slot_index": row["slot_index"],
        "smdp_address": row["smdp_address"],
        "matching_id": row["matching_id"],
        "state": row["state"],
        "progress": row["progress"],
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "supported": RSP_ENGINE_READY,
        "version": settings.version,
    }


@router.post("/esim/download/{task_id}/progress")
async def report_download_progress(
    task_id: int,
    payload: EsimDownloadProgress,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """RSP 引擎回写进度（设备侧或后台 worker 调用）。"""
    row = conn.execute(
        "SELECT * FROM esim_download_task WHERE id = ?", (task_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")

    now = utcnow_iso()
    conn.execute(
        """
        UPDATE esim_download_task
           SET state = ?, progress = ?, error = ?, updated_at = ?
         WHERE id = ?
        """,
        (payload.state, payload.progress, payload.error, now, task_id),
    )
    conn.commit()

    await manager.broadcast_clients(
        "esim_download_progress",
        {
            "task_id": task_id,
            "state": payload.state,
            "progress": payload.progress,
            "error": payload.error,
            "version": settings.version,
        },
    )
    return {"ok": True, "version": settings.version}
'''

c = c.rstrip() + "\n" + ROUTES
P.write_bytes(c.encode("utf-8"))
print("✓ esim.py 已追加写卡路由")
