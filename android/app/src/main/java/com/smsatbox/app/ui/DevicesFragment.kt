package com.smsatbox.app.ui

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.smsatbox.app.R
import com.smsatbox.app.data.ApiClient
import com.smsatbox.app.data.Device
import com.smsatbox.app.data.SimSlot
import com.smsatbox.app.databinding.FragmentDevicesBinding
import kotlinx.coroutines.launch

/**
 * 设备页：在线状态、固件版本、各 4G 模组的完整状态，支持编辑备注与隐藏卡槽。
 */
class DevicesFragment : Fragment() {

    private var _binding: FragmentDevicesBinding? = null
    private val binding get() = _binding!!

    private val api = ApiClient()

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentDevicesBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        binding.swipeRefresh.setOnRefreshListener { loadDevices() }
        binding.swipeRefresh.setColorSchemeColors(requireContext().getColor(R.color.brand))
        loadDevices()
    }

    override fun onResume() {
        super.onResume()
        loadDevices()
    }

    private fun loadDevices() {
        lifecycleScope.launch {
            try {
                val devices = api.devices()
                render(devices)
            } catch (e: Exception) {
                if (isAdded) {
                    Toast.makeText(requireContext(), e.message ?: "加载失败", Toast.LENGTH_SHORT).show()
                }
            } finally {
                if (_binding != null) binding.swipeRefresh.isRefreshing = false
            }
        }
    }

    private fun render(devices: List<Device>) {
        val ctx = requireContext()
        binding.deviceContainer.removeAllViews()
        binding.emptyText.visibility = if (devices.isEmpty()) View.VISIBLE else View.GONE
        if (devices.isEmpty()) return

        val inflater = LayoutInflater.from(ctx)
        for (dev in devices) {
            val card = com.smsatbox.app.databinding.ItemDeviceBinding
                .inflate(inflater, binding.deviceContainer, false)

            card.deviceName.text = dev.name
            card.onlineText.text = if (dev.online) "在线" else "离线"
            card.onlineDot.setBackgroundResource(
                if (dev.online) R.drawable.bg_dot_online else R.drawable.bg_dot_offline
            )
            card.firmwareText.text = "v${dev.firmwareVersion.ifEmpty { "-" }}"
            card.netModeText.text = when (dev.netMode) {
                "wifi" -> "WiFi"
                "4g" -> "4G 流量"
                else -> "离线"
            }
            card.ipText.text = dev.localIp.ifEmpty { "-" }
            card.rssiText.text =
                if (dev.wifiRssi < 0) "${dev.wifiRssi} dBm" else "-"

            // 卡槽列表
            card.slotContainer.removeAllViews()
            for (slot in dev.slots) {
                val slotView = inflater.inflate(R.layout.item_slot, card.slotContainer, false)
                bindSlot(slotView, slot)
                card.slotContainer.addView(slotView)
            }

            binding.deviceContainer.addView(card.root)
        }
    }

    /** 把卡槽数据绑到视图上，并接好点击事件。 */
    private fun bindSlot(view: View, slot: SimSlot) {
        val m = slot.module

        view.findViewById<android.widget.TextView>(R.id.slotIndex).text =
            slot.slotIndex.toString()

        // 名称：优先备注
        view.findViewById<android.widget.TextView>(R.id.slotNumber).text = slot.displayName

        // 运营商
        view.findViewById<android.widget.TextView>(R.id.slotCarrier).text =
            m.carrier.ifEmpty { slot.carrier.ifEmpty { "未知运营商" } }

        // 信号
        val signalText = when {
            !m.present -> "无模组"
            !m.hasSignal -> "无信号"
            else -> "${m.signalDbm ?: slot.signalDbm} dBm · ${m.signalLevel}/4"
        }
        view.findViewById<android.widget.TextView>(R.id.slotSignal).text = signalText

        // 套餐 / 状态描述
        val planView = view.findViewById<android.widget.TextView>(R.id.slotPlan)
        planView.text = buildString {
            if (slot.planExpireAt != null) {
                append("套餐至 ${slot.planExpireAt.take(10)}")
            } else {
                append(slot.planName.ifEmpty { "默认套餐" })
            }
            if (!slot.visible) append(" · 已隐藏")
        }

        // 隐藏状态视觉弱化
        view.alpha = if (slot.visible) 1f else 0.5f

        // 点击卡槽 → 编辑
        view.setOnClickListener { showSlotEditor(slot) }
    }

    /** 卡槽编辑弹窗：改备注、拨号号码、显示/隐藏。 */
    private fun showSlotEditor(slot: SimSlot) {
        val ctx = requireContext()
        val container = android.widget.LinearLayout(ctx).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setPadding(48, 32, 48, 8)
        }

        fun label(text: String) {
            container.addView(android.widget.TextView(ctx).apply {
                this.text = text
                textSize = 12f
                setTextColor(ContextCompat.getColor(ctx, R.color.text_2))
                setPadding(0, 20, 0, 6)
            })
        }

        label("备注名称")
        val remarkInput = android.widget.EditText(ctx).apply {
            setText(slot.remark)
            hint = "例如 主力卡 / 工作号"
            setTextColor(ContextCompat.getColor(ctx, R.color.text_0))
            setHintTextColor(ContextCompat.getColor(ctx, R.color.text_2))
        }
        container.addView(remarkInput)

        label("手机号码")
        val numberInput = android.widget.EditText(ctx).apply {
            setText(slot.phoneNumber)
            hint = "用于识别卡槽"
            setTextColor(ContextCompat.getColor(ctx, R.color.text_0))
            setHintTextColor(ContextCompat.getColor(ctx, R.color.text_2))
        }
        container.addView(numberInput)

        val visibleSwitch = android.widget.Switch(ctx).apply {
            text = "在消息列表中显示"
            isChecked = slot.visible
            setTextColor(ContextCompat.getColor(ctx, R.color.text_1))
            setPadding(0, 28, 0, 0)
        }
        container.addView(visibleSwitch)

        // 模组状态只读展示
        val info = android.widget.TextView(ctx).apply {
            text = buildString {
                append("模组：").append(if (m0(slot).present) "已检测" else "未检测")
                append("\nSIM：").append(if (m0(slot).simReady) "就绪" else "未就绪")
                append("\n网络：").append(m0(slot).regText.ifEmpty { "未知" })
                if (m0(slot).lac.isNotEmpty()) {
                    append("\nLAC/小区：").append(m0(slot).lac).append(" / ").append(m0(slot).cellId)
                }
                if (m0(slot).imsi.isNotEmpty()) append("\nIMSI：").append(m0(slot).imsi)
                if (m0(slot).iccid.isNotEmpty()) append("\nICCID：").append(m0(slot).iccid)
                if (m0(slot).imei.isNotEmpty()) append("\nIMEI：").append(m0(slot).imei)
            }
            textSize = 11f
            setTextColor(ContextCompat.getColor(ctx, R.color.text_2))
            setPadding(0, 28, 0, 0)
            setLineSpacing(0f, 1.5f)
        }
        container.addView(info)

        AlertDialog.Builder(ctx)
            .setTitle("编辑 ${slot.displayName}")
            .setView(android.widget.ScrollView(ctx).apply { addView(container) })
            .setPositiveButton("保存") { _, _ ->
                saveSlot(
                    slot,
                    remarkInput.text.toString().trim(),
                    numberInput.text.toString().trim(),
                    visibleSwitch.isChecked
                )
            }
            .setNegativeButton("取消", null)
            .show()
    }

    private fun m0(slot: SimSlot) = slot.module

    private fun saveSlot(slot: SimSlot, remark: String, number: String, visible: Boolean) {
        lifecycleScope.launch {
            try {
                api.updateSlot(
                    slotId = slot.id,
                    remark = remark,
                    phoneNumber = number,
                    visible = visible,
                )
                Toast.makeText(requireContext(), "已保存", Toast.LENGTH_SHORT).show()
                loadDevices()
            } catch (e: Exception) {
                Toast.makeText(requireContext(), e.message ?: "保存失败", Toast.LENGTH_SHORT).show()
            }
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}
