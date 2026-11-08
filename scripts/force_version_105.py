# -*- coding: utf-8 -*-
"""强制把所有版本号写成 1.0.5（不依赖链式匹配），并删登录页版本号文本"""
import re
from pathlib import Path

ROOT = Path(r"D:\SMSATBOX")
VER = "1.0.5"
CODE = 10005


def w(rel: str, content: str) -> None:
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content.encode("utf-8"))


# ---------------------------------------------------------------------------
# 1) versions/*.txt —— 直接覆盖
# ---------------------------------------------------------------------------
for name in ["server", "android", "windows"]:
    w(f"versions/{name}.txt", VER)
print(f"✓ versions/*.txt -> {VER}")

# ---------------------------------------------------------------------------
# 2) 正则替换所有 "1.0.x" 版本字段
# ---------------------------------------------------------------------------
def rewrite(rel: str, patterns: list[tuple[str, str]]) -> None:
    p = ROOT / rel
    if not p.exists():
        print(f"  ✗ {rel} 不存在")
        return
    c = p.read_text(encoding="utf-8")
    orig = c
    for pat, rep in patterns:
        c = re.sub(pat, rep, c)
    if c != orig:
        p.write_bytes(c.encode("utf-8"))
        print(f"  ✓ {rel}")
    else:
        print(f"  = {rel}（无变化）")


rewrite("server/app/version.py", [(r'VERSION = "[\d.]+"', f'VERSION = "{VER}"')])
rewrite("server/app/static/app.js", [(r'const VERSION = "[\d.]+";', f'const VERSION = "{VER}";')])
rewrite("server/app/static/sw.js", [(r'const VERSION = "[\d.]+";', f'const VERSION = "{VER}";')])
rewrite("server/app/static/index.html", [(r'id="(set-server-ver|side-version|login-version|mobile-version)">v[\d.]+',
                                         lambda m: f'id="{m.group(1)}">v{VER}')])
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
# 3) 删登录页的版本号 TextView（整块）
# ---------------------------------------------------------------------------
p = ROOT / "android/app/src/main/res/layout/activity_login.xml"
c = p.read_text(encoding="utf-8")
c2 = re.sub(
    r'\s*<TextView\s+android:id="@\+id/versionText"[\s\S]*?android:gravity="center"\s*/>',
    "",
    c,
    count=1,
)
if c2 != c:
    p.write_bytes(c2.encode("utf-8"))
    print("  ✓ 删登录页版本号 TextView")
else:
    print("  ✗ 登录页版本号未匹配")

print()
print("=== 最终版本确认 ===")
for rel in ["versions/server.txt", "versions/android.txt", "versions/windows.txt",
            "android/version.properties", "esp32/include/config.h"]:
    print(f"  {rel}: {Path(ROOT / rel).read_text(encoding='utf-8').strip().splitlines()[-1]}")
