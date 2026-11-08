# -*- coding: utf-8 -*-
"""读串口，只打印可读的关键日志（过滤乱码）"""
import re
import sys
import time

import serial

PORT = "COM4"
BAUD = 115200
SECONDS = int(sys.argv[1]) if len(sys.argv) > 1 else 60

# 只关心这些关键字
KEYS = [
    "SIM=", "ICCID", "IMSI", "cpin", "CPIN", "firmware v",
    "euicc", "eUICC", "enable", "profile", "REG", "reg ",
    "READY", "ABSENT", "CME ERROR", "CFUN", "restart",
    "SLOT1", "SLOT2", "wifi", "server", "ok", "fail",
]

ser = serial.Serial(PORT, BAUD, timeout=0.1)
time.sleep(0.5)
ser.reset_input_buffer()

buf = b""
deadline = time.time() + SECONDS
while time.time() < deadline:
    chunk = ser.read(4096)
    if chunk:
        buf += chunk

ser.close()

text = buf.decode("utf-8", errors="replace")
lines = text.split("\n")
out = []
for ln in lines:
    s = ln.strip()
    if not s:
        continue
    # 计算可打印比例
    printable = sum(1 for c in s if 32 <= ord(c) < 127 or ord(c) > 0x4E00)
    if len(s) >= 8 and printable / len(s) > 0.85:
        if any(k in s for k in KEYS):
            out.append(s)

print(f"收到 {len(buf)} 字节，命中 {len(out)} 行")
print("-" * 60)
for s in out[-60:]:
    print(s[:220])
