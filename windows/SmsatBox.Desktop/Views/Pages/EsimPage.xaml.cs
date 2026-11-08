using System;
using System.Diagnostics;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using Microsoft.Web.WebView2.Core;
using SmsatBox.Desktop.Core;

namespace SmsatBox.Desktop.Views.Pages;

/// <summary>
/// eSIM 管理页：内嵌服务端的 eSIM 工作台网页。
///
/// 为什么用 WebView2 而不是原生界面？
///   eSIM 的 profile 列表、切卡指令、APDU 会话状态都是服务端网页已实现好的，
///   直接复用能让 Android / Windows / Web 三端表现完全一致。
/// </summary>
public partial class EsimPage : UserControl
{
    private bool _initialized;

    public EsimPage()
    {
        InitializeComponent();
        Loaded += OnLoaded;
        Unloaded += OnUnloaded;
    }

    private async void OnLoaded(object sender, RoutedEventArgs e)
    {
        SubtitleText.Text = "可编程 eUICC 卡（小白卡 / 9eSIM / 5ber）的配置管理";

        var api = App.MainApi;
        if (api is null || string.IsNullOrWhiteSpace(api.ServerUrl))
        {
            ShowHint("尚未连接服务器，请先在设置页完成登录。");
            return;
        }
        if (string.IsNullOrWhiteSpace(api.Token))
        {
            ShowHint("登录状态已失效，请重新登录。");
            return;
        }

        try
        {
            if (!_initialized)
            {
                // WebView2 需要一个用户数据目录；放到 LocalAppData 避免权限问题
                var userData = System.IO.Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "SMSATBOX", "WebView2");
                var env = await CoreWebView2Environment.CreateAsync(null, userData);
                await Web.EnsureCoreWebView2Async(env);
                _initialized = true;
            }

            // 注入登录态，避免在本页再次登录
            var tokenJson = JsonSerializer.Serialize(api.Token);
            var userJson = JsonSerializer.Serialize(new { username = "" });
            var script =
                $"localStorage.setItem('smsatbox.token', {tokenJson});" +
                $"localStorage.setItem('smsatbox.user', {userJson});";

            await Web.ExecuteScriptAsync(script);

            var url = api.ServerUrl.TrimEnd('/') + "/assets/esim.html";
            Web.Source = new Uri(url);
            Web.Visibility = Visibility.Visible;
            HintPanel.Visibility = Visibility.Collapsed;
        }
        catch (Exception ex)
        {
            ShowHint(
                "无法启动内嵌浏览器（缺少 WebView2 运行时）。\n\n" +
                "可从微软官网安装「Microsoft Edge WebView2 Runtime」，\n" +
                "或点右上角「在浏览器打开」直接访问。\n\n" +
                "详细信息：" + ex.Message);
        }
    }

    private void OnUnloaded(object sender, RoutedEventArgs e)
    {
        // 页面切走时释放，避免占内存
        try { Web.Dispose(); } catch { /* 忽略 */ }
        _initialized = false;
    }

    private void ShowHint(string text)
    {
        HintText.Text = text;
        HintPanel.Visibility = Visibility.Visible;
        Web.Visibility = Visibility.Collapsed;
    }

    private void OnReloadClick(object sender, RoutedEventArgs e)
    {
        try { Web.Reload(); } catch { /* 忽略 */ }
    }

    private void OnBrowserClick(object sender, RoutedEventArgs e)
    {
        var api = App.MainApi;
        if (api is null || string.IsNullOrWhiteSpace(api.ServerUrl))
        {
            ShowHint("尚未连接服务器。");
            return;
        }
        var url = api.ServerUrl.TrimEnd('/') + "/assets/esim.html";
        try
        {
            Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
        }
        catch (Exception ex)
        {
            ShowHint("无法打开浏览器：" + ex.Message);
        }
    }
}
