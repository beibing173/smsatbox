"""截图 eSIM 工作台界面（注入登录态后渲染）"""
import base64
import json
import os
import shutil
import subprocess
import urllib.request

BASE = "http://127.0.0.1:18090"
SERVER_DIR = r"D:\SMSATBOX\server"
STATIC = os.path.join(SERVER_DIR, "app", "static")
SHOTS = r"D:\SMSATBOX\.shots"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def post(path: str, body):
    r = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(r, timeout=20) as x:
        return json.loads(x.read())


login = post("/api/v1/auth/login", {"username": "admin", "password": "Admin@123456"})
token = login["access_token"]
user = login["user"]

# 造两台设备的 eSIM 数据，看双卡槽效果
r = urllib.request.Request(
    BASE + "/api/v1/devices",
    data=json.dumps({"device_name": "客厅盒子", "slots": 2}).encode(),
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
    method="POST",
)
try:
    dev = json.loads(urllib.request.urlopen(r, timeout=20).read())["device"]
    dtoken = dev["device_token"]

    def device_post(path, body):
        rr = urllib.request.Request(
            BASE + path,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "X-Device-Token": dtoken},
            method="POST",
        )
        with urllib.request.urlopen(rr, timeout=20) as x:
            return x.status

    # 卡槽1 有 eUICC，卡槽2 没有
    device_post("/api/v1/device/esim/report", {
        "slot_index": 1, "present": True,
        "eid": "89049032005008882600031418673526",
        "installed_apps": 3, "free_nonvolatile": 512000, "free_volatile": 16384,
        "user_enabled": True,
        "profiles": [
            {"iccid": "8985201234567890123", "state": 1, "nickname": "主力卡·移动",
             "provider": "China Mobile", "profile_name": "CMCC-5G"},
            {"iccid": "8985209876543210987", "state": 0, "nickname": "备用卡·联通",
             "provider": "China Unicom", "profile_name": "CU-4G"},
            {"iccid": "8985205555666677778", "state": 0, "nickname": "香港旅游卡",
             "provider": "CSL", "profile_name": "HK-Travel"},
        ],
    })
    print("已造 3 个 profile 数据")
except Exception as exc:  # noqa: BLE001
    print("造数据:", exc)

# 注入登录态的跳板页
html = (
    '<!doctype html><html><head><meta charset="utf-8"></head><body>'
    "<script>"
    "localStorage.setItem('smsatbox.token','" + token + "');"
    "localStorage.setItem('smsatbox.user',JSON.stringify(" + json.dumps(user) + "));"
    "localStorage.setItem('smsatbox.theme','light');"
    "location.replace('/assets/esim.html');"
    "</script></body></html>"
)
bootstrap = os.path.join(STATIC, "_esim_boot.html")
with open(bootstrap, "w", encoding="utf-8") as fh:
    fh.write(html)

os.makedirs(SHOTS, exist_ok=True)
out_png = os.path.join(SHOTS, "esim-panel.png")

cmd = [
    CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
    "--window-size=1280,1100", "--virtual-time-budget=9000",
    f"--screenshot={out_png}",
    BASE + "/assets/_esim_boot.html",
]
subprocess.run(cmd, capture_output=True, timeout=90)
print("截图:", out_png, os.path.getsize(out_png) if os.path.exists(out_png) else "失败")

os.remove(bootstrap)
