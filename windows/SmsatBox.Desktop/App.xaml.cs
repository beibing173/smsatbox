using System.Diagnostics;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Threading;
using SmsatBox.Desktop.Core;
using SmsatBox.Desktop.Views;

namespace SmsatBox.Desktop;

/// <summary>
/// 应用入口：单实例、托盘常驻、登录、后台轮询、通知、主题。
/// </summary>
public partial class App : Application
{
    private System.Windows.Forms.NotifyIcon? _trayIcon;
    private DispatcherTimer? _pollTimer;
    private MainWindow? _mainWindow;
    private bool _refreshing;
    private bool _exiting;
    private bool _coldStartHandled;
    private DateTime _lastPollSilenced = DateTime.MinValue;

    /// <summary>当前 API 客户端（未登录时为 null）。</summary>
    public static ApiClient? MainApi { get; private set; }

    /// <summary>当前配置。</summary>
    public static AppConfig Config { get; private set; } = new();

    /// <summary>通知服务。</summary>
    public static NotificationService Notifications { get; private set; } = null!;

    /// <summary>当前 App 实例。</summary>
    public static new App Current => (App)Application.Current;

    /// <summary>主窗口（可能未创建）。</summary>
    public static MainWindow? Shell => (Application.Current as App)?._mainWindow;

    protected override void OnStartup(StartupEventArgs e)
    {
        // 托盘程序：登录窗口关闭时不要连带退出
        ShutdownMode = ShutdownMode.OnExplicitShutdown;

        base.OnStartup(e);

        DispatcherUnhandledException += OnDispatcherUnhandledException;
        AppDomain.CurrentDomain.UnhandledException += (_, args) =>
            Log.Write("未处理异常", args.ExceptionObject as Exception);
        TaskScheduler.UnobservedTaskException += (_, args) =>
        {
            Log.Write("未观察的任务异常", args.Exception);
            args.SetObserved();
        };

        var upgraded = e.Args.Any(a => string.Equals(a, "--upgraded", StringComparison.OrdinalIgnoreCase));
        if (!AppInstance.IsPrimary(upgraded, e.Args))
        {
            // 已有实例在运行，唤醒它后直接退出
            Shutdown(0);
            return;
        }

        AppInstance.Activated += OnSecondInstanceActivated;

        Config = ConfigStore.Load();
        ThemeManager.Apply(Config.Theme);

        InitTray();

        Notifications = new NotificationService(_trayIcon!)
        {
            Enabled = Config.NotifyEnabled,
        };
        Notifications.ToastClicked += OnToastClicked;

        WireStateEvents();

        Log.Write($"===== {AppInfo.ProductName} 启动 {AppInfo.VersionLabel}（程序集 {AppInfo.AssemblyVersionText}）=====");
        Log.Write($"配置路径：{ConfigStore.ConfigPath}");

        // 启动流程放到 UI 就绪之后，避免阻塞
        Dispatcher.BeginInvoke(new Action(async () => await StartupAsync()), DispatcherPriority.ApplicationIdle);
    }

    private async Task StartupAsync()
    {
        if (Config.HasCredentials)
        {
            var api = new ApiClient(Config.ServerUrl, Config.Token);
            try
            {
                var verify = await api.VerifyAsync();
                if (verify.Ok)
                {
                    MainApi = api;
                    AppState.Current.User = verify.User;
                    AppState.Current.IsLoggedIn = true;
                    Log.Write($"自动登录成功：{verify.User?.Username}");
                    OpenMainWindow();
                    await RequestRefreshAsync();
                    StartPolling();
                    return;
                }
            }
            catch (Exception ex)
            {
                Log.Write("自动登录失败，转手动登录：" + ex.Message);
            }

            api.Dispose();
        }

        ShowLogin();
    }

    private void ShowLogin()
    {
        var login = new LoginWindow(Config);
        var ok = login.ShowDialog();

        if (ok != true)
        {
            ExitApplication();
            return;
        }

        MainApi?.Dispose();
        MainApi = new ApiClient(login.ResultServerUrl, login.ResultToken);

        Config.ServerUrl = login.ResultServerUrl;
        Config.Token = login.ResultToken;
        if (!string.IsNullOrWhiteSpace(login.ResultUser?.Username))
        {
            Config.LastUsername = login.ResultUser!.Username;
        }

        SaveConfig();

        AppState.Current.User = login.ResultUser;
        AppState.Current.IsLoggedIn = true;

        OpenMainWindow();
        _ = RequestRefreshAsync();
        StartPolling();
    }

    private void OpenMainWindow()
    {
        if (_mainWindow is null)
        {
            _mainWindow = new MainWindow();
        }

        // 只在冷启动（本次运行第一次打开）时按设置收缩到托盘；
        // 不改写用户保存的配置，下次开机仍然最小化启动。
        if (Config.StartMinimized && !_coldStartHandled)
        {
            _coldStartHandled = true;
            _mainWindow.HideToTray();
        }
        else
        {
            _mainWindow.ShowFromTray();
        }
    }

