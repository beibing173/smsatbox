package com.smsatbox.app.data

import com.smsatbox.app.BuildConfig
import com.smsatbox.app.Prefs
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * 云端中转平台 API 客户端。
 *
 * 所有请求统一携带版本标识（X-Client-Version），
 * 与全平台版本约定一致。
 */
class ApiClient {

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .build()

    private val jsonType = "application/json; charset=utf-8".toMediaType()

    /** 服务端返回的业务错误 */
    class ApiException(val status: Int, message: String) : IOException(message)

    private fun baseUrl(): String {
        val s = Prefs.serverUrl
        if (s.isEmpty()) throw ApiException(0, "尚未配置中转平台地址")
        return if (s.endsWith("/api/v1")) s else "$s/api/v1"
    }

    private fun buildRequest(path: String, method: String = "GET", body: JSONObject? = null): Request {
        val builder = Request.Builder()
            .url(baseUrl() + path)
            .header("X-Client-Version", BuildConfig.APP_VERSION)
            .header("X-Client-Platform", "android")
            .header("Accept", "application/json")

        if (Prefs.token.isNotEmpty()) {
            builder.header("Authorization", "Bearer ${Prefs.token}")
        }
        when (method) {
            "POST" -> builder.post((body?.toString() ?: "{}").toRequestBody(jsonType))
            "PATCH" -> builder.patch((body?.toString() ?: "{}").toRequestBody(jsonType))
            "DELETE" -> builder.delete()
            else -> builder.get()
        }
        return builder.build()
    }

    private suspend fun execute(path: String, method: String = "GET", body: JSONObject? = null): JSONObject =
        withContext(Dispatchers.IO) {
            val req = buildRequest(path, method, body)
            client.newCall(req).execute().use { resp ->
                val text = resp.body?.string().orEmpty()
                if (!resp.isSuccessful) {
                    val detail = try {
                        JSONObject(text).optString("detail", "请求失败 ${resp.code}")
                    } catch (e: Exception) {
                        "请求失败 ${resp.code}"
                    }
                    throw ApiException(resp.code, detail)
                }
                if (text.isBlank()) JSONObject() else JSONObject(text)
            }
        }

    // ------------------------------------------------------------------
    // 鉴权
    // ------------------------------------------------------------------

    /** 用用户名密码登录，换取 JWT */
    suspend fun login(username: String, password: String): JSONObject {
        val body = JSONObject().apply {
            put("username", username)
            put("password", password)
        }
        return execute("/auth/login", "POST", body)
    }

    /** 用已保存的 Token 验证有效性 */
    suspend fun verify(): JSONObject = execute("/auth/verify")

    // ------------------------------------------------------------------
    // 消息
    // ------------------------------------------------------------------

    suspend fun messages(limit: Int = 50, offset: Int = 0, slotId: Int? = null): MessagePage {
        val q = buildString {
            append("/messages?limit=$limit&offset=$offset")
            if (slotId != null) append("&slot_id=$slotId")
        }
        val json = execute(q)
        val arr = json.optJSONArray("items") ?: JSONArray()
        val list = ArrayList<Message>(arr.length())
        for (i in 0 until arr.length()) {
            list.add(parseMessage(arr.getJSONObject(i)))
        }
        return MessagePage(list, json.optInt("total", list.size))
    }

    suspend fun stats(): Stats {
        val json = execute("/messages/stats")
        return Stats(
            total = json.optInt("total"),
            unread = json.optInt("unread"),
            today = json.optInt("today"),
            codes = json.optInt("codes")
        )
    }

    suspend fun markRead(id: Int, read: Boolean = true) {
        val body = JSONObject().apply { put("is_read", read) }
        execute("/messages/$id", "PATCH", body)
    }

    // ------------------------------------------------------------------
    // 设备
    // ------------------------------------------------------------------

    /** 修改卡槽：备注 / 号码 / 运营商 / 显示或隐藏。 */
    suspend fun updateSlot(
        slotId: Int,
        remark: String? = null,
        phoneNumber: String? = null,
        carrier: String? = null,
        planName: String? = null,
        visible: Boolean? = null,
    ): JSONObject {
        val body = JSONObject()
        remark?.let { body.put("remark", it) }
        phoneNumber?.let { body.put("phone_number", it) }
        carrier?.let { body.put("carrier", it) }
        planName?.let { body.put("plan_name", it) }
        visible?.let { body.put("is_active", it) }
        return execute("/devices/slots/$slotId", "PATCH", body)
    }

