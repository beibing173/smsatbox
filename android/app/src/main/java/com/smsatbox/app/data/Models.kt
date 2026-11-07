package com.smsatbox.app.data

/**
 * 数据模型（与 Server API 的 JSON 结构一一对应）
 */

/** 短信 / 来电记录 */
data class Message(
    val id: Int,
    val deviceId: Int,
    val deviceName: String,
    val slotId: Int?,
    val slotIndex: Int?,
    val slotNumber: String,
    val kind: String,          // sms | call | system
    val sender: String,
    val content: String,
    val code: String?,         // 自动提取的验证码
    val receivedAt: String,
    val isRead: Boolean
) {
    val isCall: Boolean get() = kind == "call"
    val title: String get() = sender.ifEmpty { "未知号码" }
    val slotLabel: String get() = slotIndex?.let { "卡槽 $it" } ?: "—"
}

/** 4G 模组的实时状态（ESP32 上报） */
data class ModuleStatus(
    val present: Boolean = false,
    val moduleState: String = "",
    val simState: String = "",
    val registered: Boolean = false,
    val regStatus: Int = 4,
    val regText: String = "",
    val lac: String = "",
    val cellId: String = "",
    val csq: Int = 99,
    val signalDbm: Int? = null,
    val signalLevel: Int = 0,
    val carrier: String = "",
    val phoneNumber: String = "",
    val imsi: String = "",
    val iccid: String = "",
    val imei: String = "",
) {
    val hasSignal: Boolean get() = present && csq in 0..31
    val simReady: Boolean get() = simState == "ready"
    val moduleReady: Boolean get() = moduleState == "ready"
}

/** SIM 卡槽 */
data class SimSlot(
    val id: Int,
    val slotIndex: Int,
    val phoneNumber: String,
    val carrier: String,
    val signalDbm: Int,
    val planName: String,
    val planExpireAt: String?,
    val remark: String = "",
    val visible: Boolean = true,
    val module: ModuleStatus = ModuleStatus(),
) {
    /** 优先显示备注，其次号码，最后"卡槽 N" */
    val displayName: String
        get() = remark.ifEmpty { phoneNumber.ifEmpty { "卡槽 $slotIndex" } }
}

/** 设备 */
data class Device(
    val id: Int,
    val name: String,
    val online: Boolean,
    val firmwareVersion: String,
    val netMode: String,
    val localIp: String,
    val wifiRssi: Int,
    val lastSeenAt: String?,
    val remark: String = "",
    val slots: List<SimSlot>
)

/** 分页消息结果 */
data class MessagePage(
    val items: List<Message>,
    val total: Int
)

/** 统计 */
data class Stats(
    val total: Int,
    val unread: Int,
    val today: Int,
    val codes: Int
)

/** GitHub Release 中的资产 */
data class ReleaseAsset(
    val name: String,
    val downloadUrl: String,
    val size: Long
)

/** GitHub 最新版本信息（供 APK / EXE 独立升级） */
data class ReleaseInfo(
    val tagName: String,
    val version: String,
    val body: String,
    val htmlUrl: String,
    val publishedAt: String,
    val assets: List<ReleaseAsset>
) {
    /** 找 apk 资产 */
    fun apkAsset(): ReleaseAsset? =
        assets.firstOrNull { it.name.endsWith(".apk", ignoreCase = true) }
}
