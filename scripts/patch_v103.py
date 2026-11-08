"""v1.0.3 批量改动：Web 端 eSIM 独立板块 + esim.html 嵌入模式 + Android 修 Tab bug

全部 UTF-8 无 BOM 写入。
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
            done.append(f"{desc}（已是目标状态）")
        else:
            fail.append(f"{desc}：未找到锚点")
        return
    c = c.replace(old, new, 1)
    p.write_bytes(c.encode("utf-8"))
    done.append(desc)


# ===========================================================================
# 1) app.js：恢复 eSIM 独立导航
# ===========================================================================
patch(
    "server/app/static/app.js",
    """  $("#nav").addEventListener("click", (ev) => {
    const btn = ev.target.closest(".nav-item");
    if (btn && btn.dataset.route) switchRoute(btn.dataset.route);
  });""",
    """  $("#nav").addEventListener("click", (ev) => {
    // eSIM 独立工作台（与客户端同款界面）
    if (ev.target.closest("#nav-esim")) {
      location.href = "/assets/esim.html?embed=0";
      return;
    }
    const btn = ev.target.closest(".nav-item");
    if (btn && btn.dataset.route) switchRoute(btn.dataset.route);
  });""",
    "app.js 恢复 eSIM 导航",
)

# ===========================================================================
# 2) app.js：主题切换后不丢路由（Web 端兜底）
#    Android 端的 Activity 重建问题在 MainActivity 里单独修
# ===========================================================================
patch(
    "server/app/static/app.js",
    """    set(pref) {
      this.pref = pref === "dark" || pref === "light" ? pref : "system";
      this.persist();
      this.apply();
    },""",
    """    set(pref) {
      this.pref = pref === "dark" || pref === "light" ? pref : "system";
      this.persist();
      this.apply();
      // 主题切换后保持当前路由高亮不变（避免某些浏览器重排导致视觉错位）
      if (state.route) {
        $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.route === state.route));
      }
    },""",
    "app.js 主题切换保持路由高亮",
)

# ===========================================================================
# 3) esim.html：支持 embed 模式（在客户端 WebView 里隐藏页头/返回按钮）
# ===========================================================================
patch(
    "server/app/static/esim.html",
    """  <div class="row" style="gap:10px">
    <span class="badge" id="connBadge">正在连接</span>
    <button id="themeBtn" title="切换主题">🌓</button>
    <button onclick="location.href='/'">返回管理端</button>
  </div>""",
    """  <div class="row" style="gap:10px">
    <span class="badge" id="connBadge">正在连接</span>
    <button id="themeBtn" title="切换主题">🌓</button>
    <button id="backBtn" onclick="location.href='/'">返回管理端</button>
  </div>""",
    "esim.html 给返回按钮加 id",
)

patch(
    "server/app/static/esim.html",
    """(function () {
  "use strict";

  // ---------- 基础 ----------
  const $ = (id) => document.getElementById(id);""",
    """(function () {
  "use strict";

  // ---------- 嵌入模式 ----------
  // ?embed=1 时说明是客户端 WebView 内加载：
  //   隐藏「返回管理端」按钮，避免暴露套壳网页的痕迹
  const EMBED = new URLSearchParams(location.search).get("embed") === "1";

  // ---------- 基础 ----------
  const $ = (id) => document.getElementById(id);

  if (EMBED) {
    document.addEventListener("DOMContentLoaded", () => {
      const back = document.getElementById("backBtn");
      if (back) back.style.display = "none";
    });
  }""",
    "esim.html 支持 embed 模式",
)

# ===========================================================================
# 4) Android：MainActivity 保存/恢复 Tab（修夜间模式重建后状态错乱）
# ===========================================================================
patch(
    "android/app/src/main/java/com/smsatbox/app/ui/MainActivity.kt",
    """        if (savedInstanceState == null) {
            switchTab(TAB_MESSAGES)
        }""",
    """        // 注意：切换深浅主题会让 AppCompat 重建 Activity。
        // 必须把当前 Tab 存进 savedInstanceState，否则重建后
        // 内容区回到默认页、而底部导航还停在上一次的选中项。
        val restoreTab = savedInstanceState?.getInt(KEY_CURRENT_TAB, TAB_MESSAGES)
            ?: TAB_MESSAGES
        switchTab(restoreTab)
        binding.navView.selectedItemId = tabToMenuId(restoreTab)""",
    "MainActivity 恢复 Tab",
)

# ===========================================================================
# 5) Android：EsimFragment 走 embed 模式
# ===========================================================================
patch(
    "android/app/src/main/java/com/smsatbox/app/ui/EsimFragment.kt",
    'val url = "$server/assets/esim.html"',
    'val url = "$server/assets/esim.html?embed=1"',
    "EsimFragment 用 embed 模式",
)

# ===========================================================================
# 6) Windows：EsimPage 走嵌入模式（隐藏返回按钮，去掉套壳感）
# ===========================================================================
patch(
    "windows/SmsatBox.Desktop/Views/Pages/EsimPage.xaml.cs",
    'var url = SiteRoot(api.ServerUrl) + "/assets/esim.html";',
    'var url = SiteRoot(api.ServerUrl) + "/assets/esim.html?embed=1";',
    "Windows EsimPage 用 embed 模式",
)

# ===========================================================================
# 7) 版本号 1.0.3
# ===========================================================================
VER = {
    "versions/server.txt": ("1.0.2", "1.0.3"),
    "versions/android.txt": ("1.0.2", "1.0.3"),
    "versions/windows.txt": ("1.0.2", "1.0.3"),
    "server/app/version.py": ('VERSION = "1.0.2"', 'VERSION = "1.0.3"'),
    "server/app/static/app.js": ('const VERSION = "1.0.2";', 'const VERSION = "1.0.3";'),
    "server/app/static/sw.js": ('const VERSION = "1.0.2";', 'const VERSION = "1.0.3";'),
    "esp32/include/config.h": ('#define SMSATBOX_VERSION "1.0.2"', '#define SMSATBOX_VERSION "1.0.3"'),
    "esp32/platformio.ini": (";  版本：v1.0.2", ";  版本：v1.0.3"),
    "android/version.properties": ("VERSION_NAME=1.0.2", "VERSION_NAME=1.0.3"),
    "android/app/build.gradle.kts": ('"VERSION_NAME", "1.0.2"', '"VERSION_NAME", "1.0.3"'),
    "windows/SmsatBox.Desktop/SmsatBox.Desktop.csproj": ("<Version>1.0.2</Version>", "<Version>1.0.3</Version>"),
    "windows/SmsatBox.Desktop/Core/AppInfo.cs": ('public const string Version = "1.0.2";', 'public const string Version = "1.0.3";'),
}
for rel, (o, n) in VER.items():
    patch(rel, o, n, f"版本 {rel}")

# platformio.ini 的 build flag 与 Android versionCode 单独处理
patch("esp32/platformio.ini", 'VERSION_STR=\\"1.0.2\\"', 'VERSION_STR=\\"1.0.3\\"', "版本 platformio flag")
patch("android/version.properties", "VERSION_CODE=10002", "VERSION_CODE=10003", "versionCode 10003")
patch("android/app/build.gradle.kts", '"VERSION_CODE", "10002"', '"VERSION_CODE", "10003"', "gradle versionCode")
patch("windows/SmsatBox.Desktop/SmsatBox.Desktop.csproj",
      "<AssemblyVersion>1.0.2.0</AssemblyVersion>", "<AssemblyVersion>1.0.3.0</AssemblyVersion>", "win AssemblyVersion")
patch("windows/SmsatBox.Desktop/SmsatBox.Desktop.csproj",
      "<FileVersion>1.0.2.0</FileVersion>", "<FileVersion>1.0.3.0</FileVersion>", "win FileVersion")
patch("windows/SmsatBox.Desktop/Core/AppInfo.cs",
      'public const string ClientVersion = "1.0.2";', 'public const string ClientVersion = "1.0.3";', "win ClientVersion")
patch("server/app/static/index.html", 'id="login-version">v1.0.2<', 'id="login-version">v1.0.3<', "index login ver")
patch("server/app/static/index.html", 'id="side-version">v1.0.2<', 'id="side-version">v1.0.3<', "index side ver")
patch("server/app/static/index.html", 'id="mobile-version">v1.0.2<', 'id="mobile-version">v1.0.3<', "index mobile ver")
patch("server/app/db.py", "DEFAULT '1.0.2'", "DEFAULT '1.0.3'", "db 默认固件版本")

print("=== 已完成 ===")
for d in done:
    print("  ✓", d)
if fail:
    print()
    print("=== 需人工处理 ===")
    for f in fail:
        print("  ✗", f)
