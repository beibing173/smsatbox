package com.smsatbox.app.ui

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.Toast
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.smsatbox.app.Prefs
import com.smsatbox.app.R
import com.smsatbox.app.data.ApiClient
import com.smsatbox.app.data.Device
import com.smsatbox.app.databinding.FragmentDevicesBinding
import kotlinx.coroutines.launch

/**
 * 设备页：在线状态、固件版本、各卡槽信号强度。
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
            card.firmwareText.text = "固件 v${dev.firmwareVersion.ifEmpty { "-" }}"
            card.netModeText.text = when (dev.netMode) {
                "wifi" -> "WiFi"
                "4g" -> "4G 流量"
                else -> "离线"
            }
            card.ipText.text = "IP ${dev.localIp.ifEmpty { "-" }}"
            card.rssiText.text =
                if (dev.wifiRssi < 0) "信号 ${dev.wifiRssi} dBm" else "信号 -"

            // 卡槽列表
            card.slotContainer.removeAllViews()
            for (slot in dev.slots) {
                val slotView = inflater.inflate(R.layout.item_slot, card.slotContainer, false)
                slotView.findViewById<android.widget.TextView>(R.id.slotIndex).text =
                    slot.slotIndex.toString()
                slotView.findViewById<android.widget.TextView>(R.id.slotNumber).text =
                    "号码 ${slot.phoneNumber.ifEmpty { "未设置" }}"
                slotView.findViewById<android.widget.TextView>(R.id.slotCarrier).text =
                    slot.carrier.ifEmpty { "未知运营商" }
                slotView.findViewById<android.widget.TextView>(R.id.slotSignal).text =
                    if (slot.signalDbm in -140..0) "${slot.signalDbm} dBm" else "未知"
                slotView.findViewById<android.widget.TextView>(R.id.slotPlan).text =
                    if (slot.planExpireAt != null) {
                        "套餐至 ${slot.planExpireAt.take(10)}"
                    } else {
                        slot.planName.ifEmpty { "默认套餐" }
                    }
                card.slotContainer.addView(slotView)
            }

            binding.deviceContainer.addView(card.root)
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}