    // ===================== 托盘 =====================

    private void InitTray()
    {
        _trayIcon = new System.Windows.Forms.NotifyIcon
        {
            Icon = TrayIconFactory.Create(),
            Text = $"{AppInfo.ProductName} · {AppInfo.VersionLabel}",
            Visible = true,
        };

        var menu = new System.Windows.Forms.ContextMenuStrip();
        menu.Items.Add("显示主窗口", null, (_, _) => ShowMainWindow());
        menu.Items.Add(new System.Windows.Forms.ToolStripSeparator());
        menu.Items.Add("检查更新", null, async (_, _) => await CheckUpdateFromTrayAsync());
        menu.Items.Add(new System.Windows.Forms.ToolStripSeparator());
        menu.Items.Add("退出", null, (_, _) => ExitApplication());

        _trayIcon.ContextMenuStrip = menu;
        _trayIcon.DoubleClick += (_, _) => ShowMainWindow();
        _trayIcon.MouseClick += (_, args) =>
        {
            if (args.Button == System.Windows.Forms.MouseButtons.Left)
            {
                ShowMainWindow();
            }
        };
    }

    private void ShowMainWindow()
    {
        if (_mainWindow is null)
        {
            if (MainApi is null)
            {
                ShowLogin();
                return;
            }

            _mainWindow = new MainWindow();
        }

        _mainWindow.ShowFromTray();
    }

    private void OnSecondInstanceActivated()
        => Dispatcher.BeginInvoke(new Action(ShowMainWindow));

    private void OnToastClicked(string args)
    {
        Dispatcher.BeginInvoke(new Action(() =>
        {
            ShowMainWindow();
            _mainWindow?.NavigateTo("messages");
        }));
    }

    // ===================== 轮询 =====================

    private void StartPolling()
    {
        _pollTimer?.Stop();

        var seconds = ConfigStore.ClampPoll(Config.PollSeconds);
        _pollTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(seconds) };
        _pollTimer.Tick += async (_, _) => await PollAsync();
        _pollTimer.Start();

