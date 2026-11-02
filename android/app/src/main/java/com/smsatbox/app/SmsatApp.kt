package com.smsatbox.app

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build

/**
 * SMSATBOX 应用入口。
 *
 * 职责：
 *  - 创建 Android 8.0+ 必需的通知渠道
 *  - 持有全局单例（配置、API 客户端）
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
        createNotificationChannel()
    }

    /** 注册消息通知渠道（幂等，重复调用无副作用） */
    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java) ?: return

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
