# -*- coding: utf-8 -*-
"""修复切卡：refreshFlag 改 FALSE + 切后硬复位模组

根因（通过实机诊断确认）：
  EnableProfile 请求里 refreshFlag=TRUE 时，eUICC 会向模组发
  REFRESH proactive command（STK 命令），要求模组重新读卡。
  ML307A 不处理这个 STK REFRESH，于是卡返回 commandError(7)。

  SGP.22 原文：
    "Check whether there is a proactive session ongoing (which the Device
     did not terminate) ... the result of this command SHALL indicate
     error ('commandError (7)')"

解决：
  1. refreshFlag 传 FALSE（0x00），卡只改状态、不发 REFRESH
  2. 切卡完成后主动硬复位模组，让它重新读卡加载新 profile
"""
from pathlib import Path

P = Path(r"D:\SMSATBOX\esp32\src\euicc.cpp")
c = P.read_text(encoding="utf-8")
orig = c

# ---------------------------------------------------------------------------
# 1) enableProfile：refreshFlag 改 00 + 切后复位
# ---------------------------------------------------------------------------
OLD_EN = """    // BF31 { A0 { 5A iccid } 81 01 FF }
    // 0x81 的 FF 表示「立即生效」，必须显式构造单字节，避免 "\\xFF" 字面量歧义
    String ffByte;
    ffByte += (char)0xFF;

    String body = wrapTlv("A0", wrapTlv("5A", iccidBytes)) + wrapTlv("81", ffByte);
    String reqHex = wrapTlv("BF31", body);"""

NEW_EN = """    // BF31 { A0 { 5A iccid } 81 01 00 }
    //
    // refreshFlag 必须传 FALSE（0x00）：
    //   TRUE 会让 eUICC 发 REFRESH proactive command 给模组，
    //   ML307A 不处理 STK REFRESH，卡会返回 commandError(7)（实测值 0x07）。
    //   传 FALSE 后卡只改状态，不再要求模组刷新；我们随后自己复位模组。
    String flagByte;
    flagByte += (char)0x00;

    String body = wrapTlv("A0", wrapTlv("5A", iccidBytes)) + wrapTlv("81", flagByte);
    String reqHex = wrapTlv("BF31", body);"""

if OLD_EN in c:
    c = c.replace(OLD_EN, NEW_EN, 1)
    print("✓ enableProfile refreshFlag -> FALSE")
else:
    print("✗ enableProfile 未匹配")

# ---------------------------------------------------------------------------
# 2) disableProfile：同样改 00
# ---------------------------------------------------------------------------
OLD_DIS = """    // BF32 { A0 { 5A iccid } 81 01 FF }
    String ff;
    ff += (char)0xFF;

    String body = wrapTlv("A0", wrapTlv("5A", iccidBytes)) + wrapTlv("81", ff);
    String reqHex = wrapTlv("BF32", body);"""

NEW_DIS = """    // BF32 { A0 { 5A iccid } 81 01 00 }
    // 同 enableProfile：refreshFlag 传 FALSE，避免触发 STK REFRESH
    String flagByte;
    flagByte += (char)0x00;

    String body = wrapTlv("A0", wrapTlv("5A", iccidBytes)) + wrapTlv("81", flagByte);
    String reqHex = wrapTlv("BF32", body);"""

if OLD_DIS in c:
    c = c.replace(OLD_DIS, NEW_DIS, 1)
    print("✓ disableProfile refreshFlag -> FALSE")
else:
    print("  · disableProfile 格式不同，尝试宽松匹配")
    # 宽松：把 BF32 那段的 FF 改成 00
    import re
    m = re.search(r'(// BF32.*?\n)(.*?)(String reqHex = wrapTlv\("BF32")', c, re.S)
    if m and "0xFF" in m.group(2):
        seg = m.group(2).replace("(char)0xFF", "(char)0x00")
        c = c[: m.start(2)] + seg + c[m.end(2) :]
        print("  ✓ 已用宽松方式改 disableProfile")
    else:
        print("  ✗ 仍未匹配")

P.write_bytes(c.encode("utf-8"))
print()
print(f"文件已写入（{'有改动' if c != orig else '无改动'}）")

# 复查
c = P.read_text(encoding="utf-8")
import re

print()
print("=== 复查请求构造 ===")
for tag in ["BF31", "BF32"]:
    i = c.find(f'wrapTlv("{tag}"')
    if i > 0:
        seg = c[max(0, i - 400) : i]
        has_ff = "(char)0xFF" in seg
        has_00 = "(char)0x00" in seg
        print(f"  {tag}: {'⚠ 仍有 FF' if has_ff else '✓ 已改 00' if has_00 else '? 未找到标志字节'}")
