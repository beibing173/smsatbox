"""SQLite 数据库层：建表、迁移、初始化种子数据。

表结构一览
----------
users            用户（超级管理员 / 普通成员）
sim_cards        SIM 卡槽（归属设备，记录套餐到期时间）
permissions      成员 -> 卡槽 的授权关系（RBAC，卡槽可见性）
devices          设备（ESP32），唯一 Device_Token 鉴权
messages         短信 / 来电记录，含自动提取的验证码
sms_commands     反向控制：Web 下发发送短信指令
ota_tasks        固件 OTA 任务（上传 .bin -> 下发 -> 状态回传）
user_tokens      移动端 / 桌面端长效访问令牌
audit_logs       审计日志
app_settings     全局配置（如 ESP32 最新固件信息）
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import settings
from .utils import utcnow_iso

SCHEMA_VERSION = 1

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    display_name  TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('superadmin', 'member')),
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS devices (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    device_token     TEXT NOT NULL UNIQUE,
    device_name      TEXT NOT NULL DEFAULT '',
    hardware_model   TEXT NOT NULL DEFAULT 'ESP32-S3-N16R8',
    firmware_version TEXT NOT NULL DEFAULT '1.0.1',
    local_ip         TEXT NOT NULL DEFAULT '',
    wifi_rssi        INTEGER NOT NULL DEFAULT 0,
    net_mode         TEXT NOT NULL DEFAULT 'wifi',
    online           INTEGER NOT NULL DEFAULT 0,
    last_seen_at     TEXT,
    server_version   TEXT NOT NULL DEFAULT '',
    remark           TEXT NOT NULL DEFAULT '',
    modules_json     TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sim_cards (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id      INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    slot_index     INTEGER NOT NULL,
    phone_number   TEXT NOT NULL DEFAULT '',
    provider       TEXT NOT NULL DEFAULT '',
    plan_name      TEXT NOT NULL DEFAULT '默认套餐',
    plan_expire_at TEXT,
    carrier        TEXT NOT NULL DEFAULT '',
    signal_dbm     INTEGER NOT NULL DEFAULT 99,
    is_active      INTEGER NOT NULL DEFAULT 1,
    remark         TEXT NOT NULL DEFAULT '',
    module_json    TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    UNIQUE (device_id, slot_index)
);

CREATE TABLE IF NOT EXISTS permissions (
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    slot_id      INTEGER NOT NULL REFERENCES sim_cards(id) ON DELETE CASCADE,
    can_read     INTEGER NOT NULL DEFAULT 1,
    can_send_sms INTEGER NOT NULL DEFAULT 0,
    can_send     INTEGER NOT NULL DEFAULT 0,
    granted_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at   TEXT NOT NULL,
    PRIMARY KEY (user_id, slot_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    slot_id     INTEGER REFERENCES sim_cards(id) ON DELETE SET NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('sms', 'call', 'system')),
    sender      TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL DEFAULT '',
    code        TEXT,
    received_at TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    is_read     INTEGER NOT NULL DEFAULT 0,
    raw         TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_slot_time ON messages (slot_id, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_device_time ON messages (device_id, received_at DESC);

CREATE TABLE IF NOT EXISTS sms_commands (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id     INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    slot_id       INTEGER REFERENCES sim_cards(id) ON DELETE SET NULL,
    target_number TEXT NOT NULL,
    content       TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'sent', 'delivered', 'failed')),
    error         TEXT NOT NULL DEFAULT '',
    created_by    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ota_tasks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id  INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    version    TEXT NOT NULL,
    filename   TEXT NOT NULL,
    md5        TEXT NOT NULL,
    size       INTEGER NOT NULL DEFAULT 0,
    status     TEXT NOT NULL DEFAULT 'pending'
               CHECK (status IN ('pending', 'downloading', 'success', 'failed', 'canceled')),
    error      TEXT NOT NULL DEFAULT '',
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_tokens (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name         TEXT NOT NULL DEFAULT 'client',
    token_hash   TEXT NOT NULL UNIQUE,
    created_at   TEXT NOT NULL,
    last_used_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action     TEXT NOT NULL,
    target     TEXT NOT NULL DEFAULT '',
    detail     TEXT NOT NULL DEFAULT '',
    ip         TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- eUICC / eSIM（可编程实体卡）管理
--   euicc        : 每张 eUICC 卡一条，挂在设备上（一个设备每个卡槽最多一张）
--   euicc_profile: 卡里已安装的 profile（可多个，同时只有 1 个启用）
--   esim_command : 云端下发给设备的 eSIM 操作指令（切卡/删卡/改名/刷新）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS euicc (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id         INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    slot_index        INTEGER NOT NULL DEFAULT 1,
    eid               TEXT    NOT NULL DEFAULT '',
    installed_apps    INTEGER NOT NULL DEFAULT 0,
    free_nonvolatile  INTEGER NOT NULL DEFAULT -1,
    free_volatile     INTEGER NOT NULL DEFAULT -1,
    user_enabled      INTEGER NOT NULL DEFAULT 1,
    probed_at         TEXT,
    updated_at        TEXT    NOT NULL,
    UNIQUE (device_id, slot_index)
);

CREATE TABLE IF NOT EXISTS euicc_profile (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    euicc_id    INTEGER NOT NULL REFERENCES euicc(id) ON DELETE CASCADE,
    iccid       TEXT    NOT NULL DEFAULT '',
    state       INTEGER NOT NULL DEFAULT 0,
    nickname    TEXT    NOT NULL DEFAULT '',
    provider    TEXT    NOT NULL DEFAULT '',
    profile_name TEXT   NOT NULL DEFAULT '',
    updated_at  TEXT    NOT NULL,
    UNIQUE (euicc_id, iccid)
);

CREATE TABLE IF NOT EXISTS esim_command (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id    INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    slot_index   INTEGER NOT NULL DEFAULT 1,
    command_type TEXT    NOT NULL,
    iccid        TEXT    NOT NULL DEFAULT '',
    nickname     TEXT    NOT NULL DEFAULT '',
    status       TEXT    NOT NULL DEFAULT 'pending',
    error        TEXT    NOT NULL DEFAULT '',
    created_by   INTEGER,
    created_at   TEXT    NOT NULL,
    finished_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_euicc_device ON euicc(device_id);
CREATE INDEX IF NOT EXISTS idx_euicc_profile_euicc ON euicc_profile(euicc_id);
CREATE INDEX IF NOT EXISTS idx_esim_command_device ON esim_command(device_id, status);
"""


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = str(db_path or settings.db_path)
    conn = sqlite3.connect(path, timeout=20, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 20000")
    return conn


@contextmanager
def db_session(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """脚本/初始化用的事务上下文。"""
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI 依赖：每次请求一个连接；正常退出自动 commit，异常自动 rollback。"""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _seed_admin(conn: sqlite3.Connection) -> None:
    from .security import hash_password  # 延迟导入避免循环依赖

    row = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
    if row["c"] > 0:
        return
    now = utcnow_iso()
    conn.execute(
        "INSERT INTO users (username, display_name, password_hash, role, is_active,"
        " created_at, updated_at) VALUES (?, ?, ?, 'superadmin', 1, ?, ?)",
        (
            settings.admin_username,
            settings.admin_display_name,
            hash_password(settings.admin_password),
            now,
            now,
        ),
    )
    # 内置一台示例设备，方便本地首次联调
    demo_token = "smsat_demo_device_token_replace_me"
    conn.execute(
        "INSERT OR IGNORE INTO devices (device_token, device_name, firmware_version,"
        " net_mode, online, server_version, remark, created_at)"
        " VALUES (?, ?, '1.0.0', 'wifi', 0, '', ?, ?)",
        (demo_token, "演示设备（请替换 Token）", "本地首次联调示例", now),
    )
    device_id = conn.execute(
        "SELECT id FROM devices WHERE device_token = ?", (demo_token,)
    ).fetchone()["id"]
    for slot in (1, 2):
        conn.execute(
            "INSERT OR IGNORE INTO sim_cards (device_id, slot_index, phone_number,"
            " provider, plan_name, plan_expire_at, carrier, created_at)"
            " VALUES (?, ?, '', '', '默认套餐', NULL, '', ?)",
            (device_id, slot, now),
        )


def _migrate(conn: sqlite3.Connection) -> None:
    """增量迁移：给已有数据库补字段，保证老库升级不丢数据。"""

    def columns(table: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {r["name"] for r in rows}

    # v1.1: sim_cards 增加备注
    card_cols = columns("sim_cards")
    if "remark" not in card_cols:
        conn.execute("ALTER TABLE sim_cards ADD COLUMN remark TEXT NOT NULL DEFAULT ''")
    if "module_json" not in card_cols:
        conn.execute("ALTER TABLE sim_cards ADD COLUMN module_json TEXT NOT NULL DEFAULT ''")

    # v1.1: devices 增加模组状态快照（JSON 文本，ESP32 上报后原样存）
    dev_cols = columns("devices")
    if "modules_json" not in dev_cols:
        conn.execute("ALTER TABLE devices ADD COLUMN modules_json TEXT NOT NULL DEFAULT ''")

    conn.commit()


def init_db(db_path: str | Path | None = None) -> None:
    """建表 + 迁移 + 种子数据 + 版本记录，可重复调用（幂等）。"""
    with db_session(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        _migrate(conn)
        _seed_admin(conn)
        conn.execute(
            "INSERT INTO schema_meta (key, value) VALUES ('schema_version', ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()
