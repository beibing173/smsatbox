package com.smsatbox.app.ui

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.smsatbox.app.BuildConfig
import com.smsatbox.app.Prefs
import com.smsatbox.app.R
import com.smsatbox.app.databinding.FragmentSettingsBinding
import com.smsatbox.app.update.ApkInstaller
import com.smsatbox.app.update.UpdateChecker
import kotlinx.coroutines.launch

/**
 * 设置页：连接信息、外观主题、消息通知、独立升级、退出登录。
 */
class SettingsFragment : Fragment() {

    private var _binding: FragmentSettingsBinding? = null
    private val binding get() = _binding!!

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentSettingsBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        binding.serverValue.text = Prefs.serverUrl.ifEmpty { "未配置" }
        binding.tokenValue.text = maskToken(Prefs.token)
        binding.userValue.text = Prefs.userName.ifEmpty { "—" }
        binding.currentVersion.text = "v${BuildConfig.APP_VERSION}"

        // 主题选择
        binding.themeGroup.check(
            when (Prefs.themeMode) {
                "dark" -> R.id.theme_dark
                "light" -> R.id.theme_light
                else -> R.id.theme_system
            }
        )
        binding.themeGroup.setOnCheckedChangeListener { _, checkedId ->
            Prefs.themeMode = when (checkedId) {
                R.id.theme_dark -> "dark"
                R.id.theme_light -> "light"
                else -> "system"
            }
            Toast.makeText(requireContext(), "主题已切换，重新进入生效", Toast.LENGTH_SHORT).show()
        }

        // 通知开关
        binding.notifySwitch.isChecked = Prefs.notifyEnabled
        binding.notifySwitch.setOnCheckedChangeListener { _, checked ->
            Prefs.notifyEnabled = checked
        }

        binding.updateButton.setOnClickListener { checkUpdate() }
        binding.logoutButton.setOnClickListener { confirmLogout() }
    }

    // ------------------------------------------------------------------
    // 独立升级：直连 GitHub Release API，绝不经过 Server
    // ------------------------------------------------------------------
    private fun checkUpdate() {
        binding.updateButton.isEnabled = false
        binding.updateButton.text = getString(R.string.update_checking)

        lifecycleScope.launch {
            try {
                val release = UpdateChecker.fetchLatest()
                when {
                    release == null -> {
                        toast("无法获取版本信息（仓库可能还没有 Release）")
                    }
                    !UpdateChecker.isNewer(release.version) -> {
                        toast(getString(R.string.update_latest) + "（v${BuildConfig.APP_VERSION}）")
                    }
                    else -> {
                        showUpdateDialog(release.version, release.body, release.apkAsset()?.downloadUrl)
                    }
                }
            } catch (e: Exception) {
                toast(e.message ?: getString(R.string.update_failed))
            } finally {
                if (_binding != null) {
                    binding.updateButton.isEnabled = true
                    binding.updateButton.text = getString(R.string.settings_check_update)
                }
            }
        }
    }

    private fun showUpdateDialog(version: String, notes: String, url: String?) {
        if (url == null) {
            AlertDialog.Builder(requireContext())
                .setTitle("${getString(R.string.update_available)} v$version")
                .setMessage("该版本未提供 APK 附件，请前往 Release 页面下载。")
                .setPositiveButton("知道了", null)
                .show()
            return
        }
        AlertDialog.Builder(requireContext())
            .setTitle("${getString(R.string.update_available)} v$version")
            .setMessage(notes.take(600).ifEmpty { "包含若干改进与修复。" })
            .setPositiveButton(R.string.update_download) { _, _ -> downloadAndInstall(url) }
            .setNegativeButton(R.string.update_later, null)
            .show()
    }

    private fun downloadAndInstall(url: String) {
        val ctx = requireContext()

        // 没有「安装未知应用」权限时先引导授权
        if (!ApkInstaller.canInstall(ctx)) {
            AlertDialog.Builder(ctx)
                .setTitle("需要安装权限")
                .setMessage("安装新版本需要允许本应用安装未知来源应用。")
                .setPositiveButton("去授权") { _, _ -> ApkInstaller.openInstallPermission(ctx) }
                .setNegativeButton("取消", null)
                .show()
            return
        }

        val progress = android.app.ProgressDialog(ctx).apply {
            setMessage(getString(R.string.update_downloading))
            setProgressStyle(android.app.ProgressDialog.STYLE_HORIZONTAL)
            max = 100
            setCancelable(false)
            show()
        }

        lifecycleScope.launch {
            try {
                val apk = ApkInstaller.download(ctx, url, "smsatbox.apk") { done, total ->
                    if (total > 0) {
                        progress.progress = ((done * 100) / total).toInt()
                    }
                }
                progress.dismiss()
                ApkInstaller.install(ctx, apk)
            } catch (e: Exception) {
                progress.dismiss()
                toast(e.message ?: getString(R.string.update_failed))
            }
        }
    }

    // ------------------------------------------------------------------

    private fun confirmLogout() {
        AlertDialog.Builder(requireContext())
            .setTitle("退出登录")
            .setMessage("退出后需要重新填写 Token 才能查看消息。")
            .setPositiveButton("退出") { _, _ ->
                Prefs.clearSession()
                val intent = Intent(requireContext(), LoginActivity::class.java)
                intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
                startActivity(intent)
            }
            .setNegativeButton("取消", null)
            .show()
    }

    private fun maskToken(token: String): String {
        if (token.isEmpty()) return "未配置"
        return if (token.length <= 12) "••••••"
        else "${token.take(6)}••••${token.takeLast(4)}"
    }

    private fun toast(msg: String) {
        if (isAdded) Toast.makeText(requireContext(), msg, Toast.LENGTH_SHORT).show()
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}
