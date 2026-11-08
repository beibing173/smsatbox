"""截图设备详情弹窗（含 eSIM 区块）"""
import json
import os
import subprocess

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE = "http://127.0.0.1:18093"
STATIC = r"D:\SMSATBOX\server\app\static"
SHOTS = r"D:\SMSATBOX\.shots"

with open(os.path.join(SHOTS, "_ui_creds.json"), encoding="utf-8") as fh:
    creds = json.load(fh)

token = creds["token"]
user = creds["user"]
did = creds["device_id"]

html = (
    '<!doctype html><html><head><meta charset="utf-8"></head><body>'
    "<script>"
    "localStorage.setItem('smsatbox.token'," + json.dumps(token) + ");"
    "localStorage.setItem('smsatbox.user'," + json.dumps(json.dumps(user)) + ");"
    "localStorage.setItem('smsatbox.theme','light');"
    "location.replace('/#devices/" + str(did) + "');"
    "</script></body></html>"
)
bootstrap = os.path.join(STATIC, "_ui_boot.html")
with open(bootstrap, "w", encoding="utf-8") as fh:
    fh.write(html)

os.makedirs(SHOTS, exist_ok=True)
out = os.path.join(SHOTS, "device-detail-esim.png")

cmd = [
    CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
    "--window-size=1400,1400", "--virtual-time-budget=12000",
    f"--screenshot={out}",
    BASE + "/assets/_ui_boot.html",
]
res = subprocess.run(cmd, capture_output=True, timeout=120)
print("截图:", out, os.path.getsize(out) if os.path.exists(out) else "失败")
if os.path.exists(out) is False:
    print(res.stderr.decode("utf-8", "replace")[:500])

os.remove(bootstrap)
