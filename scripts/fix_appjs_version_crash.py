# -*- coding: utf-8 -*-
"""修复 app.js 版本号赋值导致的空引用崩溃（这是 eSIM 点不进去的元凶）"""
from pathlib import Path

P = Path(r"D:\SMSATBOX\server\app\static\app.js")
c = P.read_text(encoding="utf-8")

OLD = '''    $("#side-version").textContent = "v" + v.version;
    $("#login-version").textContent = "v" + v.version;
    $("#mobile-version").textContent = "v" + v.version;'''

NEW = '''    // 版本号只在「设置 → 版本更新」一处展示，其余位置已移除；
    // 这里必须判空：元素不存在时直接 .textContent 会抛 TypeError，
    // 导致后面整段脚本（含导航、eSIM 入口）全部失效。
    const setVer = (id, text) => {
      const el = document.getElementById(id);
      if (el) el.textContent = text;
    };
    setVer("side-version", "v" + v.version);
    setVer("login-version", "v" + v.version);
    setVer("mobile-version", "v" + v.version);'''

if OLD in c:
    c = c.replace(OLD, NEW, 1)
    P.write_bytes(c.encode("utf-8"))
    print("✓ app.js 已加判空")
else:
    print("✗ 未匹配，输出上下文供检查：")
    i = c.find("side-version")
    print(repr(c[max(0, i - 200) : i + 200]))

# 复查是否还有其它无条件 textContent 赋值
import re

risk = []
for m in re.finditer(r'\$\("#([a-z0-9-]+)"\)\.textContent', c):
    risk.append(m.group(0))
if risk:
    print()
    print("仍有无条件赋值的元素：")
    for r in risk[:15]:
        print("  ", r)
else:
    print("✓ 无其它无条件赋值")
