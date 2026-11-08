"""为设备详情弹窗截图准备数据：设备 + eUICC + 多个 profile"""
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:18093"
ADMIN = {"username": "admin", "password": "Admin@123456"}


def req(path: str, method: str = "GET", body=None, token=None, dtoken=None):
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if dtoken:
        headers["X-Device-Token"] = dtoken
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=20) as x:
            return x.status, json.loads(x.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


_, login = req("/api/v1/auth/login", "POST", ADMIN)
tok = login["access_token"]
user = login["user"]

print("=== 造设备 ===")
_, dev = req("/api/v1/devices", "POST", {"device_name": "客厅盒子", "slots": 2}, tok)
d = dev["device"]
dtoken = d["device_token"]
print(f"  设备 #{d['id']} {d['device_name']}")

print("=== 上报模组状态 ===")
req("/api/v1/device/report", "POST", {
    "firmware_version": "1.0.1",
    "local_ip": "192.168.3.61",
    "wifi_rssi": -44,
    "net_mode": "wifi",
    "slots": [
        {
            "slot_index": 1, "present": True, "module_state": "ready",
            "sim_state": "ready", "registered": True, "reg_status": 7,
            "reg_text": "已注册·漫游（仅短信）", "rssi_csq": 25, "signal_dbm": -63,
            "signal_level": 4, "phone_number": "+16063741096",
            "carrier": "46001", "imsi": "454006395172165",
            "imei": "202090023561114173",
        },
        {"slot_index": 2, "present": False, "module_state": "absent"},
    ],
}, dtoken=dtoken)
print("  ✓ 已上报")

print("=== 上报 eUICC（4 个 profile）===")
req("/api/v1/device/esim/report", "POST", {
    "slot_index": 1, "present": True,
    "eid": "89086030202200000026000012149528",
    "installed_apps": 4,
    "free_nonvolatile": 480000,
    "free_volatile": 12000,
    "user_enabled": True,
    "profiles": [
        {"iccid": "8985230000000000001", "state": 1, "nickname": "HK Lucky2",
         "provider": "Lucky2", "profile_name": "Lucky2"},
        {"iccid": "8985230000000000002", "state": 0, "nickname": "CMHK 香港",
         "provider": "China Mobile HK", "profile_name": "CMHK-4G"},
        {"iccid": "8985230000000000003", "state": 0, "nickname": "日本旅游卡",
         "provider": "IIJmio", "profile_name": "JP-Travel"},
        {"iccid": "8985230000000000004", "state": 0, "nickname": "美国备用",
         "provider": "T-Mobile", "profile_name": "US-Backup"},
    ],
}, dtoken=dtoken)
print("  ✓ 已上报")

_, lst = req("/api/v1/esim", token=tok)
print(f"\n=== 验证 ===\n  eUICC 共 {len(lst['items'])} 张")
for it in lst["items"]:
    print(f"    设备={it['device_name']} 槽{it['slot_index']} EID={it['eid'][:16]}...")
    for p in it["profiles"]:
        st = "使用中" if p["state"] == 1 else "未启用"
        print(f"      · [{st}] {p['nickname']} ({p['iccid']})")

# 输出登录信息供截图脚本使用
with open(r"D:\SMSATBOX\.shots\_ui_creds.json", "w", encoding="utf-8") as fh:
    json.dump({"token": tok, "user": user, "device_id": d["id"]}, fh, ensure_ascii=False)
print("\n凭证已保存")
