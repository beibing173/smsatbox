package com.smsatbox.app

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build

/**
 * SMSATBOX 应用入口。
 *
 * 职责：
 *  - 在最早时机应用主题（避免启动闪屏配色错误）
 *  - 创建 Android 8.0+ 必需的通知渠道
 *  - 持有全局单例（配置）
 */
class SmsatApp : Application() {

    companion object {
        const val CHANNEL_MESSAGES = "smsatbox_messages"
        lateinit var instance: SmsatApp
            private set
    }

    override fun onCreate() {
        super.onCreate()
        instance = this

        Prefs.init(this)

        // 主题必须在任何 Activity 创建前应用
        ThemeApplier.applySaved(this)

        createNotificationChannel()
    }

    /** 注册消息通知渠道（Android 8.0+；低版本系统无需渠道，直接跳过） */
    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return

        val manager = getSystemService(NOTIFICATION_SERVICE) as? NotificationManager ?: return

        val channel = NotificationChannel(
            CHANNEL_MESSAGES,
            getString(R.string.channel_messages),
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = getString(R.string.channel_messages_desc)
            enableVibration(true)
            enableLights(true)
            lightColor = 0xFF22D3EE.toInt()
        }
        manager.createNotificationChannel(channel)
    }
}
