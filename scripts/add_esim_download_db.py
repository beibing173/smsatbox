# -*- coding: utf-8 -*-
"""给服务端加 eSIM 下载（写卡）任务 API

设计说明
========
写卡 = GSMA SGP.22 远程配置（RSP），需要：
  1. 解析 LPA 激活码 -> SM-DP+ 地址 + MatchingID
  2. 与 SM-DP+ 建立 HTTPS 并做 ES9+ 双向认证（证书链 + ECIES）
  3. 通过 ES10b 把 Bound Profile Package 分片写入 eUICC
  4. 处理通知（ProfileInstallationResult 等）

第 2/3 步必须能直接对卡发 APDU，而卡在本地 ESP32 上、
服务端在云端。因此需要一条「服务端 <-> 设备」的 APDU 隧道。

本文件先把「任务受理 + 状态机 + 隧道接口」落地，
RSP 引擎本身（lpac 或纯 Python 实现）作为独立模块后续接入，
接口保持不变。
"""
from pathlib import Path

ROOT = Path(r"D:\SMSATBOX")

# ---------------------------------------------------------------------------
# 1) db.py 增加下载任务表
# ---------------------------------------------------------------------------
p = ROOT / "server/app/db.py"
c = p.read_text(encoding="utf-8")
if "esim_download_task" in c:
    print("db.py 已有下载任务表")
else:
    anchor = "CREATE INDEX IF NOT EXISTS idx_esim_command_device ON esim_command(device_id, status);"
    add = """CREATE INDEX IF NOT EXISTS idx_esim_command_device ON esim_command(device_id, status);

-- eSIM 写卡（RSP 远程配置）任务
--   state: pending -> authenticating -> downloading -> installed | failed
--   progress 存 JSON：{step, percent, log}
CREATE TABLE IF NOT EXISTS esim_download_task (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id        INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    slot_index       INTEGER NOT NULL DEFAULT 1,
    activation_code  TEXT    NOT NULL,
    smdp_address     TEXT    NOT NULL DEFAULT '',
    matching_id      TEXT    NOT NULL DEFAULT '',
    confirmation_code TEXT   NOT NULL DEFAULT '',
    state            TEXT    NOT NULL DEFAULT 'pending',
    progress         TEXT    NOT NULL DEFAULT '',
    error            TEXT    NOT NULL DEFAULT '',
    created_by       INTEGER,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_esim_download_device ON esim_download_task(device_id, state);"""
    c = c.replace(anchor, add, 1)
    p.write_bytes(c.encode("utf-8"))
    print("✓ db.py 已加 esim_download_task 表")

# ---------------------------------------------------------------------------
# 2) schemas.py 增加请求/响应模型
# ---------------------------------------------------------------------------
p = ROOT / "server/app/schemas.py"
c = p.read_text(encoding="utf-8")
if "EsimDownloadCreate" in c:
    print("schemas.py 已有模型")
else:
    c += '''

# --------------------------------------------------------------------------- #
# eSIM 写卡（RSP 远程配置）
# --------------------------------------------------------------------------- #
class EsimDownloadCreate(BaseModel):
    """Web 提交写卡请求（扫二维码或手动输入激活码）。"""

    device_id: int
    slot_index: int = Field(default=1, ge=1, le=2)
    # 完整激活码，格式 LPA:1$smdp.example.com$MATCHING_ID
    activation_code: str = Field(min_length=10, max_length=512)
    # SM-DP+ 要求时的确认码，可选
    confirmation_code: str = Field(default="", max_length=128)


class EsimDownloadProgress(BaseModel):
    """设备/引擎回写写卡进度。"""

    state: Literal["pending", "authenticating", "downloading", "installed", "failed"]
    progress: str = Field(default="", max_length=2000)
    error: str = Field(default="", max_length=500)
'''
    p.write_bytes(c.encode("utf-8"))
    print("✓ schemas.py 已加写卡模型")

print()
print("数据库与模型已就绪，路由见 server/app/routers/esim.py 的追加部分")
