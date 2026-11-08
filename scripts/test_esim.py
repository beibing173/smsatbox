"""eSIM 模块端到端验证"""
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:18090"
USER = {"username": "admin", "password": "Admin@123456"}


def req(path: str, method: str = "GET", body=None, token=None):
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=25) as x:
            return x.status, x.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


print("=== 1. 静态资源 ===")
st, body = req("/assets/esim.html")
print(f"  /assets/esim.html -> {st}, {len(body)} bytes")
print(f"  含 'eSIM 工作台': { 'eSIM 工作台'.encode() in body }")
print(f"  含 'profileList': { b'profileList' in body }")

st, body = req("/")
print(f"  / -> {st}, {len(body)} bytes")
print(f"  含 nav-esim 入口: { b'nav-esim' in body }")

print("\n=== 2. eSIM API ===")
st, body = req("/api/v1/auth/login", "POST", USER)
tok = json.loads(body)["access_token"]
print(f"  登录 -> {st}")

st, body = req("/api/v1/esim", token=tok)
data = json.loads(body)
print(f"  GET /esim -> {st}, {len(data['items'])} 张卡")
for it in data["items"]:
    print(f"    卡槽{it['slot_index']} ({it['device_name']})")
    print(f"      EID: {it['eid']}")
    print(f"      容量: 已装{it['installed_apps']} / 剩余{it['free_nonvolatile']}")
    print(f"      开关: {'开' if it['user_enabled'] else '关'}")
    for p in it["profiles"]:
        state = "使用中" if p["state"] == 1 else "未启用"
        print(f"      · {p['iccid']} [{state}] {p['nickname']}")

print("\n=== 3. 未检测到 eUICC 时的行为 ===")
_, body = req("/api/v1/devices", token=tok)
devices = json.loads(body)["items"]
if devices:
    dev = devices[0]
    st, body = req(
        "/api/v1/device/esim/report",
        "POST",
        {"slot_index": 2, "present": False},
        token=None,
    )
    # 设备上报需要 device token，这里只验证 schema 不崩
    print(f"  slot2 present=false 上报 -> {st}")

print("\n=== 4. 指令流程 ===")
if data["items"]:
    it = data["items"][0]
    st, body = req(
        "/api/v1/esim/command",
        "POST",
        {
            "device_id": it["device_id"],
            "slot_index": it["slot_index"],
            "operation": "disable",
            "iccid": it["profiles"][0]["iccid"] if it["profiles"] else "8985201234567890123",
        },
        tok,
    )
    print(f"  下发停用指令 -> {st} {json.loads(body) if body else ''}")

    st, body = req("/api/v1/esim/commands?limit=10", token=tok)
    items = json.loads(body)["items"]
    print(f"  指令历史 -> {st}, {len(items)} 条")
    for c in items[:3]:
        print(f"    #{c['id']} {c['operation']} {c['status']} iccid={c['iccid']}")

print("\n=== 5. 开关功能 ===")
if data["items"]:
    eid_id = data["items"][0]["id"]
    st, body = req(f"/api/v1/esim/{eid_id}/toggle", "PATCH", {"user_enabled": False}, tok)
    print(f"  关闭 -> {st} {json.loads(body)}")
    st, body = req(f"/api/v1/esim/{eid_id}/toggle", "PATCH", {"user_enabled": True}, tok)
    print(f"  开启 -> {st} {json.loads(body)}")

print("\n全部验证完成")
