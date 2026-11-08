# -*- coding: utf-8 -*-
"""精准改 euicc.cpp：refreshFlag 从 0xFF 改成 0x00

实机诊断确认：refreshFlag=TRUE 时 eUICC 发 REFRESH 主动命令给模组，
ML307A 不处理 STK REFRESH，卡返回 commandError(7)。
改 FALSE 后卡只改状态不发 REFRESH，随后由 restart 让模组重新读卡。
"""
from pathlib import Path

P = Path(r"D:\SMSATBOX\esp32\src\euicc.cpp")
lines = P.read_text(encoding="utf-8").splitlines(keepends=True)

changed = []
for i, line in enumerate(lines):
    # 只改 "ffByte += (char)0xFF;" 和 "ff += (char)0xFF;" 这类单字节构造
    if "(char)0xFF" in line and ("ffByte" in line or "ff +=" in line):
        lines[i] = line.replace("(char)0xFF", "(char)0x00")
        changed.append(i + 1)

P.write_bytes("".join(lines).encode("utf-8"))

print(f"✓ 改了 {len(changed)} 处 refreshFlag: 行 {changed}")
print()

# 复查
c = P.read_text(encoding="utf-8")
print("=== 复查 ===")
for i, line in enumerate(c.splitlines(), 1):
    if "char)0xFF" in line or "char)0x00" in line:
        print(f"  L{i}: {line.strip()}")
