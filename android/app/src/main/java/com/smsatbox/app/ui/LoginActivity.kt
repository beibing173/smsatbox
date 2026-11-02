package com.smsatbox.app.ui

import android.content.Intent
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.WindowInsetsController
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.smsatbox.app.BuildConfig
import com.smsatbox.app.Prefs
import com.smsatbox.app.R
import com.smsatbox.app.data.ApiClient
import com.smsatbox.app.databinding.ActivityLoginBinding
import kotlinx.coroutines.launch

/**
 * 登录页：手动填写「公网中转平台地址」和 Token。
 *
 * Token 可以是：
 *  - 用用户名密码换来的 JWT（通过 /auth/login）
 *  - 管理端生成的客户端长效令牌
 */
class LoginActivity : AppCompatActivity() {

    private lateinit var binding: ActivityLoginBinding
    private val api = ApiClient()

    override fun onCreate(savedInstanceState: Bundle?) {
        applyTheme()
        super.onCreate(savedInstanceState)
        binding = ActivityLoginBinding.inflate(layoutInflater)
        setContentView(binding.root)

        applySystemBarStyle()

        binding.versionText.text = "v${BuildConfig.APP_VERSION}"
        binding.serverInput.setText(Prefs.serverUrl)
        binding.tokenInput.setText(Prefs.token)

        binding.loginButton.setOnClickListener { doLogin() }
        binding.serverInput.setOnEditorActionListener { _, _, _ ->
            binding.tokenInput.requestFocus()
            true
        }
    }

    private fun doLogin() {
        val server = binding.serverInput.text?.toString()?.trim().orEmpty()
        val token = binding.tokenInput.text?.toString()?.trim().orEmpty()

        if (server.isEmpty()) {
            binding.errorText.text = "请填写中转平台地址"
            binding.errorText.visibility = View.VISIBLE
            return
        }
        if (token.isEmpty()) {
            binding.errorText.text = "请填写访问 Token"
            binding.errorText.visibility = View.VISIBLE
            return
        }

        Prefs.serverUrl = server
        Prefs.token = token

        setLoading(true)
        binding.errorText.visibility = View.GONE

        lifecycleScope.launch {
            try {
                val user = api.verify().optJSONObject("user")
                if (user != null) {
                    Prefs.userName = user.optString("display_name").ifEmpty {
                        user.optString("username")
                    }
                    Prefs.userRole = user.optString("role", "member")
                }
                setLoading(false)
                startActivity(Intent(this@LoginActivity, MainActivity::class.java))
                finish()
            } catch (e: Exception) {
                setLoading(false)
                binding.errorText.text = e.message ?: "连接失败，请检查地址与 Token"
                binding.errorText.visibility = View.VISIBLE
            }
        }
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

    private fun applyTheme() {
        if (Prefs.themeMode == "light") setTheme(R.style.Theme_SMSATBOX_Light)
        else setTheme(R.style.Theme_SMSATBOX)
    }

    private fun applySystemBarStyle() {
        val isLight = Prefs.themeMode == "light" ||
                (Prefs.themeMode == "system" && isSystemLight())
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

    private fun isSystemLight(): Boolean {
        val mode = resources.configuration.uiMode and
                android.content.res.Configuration.UI_MODE_NIGHT_MASK
        return mode != android.content.res.Configuration.UI_MODE_NIGHT_YES
    }
}
