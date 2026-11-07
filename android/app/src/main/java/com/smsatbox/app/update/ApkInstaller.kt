package com.smsatbox.app.update

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * APK 下载与安装。
 *
 * 兼容性：
 *  - Android 8.0+ 需要「安装未知应用」权限，用 FileProvider 提供 content:// URI
 *  - Android 7.0+ 必须用 FileProvider（file:// 会抛 FileUriExposedException）
 *  - Android 6.0 及以下可直接用 file:// URI
 */
object ApkInstaller {

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .followRedirects(true)
        .build()

    private fun updateDir(ctx: Context): File =
        File(ctx.getExternalFilesDir(null) ?: ctx.filesDir, "updates").apply { mkdirs() }

    /**
     * 下载 APK。
     * @param onProgress 已下载字节数 / 总字节数（总数为 0 时表示未知）
     */
    suspend fun download(
        ctx: Context,
        url: String,
        fileName: String,
        onProgress: (downloaded: Long, total: Long) -> Unit
    ): File = withContext(Dispatchers.IO) {
        val dir = updateDir(ctx)
        val target = File(dir, "smsatbox.apk")
        if (target.exists()) target.delete()

        val req = Request.Builder()
            .url(url)
            .header("Accept", "application/octet-stream")
            .header("User-Agent", "SMSATBOX-Android")
            .build()

        client.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) {
                throw java.io.IOException("下载失败 HTTP ${resp.code}")
            }
            val body = resp.body ?: throw java.io.IOException("响应为空")
            val total = body.contentLength()
            var downloaded = 0L

            val tmp = File(dir, "smsatbox.apk.part")
            if (tmp.exists()) tmp.delete()

            body.byteStream().use { input ->
                tmp.outputStream().use { output ->
                    val buffer = ByteArray(64 * 1024)
                    while (true) {
                        val n = input.read(buffer)
                        if (n <= 0) break
                        output.write(buffer, 0, n)
                        downloaded += n
                        onProgress(downloaded, total)
                    }
                }
            }
            if (tmp.length() <= 0) throw java.io.IOException("下载内容为空")

            if (target.exists()) target.delete()
            if (!tmp.renameTo(target)) {
                tmp.copyTo(target, overwrite = true)
                tmp.delete()
            }
            target
        }
    }

    /** 系统是否允许安装未知来源应用（Android 8.0+ 才有这个概念） */
    fun canInstall(ctx: Context): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            ctx.packageManager.canRequestPackageInstalls()
        } else {
            true
        }
    }

    /** 跳转到「安装未知应用」授权页（仅 Android 8.0+） */
    fun openInstallPermission(ctx: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        try {
            val intent = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES).apply {
                data = Uri.parse("package:${ctx.packageName}")
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            ctx.startActivity(intent)
        } catch (e: Exception) {
            // 个别定制系统没有这个设置页，退回到应用详情页
            try {
                val fallback = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                    data = Uri.parse("package:${ctx.packageName}")
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                ctx.startActivity(fallback)
            } catch (_: Exception) {
                // 彻底失败则忽略
            }
        }
    }

    /** 拉起系统安装器 */
    fun install(ctx: Context, apk: File) {
        val intent = Intent(Intent.ACTION_VIEW)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            // Android 7.0+ 必须用 FileProvider
            val uri: Uri = FileProvider.getUriForFile(
                ctx,
                "${ctx.packageName}.fileprovider",
                apk
            )
            intent.setDataAndType(uri, "application/vnd.android.package-archive")
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        } else {
            // Android 6.0 及以下可直接用 file://
            @Suppress("DEPRECATION")
            intent.setDataAndType(
                Uri.fromFile(apk),
                "application/vnd.android.package-archive"
            )
        }

        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        ctx.startActivity(intent)
    }
}
