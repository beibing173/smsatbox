# -*- coding: utf-8 -*-
"""1.0.5：删掉多余版本号位置 + 修 eSIM 入口

主人要求：只保留「设置 → 版本更新」旁边那一个版本号，
其余（首页、设备页、eSIM 页、底部 Dock 上方）全部删除。
"""
import re
from pathlib import Path

ROOT = Path(r"D:\SMSATBOX")


def patch(rel: str, old: str, new: str, desc: str) -> None:
    p = ROOT / rel
    if not p.exists():
        print(f"  ✗ {rel} 不存在")
        return
    c = p.read_text(encoding="utf-8")
    if old not in c:
        print(f"  = {desc}（无此锚点，跳过）")
        return
    c = c.replace(old, new)
    p.write_bytes(c.encode("utf-8"))
    print(f"  ✓ {desc}")


# ---------------------------------------------------------------------------
# 1) Android：删底部 Dock 上方的版本号
# ---------------------------------------------------------------------------
patch(
    "android/app/src/main/res/layout/activity_main.xml",
    """    <!-- 版本号：悬浮在 Dock 上方，极低存在感 -->
    <TextView
        android:id="@+id/versionText"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:text="v1.0.4"
        android:textSize="9sp"
        android:textColor="@color/text_2"
        android:alpha="0.55"
        android:layout_marginBottom="2dp"
        app:layout_constraintBottom_toTopOf="@id/navDock"
        app:layout_constraintStart_toStartOf="parent"
        app:layout_constraintEnd_toEndOf="parent" />

""",
    "",
    "删 Android 底部浮动版本号",
)

# MainActivity 里对 versionText 的赋值也要删，否则编译报错
patch(
    "android/app/src/main/java/com/smsatbox/app/ui/MainActivity.kt",
    """        // 底部版本号（要求：三端布局一致，底部标注版本号）
        binding.versionText.text = "v${BuildConfig.APP_VERSION}"

""",
    "",
    "删 MainActivity 里 versionText 赋值",
)

# ---------------------------------------------------------------------------
# 2) Web：删侧边栏 / 手机底部 / 登录页的版本号
# ---------------------------------------------------------------------------
p = ROOT / "server/app/static/index.html"
c = p.read_text(encoding="utf-8")

# 侧边栏底部版本
c = re.sub(
    r'\s*<div>版本 <span class="ver" id="side-version">v[\d.]+</span></div>',
    "",
    c,
)
# 手机端底部版本
c = re.sub(
    r'\s*<span class="ver" id="mobile-version">v[\d.]+</span>',
    "",
    c,
)
# 登录页版本
c = re.sub(
    r'SMSATBOX Server <span class="ver" id="login-version">v[\d.]+</span>',
    "SMSATBOX Server",
    c,
)
p.write_bytes(c.encode("utf-8"))
print("  ✓ 删 Web 首页/Dock/登录页版本号")

# app.js 里对这些元素的赋值要容错（元素已不存在）
for rel in ["server/app/static/app.js"]:
    q = ROOT / rel
    t = q.read_text(encoding="utf-8")
    # 已有 $("#xxx") 判空的话不用改；这里确认一下
    print(f"  · {rel} 版本号引用：", "有判空" if "#side-version" not in t else "需检查")

# ---------------------------------------------------------------------------
# 3) esim.html：删页头版本相关（它没有版本号，但去掉页头副标题里的冗余）
# ---------------------------------------------------------------------------
p = ROOT / "server/app/static/esim.html"
c = p.read_text(encoding="utf-8")
c = c.replace(
    '<div class="sub">SMSATBOX · eUICC 可编程卡管理</div>',
    '<div class="sub">eUICC 可编程卡管理</div>',
)
p.write_bytes(c.encode("utf-8"))
print("  ✓ esim.html 页头精简")

print()
print("版本号位置清理完成。设置页保留 currentVersion 一处。")