    /** 修改设备名称 / 备注（需要超级管理员）。 */
    suspend fun updateDevice(
        deviceId: Int,
        name: String? = null,
        remark: String? = null,
    ): JSONObject {
        val body = JSONObject()
        name?.let { body.put("device_name", it) }
        remark?.let { body.put("remark", it) }
        return execute("/devices/$deviceId", "PATCH", body)
    }

    suspend fun devices(): List<Device> {
        val json = execute("/devices")
        val arr = json.optJSONArray("items") ?: JSONArray()
        val list = ArrayList<Device>(arr.length())
        for (i in 0 until arr.length()) {
            list.add(parseDevice(arr.getJSONObject(i)))
        }
        return list
    }

    // ------------------------------------------------------------------
    // 解析
    // ------------------------------------------------------------------

    private fun parseMessage(o: JSONObject): Message = Message(
        id = o.optInt("id"),
        deviceId = o.optInt("device_id"),
        deviceName = o.optString("device_name"),
        slotId = if (o.isNull("slot_id")) null else o.optInt("slot_id"),
        slotIndex = if (o.isNull("slot_index")) null else o.optInt("slot_index"),
        slotNumber = o.optString("slot_number"),
        kind = o.optString("kind", "sms"),
        sender = o.optString("sender"),
        content = o.optString("content"),
        code = if (o.isNull("code")) null else o.optString("code").ifEmpty { null },
        receivedAt = o.optString("received_at"),
        isRead = o.optBoolean("is_read")
    )

    private fun parseSlot(o: JSONObject): SimSlot {
        val m = o.optJSONObject("module")
        val module = if (m != null) {
            ModuleStatus(
                present = m.optBoolean("present"),
                moduleState = m.optString("module_state"),
                simState = m.optString("sim_state"),
                registered = m.optBoolean("registered"),
                regStatus = m.optInt("reg_status", 4),
                regText = m.optString("reg_text"),
                lac = m.optString("lac"),
                cellId = m.optString("cell_id"),
                csq = m.optInt("rssi_csq", 99),
                signalDbm = if (m.isNull("signal_dbm")) null else m.optInt("signal_dbm"),
                signalLevel = m.optInt("signal_level"),
                carrier = m.optString("carrier"),
                phoneNumber = m.optString("phone_number"),
                imsi = m.optString("imsi"),
                iccid = m.optString("iccid"),
                imei = m.optString("imei"),
            )
        } else {
            ModuleStatus()
        }

        return SimSlot(
            id = o.optInt("id"),
            slotIndex = o.optInt("slot_index"),
            phoneNumber = o.optString("phone_number"),
            carrier = o.optString("carrier"),
            signalDbm = o.optInt("signal_dbm", 99),
            planName = o.optString("plan_name"),
            planExpireAt = if (o.isNull("plan_expire_at")) null else o.optString("plan_expire_at"),
            remark = o.optString("remark"),
            visible = if (o.has("visible")) o.optBoolean("visible", true) else o.optBoolean("is_active", true),
            module = module,
        )
    }

    private fun parseDevice(o: JSONObject): Device {
        val slotsArr = o.optJSONArray("slots") ?: JSONArray()
        val slots = ArrayList<SimSlot>(slotsArr.length())
        for (i in 0 until slotsArr.length()) {
            slots.add(parseSlot(slotsArr.getJSONObject(i)))
        }
        return Device(
            id = o.optInt("id"),
            name = o.optString("device_name").ifEmpty { "未命名设备" },
            online = o.optBoolean("online"),
            firmwareVersion = o.optString("firmware_version"),
            netMode = o.optString("net_mode"),
            localIp = o.optString("local_ip"),
            wifiRssi = o.optInt("wifi_rssi"),
            lastSeenAt = if (o.isNull("last_seen_at")) null else o.optString("last_seen_at"),
            remark = o.optString("remark"),
            slots = slots,
        )
    }
}
