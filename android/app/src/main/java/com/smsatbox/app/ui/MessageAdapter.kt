package com.smsatbox.app.ui

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.RecyclerView
import com.smsatbox.app.R
import com.smsatbox.app.data.Message
import com.smsatbox.app.databinding.ItemMessageBinding
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone

/**
 * 消息列表适配器。
 *
 * 有验证码时显示可点击的验证码块（一眼看到、一点即复制）。
 */
class MessageAdapter(
    private val onCopyCode: (String) -> Unit,
    private val onCopyContent: (String) -> Unit,
    private val onMarkRead: (Message) -> Unit
) : RecyclerView.Adapter<MessageAdapter.VH>() {

    private val items = ArrayList<Message>()

    fun submit(list: List<Message>) {
        items.clear()
        items.addAll(list)
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val binding = ItemMessageBinding.inflate(
            LayoutInflater.from(parent.context), parent, false
        )
        return VH(binding)
    }

    override fun getItemCount(): Int = items.size

    override fun onBindViewHolder(holder: VH, position: Int) {
        holder.bind(items[position])
    }

    inner class VH(private val b: ItemMessageBinding) : RecyclerView.ViewHolder(b.root) {

        fun bind(msg: Message) {
            val ctx = b.root.context

            b.senderText.text = msg.title
            b.slotTag.text = msg.slotLabel

            // 类型标签
            if (msg.isCall) {
                b.kindTag.text = "来电"
                b.kindTag.setTextColor(ContextCompat.getColor(ctx, R.color.warn))
                b.bodyText.text = "未接来电"
            } else {
                b.kindTag.text = "短信"
                b.kindTag.setTextColor(ContextCompat.getColor(ctx, R.color.brand))
                b.bodyText.text = msg.content
            }

            b.timeText.text = formatTime(msg.receivedAt)

            // 验证码块
            if (!msg.code.isNullOrEmpty()) {
                b.codeChip.visibility = View.VISIBLE
                b.codeText.text = msg.code
                b.codeChip.setOnClickListener { onCopyCode(msg.code) }
            } else {
                b.codeChip.visibility = View.GONE
                b.codeChip.setOnClickListener(null)
            }

            // 未读指示
            b.unreadDot.visibility = if (msg.isRead) View.GONE else View.VISIBLE

            b.copyButton.setOnClickListener { onCopyContent(msg.content) }
            b.readButton.visibility = if (msg.isRead) View.GONE else View.VISIBLE
            b.readButton.setOnClickListener { onMarkRead(msg) }
        }

        /** 把 UTC ISO 时间转成本地「今天 HH:mm」/「MM-dd HH:mm」 */
        private fun formatTime(iso: String): String {
            return try {
                val parser = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
                    timeZone = TimeZone.getTimeZone("UTC")
                }
                val date = parser.parse(iso) ?: return iso
                val out = SimpleDateFormat("HH:mm", Locale.getDefault())
                val sameDay = SimpleDateFormat("yyyyMMdd", Locale.getDefault())
                    .format(date) == SimpleDateFormat("yyyyMMdd", Locale.getDefault())
                    .format(java.util.Date())
                if (sameDay) "今天 ${out.format(date)}"
                else SimpleDateFormat("MM-dd HH:mm", Locale.getDefault()).format(date)
            } catch (e: Exception) {
                iso
            }
        }
    }
}