        Log.Write($"开始轮询，间隔 {seconds} 秒");
    }

    /// <summary>配置变更后重启轮询。</summary>
    public static void RestartPolling() => Current.StartPolling();

    private async Task PollAsync()
    {
        if (MainApi is null || _refreshing)
        {
            return;
        }

        // 登录失效时静默跳过，避免每 20 秒弹一次错误
        if (DateTime.UtcNow - _lastPollSilenced < TimeSpan.FromMinutes(2))
        {
            return;
        }

        await RequestRefreshAsync();
    }

    /// <summary>请求刷新数据（供各页面按钮调用）。</summary>
    public static Task RequestRefreshAsync() => Current.RefreshAsyncInternal();

    private async Task RefreshAsyncInternal()
    {
        if (MainApi is null || _refreshing)
        {
            return;
        }

        _refreshing = true;
        try
        {
            var outcome = await AppState.Current.RefreshAsync(MainApi, emitNotifications: true);

            if (!outcome.Ok)
            {
                // 授权失效时提示一次
                if (outcome.Message.Contains("Token", StringComparison.OrdinalIgnoreCase) ||
                    outcome.Message.Contains("401", StringComparison.Ordinal))
                {
                    _lastPollSilenced = DateTime.UtcNow;
                    await Dispatcher.InvokeAsync(() =>
                    {
                        var result = MessageBox.Show(
                            "登录已失效（Token 无效或已过期）。\r\n\r\n是否重新登录？",
                            AppInfo.ProductName,
                            MessageBoxButton.YesNo,
                            MessageBoxImage.Warning);

                        if (result == MessageBoxResult.Yes)
                        {
                            RequestRelogin();
                        }
                    });
                }
            }

            UpdateTrayState();
        }
        catch (Exception ex)
        {
            Log.Write("刷新异常", ex);
        }
        finally
        {
            _refreshing = false;
        }
    }

    private void UpdateTrayState()
    {
        if (_trayIcon is null)
        {
            return;
        }

        var unread = AppState.Current.Unread;
        _trayIcon.Text = unread > 0
            ? $"{AppInfo.ProductName} · {unread} 条未读 · {AppInfo.VersionLabel}"
            : $"{AppInfo.ProductName} · {AppInfo.VersionLabel}";

        // 有未读时换成带红点的图标（原生 NotifyIcon.Text 最多 63 字符，这里不会超）
        try
        {
            var icon = unread > 0 ? TrayIconFactory.CreateWithBadge() : TrayIconFactory.Create();
            var old = _trayIcon.Icon;
            _trayIcon.Icon = icon;
            old?.Dispose();
        }
        catch (Exception ex)
        {
            Log.Write("更新托盘图标失败", ex);
        }
    }

    // ===================== 新消息 → 系统通知 =====================

    private void HookStateEvents()
    {
        AppState.Current.NewMessageDetected += (msg, count) =>
        {
            try
            {
                Notifications.NotifyNewMessage(msg, count);
                if (msg.HasCode)
                {
                    Log.Write($"验证码通知：{msg.Sender} / {msg.Code}（{msg.SlotLabel}）");
                }
            }
            catch (Exception ex)
            {
                Log.Write("发送新消息通知失败", ex);
            }
        };
    }

    // ===================== 更新 =====================

    private async Task CheckUpdateFromTrayAsync()
    {
        ShowMainWindow();
        _mainWindow?.NavigateTo("settings");

        try
        {
            var result = await UpdateService.CheckAsync();
            if (result.IsError)
            {
                Notifications.NotifyInfo("检查更新失败", result.Message);
                return;
            }

            if (!result.HasUpdate)
            {
                Notifications.NotifyInfo("检查更新", $"已是最新版本 {AppInfo.VersionLabel}");
                return;
            }

            Notifications.NotifyInfo(
                "发现新版本 v" + result.LatestVersion,
                "打开「设置 → 独立升级」即可下载安装。",
                important: true);
        }
        catch (Exception ex)
        {
            Log.Write("托盘检查更新失败", ex);
            Notifications.NotifyInfo("检查更新失败", ex.Message);
        }
    }

    // ===================== 登录 / 退出 =====================

    /// <summary>供设置页调用：重新登录。</summary>
    public static void RequestRelogin() => Current.ReloginInternal();

    private void ReloginInternal()
    {
        _pollTimer?.Stop();

        var login = new LoginWindow(Config);
        var ok = login.ShowDialog();

        if (ok != true)
        {
            // 取消登录但已有有效会话时继续工作
            if (MainApi is not null)
            {
                StartPolling();
            }

            return;
        }

        MainApi?.Dispose();
        MainApi = new ApiClient(login.ResultServerUrl, login.ResultToken);

        Config.ServerUrl = login.ResultServerUrl;
        Config.Token = login.ResultToken;
        SaveConfig();

        AppState.Current.User = login.ResultUser;
        AppState.Current.IsLoggedIn = true;

        _ = RequestRefreshAsync();
        StartPolling();
    }

    /// <summary>轻提示：复用托盘气泡，不侵入 UI。</summary>
    public static void Toast(string message)
    {
        try
        {
            var current = Current;
            current.Dispatcher.BeginInvoke(new Action(() =>
            {
                try
                {
                    if (current._trayIcon is { Visible: true })
                    {
                        current._trayIcon.BalloonTipTitle = AppInfo.ProductName;
                        current._trayIcon.BalloonTipText = message;
                        current._trayIcon.BalloonTipIcon = System.Windows.Forms.ToolTipIcon.None;
                        current._trayIcon.ShowBalloonTip(2500);
                    }
                }
                catch
                {
                    // 忽略
                }
            }));
        }
        catch
        {
            // 提示失败不影响主流程
        }
    }

    public static void SaveConfig()
    {
        try
        {
            ConfigStore.Save(Config);
        }
        catch (Exception ex)
        {
            Log.Write("保存配置失败", ex);
        }
    }

    private void ExitApplication()
    {
        if (_exiting)
        {
            return;
        }

        _exiting = true;
        Log.Write("用户退出应用");

        try
        {
            _pollTimer?.Stop();
            _pollTimer = null;

            _mainWindow?.RequestExit();

            if (_trayIcon is not null)
            {
                _trayIcon.Visible = false;
                _trayIcon.Dispose();
                _trayIcon = null;
            }

            MainApi?.Dispose();
            MainApi = null;
        }
        catch (Exception ex)
        {
            Log.Write("退出清理失败", ex);
        }
        finally
        {
            Shutdown(0);
        }
    }

    protected override void OnExit(ExitEventArgs e)
    {
        try
        {
            _trayIcon?.Dispose();
        }
        catch
        {
            // 忽略
        }

        base.OnExit(e);
    }

    private void OnDispatcherUnhandledException(object sender, DispatcherUnhandledExceptionEventArgs e)
    {
        Log.Write("UI 线程未处理异常", e.Exception);

        // 弹窗本身失败时不要再抛
        try
        {
            MessageBox.Show(
                "程序遇到一个未预期的错误，已记录到日志：\r\n" + Log.LogPath + "\r\n\r\n" + e.Exception.Message,
                AppInfo.ProductName,
                MessageBoxButton.OK,
                MessageBoxImage.Error);
        }
        catch
        {
            // 忽略
        }

        e.Handled = true;
    }

    /// <summary>订阅 AppState 事件（在 UI 线程启动完成后调用）。</summary>
    internal static void WireStateEvents() => Current.HookStateEvents();
}
