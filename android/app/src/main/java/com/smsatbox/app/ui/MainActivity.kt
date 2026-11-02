package com.smsatbox.app.ui

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.WindowInsetsController
import androidx.appcompat.app.AppCompatActivity
import androidx.fragment.app.Fragment
import com.smsatbox.app.BuildConfig
import com.smsatbox.app.Prefs
import com.smsatbox.app.R
import com.smsatbox.app.databinding.ActivityMainBinding
import com.smsatbox.app.notify.Notifier

/**
 * 主界面：底部导航（消息 / 设备 / 设置），底部标注版本号。
 */
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding

    private val messagesFragment by lazy { MessagesFragment() }
    private val devicesFragment by lazy { DevicesFragment() }
    private val settingsFragment by lazy { SettingsFragment() }

    override fun onCreate(savedInstanceState: Bundle?) {
        applyTheme()
        super.onCreate(savedInstanceState)

        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setupNav()
        applySystemBarStyle()

        // 底部版本号（要求：三端布局一致，底部标注版本号）
        binding.versionText.text = "v${BuildConfig.APP_VERSION}"

        if (savedInstanceState == null) {
            switchTab(TAB_MESSAGES)
        }

        // 请求通知权限（Android 13+）
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && !Notifier.hasPermission(this)) {
            requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), 1001)
        }
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        // 从通知点击进入：切到消息页
        if (intent?.hasExtra("message_id") == true) {
            switchTab(TAB_MESSAGES)
        }
    }

    override fun onResume() {
        super.onResume()
        // 登录态失效则回到登录页
        if (!Prefs.isLoggedIn && !isFinishing) {
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
        }
    }

    private fun setupNav() {
        binding.navView.setOnItemSelectedListener { item ->
            when (item.itemId) {
                R.id.nav_messages -> { switchTab(TAB_MESSAGES); true }
                R.id.nav_devices -> { switchTab(TAB_DEVICES); true }
                R.id.nav_settings -> { switchTab(TAB_SETTINGS); true }
                else -> false
            }
        }
        binding.navView.selectedItemId = R.id.nav_messages
    }

    private fun switchTab(tab: Int) {
        val fragment: Fragment = when (tab) {
            TAB_DEVICES -> devicesFragment
            TAB_SETTINGS -> settingsFragment
            else -> messagesFragment
        }
        supportFragmentManager.beginTransaction()
            .replace(R.id.container, fragment)
            .commit()
    }

    /** 主题模式：system / dark / light */
    private fun applyTheme() {
        when (Prefs.themeMode) {
            "light" -> setTheme(R.style.Theme_SMSATBOX_Light)
            "dark" -> setTheme(R.style.Theme_SMSATBOX)
            else -> setTheme(R.style.Theme_SMSATBOX)
        }
    }

    @SuppressLint("InlinedApi")
    private fun applySystemBarStyle() {
        val isLight = Prefs.themeMode == "light" ||
                (Prefs.themeMode == "system" && isSystemInLightMode())
        val controller = window.insetsController
        if (controller != null) {
            val appearance = if (isLight) {
                WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS or
                        WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS
            } else 0
            controller.setSystemBarsAppearance(appearance, appearance)
        } else {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility =
                if (isLight) View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR else 0
        }
    }

    private fun isSystemInLightMode(): Boolean {
        val mode = resources.configuration.uiMode and
                android.content.res.Configuration.UI_MODE_NIGHT_MASK
        return mode != android.content.res.Configuration.UI_MODE_NIGHT_YES
    }

    companion object {
        const val TAB_MESSAGES = 0
        const val TAB_DEVICES = 1
        const val TAB_SETTINGS = 2
    }
}
