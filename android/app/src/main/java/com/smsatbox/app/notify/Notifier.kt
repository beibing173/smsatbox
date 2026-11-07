package com.smsatbox.app.notify

import android.Manifest
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.smsatbox.app.Prefs
import com.smsatbox.app.R
import com.smsatbox.app.SmsatApp
import com.smsatbox.app.data.Message
import com.smsatbox.app.ui.MainActivity

/**
 * 系统通知：新短信 / 未接来电。
 *
 * 兼容性处理：
 *  - Android 8.0+ 走通知渠道；以下版本不用渠道
 *  - Android 13+ 才需要 POST_NOTIFICATIONS 运行时权限
 *  - Android 12+ 要求 PendingIntent 显式指定可变性；以下版本没有该 FLAG
 */
object Notifier {

    /** PendingIntent 的 flags：Android 12+ 必须带 mutable/immutable 标记 */
    private fun pendingFlags(): Int {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        } else {
            PendingIntent.FLAG_UPDATE_CURRENT
        }
    }

    /** Android 13+ 需要运行时授权；低版本直接视为已授权 */
    fun hasPermission(ctx: Context): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return true
        return ContextCompat.checkSelfPermission(
            ctx, Manifest.permission.POST_NOTIFICATIONS
        ) == PackageManager.PERMISSION_GRANTED
    }

    /** 推送一条消息通知 */
    fun notifyMessage(ctx: Context, msg: Message) {
        if (!Prefs.notifyEnabled) return
        if (!hasPermission(ctx)) return

        val intent = Intent(ctx, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra("message_id", msg.id)
        }
        val pending = PendingIntent.getActivity(ctx, msg.id, intent, pendingFlags())

        val title = buildString {
            if (msg.isCall) append("📞 未接来电") else append("💬 新短信")
            append(" · ")
            append(msg.slotLabel)
        }

        val body = buildString {
            if (msg.sender.isNotEmpty()) {
                append(msg.sender)
                append("：")
            }
            append(if (msg.isCall) "未接来电" else msg.content.take(120))
        }

        val builder = NotificationCompat.Builder(ctx, SmsatApp.CHANNEL_MESSAGES)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
            .setAutoCancel(true)
            .setContentIntent(pending)
            .setWhen(System.currentTimeMillis())
            .setShowWhen(true)

        if (!msg.code.isNullOrEmpty()) {
            builder.setSubText("验证码 ${msg.code}")
            val copyIntent = Intent(ctx, CopyReceiver::class.java).apply {
                action = CopyReceiver.ACTION_COPY
                putExtra(CopyReceiver.EXTRA_TEXT, msg.code)
            }
            val copyPending = PendingIntent.getBroadcast(
                ctx, msg.id + 100000, copyIntent, pendingFlags()
            )
            builder.addAction(0, ctx.getString(R.string.copy_code), copyPending)
        }

        try {
            NotificationManagerCompat.from(ctx).notify(msg.id, builder.build())
        } catch (e: SecurityException) {
            // 用户未授权，静默忽略
        } catch (e: Exception) {
            // 个别定制系统通知服务异常，不影响主流程
        }
    }

    /** 清空本应用的通知 */
    fun clearAll(ctx: Context) {
        try {
            NotificationManagerCompat.from(ctx).cancelAll()
        } catch (e: Exception) {
            // ignore
        }
    }
}
