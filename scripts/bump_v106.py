# -*- coding: utf-8 -*-
"""1.0.6 版本号 + 切卡反馈提示"""
import re
from pathlib import Path

ROOT = Path(r"D:\SMSATBOX")
VER = "1.0.6"
CODE = 10006


def rewrite(rel, pairs):
    p = ROOT / rel
    if not p.exists():
        print(f"  ✗ {rel} 不存在")
        return
    c = p.read_text(encoding="utf-8")
    o = c
    for pat, rep in pairs:
        c = re.sub(pat, rep, c)
    if c != o:
        p.write_bytes(c.encode("utf-8"))
        print(f"  ✓ {rel}")
    else:
        print(f"  = {rel}")


for name in ["server", "android", "windows"]:
    (ROOT / f"versions/{name}.txt").write_bytes(VER.encode())
print(f"versions/*.txt -> {VER}")

rewrite("server/app/version.py", [(r'VERSION = "[\d.]+"', f'VERSION = "{VER}"')])
rewrite("server/app/static/app.js", [(r'const VERSION = "[\d.]+";', f'const VERSION = "{VER}";')])
rewrite("server/app/static/sw.js", [(r'const VERSION = "[\d.]+";', f'const VERSION = "{VER}";')])
rewrite("server/app/db.py", [(r"firmware_version TEXT NOT NULL DEFAULT '[\d.]+'",
                              f"firmware_version TEXT NOT NULL DEFAULT '{VER}'")])
rewrite("esp32/include/config.h", [(r'#define SMSATBOX_VERSION "[\d.]+"', f'#define SMSATBOX_VERSION "{VER}"')])
rewrite("esp32/platformio.ini", [
    (r";  版本：v[\d.]+", f";  版本：v{VER}"),
    (r'VERSION_STR=\\"[\d.]+\\"', f'VERSION_STR=\\"{VER}\\"'),
])
rewrite("android/version.properties", [
    (r"VERSION_NAME=[\d.]+", f"VERSION_NAME={VER}"),
    (r"VERSION_CODE=\d+", f"VERSION_CODE={CODE}"),
])
rewrite("android/app/build.gradle.kts", [
    (r'"VERSION_NAME", "[\d.]+"', f'"VERSION_NAME", "{VER}"'),
    (r'"VERSION_CODE", "\d+"', f'"VERSION_CODE", "{CODE}"'),
])
rewrite("windows/SmsatBox.Desktop/SmsatBox.Desktop.csproj", [
    (r"<Version>[\d.]+</Version>", f"<Version>{VER}</Version>"),
    (r"<AssemblyVersion>[\d.]+</AssemblyVersion>", f"<AssemblyVersion>{VER}.0</AssemblyVersion>"),
    (r"<FileVersion>[\d.]+</FileVersion>", f"<FileVersion>{VER}.0</FileVersion>"),
])
rewrite("windows/SmsatBox.Desktop/Core/AppInfo.cs", [
    (r'public const string Version = "[\d.]+";', f'public const string Version = "{VER}";'),
    (r'public const string ClientVersion = "[\d.]+";', f'public const string ClientVersion = "{VER}";'),
])

# ---------------------------------------------------------------------------
# 切卡反馈：esim.html 的操作按钮点了要有明确提示
# ---------------------------------------------------------------------------
p = ROOT / "server/app/static/esim.html"
c = p.read_text(encoding="utf-8")

if "切卡中" not in c:
    c = c.replace(
        '  async function sendCommand(op, iccid, nickname) {',
        '''  async function sendCommand(op, iccid, nickname) {
    // 切卡/停用比较慢（要等模组 CFUN 重启，约 20-30 秒），先给个明确提示
    const slowOps = { enable: "切换中", disable: "停用中", delete: "删除中", refresh: "刷新中" };
    if (slowOps[op]) {
      note(slowOps[op] + "…约需 20-30 秒，请稍候（模组需要重启才能读新卡）");
    }''',
        1,
    )
    p.write_bytes(c.encode("utf-8"))
    print("  ✓ esim.html 切卡提示已加")
else:
    print("  = esim.html 切卡提示已存在")

print()
print(f"版本 -> {VER} (code {CODE})")
