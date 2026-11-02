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
 * 下载到外部私有目录，再通过 FileProvider 交给系统安装器。
 */
object ApkInstaller {

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .followRedirects(true)
        .build()

    private fun updateDir(ctx: Context): File =
        File(ctx.getExternalFilesDir(null), "updates").apply { mkdirs() }

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
        val ico = File(updateDir(ctx), "smsatbox.apk")
        if (ico.exists()) ico.delete()

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
            val tmp = File(updateDir(ctx), "smsatbox.apk.part")
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
            if (tmp.renameTo(ico).not()) {
                tmp.copyTo(ico, overwrite = true)
                tmp.delete()
            }
            ico
        }
    }

    /** 系统是否允许安装未知来源应用 */
    fun canInstall(ctx: Context): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            ctx.packageManager.canRequestPackageInstalls()
        } else {
            true
        }
    }

    /** 跳转到“安装未知应用”授权页 */
    fun openInstallPermission(ctx: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val intent = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES).apply {
            data = Uri.parse("package:${ctx.packageName}")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        ctx.startActivity(intent)
    }

    /** 拉起系统安装器 */
    fun install(ctx: Context, apk: File) {
        val uri: Uri = FileProvider.getUriForFile(
            ctx,
            "${ctx.packageName}.fileprovider",
            apk
        )
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        ctx.startActivity(intent)
    }
}
