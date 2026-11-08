# -*- coding: utf-8 -*-
"""从 spill 输出文件里提取 eUICC 诊断关键结果"""
import re
from pathlib import Path

FILES = [
    r"C:\Users\17367\AppData\Local\Temp\dsh-spill-ORRZtb\session-28d95a6d365e\4542d381aed1-pwsh.txt",
    r"C:\Users\17367\AppData\Local\Temp\dsh-spill-ORRZtb\session-28d95a6d365e\0818d7bb34f1-pwsh.txt",
]

PATTERNS = [
    r"request: [0-9A-F]+",
    r"channel = \d+",
    r"ICCID: \d+",
    r"BCD\s*: [0-9A-F]+",
    r"raw: .*",
    r"dataHex: .*",
    r"RESULT = .*",
    r"dataLen: \d+",
    r"modem OK",
    r"异常状态字: .*",
]

for path in FILES:
    p = Path(path)
    if not p.exists():
        continue
    print(f"=== {p.name} ===")
    text = p.read_text(encoding="utf-8", errors="replace")
    for pat in PATTERNS:
        for m in re.finditer(pat, text):
            line = m.group(0).strip()
            # 过滤掉纯乱码
            printable = sum(1 for c in line if 32 <= ord(c) < 127)
            if printable >= len(line) * 0.8:
                print("  ", line[:200])
    print()
