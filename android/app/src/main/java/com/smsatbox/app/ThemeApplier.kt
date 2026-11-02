package com.smsatbox.app

import android.content.Context
import androidx.appcompat.app.AppCompatDelegate

/**
 * 主题应用：把三档模式映射到 AppCompatDelegate。
 *
 * - SYSTEM → MODE_NIGHT_FOLLOW_SYSTEM：完全交给系统日夜模式，
 *   配合 values/ 与 values-night/ 两套资源自动切换。
 * - DARK   → MODE_NIGHT_YES
 * - LIGHT  → MODE_NIGHT_NO
 *
 * 关键点：**绝不修改系统设置**，只影响本应用自身的界面。
 */
object ThemeApplier {

    /** 在 Application / Activity 创建前调用，避免启动闪屏用错配色。 */
    fun apply(mode: ThemeMode) {
        AppCompatDelegate.setDefaultNightMode(
            when (mode) {
                ThemeMode.DARK -> AppCompatDelegate.MODE_NIGHT_YES
                ThemeMode.LIGHT -> AppCompatDelegate.MODE_NIGHT_NO
                ThemeMode.SYSTEM -> AppCompatDelegate.MODE_NIGHT_FOLLOW_SYSTEM
            }
        )
    }

    /** 从本地配置读取并应用。 */
    fun applySaved(context: Context) {
        apply(Prefs.themeMode)
    }

    /** 切换模式并持久化，返回切换后的模式（供界面提示）。 */
    fun set(context: Context, mode: ThemeMode): ThemeMode {
        Prefs.themeMode = mode
        apply(mode)
        return mode
    }

    fun label(mode: ThemeMode): String = when (mode) {
        ThemeMode.DARK -> "深色"
        ThemeMode.LIGHT -> "浅色"
        ThemeMode.SYSTEM -> "跟随系统"
    }
}
