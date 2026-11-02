package com.smsatbox.app.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import com.smsatbox.app.Prefs
import com.smsatbox.app.R
import com.smsatbox.app.data.ApiClient
import com.smsatbox.app.data.Message
import com.smsatbox.app.data.Stats
import com.smsatbox.app.databinding.FragmentMessagesBinding
import com.smsatbox.app.notify.Notifier
import kotlinx.coroutines.launch

/**
 * 消息页：短信 + 未接来电列表，支持一键复制验证码、下拉刷新。
 */
class MessagesFragment : Fragment() {

    private var _binding: FragmentMessagesBinding? = null
    private val binding get() = _binding!!

    private val api = ApiClient()
    private lateinit var adapter: MessageAdapter

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentMessagesBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        adapter = MessageAdapter(
            onCopyCode = { code -> copyToClipboard(code) },
            onCopyContent = { text -> copyToClipboard(text) },
            onMarkRead = { msg -> markRead(msg) }
        )
        binding.recycler.layoutManager = LinearLayoutManager(requireContext())
        binding.recycler.adapter = adapter

        binding.swipeRefresh.setColorSchemeColors(
            requireContext().getColor(R.color.brand)
        )
        binding.swipeRefresh.setOnRefreshListener { loadMessages(showLoading = false) }

        loadMessages(showLoading = true)
    }

    override fun onResume() {
        super.onResume()
        loadMessages(showLoading = false)
    }

    private fun loadMessages(showLoading: Boolean) {
        if (showLoading) binding.loading.visibility = View.VISIBLE
        lifecycleScope.launch {
            try {
                val stats = api.stats()
                val page = api.messages(limit = 100)
                renderStats(stats)
                adapter.submit(page.items)
                binding.emptyText.visibility =
                    if (page.items.isEmpty()) View.VISIBLE else View.GONE
                // 记住最新的消息 ID，用于后续增量通知
                if (page.items.isNotEmpty()) {
                    Prefs.lastMessageId = maxOf(Prefs.lastMessageId, page.items.first().id)
                }
            } catch (e: Exception) {
                if (isAdded) {
                    Toast.makeText(requireContext(), e.message ?: "加载失败", Toast.LENGTH_SHORT).show()
                }
            } finally {
                if (_binding != null) {
                    binding.loading.visibility = View.GONE
                    binding.swipeRefresh.isRefreshing = false
                }
            }
        }
    }

    private fun renderStats(s: Stats) {
        binding.statTotal.text = s.total.toString()
        binding.statUnread.text = s.unread.toString()
        binding.statToday.text = s.today.toString()
        binding.statCodes.text = s.codes.toString()
    }

    private fun markRead(msg: Message) {
        lifecycleScope.launch {
            try {
                api.markRead(msg.id, true)
                loadMessages(showLoading = false)
            } catch (e: Exception) {
                Toast.makeText(requireContext(), e.message ?: "操作失败", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun copyToClipboard(text: String) {
        if (text.isEmpty()) return
        val cm = requireContext()
            .getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        cm.setPrimaryClip(ClipData.newPlainText("SMSATBOX", text))
        Toast.makeText(
            requireContext(),
            "${getString(R.string.copied)}：$text",
            Toast.LENGTH_SHORT
        ).show()
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}
