"""服务端端到端测试：鉴权、RBAC、设备上报、反向控制、OTA。"""

from __future__ import annotations

import hashlib


def test_health_and_version(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["version"] == "1.0.0"
    # 全平台约定：响应头带版本
    assert res.headers["X-API-Version"] == "1.0.0"

    ver = client.get("/api/v1/version").json()
    assert ver["product"] == "SMSATBOX"
    assert ver["api_prefix"] == "/api/v1"


def test_login_success_and_failure(client):
    ok = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "Admin@123456"}
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["role"] == "superadmin"
    assert body["version"] == "1.0.0"
    assert "password_hash" not in body["user"]

    bad = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "wrong-pass"}
    )
    assert bad.status_code == 401


def test_unauthorized_access(client):
    assert client.get("/api/v1/messages").status_code == 401
    assert client.get("/api/v1/devices").status_code == 401


def test_me(client, admin_headers):
    res = client.get("/api/v1/auth/me", headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["user"]["username"] == "admin"


def test_device_lifecycle_and_message_flow(client, admin_headers):
    # 1) 创建设备
    res = client.post(
        "/api/v1/devices",
        headers=admin_headers,
        json={"device_name": "测试盒子", "hardware_model": "ESP32-S3-N16R8", "slots": 2},
    )
    assert res.status_code == 201, res.text
    device = res.json()["device"]
    device_token = device["device_token"]
    device_id = device["id"]
    assert device_token.startswith("smsat_")
    assert len(device["slots"]) == 2

    # 2) 设备鉴权失败
    bad = client.post("/api/v1/device/report", headers={"X-Device-Token": "bad"}, json={})
    assert bad.status_code == 401

    # 3) 设备上报状态
    rep = client.post(
        "/api/v1/device/report",
        headers={"X-Device-Token": device_token},
        json={
            "firmware_version": "1.0.0",
            "local_ip": "192.168.1.50",
            "wifi_rssi": -52,
            "net_mode": "wifi",
            "slots": [
                {"slot_index": 1, "phone_number": "13800138000", "signal_dbm": -67},
                {"slot_index": 2, "phone_number": "13900139000", "signal_dbm": -71},
            ],
        },
    )
    assert rep.status_code == 200, rep.text

    detail = client.get(f"/api/v1/devices/{device_id}", headers=admin_headers).json()["device"]
    assert detail["firmware_version"] == "1.0.0"
    assert detail["local_ip"] == "192.168.1.50"
    assert detail["slots"][0]["phone_number"] == "13800138000"

    # 4) 上报短信（含验证码）
    msg = client.post(
        "/api/v1/device/messages",
        headers={"X-Device-Token": device_token},
        json={
            "kind": "sms",
            "slot_index": 1,
            "sender": "10690001",
            "content": "【示例】您的验证码是 483920，5分钟内有效。",
        },
    )
    assert msg.status_code == 201, msg.text
    payload = msg.json()
    assert payload["code"] == "483920"

    # 5) 上报未接来电
    call = client.post(
        "/api/v1/device/messages",
        headers={"X-Device-Token": device_token},
        json={"kind": "call", "slot_index": 2, "sender": "13700137000", "content": "未接来电"},
    )
    assert call.status_code == 201
    assert call.json()["code"] is None

    # 6) 管理员查看消息
    listing = client.get("/api/v1/messages", headers=admin_headers).json()
    assert listing["total"] >= 2
    kinds = {m["kind"] for m in listing["items"]}
    assert "sms" in kinds and "call" in kinds

    stats = client.get("/api/v1/messages/stats", headers=admin_headers).json()
    assert stats["total"] >= 2
    assert stats["codes"] >= 1

    # 7) 验证码列表
    codes = client.get("/api/v1/messages/codes", headers=admin_headers).json()
    assert any(c["code"] == "483920" for c in codes["items"])


def test_rbac_member_only_sees_granted_slot(client, admin_headers):
    # 准备：创建带一台设备和两个卡槽
    dev = client.post(
        "/api/v1/devices",
        headers=admin_headers,
        json={"device_name": "权限盒子", "slots": 2},
    ).json()["device"]
    token = dev["device_token"]
    slot_a, slot_b = dev["slots"][0]["id"], dev["slots"][1]["id"]

    client.post(
        "/api/v1/device/messages",
        headers={"X-Device-Token": token},
        json={"kind": "sms", "slot_index": 1, "sender": "A1", "content": "卡槽1 的消息"},
    )
    client.post(
        "/api/v1/device/messages",
        headers={"X-Device-Token": token},
        json={"kind": "sms", "slot_index": 2, "sender": "B1", "content": "卡槽2 的消息"},
    )

    # 创建普通成员
    created = client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "username": "member1",
            "password": "Member@123456",
            "display_name": "小成员",
            "role": "member",
        },
    )
    assert created.status_code == 201, created.text
    member_id = created.json()["user"]["id"]

    # 只授权卡槽 A
    perm = client.put(
        f"/api/v1/users/{member_id}/permissions",
        headers=admin_headers,
        json={"items": [{"slot_id": slot_a, "can_read": True, "can_send_sms": False}]},
    )
    assert perm.status_code == 200, perm.text

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "member1", "password": "Member@123456"},
    ).json()
    member_headers = {"Authorization": f"Bearer {login['access_token']}"}

    # 成员只能看到卡槽 A 的消息
    listing = client.get("/api/v1/messages", headers=member_headers).json()
    slot_ids = {m["slot_id"] for m in listing["items"]}
    assert slot_ids == {slot_a}

    # 成员无权访问卡槽 B
    denied = client.get(
        f"/api/v1/messages?slot_id={slot_b}", headers=member_headers
    )
    assert denied.status_code == 403

    # 成员不能执行管理操作
    assert client.get("/api/v1/users", headers=member_headers).status_code == 403
    assert (
        client.post(
            "/api/v1/devices", headers=member_headers, json={"device_name": "x"}
        ).status_code
        == 403
    )

    # 成员没有发短信权限时被拒绝
    assert (
        client.post(
            "/api/v1/messages/send",
            headers=member_headers,
            json={"slot_id": slot_a, "target_number": "13800138000", "content": "hi"},
        ).status_code
        == 403
    )

    # 授予发短信权限后可以下发
    client.put(
        f"/api/v1/users/{member_id}/permissions",
        headers=admin_headers,
        json={"items": [{"slot_id": slot_a, "can_read": True, "can_send_sms": True}]},
    )
    sent = client.post(
        "/api/v1/messages/send",
        headers=member_headers,
        json={"slot_id": slot_a, "target_number": "13800138000", "content": "测试下发"},
    )
    assert sent.status_code == 201, sent.text
    assert sent.json()["command"]["status"] == "pending"
    assert sent.json()["pushed"] is False  # 设备没有 WS 连接

    # 设备通过 HTTP 轮询拿到指令
    pending = client.get(
        "/api/v1/device/commands", headers={"X-Device-Token": token}
    ).json()
    assert len(pending["items"]) >= 1
    cmd = pending["items"][0]
    assert cmd["type"] == "send_sms"
    assert cmd["slot_index"] == 1

    # 设备回写结果
    done = client.post(
        f"/api/v1/device/commands/{cmd['command_id']}",
        headers={"X-Device-Token": token},
        json={"status": "sent"},
    )
    assert done.status_code == 200

    cmds = client.get("/api/v1/messages/commands/list", headers=admin_headers).json()
    target = [c for c in cmds["items"] if c["id"] == cmd["command_id"]][0]
    assert target["status"] == "sent"


