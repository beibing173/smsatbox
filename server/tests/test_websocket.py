"""WebSocket 实时通道测试：客户端订阅、设备长连接、指令实时下发。"""

from __future__ import annotations

import json

from app.version import VERSION as APP_VERSION


def _login(client) -> str:
    return client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "Admin@123456"}
    ).json()["access_token"]


def test_client_ws_receives_new_message(client):
    token = _login(client)
    dev = client.post(
        "/api/v1/devices",
        headers={"Authorization": f"Bearer {token}"},
        json={"device_name": "WS盒子", "slots": 1},
    ).json()["device"]

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        hello = json.loads(ws.receive_text())
        assert hello["event"] == "connected"
        assert hello["data"]["version"] == APP_VERSION

        # 设备上报短信 -> 客户端应实时收到 new_message
        res = client.post(
            "/api/v1/device/messages",
            headers={"X-Device-Token": dev["device_token"]},
            json={
                "kind": "sms",
                "slot_index": 1,
                "sender": "10086",
                "content": "您的验证码为 998877",
            },
        )
        assert res.status_code == 201

        event = json.loads(ws.receive_text())
        assert event["event"] == "new_message"
        assert event["data"]["message"]["code"] == "998877"

        ws.send_text("ping")
        pong = json.loads(ws.receive_text())
        assert pong["event"] == "pong"


def test_device_ws_receives_command_in_realtime(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    dev = client.post(
        "/api/v1/devices",
        headers=headers,
        json={"device_name": "实时指令盒子", "slots": 1},
    ).json()["device"]
    slot_id = dev["slots"][0]["id"]

    with client.websocket_connect(
        f"/api/v1/ws/device?token={dev['device_token']}"
    ) as ws:
        hello = json.loads(ws.receive_text())
        assert hello["event"] == "connected"

        send = client.post(
            "/api/v1/messages/send",
            headers=headers,
            json={"slot_id": slot_id, "target_number": "13900139000", "content": "实时下发"},
        ).json()
        assert send["pushed"] is True, send

        event = json.loads(ws.receive_text())
        assert event["event"] == "command"
        assert event["data"]["type"] == "send_sms"
        assert event["data"]["content"] == "实时下发"

        # 设备回写执行结果
        ws.send_text(
            json.dumps(
                {
                    "event": "result",
                    "data": {"command_id": event["data"]["command_id"], "status": "sent"},
                }
            )
        )
        import time

        time.sleep(0.3)
        cmds = client.get("/api/v1/messages/commands/list", headers=headers).json()
        target = next(c for c in cmds["items"] if c["id"] == event["data"]["command_id"])
        assert target["status"] == "sent"


def test_ws_rejects_bad_token(client):
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/v1/ws?token=invalid-token") as ws:
            ws.receive_text()
