"""ESP32 固件与 Server 的协议一致性验证。

固件本身烧在硬件上才能跑，但**协议对接**可以离线验证：
本脚本用与 cloud.cpp 完全相同的请求头 / 请求体 / 路径，去打真实 Server，
确认两端契约一致——避免"固件编译过了，一上机就 404/401"的经典事故。

用法：
    python scripts/protocol_check.py http://127.0.0.1:18080
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18080"
API = BASE + "/api/v1"
FIRMWARE_VERSION = "1.0.0"   # 与 config.h 的 SMSATBOX_VERSION 一致

PASSED: list[str] = []
FAILED: list[str] = []


def req(method, path, body=None, headers=None, raw=False):
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode() if body is not None else None
    h = {
        "X-Client-Version": FIRMWARE_VERSION,
        "X-Client-Platform": "esp32",
        "X-Client-Hardware": "ESP32-S3-N16R8",
        "Accept": "application/json",
    }
    if body is not None:
        h["Content-Type"] = "application/json"
    if headers:
        h.update(headers)
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            payload = resp.read()
            return resp.status, (payload if raw else json.loads(payload or b"{}"))
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try:
            return exc.code, json.loads(payload or b"{}")
        except json.JSONDecodeError:
            return exc.code, {"raw": payload.decode("utf-8", "replace")}


def check(name, cond, extra=""):
    if cond:
        PASSED.append(name)
        print(f"  \033[92mOK\033[0m  {name} {extra}")
    else:
        FAILED.append(name)
        print(f"  \033[91mFAIL\033[0m {name} {extra}")


def main():
    print(f"\n== ESP32 固件 <-> Server 协议一致性验证 ==\n   Server: {BASE}\n")

    # ---- 1. 管理员登录取设备令牌（模拟管理端创建设备）----
    print("[1] 准备：管理端创建设备，拿到 Device_Token")
    status, body = req(
        "POST", "/auth/login", {"username": "admin", "password": "Admin@123456"}
    )
    check("管理员登录", status == 200, f"v{body.get('version')}")
    admin = body["access_token"]
    auth = {"Authorization": "Bearer " + admin}

    status, body = req(
        "POST",
        "/devices",
        {"device_name": "协议验证盒子", "hardware_model": "ESP32-S3-N16R8", "slots": 2},
        auth,
    )
    check("创建设备", status == 201)
    device = body["device"]
    dev_token = device["device_token"]
    device_id = device["id"]
    slot1 = device["slots"][0]["id"]

    # ---- 2. 设备鉴权头 ----
    print("\n[2] Device_Token 鉴权（固件用 X-Device-Token 头）")
    status, _ = req("POST", "/device/report", {})
    check("无令牌 -> 401", status == 401)
    status, _ = req("POST", "/device/report", {}, {"X-Device-Token": "wrong"})
    check("错误令牌 -> 401", status == 401)

    dev = {"X-Device-Token": dev_token}

    # ---- 3. 心跳上报（cloud::reportStatus 的完整报文）----
    print("\n[3] 心跳上报 POST /device/report")
    status, body = req(
        "POST",
        "/device/report",
        {
            "firmware_version": FIRMWARE_VERSION,
            "local_ip": "192.168.1.77",
            "wifi_rssi": -55,
            "net_mode": "wifi",
            "slots": [
                {"slot_index": 1, "signal_dbm": -63, "phone_number": "13800138000",
                 "carrier": "China Mobile"},
                {"slot_index": 2, "signal_dbm": -71, "phone_number": "13900139000",
                 "carrier": "China Unicom"},
            ],
        },
        dev,
    )
    check("上报成功", status == 200, f"server_version={body.get('server_version')}")
    check("Server 返回自身版本（协同升级依据）",
          body.get("server_version") == FIRMWARE_VERSION,
          body.get("server_version", ""))

    # Server 侧应能看到设备在线与卡槽信息
    status, body = req("GET", f"/devices/{device_id}", None, auth)
    d = body["device"]
    check("设备已在线", d["online"] is True)
    check("固件版本已同步", d["firmware_version"] == FIRMWARE_VERSION)
    check("局域网 IP 已同步", d["local_ip"] == "192.168.1.77")
    check("卡槽1 号码已同步", d["slots"][0]["phone_number"] == "13800138000")
    check("卡槽1 信号已同步", d["slots"][0]["signal_dbm"] == -63)
    check("卡槽2 运营商已同步", d["slots"][1]["carrier"] == "China Unicom")

    # ---- 4. 短信上报（onSms 回调的报文）----
    print("\n[4] 短信上报 POST /device/messages（+CMTI 触发后）")
    status, body = req(
        "POST",
        "/device/messages",
        {
            "kind": "sms",
            "slot_index": 1,
            "sender": "+8613800138000",
            "content": "【验证】您的登录验证码是 246813，5分钟内有效。",
        },
        dev,
    )
    check("短信入库", status == 201, f"code={body.get('code')}")
    check("Server 提取出验证码", body.get("code") == "246813", str(body.get("code")))

    # ---- 5. 来电上报（onCall 回调的报文）----
    print("\n[5] 来电上报 POST /device/messages（+CLIP 触发后）")
    status, body = req(
        "POST",
        "/device/messages",
        {"kind": "call", "slot_index": 2, "sender": "+8613700137000",
         "content": "未接来电"},
        dev,
    )
    check("来电入库", status == 201)
    check("来电不提取验证码", body.get("code") is None)

    # ---- 6. 指令轮询（cloud::pollCommands）----
    print("\n[6] 指令轮询 GET /device/commands")
    status, body = req(
        "POST",
        "/messages/send",
        {"slot_id": slot1, "target_number": "13800138000", "content": "回执测试"},
        auth,
    )
    check("管理端下发短信指令", status == 201)

    status, body = req("GET", "/device/commands", None, dev)
    check("设备轮询成功", status == 200)
    items = body.get("items", [])
    check("取到待执行指令", len(items) >= 1, f"{len(items)} 条")
    if items:
        cmd = items[0]
        check("指令 type=send_sms", cmd.get("type") == "send_sms")
        check("含 command_id", isinstance(cmd.get("command_id"), int))
        check("含 slot_index", cmd.get("slot_index") == 1)
        check("含 target_number", cmd.get("target_number") == "13800138000")
        check("含 version", cmd.get("version") == FIRMWARE_VERSION)

        # ---- 7. 指令结果回写 ----
        print("\n[7] 指令结果回写 POST /device/commands/{id}")
        status, _ = req(
            "POST", f"/device/commands/{cmd['command_id']}", {"status": "sent"}, dev
        )
        check("回写成功", status == 200)
        status, body = req("GET", "/messages/commands/list", None, auth)
        target = next(
            (c for c in body["items"] if c["id"] == cmd["command_id"]), None
        )
        check("Server 侧状态已更新为 sent", target and target["status"] == "sent")

    # ---- 8. OTA 任务轮询与固件下载 ----
    print("\n[8] OTA 任务轮询 GET /device/ota")
    firmware = b"\xE9\x00\x00\x00" + b"SMSATBOX-ESP32-FW" * 200
    md5 = hashlib.md5(firmware).hexdigest()
    boundary = "----smsatboxproto"
    payload = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="version"\r\n\r\n'
        f"1.0.1\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="smsatbox.bin"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + firmware + f"\r\n--{boundary}--\r\n".encode()
    r = urllib.request.Request(
        f"{API}/devices/{device_id}/ota",
        data=payload,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": "Bearer " + admin,
        },
        method="POST",
    )
    with urllib.request.urlopen(r, timeout=30) as resp:
        ota = json.loads(resp.read())
    check("管理端上传固件", resp.status == 201, f"md5={ota['md5'][:8]}")

    status, body = req("GET", "/device/ota", None, dev)
    task = body.get("task")
    check("设备拉到 OTA 任务", task is not None)
    check("任务带 md5（供校验）", task and task.get("md5") == md5)
    check("任务带 url", task and task.get("url", "").startswith("/api/v1/ota/download/"))

    # 设备静默下载
    url = sorted(c for c in [task["url"]] if c)
    r = urllib.request.Request(
        BASE + task["url"], headers={"X-Device-Token": dev_token}, method="GET"
    )
    with urllib.request.urlopen(r, timeout=30) as resp:
        got = resp.read()
    check("设备下载固件", len(got) == len(firmware), f"{len(got)} bytes")
    check("MD5 校验一致", hashlib.md5(got).hexdigest() == md5)

    status, _ = req("POST", f"/device/ota/{task['id']}", {"status": "success"}, dev)
    check("OTA 结果回写", status == 200)
    status, body = req("GET", f"/devices/{device_id}", None, auth)
    check("固件版本已更新到 1.0.1", body["device"]["firmware_version"] == "1.0.1")

    # ---- 9. 设备触发 Server 升级 ----
    print("\n[9] 设备请求 Server 升级 POST /device/server-upgrade")
    status, body = req(
        "POST", "/device/server-upgrade", {"target_version": "1.0.1"}, dev
    )
    check("请求被受理（HTTP 200）", status == 200)
    check("默认安全关闭自动升级", body.get("accepted") is False,
          f"accepted={body.get('accepted')}")

    print("\n" + "=" * 58)
    print(f"  通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    if FAILED:
        print("  失败：" + ", ".join(FAILED))
    print("=" * 58 + "\n")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
