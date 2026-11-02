package com.smsatbox.app.notify

import android.content.BroadcastReceiver
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.widget.Toast
import com.smsatbox.app.R

/**
 * 通知栏「复制验证码」按钮的接收器。
 * 无需打开 App 即可把验证码放进剪贴板。
 */
class CopyReceiver : BroadcastReceiver() {

    companion object {
        const val ACTION_COPY = "com.smsatbox.app.COPY_CODE"
        const val EXTRA_TEXT = "text"
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION_COPY) return
        val text = intent.getStringExtra(EXTRA_TEXT) ?: return
        if (text.isEmpty()) return

        val cm = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        cm.setPrimaryClip(ClipData.newPlainText("SMSATBOX 验证码", text))
        Toast.makeText(
            context,
            context.getString(R.string.copied) + "：" + text,
            Toast.LENGTH_SHORT
        ).show()
    }
}
