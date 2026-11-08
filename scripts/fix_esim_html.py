# -*- coding: utf-8 -*-
"""修复 esim.html 里被吞掉引号的属性，并隐藏写卡区块"""
import re
from pathlib import Path

P = Path(r"D:\SMSATBOX\server\app\static\esim.html")
c = P.read_text(encoding="utf-8")

# 修 downloadSection 的引号 + 默认隐藏
c = c.replace(
    "<section id=downloadSection>",
    '<section id="downloadSection" style="display:none">',
)

P.write_bytes(c.encode("utf-8"))

# 复查
c = P.read_text(encoding="utf-8")
bad = []
for m in re.finditer(r'<[a-zA-Z]+[^>]*?\s(?:id|class)=(?![">])[^\s>]+', c):
    bad.append(m.group(0)[:80])

print("修复完成")
if bad:
    print("仍有问题的属性：")
    for b in bad[:10]:
        print("  ", b)
else:
    print("✓ 所有 id/class 属性都带引号了")

i = c.find("downloadSection")
print("下载区块：", c[max(0, i - 20) : i + 60].replace("\n", " "))
