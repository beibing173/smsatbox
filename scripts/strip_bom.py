"""批量清除文本文件里的 UTF-8 BOM。

背景：PowerShell 的 `Set-Content -Encoding UTF8` 会写入 BOM，
导致：
  - PlatformIO 的 configparser 读 platformio.ini 失败
  - Android AAPT 解析 XML 失败
  - Linux 下脚本首行 shebang 失效
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(r"D:\SMSATBOX")

EXTS = {
    ".ini", ".xml", ".kt", ".kts", ".cs", ".xaml", ".py", ".js", ".html", ".css",
    ".h", ".cpp", ".c", ".txt", ".json", ".yml", ".yaml", ".md", ".sh", ".bat",
    ".properties", ".gradle", ".csv", ".toml",
}

SKIP_DIRS = {
    ".git", ".pio", "build", "node_modules", ".gradle", "bin", "obj", ".venv",
    "__pycache__", ".shots", "data", "data-esim", "data-test", "data-test2",
    "data-utf8", "data-verify", "venv", ".idea", ".vs",
}

BOM = b"\xef\xbb\xbf"

fixed: list[str] = []
checked = 0

for path in ROOT.rglob("*"):
    if not path.is_file():
        continue
    # 跳过构建产物/依赖目录
    if any(part in SKIP_DIRS for part in path.parts):
        continue
    if path.suffix.lower() not in EXTS:
        continue

    checked += 1
    try:
        raw = path.read_bytes()
    except OSError:
        continue

    if raw.startswith(BOM):
        body = raw[len(BOM):]
        path.write_bytes(body)
        fixed.append(str(path.relative_to(ROOT)))

print(f"检查 {checked} 个文件，清除 BOM {len(fixed)} 个：")
for f in fixed:
    print("  -", f)

if not fixed:
    print("  （没有需要清理的文件）")
