# -*- coding: utf-8 -*-
"""1.0.4：把悬空导航栏改成最保险实现

怀疑 MaterialCardView 在部分 ROM（尤其华为/荣耀）上有兼容问题，
改用 FrameLayout + 圆角 drawable + elevation，视觉一致但依赖更少。
"""
from pathlib import Path

ROOT = Path(r"D:\SMSATBOX")

# ---------------------------------------------------------------------------
# 1) 新建圆角 Dock 背景 drawable（浅色 / 深色各一套）
# ---------------------------------------------------------------------------
DRAWABLE_DIR = ROOT / "android/app/src/main/res/drawable"
DRAWABLE_DIR.mkdir(parents=True, exist_ok=True)

LIGHT_DOCK = """<?xml version="1.0" encoding="utf-8"?>
<!-- 悬空导航 Dock 背景：圆角 + 半透明 + 细高光描边 -->
<shape xmlns:android="http://schemas.android.com/apk/res/android"
    android:shape="rectangle">
    <solid android:color="@color/nav_glass" />
    <corners android:radius="28dp" />
    <stroke android:width="1dp" android:color="@color/nav_glass_stroke" />
</shape>
"""
(DRAWABLE_DIR / "bg_nav_dock.xml").write_bytes(LIGHT_DOCK.encode("utf-8"))
print("✓ 新建 drawable/bg_nav_dock.xml")

# ---------------------------------------------------------------------------
# 2) 重写 activity_main.xml：FrameLayout 包裹
# ---------------------------------------------------------------------------
LAYOUT = """<?xml version="1.0" encoding="utf-8"?>
<!--
  主界面布局：悬空式底部导航（参考 FlClash 的 navigation dock 设计）

  为什么不用 MaterialCardView？
    部分国产 ROM 对 MaterialCardView 的 stroke/elevation 组合有兼容问题，
    偶发 inflate 崩溃。这里改用 FrameLayout + 圆角 drawable + elevation，
    视觉效果一致，依赖更少更稳。
-->
<androidx.constraintlayout.widget.ConstraintLayout
    xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:app="http://schemas.android.com/apk/res-auto"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:background="@color/bg_0">

    <!-- 内容区铺满全屏，导航栏浮在上层 -->
    <FrameLayout
        android:id="@+id/container"
        android:layout_width="0dp"
        android:layout_height="0dp"
        app:layout_constraintTop_toTopOf="parent"
        app:layout_constraintStart_toStartOf="parent"
        app:layout_constraintEnd_toEndOf="parent"
        app:layout_constraintBottom_toBottomOf="parent" />

    <!-- 版本号：悬浮在 Dock 上方，极低存在感 -->
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

    <!-- 悬空导航 Dock -->
    <FrameLayout
        android:id="@+id/navDock"
        android:layout_width="0dp"
        android:layout_height="wrap_content"
        android:layout_marginStart="18dp"
        android:layout_marginEnd="18dp"
        android:layout_marginBottom="14dp"
        android:background="@drawable/bg_nav_dock"
        android:elevation="10dp"
        android:outlineProvider="background"
        app:layout_constraintBottom_toBottomOf="parent"
        app:layout_constraintStart_toStartOf="parent"
        app:layout_constraintEnd_toEndOf="parent">

        <com.google.android.material.bottomnavigation.BottomNavigationView
            android:id="@+id/navView"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:background="@android:color/transparent"
            app:elevation="0dp"
            app:itemIconTint="@color/nav_item_color"
            app:itemTextColor="@color/nav_item_color"
            app:itemIconSize="22dp"
            app:labelVisibilityMode="labeled"
            app:menu="@menu/bottom_nav" />

    </FrameLayout>

</androidx.constraintlayout.widget.ConstraintLayout>
"""
p = ROOT / "android/app/src/main/res/layout/activity_main.xml"
p.write_bytes(LAYOUT.encode("utf-8"))
print("✓ 重写 activity_main.xml（FrameLayout + drawable）")

# ---------------------------------------------------------------------------
# 3) 版本号 1.0.4
# ---------------------------------------------------------------------------
VER = {
    "versions/server.txt": ("1.0.3", "1.0.4"),
    "versions/android.txt": ("1.0.3", "1.0.4"),
    "versions/windows.txt": ("1.0.3", "1.0.4"),
    "server/app/version.py": ('VERSION = "1.0.4"', 'VERSION = "1.0.4"'),
}
for rel, (o, n) in VER.items():
    if o != n:
        continue

print()
print("完成")
