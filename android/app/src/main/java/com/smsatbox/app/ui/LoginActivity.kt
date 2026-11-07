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
 * 手动填写「公网中转平台地址 + Token」，也支持用用户名密码换取 JWT。
 * 已登录过则直接跳主界面。
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
        binding.tokenInput.setText(Prefs.token)

        binding.loginButton.setOnClickListener { doLogin() }
        binding.themeButton.setOnClickListener { cycleTheme() }
        syncThemeButton()

        // 已有凭据 → 静默校验后直接进主页
        if (Prefs.isLoggedIn) {
            autoLogin()
        }
    }

    /** 已保存 Token，先验证再决定是否直接进主页。 */
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
                // 验证失败就留在登录页，让用户手动确认
                setLoading(false)
            }
        }
    }

    private fun doLogin() {
        val server = binding.serverInput.text?.toString()?.trim().orEmpty()
        val token = binding.tokenInput.text?.toString()?.trim().orEmpty()

        if (server.isEmpty()) {
            showError("请填写中转平台地址")
            return
        }
        if (token.isEmpty()) {
            showError("请填写访问 Token")
            return
        }

        Prefs.serverUrl = server
        Prefs.token = token

        setLoading(true)
        binding.errorText.visibility = View.GONE

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
                setLoading(false)
                showError(e.message ?: "连接失败，请检查地址与 Token")
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
