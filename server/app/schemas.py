"""Pydantic 数据模型（请求/响应 Schema）。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# 鉴权
# --------------------------------------------------------------------------- #
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    version: str
    user: dict[str, Any]


class ClientTokenCreate(BaseModel):
    name: str = Field(default="client", max_length=64)


class PasswordChange(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# --------------------------------------------------------------------------- #
# 用户 / 权限
# --------------------------------------------------------------------------- #
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=64)
    role: Literal["superadmin", "member"] = "member"


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=64)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool | None = None
    role: Literal["superadmin", "member"] | None = None


class PermissionItem(BaseModel):
    slot_id: int
    can_read: bool = True
    can_send_sms: bool = False


class PermissionUpdate(BaseModel):
    items: list[PermissionItem] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# 设备 / 卡槽
# --------------------------------------------------------------------------- #
class DeviceCreate(BaseModel):
    device_name: str = Field(default="", max_length=64)
    hardware_model: str = Field(default="ESP32-S3-N16R8", max_length=64)
    slots: int = Field(default=2, ge=1, le=2)
    remark: str = Field(default="", max_length=200)


class DeviceUpdate(BaseModel):
    device_name: str | None = Field(default=None, max_length=64)
    remark: str | None = Field(default=None, max_length=200)


class SimCardUpdate(BaseModel):
    phone_number: str | None = Field(default=None, max_length=32)
    provider: str | None = Field(default=None, max_length=64)
    plan_name: str | None = Field(default=None, max_length=64)
    plan_expire_at: str | None = None
    carrier: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None
    remark: str | None = Field(default=None, max_length=120)


# --------------------------------------------------------------------------- #
# 设备上报（ESP32 -> Server）
# --------------------------------------------------------------------------- #
class SlotReport(BaseModel):
    """单个 4G 模组（卡槽）的状态上报。

    字段覆盖「模组是否插卡 / 是否注册网络 / 注册详情 / 运营商 / 信号 / 号码」，
    便于用户在管理端一眼看出卡槽到底能不能用。
    """

    slot_index: int = Field(ge=1, le=2)

    # ---- 基础 ----
    phone_number: str | None = Field(default=None, max_length=32)
    carrier: str | None = Field(default=None, max_length=64)
    signal_dbm: int | None = Field(default=None, ge=-140, le=0)
    msisdn: str | None = Field(default=None, max_length=32)

    # ---- 模组与 SIM ----
    # present: 设备是否物理检测到该模组（未接线/未焊 = false）
    present: bool | None = None
    # module_state: off / booting / ready / error
    module_state: str | None = Field(default=None, max_length=16)
    # sim_state: absent / ready / pin_required / error
    sim_state: str | None = Field(default=None, max_length=16)

    # ---- 网络注册 ----
    # registered: 是否已注册到网络
    registered: bool | None = None
    # reg_status: AT+CREG 状态码
    #   0=未注册且未搜索  1=已注册本地网  2=搜索中  3=注册被拒
    #   4=未知  5=已注册漫游
    # 放宽到 0..99：不同模组固件格式差异较大（有的返回粘连值），
    # 服务端以 registered 布尔值为主判断，不因解析差异拒绝整条上报。
    reg_status: int | None = Field(default=None, ge=0, le=99)
    # reg_text: 人类可读描述，如"已注册（本地网络）"
    reg_text: str | None = Field(default=None, max_length=32)
    # lac / cell_id: 位置区码与小区 ID
    lac: str | None = Field(default=None, max_length=16)
    cell_id: str | None = Field(default=None, max_length=32)

    # ---- 信号 ----
    # rssi_csq: 0-31 原始 CSQ，99=未知
    rssi_csq: int | None = Field(default=None, ge=0, le=99)
    # signal_level: 0-4 格，便于前端画信号格
    signal_level: int | None = Field(default=None, ge=0, le=4)

    # ---- 身份识别 ----
    imsi: str | None = Field(default=None, max_length=32)
    iccid: str | None = Field(default=None, max_length=32)
    imei: str | None = Field(default=None, max_length=32)


class DeviceReport(BaseModel):
    firmware_version: str | None = Field(default=None, max_length=32)
    server_version: str | None = Field(default=None, max_length=32)
    local_ip: str | None = Field(default=None, max_length=64)
    wifi_rssi: int | None = Field(default=None, ge=-120, le=0)
    net_mode: Literal["wifi", "4g", "none"] | None = None
    slots: list[SlotReport] = Field(default_factory=list)


class InboundMessage(BaseModel):
    """ESP32 上报的短信 / 来电记录。"""

    kind: Literal["sms", "call", "system"] = "sms"
    slot_index: int = Field(default=1, ge=1, le=2)
    sender: str = Field(default="", max_length=64)
    content: str = Field(default="", max_length=2000)
    received_at: str | None = None
    raw: str | None = Field(default=None, max_length=4000)


class MessageStatusUpdate(BaseModel):
    is_read: bool


# --------------------------------------------------------------------------- #
# 反向控制：发送短信
# --------------------------------------------------------------------------- #
class SendSmsRequest(BaseModel):
    slot_id: int | None = None
    device_id: int | None = None
    target_number: str = Field(min_length=3, max_length=32)
    content: str = Field(min_length=1, max_length=500)


class CommandResult(BaseModel):
    status: Literal["sent", "delivered", "failed"]
    error: str = Field(default="", max_length=500)


# --------------------------------------------------------------------------- #
# OTA / 升级
# --------------------------------------------------------------------------- #
class OtaCreate(BaseModel):
    device_id: int
    version: str = Field(min_length=1, max_length=32)


class OtaUpdate(BaseModel):
    status: Literal["pending", "downloading", "success", "failed", "canceled"]
    error: str = Field(default="", max_length=500)


class ServerUpgradeRequest(BaseModel):
    """ESP32 请求 Server 升级到 Docker Hub 最新镜像。"""

    target_version: str = Field(default="", max_length=32)
    reason: str = Field(default="device-triggered", max_length=200)
