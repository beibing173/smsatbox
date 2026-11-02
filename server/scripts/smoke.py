"""本地真实进程冒烟脚本（不依赖 pytest）。

用法：
    python scripts/smoke.py http://127.0.0.1:18080
模拟完整链路：管理员登录 -> 建卡 -> 设备联机上报 -> 消息入库 -> 成员授权 -> 反向控制 -> OTA。
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18080"
API = BASE + "/api/v1"

ADMIN = ("admin", "Admin@123456")
PASSED: list[str] = []
FAILED: list[str] = []


def call(method: str, path: str, *, token: str | None = None, body=None, raw=False):
    url = path if path.startswith("http") else API + path
    data = None
    headers = {"X-Client-Version": "1.0.0", "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = resp.read()
            return resp.status, (payload if raw else json.loads(payload or b"{}")), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try:
            parsed = json.loads(payload or b"{}")
        except json.JSONDecodeError:
            parsed = {"raw": payload.decode("utf-8", "replace")}
        return exc.code, parsed, dict(exc.headers)


def check(name: str, cond: bool, extra: str = "") -> None:
    if cond:
        PASSED.append(name)
        print(f"  \033[92m✓\033[0m {name} {extra}")
    else:
        FAILED.append(name)
        print(f"  \033[91m✗\033[0m {name} {extra}")


def main() -> int:
    print(f"\n== SMSATBOX Server 冒烟测试 -> {BASE} ==\n")

    print("[1] 健康检查与版本")
    status, body, headers = call("GET", "/health")
    check("health 200", status == 200, str(body))
    check("版本 v1.0.0", body.get("version") == "1.0.0")
    check("响应头带 X-API-Version", headers.get("x-api-version") == "1.0.0")

    status, body, _ = call("GET", "/version")
    check("version 接口", status == 200 and body["product"] == "SMSATBOX")

    print("\n[2] 管理员登录")
    status, body, _ = call("POST", "/auth/login", body={"username": ADMIN[0], "password": ADMIN[1]})
    check("登录成功", status == 200, f"role={body.get('user', {}).get('role')}")
    admin_token = body.get("access_token", "")
    status, body, _ = call("POST", "/auth/login", body={"username": "admin", "password": "nope"})
    check("错误密码 401", status == 401)
    status, _, _ = call("GET", "/messages")
    check("未授权访问 401", status == 401)

    print("\n[3] 创建设备与卡槽")
    status, body, _ = call(
        "POST",
        "/devices",
        token=admin_token,
        body={"device_name": "冒烟盒子", "hardware_model": "ESP32-S3-N16R8", "slots": 2},
    )
    check("创建设备 201", status == 201)
    device = body["device"]
    dev_token = device["device_token"]
    device_id = device["id"]
    check("Device_Token 已生成", dev_token.startswith("smsat_"))
    check("两个卡槽", len(device["slots"]) == 2)
    slot1_id = device["slots"][0]["id"]

    print("\n[4] 设备上报（Device_Token 鉴权）")
    status, body, _ = call(
        "POST",
        "/device/report",
        body={},
    )
    check("无令牌被拒 401", status == 401)
    status, body, _ = call(
        "POST",
        "/device/report",
        token=None,
        body={},
    )
    # 用设备令牌上报
    req = urllib.request.Request(
        API + "/device/report",
        data=json.dumps(
            {
                "firmware_version": "1.0.0",
                "local_ip": "192.168.1.66",
                "wifi_rssi": -48,
                "net_mode": "wifi",
                "slots": [
                    {"slot_index": 1, "phone_number": "13800138000", "signal_dbm": -63},
                    {"slot_index": 2, "phone_number": "13900139000", "signal_dbm": -70},
                ],
            }
        ).encode(),
        headers={"Content-Type": "application/json", "X-Device-Token": dev_token},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        check("设备状态上报", resp.status == 200, json.loads(resp.read()).get("version", ""))

    status, body, _ = call("GET", f"/devices/{device_id}", token=admin_token)
    detail = body["device"]
    check("设备在线", detail["online"] is True)
    check("固件版本同步", detail["firmware_version"] == "1.0.0")
    check("局域网 IP 同步", detail["local_ip"] == "192.168.1.66")
    check("卡槽号码同步", detail["slots"][0]["phone_number"] == "13800138000")

    print("\n[5] 短信 / 来电入库与验证码提取")
    req = urllib.request.Request(
        API + "/device/messages",
        data=json.dumps(
            {
                "kind": "sms",
                "slot_index": 1,
                "sender": "10690333",
                "content": "【某银行】您正在登录，验证码 730154，请勿泄露。",
            }
        ).encode(),
        headers={"Content-Type": "application/json", "X-Device-Token": dev_token},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read())
    check("短信入库", resp.status == 201)
    check("自动提取验证码", payload["code"] == "730154", payload["code"])

    req = urllib.request.Request(
        API + "/device/messages",
        data=json.dumps(
            {"kind": "call", "slot_index": 2, "sender": "13700137000", "content": "未接来电"}
        ).encode(),
        headers={"Content-Type": "application/json", "X-Device-Token": dev_token},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        json.loads(resp.read())
    check("来电入库", resp.status == 201)

    status, body, _ = call("GET", "/messages?limit=10", token=admin_token)
    check("消息列表可读", status == 200 and body["total"] >= 2, f"total={body.get('total')}")
    status, body, _ = call("GET", "/messages/stats", token=admin_token)
    check("统计接口", body["unread"] >= 2, f"unread={body.get('unread')}")
    status, body, _ = call("GET", "/messages/codes", token=admin_token)
    check("验证码列表", any(c["code"] == "730154" for c in body["items"]))

    print("\n[6] 普通成员 RBAC")
    status, body, _ = call(
        "POST",
        "/users",
        token=admin_token,
        body={
            "username": "smoke_member",
            "password": "Member@123456",
            "display_name": "冒烟成员",
            "role": "member",
        },
    )
    if status == 409:
        _, listing, _ = call("GET", "/users", token=admin_token)
        member_id = next(u["id"] for u in listing["items"] if u["username"] == "smoke_member")
        check("成员已存在（复用）", True)
    else:
        member_id = body["user"]["id"]
        check("创建成员", status == 201)

    status, body, _ = call(
        "PUT",
        f"/users/{member_id}/permissions",
        token=admin_token,
        body={"items": [{"slot_id": slot1_id, "can_read": True, "can_send_sms": True}]},
    )
    check("分配卡槽权限", status == 200)

    status, body, _ = call(
        "POST", "/auth/login", body={"username": "smoke_member", "password": "Member@123456"}
    )
    member_token = body.get("access_token", "")
    check("成员登录", status == 200)
    status, body, _ = call("GET", "/messages", token=member_token)
    slots = {m["slot_id"] for m in body["items"]}
    check("成员只见授权卡槽", slots == {slot1_id}, str(slots))
    status, _, _ = call("GET", "/users", token=member_token)
    check("成员管理接口 403", status == 403)
    status, _, _ = call("GET", "/devices", token=member_token)
    check("成员设备列表可用（已过滤）", status == 200)

    print("\n[7] 反向控制：下发短信")
    status, body, _ = call(
        "POST",
        "/messages/send",
        token=member_token,
        body={"slot_id": slot1_id, "target_number": "13800138000", "content": "冒烟测试短信"},
    )
    check("创建下发指令", status == 201, f"pushed={body.get('pushed')}")
    cmd_id = body["command"]["id"]

    status, body, _ = call("GET", "/device/commands", token=None)
    check("设备轮询需要鉴权", status == 401)
    req = urllib.request.Request(
        API + "/device/commands", headers={"X-Device-Token": dev_token}, method="GET"
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        pending = json.loads(resp.read())
    check("设备取到待发指令", len(pending["items"]) >= 1)
    if pending["items"]:
        item = pending["items"][0]
        check("指令结构正确", item["type"] == "send_sms" and item["slot_index"] == 1)

    req = urllib.request.Request(
        API + f"/device/commands/{cmd_id}",
        data=json.dumps({"status": "delivered"}).encode(),
        headers={"Content-Type": "application/json", "X-Device-Token": dev_token},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        check("设备回写结果", resp.status == 200)

    status, body, _ = call("GET", "/messages/commands/list", token=admin_token)
    target = next((c for c in body["items"] if c["id"] == cmd_id), None)
    check("指令状态已更新", target and target["status"] == "delivered", target and target["status"])

    print("\n[8] OTA 固件上传与设备下载")
    firmware = b"\xE9\x00\x00\x00" + b"SMSATBOX-SMOKE-FW" * 128
    md5 = hashlib.md5(firmware).hexdigest()
    boundary = "----smsatboxsmoke"
    body_bytes = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="version"\r\n\r\n'
        "1.0.1\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="firmware.bin"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + firmware + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        API + f"/devices/{device_id}/ota",
        data=body_bytes,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": "Bearer " + admin_token,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        ota = json.loads(resp.read())
    check("OTA 上传", resp.status == 201, f"md5={ota.get('md5', '')[:8]}")
    check("MD5 一致", ota.get("md5") == md5)

    status, body, _ = call("GET", task_url := f"/ota/download/esp32-1.0.1-{md5[:8]}.bin")
    check("无令牌下载固件 401", status == 401)
    req = urllib.request.Request(
        API + task_url, headers={"X-Device-Token": dev_token}, method="GET"
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        downloaded = resp.read()
    check("设备带令牌下载成功", hashlib.md5(downloaded).hexdigest() == md5)

    print("\n[9] 系统总览 / 审计 / Web 静态资源")
    status, body, _ = call("GET", "/system/overview", token=admin_token)
    check("系统总览", status == 200 and body["stats"]["devices_total"] >= 1)
    status, body, _ = call("GET", "/audit", token=admin_token)
    check("审计日志", status == 200 and len(body["items"]) > 0)
    status, body, _ = call("GET", "/auth/client-tokens", token=admin_token)
    check("客户端令牌列表", status == 200)

    for path, name in [("/", "首页 HTML"), ("/assets/app.js", "前端 JS"), ("/assets/styles.css", "样式"), ("/manifest.webmanifest", "PWA 清单"), ("/sw.js", "Service Worker")]:
        status, _, _ = call("GET", BASE + path, raw=True)
        check(f"静态资源 {name}", status == 200)

    print("\n" + "=" * 52)
    print(f"  通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    if FAILED:
        print("  失败项：" + ", ".join(FAILED))
    print("=" * 52 + "\n")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
