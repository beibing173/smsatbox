package com.smsatbox.app.notify

import android.Manifest
import android.app.Notification
import android.app.NotificationManager
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
 * 验证码消息会单独展示，方便下拉通知栏直接复制。
 */
object Notifier {

    private const val TAG = "smsatbox-msg"

    /** Android 13+ 需要运行时授权 */
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
        val pending = PendingIntent.getActivity(
            ctx,
            msg.id,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

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
            if (msg.isCall) {
                append("未接来电")
            } else {
                append(msg.content.take(120))
            }
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

        // 验证码消息：额外提示并允许直接复制
        if (!msg.code.isNullOrEmpty()) {
            builder.setSubText("验证码 ${msg.code}")
            val copyIntent = Intent(ctx, CopyReceiver::class.java).apply {
                action = CopyReceiver.ACTION_COPY
                putExtra(CopyReceiver.EXTRA_TEXT, msg.code)
            }
            val copyPending = PendingIntent.getBroadcast(
                ctx,
                msg.id + 100000,
                copyIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            builder.addAction(0, ctx.getString(R.string.copy_code), copyPending)
        }

        try {
            NotificationManagerCompat.from(ctx)
                .notify(msg.id, builder.build())
        } catch (e: SecurityException) {
            // 用户未授权，静默忽略
        }
    }

    /** 清空本应用的通知 */
    fun clearAll(ctx: Context) {
        try {
            NotificationManagerCompat.from(ctx).cancelAll()
        } catch (e: SecurityException) {
            // ignore
        }
    }
}
