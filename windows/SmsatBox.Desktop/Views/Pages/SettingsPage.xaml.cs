using System.Diagnostics;
using System.Windows;
using System.Windows.Controls;
using SmsatBox.Desktop.Core;

namespace SmsatBox.Desktop.Views.Pages;

/// <summary>设置页：账号、主题、通知、窗口行为、独立升级、关于。</summary>
public partial class SettingsPage : UserControl
{
    private readonly AppState _state = AppState.Current;
    private bool _suppressToggleEvents;
    private bool _checking;

    public SettingsPage()
    {
        InitializeComponent();
        Loaded += OnLoaded;
        Unloaded += OnUnloaded;
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        _state.Changed += OnStateChanged;
        LoadFromConfig();
        RefreshUi();
    }

    private void OnUnloaded(object sender, RoutedEventArgs e)
    {
        _state.Changed -= OnStateChanged;
    }

    private void OnStateChanged() => Dispatcher.BeginInvoke(new Action(RefreshUi));

    private void LoadFromConfig()
    {
        _suppressToggleEvents = true;
        try
        {
            var cfg = App.Config;
            NotifyToggle.IsChecked = cfg.NotifyEnabled;
            StartMinimizedToggle.IsChecked = cfg.StartMinimized;
            PollTextBox.Text = ConfigStore.ClampPoll(cfg.PollSeconds).ToString();

            var dark = ThemeManager.IsDark;
            DarkThemeButton.IsChecked = dark;
            LightThemeButton.IsChecked = !dark;
        }
        finally
        {
            _suppressToggleEvents = false;
        }
    }

    private void RefreshUi()
    {
        var cfg = App.Config;

        ServerUrlText.Text = ApiClient.DisplayHost(cfg.ServerUrl);
        ServerUrlText.ToolTip = ApiClient.NormalizeBase(cfg.ServerUrl);

        UserText.Text = _state.User is null
            ? "未登录"
            : $"{_state.User.Display}（{_state.User.RoleLabel}）";

        var token = cfg.Token ?? "";
        TokenText.Text = string.IsNullOrWhiteSpace(token)
            ? "未配置"
            : token.Length <= 10
                ? new string('•', token.Length)
                : token[..6] + new string('•', 12) + token[^4..];

        ConnectionHintText.Text = _state.StatusText;

        CurrentVersionText.Text = AppInfo.VersionLabel;
        RepoText.Text = $"{AppInfo.RepoOwner}/{AppInfo.RepoName} · releases/latest";
        AboutText.Text =
            $"{AppInfo.ProductName} · {AppInfo.Tagline}\r\n" +
            "三端一致：Web 管理端 / Android APK / Windows EXE";
        AboutVersionText.Text =
            $"客户端版本 {AppInfo.VersionLabel} · 程序集 {AppInfo.AssemblyVersionText}\r\n" +
            $"配置文件：{ConfigStore.ConfigPath}";
        FooterVersionText.Text = $"{AppInfo.ProductName} · {AppInfo.VersionLabel}";
    }

    // ===== 平台 =====

    private void OnReloginClick(object sender, RoutedEventArgs e) => App.RequestRelogin();

    private async void OnTestConnectionClick(object sender, RoutedEventArgs e)
    {
        if (App.MainApi is null)
        {
            ConnectionHintText.Text = "尚未配置平台地址或 Token";
            return;
        }

        ConnectionHintText.Text = "正在测试连接…";
        try
        {
            var verify = await App.MainApi.VerifyAsync();
            var text = verify.Ok
                ? $"连接成功 · {ApiClient.DisplayHost(App.Config.ServerUrl)} · 服务端 v{verify.Version}"
                : "验证未通过";
            ConnectionHintText.Text = text;
            App.Toast(text);
        }
        catch (ApiException ex)
        {
            ConnectionHintText.Text = "连接失败：" + ex.Message;
            App.Toast("连接失败：" + ex.Message);
        }
        catch (Exception ex)
        {
            ConnectionHintText.Text = "连接失败：" + ex.Message;
            Log.Write("测试连接异常", ex);
        }
    }

    private void OnOpenConfigFolderClick(object sender, RoutedEventArgs e)
        => OpenFolder(ConfigStore.ConfigDirectory);

    private void OnOpenLogFolderClick(object sender, RoutedEventArgs e)
        => OpenFolder(Log.LogDirectory);

    private static void OpenFolder(string path)
    {
        try
        {
            Directory.CreateDirectory(path);
            Process.Start(new ProcessStartInfo
            {
                FileName = path,
                UseShellExecute = true,
            });
        }
        catch (Exception ex)
        {
            Log.Write("打开文件夹失败：" + path, ex);
            App.Toast("打开文件夹失败：" + ex.Message);
        }
    }

    // ===== 主题 =====

    private void OnDarkThemeClick(object sender, RoutedEventArgs e) => SetTheme("dark");

    private void OnLightThemeClick(object sender, RoutedEventArgs e) => SetTheme("light");

    private void SetTheme(string theme)
    {
        if (_suppressToggleEvents)
        {
            return;
        }

        ThemeManager.Apply(theme);
        App.Config.Theme = ThemeManager.Current;
        App.SaveConfig();

        _suppressToggleEvents = true;
        DarkThemeButton.IsChecked = ThemeManager.IsDark;
        LightThemeButton.IsChecked = !ThemeManager.IsDark;
        _suppressToggleEvents = false;
    }

    // ===== 通知 =====

