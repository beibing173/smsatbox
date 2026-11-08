# -*- coding: utf-8 -*-
"""精确修 app.js：只给已删除的三个版本号元素加判空，保留设置页的 #set-server-ver"""
from pathlib import Path

P = Path(r"D:\SMSATBOX\server\app\static\app.js")
c = P.read_text(encoding="utf-8")

# 逐行替换（保持缩进 8 空格）
targets = [
    '        $("#side-version").textContent = "v" + v.version;',
    '        $("#login-version").textContent = "v" + v.version;',
    '        $("#mobile-version").textContent = "v" + v.version;',
]

# 确认这几行确实存在
found = [t for t in targets if t in c]
print(f"找到 {len(found)}/3 个待修行")

if found:
    # 把连续的三行替换成带判空的写法
    block_old = "\n".join(found)
    block_new = """        // 版本号只保留「设置 → 版本更新」那一处（#set-server-ver），
        // 其余位置已从 HTML 移除；这里做判空，防止空引用让整段脚本中断。
        const setVer = (id, text) => {
          const node = document.getElementById(id);
          if (node) node.textContent = text;
        };
        setVer("side-version", "v" + v.version);
        setVer("login-version", "v" + v.version);
        setVer("mobile-version", "v" + v.version);"""
    c = c.replace(block_old, block_new, 1)
    P.write_bytes(c.encode("utf-8"))
    print("✓ 已改为判空写法")
else:
    print("✗ 未找到目标行")

# 复查
c = P.read_text(encoding="utf-8")
print()
print("剩余直接赋值检查：")
for name in ["side-version", "login-version", "mobile-version", "set-server-ver"]:
    direct = f'$("#{name}").textContent' in c
    print(f"  {name:18s} 直接赋值: {'❌ 还有' if direct else '✅ 已处理'}")
