# -*- coding: utf-8 -*-
"""1.0.4：修复 Android 崩溃，保守回退高风险改动

崩溃嫌疑点（按概率）：
  1. itemActiveIndicatorStyle 引用的父样式在运行时解析失败
  2. switchTab 用 show/hide + add 混用，Fragment 事务状态异常
  3. tabToMenuId 对 TAB_ESIM 返回 nav_messages，触发监听递归

策略：全部走最保守写法，先保证能启动，视觉保持悬空导航。
"""
from pathlib import Path

ROOT = Path(r"D:\SMSATBOX")
done: list[str] = []


def patch(rel: str, old: str, new: str, desc: str) -> None:
    p = ROOT / rel
    if not p.exists():
        print(f"  ✗ {rel} 不存在")
        return
    c = p.read_text(encoding="utf-8")
    if old not in c:
        if new in c:
            print(f"  = {desc}（已是目标）")
        else:
            print(f"  ✗ {desc}：未找到锚点")
        return
    c = c.replace(old, new, 1)
    p.write_bytes(c.encode("utf-8"))
    done.append(desc)
    print(f"  ✓ {desc}")


# ---------------------------------------------------------------------------
# 1) 移除 itemActiveIndicatorStyle（最可疑的崩溃点）
# ---------------------------------------------------------------------------
patch(
    "android/app/src/main/res/layout/activity_main.xml",
    '            app:itemActiveIndicatorStyle="@style/NavActiveIndicator"\n',
    "",
    "移除 itemActiveIndicatorStyle",
)

# ---------------------------------------------------------------------------
# 2) switchTab 回退为 replace（show/hide 混 add 容易出事务问题）
# ---------------------------------------------------------------------------
patch(
    "android/app/src/main/java/com/smsatbox/app/ui/MainActivity.kt",
    """        // 用 show/hide 而非 replace，避免每次切页都重建 View
        val tx = supportFragmentManager.beginTransaction()
        listOf(messagesFragment, devicesFragment, esimFragment, settingsFragment).forEach {
            if (it.isAdded) tx.hide(it)
        }
        if (!fragment.isAdded) tx.add(R.id.container, fragment) else tx.show(fragment)
        tx.commitAllowingStateLoss()""",
    """        supportFragmentManager.beginTransaction()
            .replace(R.id.container, fragment)
            .commitAllowingStateLoss()""",
    "switchTab 回退 replace",
)

# ---------------------------------------------------------------------------
# 3) tabToMenuId 增加 ESIM 分支（原先落到 nav_messages 会导致选错页）
# ---------------------------------------------------------------------------
patch(
    "android/app/src/main/java/com/smsatbox/app/ui/MainActivity.kt",
    """    /** Tab 序号 -> 底部导航菜单项 id */
    private fun tabToMenuId(tab: Int): Int = when (tab) {
        TAB_DEVICES -> R.id.nav_devices
        TAB_SETTINGS -> R.id.nav_settings
        else -> R.id.nav_messages
    }""",
    """    /**
     * Tab 序号 -> 底部导航菜单项 id。
     * eSIM 已不在底部导航里，返回 0 表示「不选中任何项」。
     */
    private fun tabToMenuId(tab: Int): Int = when (tab) {
        TAB_DEVICES -> R.id.nav_devices
        TAB_SETTINGS -> R.id.nav_settings
        TAB_ESIM -> 0
        else -> R.id.nav_messages
    }""",
    "tabToMenuId 增加 ESIM 分支",
)

# ---------------------------------------------------------------------------
# 4) 设置 selectedItemId 前判 0，避免非法 id 触发异常
# ---------------------------------------------------------------------------
patch(
    "android/app/src/main/java/com/smsatbox/app/ui/MainActivity.kt",
    """        switchTab(restoreTab)
        binding.navView.selectedItemId = tabToMenuId(restoreTab)""",
    """        switchTab(restoreTab)
        val menuId = tabToMenuId(restoreTab)
        if (menuId != 0) binding.navView.selectedItemId = menuId""",
    "selectedItemId 加 0 判断",
)

# ---------------------------------------------------------------------------
# 5) 版本 1.0.4
# ---------------------------------------------------------------------------
VER = {
    "versions/server.txt": ("1.0.3", "1.0.4"),
    "versions/android.txt": ("1.0.3", "1.0.4"),
    "versions/windows.txt": ("1.0.3", "1.0.4"),
    "server/app/version.py": ('VERSION = "1.0.3"', 'VERSION = "1.0.4"'),
    "server/app/static/app.js": ('const VERSION = "1.0.3";', 'const VERSION = "1.0.4";'),
    "server/app/static/sw.js": ('const VERSION = "1.0.3";', 'const VERSION = "1.0.4";'),
    "esp32/include/config.h": ('#define SMSATBOX_VERSION "1.0.3"', '#define SMSATBOX_VERSION "1.0.4"'),
    "esp32/platformio.ini": (";  版本：v1.0.3", ";  版本：v1.0.4"),
    "android/version.properties": ("VERSION_NAME=1.0.3", "VERSION_NAME=1.0.4"),
    "android/version.properties": ("VERSION_CODE=10003", "VERSION_CODE=10004"),
    "android/app/build.gradle.kts": ('"VERSION_NAME", "1.0.3"', '"VERSION_NAME", "1.0.4"'),
    "android/app/build.gradle.kts": ('"VERSION_CODE", "10003"', '"VERSION_CODE", "10004"'),
    "windows/SmsatBox.Desktop/SmsatBox.Desktop.csproj": ("<Version>1.0.3</Version>", "<Version>1.0.4</Version>"),
    "windows/SmsatBox.Desktop/SmsatBox.Desktop.csproj": ("<AssemblyVersion>1.0.3.0</AssemblyVersion>", "<AssemblyVersion>1.0.4.0</AssemblyVersion>"),
    "windows/SmsatBox.Desktop/SmsatBox.Desktop.csproj": ("<FileVersion>1.0.3.0</FileVersion>", "<FileVersion>1.0.4.0</FileVersion>"),
    "windows/SmsatBox.Desktop/Core/AppInfo.cs": ('public const string Version = "1.0.3";', 'public const string Version = "1.0.4";'),
    "windows/SmsatBox.Desktop/Core/AppInfo.cs": ('public const string ClientVersion = "1.0.3";', 'public const string ClientVersion = "1.0.4";'),
    "server/app/static/index.html": ('id="login-version">v1.0.3<', 'id="login-version">v1.0.4<'),
    "server/app/static/index.html": ('id="side-version">v1.0.3<', 'id="side-version">v1.0.4<'),
    "server/app/static/index.html": ('id="mobile-version">v1.0.3<', 'id="mobile-version">v1.0.4<'),
    "server/app/db.py": ("DEFAULT '1.0.3'", "DEFAULT '1.0.4'"),
    "esp32/platformio.ini": ('VERSION_STR=\\"1.0.3\\"', 'VERSION_STR=\\"1.0.4\\"'),
}
print()
for rel, (o, n) in VER.items():
    patch(rel, o, n, f"版本 {rel}")

print()
print(f"共完成 {len(done)} 项")
