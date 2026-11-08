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
    private val esimFragment by lazy { EsimFragment() }
    private val settingsFragment by lazy { SettingsFragment() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // 未登录直接回登录页（正常流程下 LoginActivity 才应是入口）
        if (!Prefs.isLoggedIn) {
            goLogin()
            return
        }

        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setupNav()
        applySystemBarStyle()

        // 底部版本号（要求：三端布局一致，底部标注版本号）
        binding.versionText.text = "v${BuildConfig.APP_VERSION}"

        if (savedInstanceState == null) {
            switchTab(TAB_MESSAGES)
        }

        // 请求通知权限（Android 13+ 才有这个运行时权限）
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && !Notifier.hasPermission(this)) {
            requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), 1001)
        }
    }

    private fun goLogin() {
        startActivity(Intent(this, LoginActivity::class.java))
        finish()
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
            goLogin()
        }
    }

    private fun setupNav() {
        binding.navView.setOnItemSelectedListener { item ->
            when (item.itemId) {
                R.id.nav_messages -> { switchTab(TAB_MESSAGES); true }
                R.id.nav_devices -> { switchTab(TAB_DEVICES); true }
                R.id.nav_esim -> { switchTab(TAB_ESIM); true }
                R.id.nav_settings -> { switchTab(TAB_SETTINGS); true }
                else -> false
            }
        }
        binding.navView.selectedItemId = R.id.nav_messages
    }

    private fun switchTab(tab: Int) {
        val fragment: Fragment = when (tab) {
            TAB_DEVICES -> devicesFragment
            TAB_ESIM -> esimFragment
            TAB_SETTINGS -> settingsFragment
            else -> messagesFragment
        }
        supportFragmentManager.beginTransaction()
            .replace(R.id.container, fragment)
            .commit()
    }

    /** 状态栏 / 导航栏图标明暗：由当前实际生效的日夜模式决定（系统已自动切换资源）。 */
    @SuppressLint("InlinedApi")
    private fun applySystemBarStyle() {
        val isLight = isLightThemeNow()
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

    /** 当前解析后的主题是否为浅色（系统日夜模式已由 AppCompatDelegate 接管）。 */
    private fun isLightThemeNow(): Boolean {
        val mode = resources.configuration.uiMode and
                android.content.res.Configuration.UI_MODE_NIGHT_MASK
        return mode != android.content.res.Configuration.UI_MODE_NIGHT_YES
    }

    companion object {
        const val TAB_MESSAGES = 0
        const val TAB_DEVICES = 1
        const val TAB_ESIM = 2
        const val TAB_SETTINGS = 3
    }
}
