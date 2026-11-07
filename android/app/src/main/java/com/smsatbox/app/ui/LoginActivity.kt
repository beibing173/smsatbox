package com.smsatbox.app.ui

import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.WindowInsetsController
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.smsatbox.app.BuildConfig
import com.smsatbox.app.Prefs
import com.smsatbox.app.R
import com.smsatbox.app.ThemeApplier
import com.smsatbox.app.ThemeMode
import com.smsatbox.app.data.ApiClient
import com.smsatbox.app.databinding.ActivityLoginBinding
import kotlinx.coroutines.launch

/**
 * 登录页 —— 应用的启动入口。
 *
 * 三项输入：中转平台地址 + 账号 + 密码。
 * 登录成功后服务端返回 JWT，保存在本地用于后续请求。
 */
class LoginActivity : AppCompatActivity() {

    private lateinit var binding: ActivityLoginBinding
    private val api = ApiClient()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityLoginBinding.inflate(layoutInflater)
        setContentView(binding.root)

        applySystemBarStyle()

        binding.versionText.text = "v${BuildConfig.APP_VERSION}"
        binding.serverInput.setText(Prefs.serverUrl)
        binding.usernameInput.setText(Prefs.lastUsername)
        binding.passwordInput.setText("")

        binding.loginButton.setOnClickListener { doLogin() }
        binding.themeButton.setOnClickListener { cycleTheme() }
        syncThemeButton()

        // 已有有效 Token → 静默验证后直接进主页
        if (Prefs.serverUrl.isNotEmpty() && Prefs.token.isNotEmpty()) {
            autoLogin()
        }
    }

    /** 已保存 Token，先验证有效性再决定是否直接进主页。 */
    private fun autoLogin() {
        setLoading(true)
        lifecycleScope.launch {
            try {
                val res = api.verify()
                val user = res.optJSONObject("user")
                if (user != null) {
                    Prefs.userName = user.optString("display_name")
                        .ifEmpty { user.optString("username") }
                    Prefs.userRole = user.optString("role", "member")
                }
                setLoading(false)
                goMain()
            } catch (e: Exception) {
                // Token 失效，留在登录页
                Prefs.clearSession()
                setLoading(false)
            }
        }
    }

    private fun doLogin() {
        val server = binding.serverInput.text?.toString()?.trim().orEmpty()
        val username = binding.usernameInput.text?.toString()?.trim().orEmpty()
        val password = binding.passwordInput.text?.toString() ?: ""

        if (server.isEmpty()) {
            showError("请填写中转平台地址")
            return
        }
        if (username.isEmpty()) {
            showError("请填写账号")
            return
        }
        if (password.isEmpty()) {
            showError("请填写密码")
            return
        }

        Prefs.serverUrl = server

        setLoading(true)
        binding.errorText.visibility = View.GONE

        lifecycleScope.launch {
            try {
                val res = api.login(username, password)

                val token = res.optString("access_token")
                if (token.isEmpty()) {
                    setLoading(false)
                    showError("服务端未返回访问令牌")
                    return@launch
                }
                Prefs.token = token

                val user = res.optJSONObject("user")
                if (user != null) {
                    Prefs.userName = user.optString("display_name")
                        .ifEmpty { user.optString("username") }
                    Prefs.userRole = user.optString("role", "member")
                }
                Prefs.lastUsername = username

                setLoading(false)
                goMain()
            } catch (e: Exception) {
                setLoading(false)
                val msg = e.message ?: ""
                showError(
                    when {
                        msg.contains("401") || msg.contains("用户名或密码") ->
                            "账号或密码错误"
                        msg.contains("403") -> "该账号已被禁用"
                        else -> msg.ifEmpty { "连接失败，请检查地址" }
                    }
                )
            }
        }
    }

    private fun goMain() {
        startActivity(Intent(this, MainActivity::class.java))
        finish()
    }

    private fun showError(msg: String) {
        binding.errorText.text = msg
        binding.errorText.visibility = View.VISIBLE
    }

    private fun setLoading(loading: Boolean) {
        binding.loginButton.isEnabled = !loading
        binding.loginButton.text = if (loading) {
            getString(R.string.login_verifying)
        } else {
            getString(R.string.login_button)
        }
        binding.progressBar.visibility = if (loading) View.VISIBLE else View.GONE
    }

    // ===== 主题 =====

    private fun syncThemeButton() {
        binding.themeButton.text = when (Prefs.themeMode) {
            ThemeMode.DARK -> "🌙 深色"
            ThemeMode.LIGHT -> "☀ 浅色"
            ThemeMode.SYSTEM -> "🖥 跟随系统"
        }
    }

    private fun cycleTheme() {
        val next = when (Prefs.themeMode) {
            ThemeMode.SYSTEM -> ThemeMode.DARK
            ThemeMode.DARK -> ThemeMode.LIGHT
            ThemeMode.LIGHT -> ThemeMode.SYSTEM
        }
        ThemeApplier.set(this, next)
        syncThemeButton()
    }

    private fun applySystemBarStyle() {
        val isLight = isLightThemeNow()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.insetsController?.let { c ->
                val mask = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS or
                        WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS
                c.setSystemBarsAppearance(if (isLight) mask else 0, mask)
            }
        } else {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility =
                if (isLight) View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR else 0
        }
    }

    private fun isLightThemeNow(): Boolean {
        val mode = resources.configuration.uiMode and
                android.content.res.Configuration.UI_MODE_NIGHT_MASK
        return mode != android.content.res.Configuration.UI_MODE_NIGHT_YES
    }
}
