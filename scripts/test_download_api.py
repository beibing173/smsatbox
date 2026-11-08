# -*- coding: utf-8 -*-
"""验证写卡 API（后端可用，前端暂隐藏）"""
import json
import urllib.error
import urllib.request

B = "http://127.0.0.1:18097/api/v1"


def rq(p, m="GET", b=None, t=None):
    h = {"Content-Type": "application/json"}
    if t:
        h["Authorization"] = "Bearer " + t
    d = json.dumps(b).encode() if b else None
    r = urllib.request.Request(B + p, data=d, headers=h, method=m)
    try:
        with urllib.request.urlopen(r, timeout=15) as x:
            return x.status, json.loads(x.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


_, lg = rq("/auth/login", "POST", {"username": "admin", "password": "Admin@123456"})
tok = lg["access_token"]

_, dv = rq("/devices", "POST", {"device_name": "写卡测试", "slots": 1}, tok)
did = dv["device"]["id"]

lpa = "LPA:1$smdp.example.com$ABC123"
st, r = rq(
    "/esim/download",
    "POST",
    {"device_id": did, "slot_index": 1, "activation_code": lpa},
    tok,
)
print(f"创建写卡任务 -> {st}")
print(f"  task_id  = {r.get('task_id')}")
print(f"  supported= {r.get('supported')}")
print(f"  smdp     = {r.get('smdp_address')}")
print(f"  matching = {r.get('matching_id')}")
print(f"  message  = {r.get('message', '')[:80]}")

if r.get("task_id"):
    st2, r2 = rq(f"/esim/download/{r['task_id']}", t=tok)
    print(f"\n查询任务 -> {st2}  state={r2.get('state')}")

# 错误激活码应 400
st3, r3 = rq(
    "/esim/download", "POST", {"device_id": did, "slot_index": 1, "activation_code": "BADCODE"}, tok
)
print(f"\n错误激活码 -> {st3}  {r3.get('detail', '')[:40]}")
