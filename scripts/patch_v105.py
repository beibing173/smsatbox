# -*- coding: utf-8 -*-
"""1.0.5：删登录页版本号 + eSIM 入口加反馈 + 液态玻璃质感增强"""
from pathlib import Path

ROOT = Path(r"D:\SMSATBOX")
A = ROOT / "android"


def patch(rel: str, old: str, new: str, desc: str) -> None:
    p = ROOT / rel
    if not p.exists():
        print(f"  ✗ {rel} 不存在")
        return
    c = p.read_text(encoding="utf-8")
    if old not in c:
        print(f"  = {desc}（无锚点）")
        return
    c = c.replace(old, new, 1)
    p.write_bytes(c.encode("utf-8"))
    print(f"  ✓ {desc}")


# ---------------------------------------------------------------------------
# 1) 删登录页版本号（登录页 = 首页，主人要求只留设置页那一处）
# ---------------------------------------------------------------------------
p = A / "app/src/main/res/layout/activity_login.xml"
c = p.read_text(encoding="utf-8")
import re

c2 = re.sub(
    r'\s*<TextView\s+android:id="@\+id/versionText"[^/]*?/>',
    "",
    c,
    flags=re.S,
)
if c2 != c:
    p.write_bytes(c2.encode("utf-8"))
    print("  ✓ 删登录页版本号 TextView")
else:
    print("  = 登录页版本号未匹配")

patch(
    "android/app/src/main/java/com/smsatbox/app/ui/LoginActivity.kt",
    'binding.versionText.text = "v${BuildConfig.APP_VERSION}"',
    "// 版本号只在设置页展示，登录页不再显示",
    "删 LoginActivity 版本号赋值",
)

# ---------------------------------------------------------------------------
# 2) eSIM 入口：加呼吸反馈 + 更明确的跳转
# ---------------------------------------------------------------------------
patch(
    "android/app/src/main/java/com/smsatbox/app/ui/MainActivity.kt",
    """    /** 设置页里点「eSIM 管理」时调用：切到 eSIM 页并把底部导航同步过去 */
    fun openEsim() {
        switchTab(TAB_ESIM)
        // eSIM 不在底部导航里，清掉选中态避免误导
        binding.navView.menu.findItem(R.id.nav_settings)?.isChecked = false
    }""",
    """    /** 设置页里点「eSIM 管理」时调用 */
    fun openEsim() {
        try {
            switchTab(TAB_ESIM)
            // eSIM 不在底部导航里，清掉选中态避免误导
            binding.navView.menu.findItem(R.id.nav_settings)?.isChecked = false
        } catch (e: Exception) {
            android.widget.Toast.makeText(
                this, "打开 eSIM 页面失败：" + e.message,
                android.widget.Toast.LENGTH_LONG
            ).show()
        }
    }""",
    "openEsim 加异常兜底提示",
)

# ---------------------------------------------------------------------------
# 3) 液态玻璃增强：渐变高光 + 顶部提亮，模拟玻璃反光
# ---------------------------------------------------------------------------
DOCK = """<?xml version="1.0" encoding="utf-8"?>
<!--
  悬空导航 Dock 背景：液态玻璃质感
  - 28dp 大圆角
  - 垂直渐变：顶部略亮 -> 底部略暗，模拟玻璃受光面
  - 1dp 半透明描边，模拟玻璃边缘折射高光
-->
<shape xmlns:android="http://schemas.android.com/apk/res/android"
    android:shape="rectangle">
    <gradient
        android:angle="270"
        android:startColor="@color/nav_glass_top"
        android:endColor="@color/nav_glass_bottom"
        android:type="linear" />
    <corners android:radius="28dp" />
    <stroke android:width="1dp" android:color="@color/nav_glass_stroke" />
</shape>
"""
(A / "app/src/main/res/drawable/bg_nav_dock.xml").write_bytes(DOCK.encode("utf-8"))
print("  ✓ bg_nav_dock.xml 改为渐变玻璃")

# 新增渐变两端颜色
for rel, top, bottom in [
    ("android/app/src/main/res/values/colors.xml", "#F5FFFFFF", "#E8F1F5FB"),
    ("android/app/src/main/res/values-night/colors.xml", "#F51E2A3E", "#E81A2438"),
]:
    p = ROOT / rel
    c = p.read_text(encoding="utf-8")
    if "nav_glass_top" in c:
        print(f"  = {rel} 已有渐变颜色")
        continue
    add = f'''    <!-- 悬空 Dock 渐变玻璃（顶部受光 / 底部略暗） -->
    <color name="nav_glass_top">{top}</color>
    <color name="nav_glass_bottom">{bottom}</color>
</resources>'''
    c = c.replace("</resources>", add)
    p.write_bytes(c.encode("utf-8"))
    print(f"  ✓ {rel} 加渐变颜色")

# ---------------------------------------------------------------------------
# 4) 版本 1.0.5
# ---------------------------------------------------------------------------
VER = [
    ("versions/server.txt", "1.0.4", "1.0.5"),
    ("versions/android.txt", "1.0.4", "1.0.5"),
    ("versions/windows.txt", "1.0.4", "1.0.5"),
    ("server/app/version.py", 'VERSION = "1.0.4"', 'VERSION = "1.0.5"'),
    ("server/app/static/app.js", 'const VERSION = "1.0.4";', 'const VERSION = "1.0.5";'),
    ("server/app/static/sw.js", 'const VERSION = "1.0.4";', 'const VERSION = "1.0.5";'),
    ("esp32/include/config.h", '#define SMSATBOX_VERSION "1.0.4"', '#define SMSATBOX_VERSION "1.0.5"'),
    ("esp32/platformio.ini", ";  版本：v1.0.4", ";  版本：v1.0.5"),
    ("esp32/platformio.ini", 'VERSION_STR=\\"1.0.4\\"', 'VERSION_STR=\\"1.0.5\\"'),
    ("android/version.properties", "VERSION_NAME=1.0.4", "VERSION_NAME=1.0.5"),
    ("android/version.properties", "VERSION_CODE=10004", "VERSION_CODE=10005"),
    ("android/app/build.gradle.kts", '"VERSION_NAME", "1.0.4"', '"VERSION_NAME", "1.0.5"'),
    ("android/app/build.gradle.kts", '"VERSION_CODE", "10004"', '"VERSION_CODE", "10005"'),
    ("windows/SmsatBox.Desktop/SmsatBox.Desktop.csproj", "<Version>1.0.4</Version>", "<Version>1.0.5</Version>"),
    ("windows/SmsatBox.Desktop/SmsatBox.Desktop.csproj", "<AssemblyVersion>1.0.4.0</AssemblyVersion>", "<AssemblyVersion>1.0.5.0</AssemblyVersion>"),
    ("windows/SmsatBox.Desktop/SmsatBox.Desktop.csproj", "<FileVersion>1.0.4.0</FileVersion>", "<FileVersion>1.0.5.0</FileVersion>"),
    ("windows/SmsatBox.Desktop/Core/AppInfo.cs", 'public const string Version = "1.0.4";', 'public const string Version = "1.0.5";'),
    ("windows/SmsatBox.Desktop/Core/AppInfo.cs", 'public const string ClientVersion = "1.0.4";', 'public const string ClientVersion = "1.0.5";'),
    ("server/app/db.py", "DEFAULT '1.0.4'", "DEFAULT '1.0.5'"),
]
print()
for rel, o, n in VER:
    patch(rel, o, n, f"版本 {rel}")

print()
print("完成")