def test_ota_upload_and_poll(client, admin_headers):
    dev = client.post(
        "/api/v1/devices", headers=admin_headers, json={"device_name": "OTA盒子", "slots": 1}
    ).json()["device"]
    device_id, token = dev["id"], dev["device_token"]

    firmware = b"\xE9\x00\x00\x00" + b"SMSATBOX-FAKE-FIRMWARE" * 64
    res = client.post(
        f"/api/v1/devices/{device_id}/ota",
        headers=admin_headers,
        data={"version": "1.0.1"},
        files={"file": ("firmware.bin", firmware, "application/octet-stream")},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["md5"] == hashlib.md5(firmware).hexdigest()
    assert body["size"] == len(firmware)

    # 设备拉取 OTA
    task = client.get("/api/v1/device/ota", headers={"X-Device-Token": token}).json()["task"]
    assert task is not None
    assert task["version"] == "1.0.1"
    assert task["md5"] == body["md5"]

    # 无令牌下载固件应被拒绝
    assert client.get(task["url"]).status_code == 401

    # 带设备令牌下载
    download = client.get(task["url"], headers={"X-Device-Token": token})
    assert download.status_code == 200
    assert hashlib.md5(download.content).hexdigest() == body["md5"]

    # 回写成功，固件版本随之更新
    client.post(
        f"/api/v1/device/ota/{task['id']}",
        headers={"X-Device-Token": token},
        json={"status": "success"},
    )
    detail = client.get(f"/api/v1/devices/{device_id}", headers=admin_headers).json()["device"]
    assert detail["firmware_version"] == "1.0.1"


def test_reject_non_bin_firmware(client, admin_headers):
    dev = client.post(
        "/api/v1/devices", headers=admin_headers, json={"device_name": "拒绝测试", "slots": 1}
    ).json()["device"]
    res = client.post(
        f"/api/v1/devices/{dev['id']}/ota",
        headers=admin_headers,
        data={"version": "1.0.1"},
        files={"file": ("evil.txt", b"hello", "text/plain")},
    )
    assert res.status_code == 400


def test_client_token_flow(client):
    login = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "Admin@123456"}
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    created = client.post(
        "/api/v1/auth/client-tokens", headers=headers, json={"name": "apk"}
    ).json()
    raw = created["token"]
    assert raw.startswith("u_")

    verify = client.get("/api/v1/auth/verify", headers={"Authorization": f"Bearer {raw}"})
    assert verify.status_code == 200
    assert verify.json()["ok"] is True

    listing = client.get("/api/v1/auth/client-tokens", headers=headers).json()
    token_id = listing["items"][0]["id"]
    assert client.delete(f"/api/v1/auth/client-tokens/{token_id}", headers=headers).status_code == 200


def test_server_upgrade_guard(client):
    # 默认未启用自动升级，应返回 accepted=false 而不是执行命令
    login = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "Admin@123456"}
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    d = client.post(
        "/api/v1/devices", headers=headers, json={"device_name": "升级测试", "slots": 1}
    ).json()["device"]
    res = client.post(
        "/api/v1/device/server-upgrade",
        headers={"X-Device-Token": d["device_token"]},
        json={"target_version": "1.0.1"},
    )
    assert res.status_code == 200
    assert res.json()["accepted"] is False


def test_system_overview(client, admin_headers):
    data = client.get("/api/v1/system/overview", headers=admin_headers).json()
    assert data["version"] == "1.0.0"
    assert data["stats"]["devices_total"] >= 1


def test_static_web_ui(client):
    index = client.get("/")
    assert index.status_code == 200
    assert "SMSATBOX" in index.text
    assert "v1.0.0" in index.text

    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/assets/styles.css").status_code == 200
    assert client.get("/manifest.webmanifest").status_code == 200
    assert client.get("/sw.js").status_code == 200
