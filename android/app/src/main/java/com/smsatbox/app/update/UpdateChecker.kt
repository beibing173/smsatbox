package com.smsatbox.app.update

import com.smsatbox.app.BuildConfig
import com.smsatbox.app.data.ReleaseAsset
import com.smsatbox.app.data.ReleaseInfo
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * 独立升级检查器 —— 直连 GitHub Release API。
 *
 * 【架构要求】更新检查与下载**绝不经过 Server 中转**，
 * 客户端内嵌代码直接访问 GitHub，与云端中转平台完全解耦。
 *
 * 【关键设计】一个 Release 同时承载 APK 与 EXE，两端版本号各自独立。
 * 因此不能用 Release 的 tag 当版本依据（tag 只是快照标识），
 * 而是从**自己那个附件文件名**里解析版本：
 *     smsatbox-android-1.2.0.apk  → 1.2.0
 *     smsatbox-windows-1.0.5.exe  → 1.0.5
 * 这样 Android 升级不会被 Windows 的版本号误导。
 */
object UpdateChecker {

    private const val LATEST_RELEASE_URL =
        "https://api.github.com/repos/%s/%s/releases/latest"

    /** 新命名：smsatbox-android-1.2.0.apk */
    private val ANDROID_ASSET = Regex(
        """^smsatbox-android-(?<ver>\d+\.\d+\.\d+)\.apk$""",
        RegexOption.IGNORE_CASE
    )

    /** 兼容旧命名：smsatbox-v1.0.0.apk */
    private val LEGACY_ASSET = Regex(
        """^(?:smsatbox-v?(?<ver>\d+\.\d+\.\d+)|smsatbox)\.apk$""",
        RegexOption.IGNORE_CASE
    )

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .followRedirects(true)
        .build()

    /** 从附件文件名解析版本号；解析不出返回 null */
    fun versionFromAssetName(name: String?): String? {
        if (name.isNullOrBlank()) return null
        ANDROID_ASSET.find(name)?.let { return it.groupValues[1] }
        LEGACY_ASSET.find(name)?.let { return it.groupValues[1] }
        return null
    }

    /** 在资产里挑 Android 的 .apk（优先新命名且版本最高） */
    private fun pickApkAsset(assets: List<ReleaseAsset>): ReleaseAsset? {
        val preferred = assets
            .filter { ANDROID_ASSET.matches(it.name) }
            .maxByOrNull { parseVersion(versionFromAssetName(it.name) ?: "0")?.let { v ->
                v[0] * 10000 + v[1] * 100 + v[2]
            } ?: 0 }
        if (preferred != null) return preferred

        return assets.firstOrNull { it.name.endsWith(".apk", ignoreCase = true) }
    }

    /** 查询最新 Release；无 Release 时返回 null */
    suspend fun fetchLatest(): ReleaseInfo? = withContext(Dispatchers.IO) {
        val url = LATEST_RELEASE_URL.format(BuildConfig.GITHUB_OWNER, BuildConfig.GITHUB_REPO)
        val req = Request.Builder()
            .url(url)
            .header("Accept", "application/vnd.github+json")
            .header("X-Client-Version", BuildConfig.APP_VERSION)
            .header("User-Agent", "SMSATBOX-Android/${BuildConfig.APP_VERSION}")
            .build()

        client.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) return@withContext null
            val text = resp.body?.string().orEmpty()
            if (text.isBlank()) return@withContext null

            val o = JSONObject(text)
            val tag = o.optString("tag_name")
            val assetsArr = o.optJSONArray("assets")
            val assets = ArrayList<ReleaseAsset>()
            if (assetsArr != null) {
                for (i in 0 until assetsArr.length()) {
                    val a = assetsArr.getJSONObject(i)
                    assets.add(
                        ReleaseAsset(
                            name = a.optString("name"),
                            downloadUrl = a.optString("browser_download_url"),
                            size = a.optLong("size")
                        )
                    )
                }
            }

            // ★ 版本依据 = APK 附件文件名里的版本，而不是 Release tag
            val apk = pickApkAsset(assets)
            val version = apk?.let { versionFromAssetName(it.name) }
                ?: tag.removePrefix("v")

            ReleaseInfo(
                tagName = tag,
                version = version,
                body = o.optString("body"),
                htmlUrl = o.optString("html_url"),
                publishedAt = o.optString("published_at"),
                assets = assets
            )
        }
    }

    /**
     * 比较版本号：返回 true 表示 [remote] 比 [local] 新。
     * 支持 "1.0.0" 与 "1.0.0-beta" 之类的形式。
     */
    fun isNewer(remote: String, local: String = BuildConfig.APP_VERSION): Boolean {
        val r = parseVersion(remote) ?: return false
        val l = parseVersion(local) ?: return false
        for (i in 0 until 3) {
            val a = r.getOrElse(i) { 0 }
            val b = l.getOrElse(i) { 0 }
            if (a != b) return a > b
        }
        return false
    }

    private fun parseVersion(v: String): List<Int>? {
        val cleaned = v.removePrefix("v").substringBefore('-').substringBefore('+')
        val parts = cleaned.split('.')
        if (parts.isEmpty()) return null
        return try {
            parts.map { it.toInt() }
        } catch (e: NumberFormatException) {
            null
        }
    }
}
