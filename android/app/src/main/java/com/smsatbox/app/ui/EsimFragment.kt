package com.smsatbox.app.ui

import android.annotation.SuppressLint
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import com.smsatbox.app.Prefs
import com.smsatbox.app.databinding.FragmentEsimBinding
import org.json.JSONObject

/**
 * eSIM 管理页：内嵌服务端的 eSIM 工作台网页。
 *
 * 为什么用 WebView 而不是原生界面？
 *   eSIM 管理涉及 APDU 会话、profile 列表、指令排队等复杂交互，
 *   服务端网页已完整实现（沿用开源项目 HoshinoDesu 的界面设计）。
 *   用 WebView 直接复用，三端行为天然一致，也便于后续独立升级。
 *
 * 登录态通过注入 localStorage 传递，用户无需在本页重新登录。
 */
class EsimFragment : androidx.fragment.app.Fragment() {

    private var _binding: FragmentEsimBinding? = null
    private val binding get() = _binding!!

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentEsimBinding.inflate(inflater, container, false)
        return binding.root
    }

    /**
     * 从 API base 推导站点根地址。
     *
     * ApiClient 内部 base 形如 http://host:8000/api/v1，
     * 但静态页面 esim.html 挂在站点根下（/assets/esim.html）。
     * 直接拼会变成 /api/v1/assets/esim.html → 404。
     */
    private fun siteRoot(serverUrl: String): String {
        var s = serverUrl.trim().trimEnd('/')
        for (suffix in listOf("/api/v1", "/api")) {
            if (s.endsWith(suffix, ignoreCase = true)) {
                s = s.dropLast(suffix.length).trimEnd('/')
                break
            }
        }
        return s
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        val server = siteRoot(Prefs.serverUrl)
        if (server.isEmpty()) {
            binding.hintText.text = "请先在设置里填写服务器地址"
            binding.hintText.visibility = View.VISIBLE
            return
        }

        val url = "$server/assets/esim.html"
        val token = Prefs.token
        val user = JSONObject().apply {
            put("username", Prefs.userName)
        }.toString()

        binding.webView.apply {
            settings.apply {
                javaScriptEnabled = true
                domStorageEnabled = true
                loadWithOverviewMode = true
                useWideViewPort = true
                mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
                cacheMode = WebSettings.LOAD_DEFAULT
            }
            // 打开页面之前先把登录态写进 localStorage
            val inject =
                "localStorage.setItem('smsatbox.token', ${JSONObject.quote(token)});" +
                "localStorage.setItem('smsatbox.user', ${JSONObject.quote(user)});"
            evaluateJavascript(inject, null)

            webViewClient = object : WebViewClient() {
                override fun onPageStarted(view: WebView?, url: String?, favicon: android.graphics.Bitmap?) {
                    super.onPageStarted(view, url, favicon)
                    // 每次导航后重新注入，避免刷新丢失
                    view?.evaluateJavascript(inject, null)
                }

                override fun shouldOverrideUrlLoading(
                    view: WebView?,
                    request: WebResourceRequest?
                ): Boolean {
                    // 只在本 WebView 内跳转，不打开外部浏览器
                    return false
                }
            }
            loadUrl(url)
        }
    }

    override fun onDestroyView() {
        binding.webView.apply {
            loadUrl("about:blank")
            destroy()
        }
        super.onDestroyView()
        _binding = null
    }
}
