"""统一升级全平台版本号。

用法：python scripts/bump_version.py 1.0.2 [versionCode]

说明：全部用 UTF-8 无 BOM 写入。PowerShell 的 Set-Content -Encoding UTF8
会写 BOM，曾导致 PlatformIO 读不到 platformio.ini、AAPT 解析 XML 出错。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(r"D:\SMSATBOX")

if len(sys.argv) < 2:
    print("用法: python bump_version.py <新版本号> [versionCode]")
    sys.exit(1)

NEW = sys.argv[1].strip()
parts = NEW.split(".")
if len(parts) != 3 or not all(p.isdigit() for p in parts):
    print(f"版本号格式不对: {NEW}（应为 X.Y.Z）")
    sys.exit(1)

major, minor, patch = (int(p) for p in parts)
CODE = int(sys.argv[2]) if len(sys.argv) > 2 else major * 10000 + minor * 100 + patch

# 读取旧版本
old_file = ROOT / "versions" / "server.txt"
OLD = old_file.read_text(encoding="utf-8").strip() if old_file.exists() else "1.0.0"
old_parts = OLD.split(".")
OLD_CODE = int(old_parts[0]) * 10000 + int(old_parts[1]) * 100 + int(old_parts[2])

print(f"版本升级: {OLD} -> {NEW}    versionCode: {OLD_CODE} -> {CODE}")
print()

# (相对路径, 旧片段, 新片段) —— 精确替换，避免误伤
REPLACEMENTS: list[tuple[str, str, str]] = [
    # 版本文件
    ("versions/server.txt", OLD, NEW),
    ("versions/android.txt", OLD, NEW),
    ("versions/windows.txt", OLD, NEW),
    # Server
    ("server/app/version.py", f'VERSION = "{OLD}"', f'VERSION = "{NEW}"'),
    ("server/app/static/app.js", f'const VERSION = "{OLD}";', f'const VERSION = "{NEW}";'),
    ("server/app/static/sw.js", f'const VERSION = "{OLD}";', f'const VERSION = "{NEW}";'),
    ("server/app/static/index.html", f'id="login-version">v{OLD}<', f'id="login-version">v{NEW}<'),
    ("server/app/static/index.html", f'id="side-version">v{OLD}<', f'id="side-version">v{NEW}<'),
    ("server/app/static/index.html", f'id="mobile-version">v{OLD}<', f'id="mobile-version">v{NEW}<'),
    ("server/app/db.py", f"firmware_version TEXT NOT NULL DEFAULT '{OLD}'",
                        f"firmware_version TEXT NOT NULL DEFAULT '{NEW}'"),
    ("server/app/services/commands.py", f'"version": "{OLD}",', f'"version": "{NEW}",'),
    ("server/app/routers/devices.py", f'or "{OLD}"', f'or "{NEW}"'),
    # ESP32
    ("esp32/include/config.h", f'#define SMSATBOX_VERSION "{OLD}"',
                               f'#define SMSATBOX_VERSION "{NEW}"'),
    ("esp32/platformio.ini", f";  版本：v{OLD}", f";  版本：v{NEW}"),
    ("esp32/platformio.ini", f'-DSMSATBOX_VERSION_STR=\\"{OLD}\\"',
                             f'-DSMSATBOX_VERSION_STR=\\"{NEW}\\"'),
    # Android
    ("android/version.properties", f"VERSION_NAME={OLD}", f"VERSION_NAME={NEW}"),
    ("android/version.properties", f"VERSION_CODE={OLD_CODE}", f"VERSION_CODE={CODE}"),
    ("android/app/build.gradle.kts", f'getProperty("VERSION_NAME", "{OLD}")',
                                     f'getProperty("VERSION_NAME", "{NEW}")'),
    # Windows
    ("windows/SmsatBox.Desktop/SmsatBox.Desktop.csproj",
     f"<Version>{OLD}</Version>", f"<Version>{NEW}</Version>"),
    ("windows/SmsatBox.Desktop/SmsatBox.Desktop.csproj",
     f"<AssemblyVersion>{OLD}.0</AssemblyVersion>", f"<AssemblyVersion>{NEW}.0</AssemblyVersion>"),
    ("windows/SmsatBox.Desktop/SmsatBox.Desktop.csproj",
     f"<FileVersion>{OLD}.0</FileVersion>", f"<FileVersion>{NEW}.0</FileVersion>"),
    ("windows/SmsatBox.Desktop/Core/AppInfo.cs",
     f'public const string Version = "{OLD}";', f'public const string Version = "{NEW}";'),
    ("windows/SmsatBox.Desktop/Core/AppInfo.cs",
     f'public const string ClientVersion = "{OLD}";', f'public const string ClientVersion = "{NEW}";'),
]

changed = 0
for rel, old_s, new_s in REPLACEMENTS:
    p = ROOT / rel
    if not p.exists():
        print(f"  跳过（文件不存在）: {rel}")
        continue
    text = p.read_text(encoding="utf-8")
    if old_s not in text:
        if new_s in text:
            print(f"  已是新值: {rel}")
        else:
            print(f"  未匹配: {rel}  (找 {old_s!r})")
        continue
    count = text.count(old_s)
    text = text.replace(old_s, new_s)
    # UTF-8 无 BOM 写回
    p.write_bytes(text.encode("utf-8"))
    print(f"  ✓ {rel}  ({count} 处)")
    changed += 1

print()
print(f"共修改 {changed} 个文件")
print()
print("=== 校验 ===")
for rel, _, new_s in REPLACEMENTS:
    p = ROOT / rel
    if not p.exists():
        continue
    text = p.read_text(encoding="utf-8")
    ok = new_s in text
    print(f"  {'✓' if ok else '✗'} {rel}")
