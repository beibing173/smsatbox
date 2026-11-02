package com.smsatbox.app

import android.content.Context
import android.content.SharedPreferences

/**
 * 主题模式。
 */
enum class ThemeMode(val key: String) {
    /** 跟随系统（默认）。 */
    SYSTEM("system"),

    /** 强制深色。 */
    DARK("dark"),

    /** 强制浅色。 */
    LIGHT("light");

    companion object {
        fun fromKey(value: String?): ThemeMode =
            entries.firstOrNull { it.key == value } ?: SYSTEM
    }
}

/**
 * 本地配置存储。
 *
 * 只保存客户端所需的连接信息与外观偏好，不保存任何服务器端凭据。
 * 注意：这里存的是用户自己的访问 Token，与 ESP32 的 Device_Token 无关。
 */
object Prefs {

    private const val FILE = "smsatbox_prefs"
    private const val KEY_SERVER = "server_url"
    private const val KEY_TOKEN = "access_token"
    private const val KEY_THEME = "theme_mode"
    private const val KEY_NOTIFY = "notify_enabled"
    private const val KEY_LAST_MSG_ID = "last_message_id"
    private const val KEY_USER_NAME = "user_name"
    private const val KEY_USER_ROLE = "user_role"

    private lateinit var sp: SharedPreferences

    fun init(ctx: Context) {
        sp = ctx.getSharedPreferences(FILE, Context.MODE_PRIVATE)
    }

    var serverUrl: String
        get() = sp.getString(KEY_SERVER, "") ?: ""
        set(value) = sp.edit().putString(KEY_SERVER, value.trimEnd('/')).apply()

    var token: String
        get() = sp.getString(KEY_TOKEN, "") ?: ""
        set(value) = sp.edit().putString(KEY_TOKEN, value).apply()

    /** 主题模式，默认跟随系统。 */
    var themeMode: ThemeMode
        get() = ThemeMode.fromKey(sp.getString(KEY_THEME, null))
        set(value) = sp.edit().putString(KEY_THEME, value.key).apply()

    var notifyEnabled: Boolean
        get() = sp.getBoolean(KEY_NOTIFY, true)
        set(value) = sp.edit().putBoolean(KEY_NOTIFY, value).apply()

    var lastMessageId: Int
        get() = sp.getInt(KEY_LAST_MSG_ID, 0)
        set(value) = sp.edit().putInt(KEY_LAST_MSG_ID, value).apply()

    var userName: String
        get() = sp.getString(KEY_USER_NAME, "") ?: ""
        set(value) = sp.edit().putString(KEY_USER_NAME, value).apply()

    var userRole: String
        get() = sp.getString(KEY_USER_ROLE, "member") ?: "member"
        set(value) = sp.edit().putString(KEY_USER_ROLE, value).apply()

    val isLoggedIn: Boolean
        get() = serverUrl.isNotEmpty() && token.isNotEmpty()

    fun clearSession() {
        sp.edit()
            .remove(KEY_TOKEN)
            .remove(KEY_USER_NAME)
            .remove(KEY_USER_ROLE)
            .apply()
    }
}
