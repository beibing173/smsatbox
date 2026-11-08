"""v1.0.3 Android 改造：Tab 状态、eSIM 移到设置、悬空导航栏

用 UTF-8 无 BOM 写入。
"""
from pathlib import Path

ROOT = Path(r"D:\SMSATBOX")
done: list[str] = []
fail: list[str] = []


def patch(rel: str, old: str, new: str, desc: str) -> None:
    p = ROOT / rel
    if not p.exists():
        fail.append(f"{rel} 不存在")
        return
    c = p.read_text(encoding="utf-8")
    if old not in c:
        if new in c:
            done.append(f"{desc}（已是目标）")
        else:
            fail.append(f"{desc}：未找到锚点")
        return
    c = c.replace(old, new, 1)
    p.write_bytes(c.encode("utf-8"))
    done.append(desc)


MAIN = "android/app/src/main/java/com/smsatbox/app/ui/MainActivity.kt"

# ---------------------------------------------------------------------------
# 1) MainActivity：补 KEY / tabToMenuId / onSaveInstanceState / currentTab
# ---------------------------------------------------------------------------
patch(
    MAIN,
    """    private fun setupNav() {
        binding.navView.setOnItemSelectedListener { item ->
            when (item.itemId) {
                R.id.nav_messages -> { switchTab(TAB_MESSAGES); true }
                R.id.nav_devices -> { switchTab(TAB_DEVICES); true }
                R.id.nav_esim -> { switchTab(TAB_ESIM); true }
                R.id.nav_settings -> { switchTab(TAB_SETTINGS); true }
                else -> false
            }
        }
        binding.navView.selectedItemId = R.id.nav_messages
    }""",
    """    private fun setupNav() {
        binding.navView.setOnItemSelectedListener { item ->
            when (item.itemId) {
                R.id.nav_messages -> { switchTab(TAB_MESSAGES); true }
                R.id.nav_devices -> { switchTab(TAB_DEVICES); true }
                R.id.nav_settings -> { switchTab(TAB_SETTINGS); true }
                else -> false
            }
        }
    }

    /** Tab 序号 -> 底部导航菜单项 id */
    private fun tabToMenuId(tab: Int): Int = when (tab) {
        TAB_DEVICES -> R.id.nav_devices
        TAB_SETTINGS -> R.id.nav_settings
        else -> R.id.nav_messages
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putInt(KEY_CURRENT_TAB, currentTab)
    }""",
    "MainActivity setupNav + tabToMenuId + onSaveInstanceState",
)

patch(
    MAIN,
    """    private fun switchTab(tab: Int) {
        val fragment: Fragment = when (tab) {
            TAB_DEVICES -> devicesFragment
            TAB_ESIM -> esimFragment
            TAB_SETTINGS -> settingsFragment
            else -> messagesFragment
        }
        supportFragmentManager.beginTransaction()
            .replace(R.id.container, fragment)
            .commit()
    }""",
    """    private fun switchTab(tab: Int) {
        currentTab = tab
        val fragment: Fragment = when (tab) {
            TAB_DEVICES -> devicesFragment
            TAB_ESIM -> esimFragment
            TAB_SETTINGS -> settingsFragment
            else -> messagesFragment
        }
        // 用 show/hide 而非 replace，避免每次切页都重建 View
        val tx = supportFragmentManager.beginTransaction()
        listOf(messagesFragment, devicesFragment, esimFragment, settingsFragment).forEach {
            if (it.isAdded) tx.hide(it)
        }
        if (!fragment.isAdded) tx.add(R.id.container, fragment) else tx.show(fragment)
        tx.commitAllowingStateLoss()
    }

    /** 设置页里点「eSIM 管理」时调用：切到 eSIM 页并把底部导航同步过去 */
    fun openEsim() {
        switchTab(TAB_ESIM)
        // eSIM 不在底部导航里，清掉选中态避免误导
        binding.navView.menu.findItem(R.id.nav_settings)?.isChecked = false
    }""",
    "MainActivity switchTab + openEsim",
)

patch(
    MAIN,
    """    private val messagesFragment by lazy { MessagesFragment() }
    private val devicesFragment by lazy { DevicesFragment() }
    private val esimFragment by lazy { EsimFragment() }
    private val settingsFragment by lazy { SettingsFragment() }""",
    """    private val messagesFragment by lazy { MessagesFragment() }
    private val devicesFragment by lazy { DevicesFragment() }
    private val esimFragment by lazy { EsimFragment() }
    private val settingsFragment by lazy { SettingsFragment() }

    /** 当前 Tab，用于夜间模式重建 Activity 后恢复 */
    private var currentTab: Int = TAB_MESSAGES""",
    "MainActivity currentTab 字段",
)

patch(
    MAIN,
    """        const val TAB_ESIM = 2
        const val TAB_SETTINGS = 3""",
    """        const val TAB_ESIM = 2
        const val TAB_SETTINGS = 3

        /** Activity 重建后恢复当前页用 */
        const val KEY_CURRENT_TAB = "smsatbox_current_tab\"""",
    "MainActivity KEY_CURRENT_TAB",
)

# ---------------------------------------------------------------------------
# 2) 底部导航移除 eSIM 项（迁到设置页）
# ---------------------------------------------------------------------------
patch(
    "android/app/src/main/res/menu/bottom_nav.xml",
    """    <item
        android:id="@+id/nav_esim"
        android:icon="@drawable/ic_nav_devices"
        android:title="@string/nav_esim" />
    <item
        android:id="@+id/nav_settings\"""",
    """    <item
        android:id="@+id/nav_settings\"""",
    "menu 移除 nav_esim",
)

# ---------------------------------------------------------------------------
# 3) 设置页加入 eSIM 入口
# ---------------------------------------------------------------------------
print()
print("=== 已完成 ===")
for d in done:
    print("  ✓", d)
if fail:
    print()
    print("=== 需人工处理 ===")
    for f in fail:
        print("  ✗", f)
