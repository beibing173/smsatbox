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
 */
object UpdateChecker {

    private const val LATEST_RELEASE_URL =
        "https://api.github.com/repos/%s/%s/releases/latest"

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .followRedirects(true)
        .build()

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
            ReleaseInfo(
                tagName = tag,
                version = tag.removePrefix("v"),
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