    private void OnNotifyToggleClick(object sender, RoutedEventArgs e)
    {
        if (_suppressToggleEvents)
        {
            return;
        }

        App.Config.NotifyEnabled = NotifyToggle.IsChecked == true;
        App.SaveConfig();
        App.Notifications.Enabled = App.Config.NotifyEnabled;
        App.Toast(App.Config.NotifyEnabled ? "已开启新消息通知" : "已关闭新消息通知");
    }

    private void OnStartMinimizedToggleClick(object sender, RoutedEventArgs e)
    {
        if (_suppressToggleEvents)
        {
            return;
        }

        App.Config.StartMinimized = StartMinimizedToggle.IsChecked == true;
        App.SaveConfig();
    }

    private void OnTestNotifyClick(object sender, RoutedEventArgs e)
    {
        App.Notifications.NotifyInfo(
            "SMSATBOX 测试通知",
            "如果你看到这条通知，说明系统通知工作正常。" + (AppInfo.VersionLabel),
            important: true);
        App.Toast("已发送测试通知，请留意系统通知中心");
    }

    private void OnPollTextChanged(object sender, TextChangedEventArgs e)
    {
        // 使用 LostFocus 触发保存，避免每敲一个字符就写盘
    }

    // ===== 升级 =====

    private void OnOpenReleaseClick(object sender, RoutedEventArgs e)
    {
        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = AppInfo.GitHubReleasesPage,
                UseShellExecute = true,
            });
        }
        catch (Exception ex)
        {
            Log.Write("打开发布页失败", ex);
        }
    }

    private async void OnCheckUpdateClick(object sender, RoutedEventArgs e)
    {
        if (_checking)
        {
            return;
        }

        _checking = true;
        CheckUpdateButton.IsEnabled = false;
        CheckUpdateButton.Content = "检查中…";
        UpdateResultBorder.Visibility = Visibility.Visible;
        UpdateResultText.Text = "正在访问 GitHub Release API…";
        UpdateProgress.Visibility = Visibility.Collapsed;

        try
        {
            var result = await UpdateService.CheckAsync();

            if (result.IsError)
            {
                UpdateResultText.Text = "❌ " + result.Message;
                return;
            }

            if (!result.HasUpdate)
            {
                UpdateResultText.Text = $"✅ 已是最新版本 {AppInfo.VersionLabel}";
                return;
            }

            UpdateResultText.Text =
                $"🎉 发现新版本 v{result.LatestVersion}（当前 {AppInfo.VersionLabel}）\r\n" +
                (string.IsNullOrWhiteSpace(result.AssetName)
                    ? "该 Release 没有 .exe 资产，只能到发布页手动下载。"
                    : $"资产：{result.AssetName}（{FormatSize(result.AssetSize)}）");

            var ask = MessageBox.Show(
                $"发现新版本 v{result.LatestVersion}，当前版本 {AppInfo.VersionLabel}。\r\n\r\n" +
                (string.IsNullOrWhiteSpace(result.AssetName)
                    ? "该 Release 没有可自动下载的 .exe，是否打开发布页手动下载？"
                    : "是否立即下载并安装？下载完成后会自动启动新版本并退出当前程序。"),
                "SMSATBOX 检查更新",
                MessageBoxButton.YesNo,
                MessageBoxImage.Information);

            if (ask != MessageBoxResult.Yes)
            {
                return;
            }

            if (string.IsNullOrWhiteSpace(result.DownloadUrl))
            {
                OnOpenReleaseClick(sender, e);
                return;
            }

            UpdateProgress.Visibility = Visibility.Visible;
            UpdateProgress.Value = 0;

            var progress = new Progress<double>(p =>
            {
                UpdateProgress.Value = p;
                UpdateResultText.Text = $"正在下载新版本 v{result.LatestVersion}… {p:0}%";
            });

            var path = await UpdateService.DownloadAsync(result, progress);
            UpdateResultText.Text = $"下载完成：{path}\r\n即将启动新版本…";

            var confirm = MessageBox.Show(
                "新版本已下载完成。现在启动新版本并退出当前程序吗？\r\n\r\n" +
                $"文件位置：{path}",
                "SMSATBOX 升级",
                MessageBoxButton.YesNo,
                MessageBoxImage.Question);

            if (confirm == MessageBoxResult.Yes)
            {
                UpdateService.LaunchAndExit(path);
            }
        }
        catch (Exception ex)
        {
            Log.Write("检查更新异常", ex);
            UpdateResultText.Text = "❌ 升级失败：" + ex.Message;
        }
        finally
        {
            _checking = false;
            CheckUpdateButton.IsEnabled = true;
            CheckUpdateButton.Content = "检查更新";
        }
    }

    private static string FormatSize(long bytes)
    {
        if (bytes <= 0)
        {
            return "未知大小";
        }

        if (bytes < 1024)
        {
            return bytes + " B";
        }

        if (bytes < 1024 * 1024)
        {
            return (bytes / 1024.0).ToString("0.0") + " KB";
        }

        return (bytes / 1024.0 / 1024.0).ToString("0.0") + " MB";
    }

    /// <summary>轮询间隔输入框失焦时保存。</summary>
    private void OnPollTextBoxLostFocus(object sender, RoutedEventArgs e)
    {
        if (!int.TryParse(PollTextBox.Text?.Trim(), out var seconds))
        {
            seconds = 20;
        }

        seconds = ConfigStore.ClampPoll(seconds);
        PollTextBox.Text = seconds.ToString();
        App.Config.PollSeconds = seconds;
        App.SaveConfig();
        App.RestartPolling();
    }
}
