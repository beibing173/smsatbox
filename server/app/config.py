"""运行配置：全部来自环境变量，便于 Docker 部署。"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from .version import VERSION

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "y"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class Settings:
    """进程级配置单例。"""

    def __init__(self) -> None:
        self.app_name = "SMSATBOX"
        self.version = VERSION
        self.api_prefix = "/api/v1"

        self.data_dir = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(
            os.getenv("DATABASE_PATH", str(self.data_dir / "smsatbox.db"))
        ).resolve()
        self.firmware_dir = self.data_dir / "firmware"
        self.firmware_dir.mkdir(parents=True, exist_ok=True)

        self.static_dir = BASE_DIR / "app" / "static"

        self.token_ttl_minutes = _env_int("TOKEN_TTL_MINUTES", 720)
        self.admin_username = os.getenv("ADMIN_USERNAME", "admin")
        self.admin_password = os.getenv("ADMIN_PASSWORD", "Admin@123456")
        self.admin_display_name = os.getenv("ADMIN_DISPLAY_NAME", "超级管理员")

        self.allow_device_auto_register = _env_bool("ALLOW_DEVICE_AUTO_REGISTER", True)
        self.device_offline_seconds = _env_int("DEVICE_OFFLINE_SECONDS", 90)
        self.max_firmware_mb = _env_int("MAX_FIRMWARE_MB", 16)

        # 维度二：Server 与 ESP32 协同升级
        self.server_image = os.getenv("SERVER_IMAGE", "beibing173/smsatbox-server")
        self.server_upgrade_enabled = _env_bool("SERVER_UPGRADE_ENABLED", False)
        self.server_upgrade_command = os.getenv("SERVER_UPGRADE_COMMAND", "")

        self.cors_origins = [
            o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()
        ]

        self._secret_key = (os.getenv("SECRET_KEY") or "").strip()
        if not self._secret_key:
            secret_file = self.data_dir / ".secret_key"
            if secret_file.exists():
                self._secret_key = secret_file.read_text(encoding="utf-8").strip()
            if not self._secret_key:
                self._secret_key = secrets.token_urlsafe(48)
                secret_file.write_text(self._secret_key, encoding="utf-8")
                try:
                    os.chmod(secret_file, 0o600)
                except OSError:  # Windows 上可能不支持
                    pass

    @property
    def secret_key(self) -> str:
        return self._secret_key


settings = Settings()
