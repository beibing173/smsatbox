using System.ComponentModel;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using SmsatBox.Desktop.Core;
using SmsatBox.Desktop.Views.Pages;

namespace SmsatBox.Desktop;

/// <summary>
/// 主窗口：三页布局（消息列表 / 设备状态 / 设置），左侧导航，底部标注版本号 v1.0.0。
/// 关闭或最小化时收缩到系统托盘，不退出进程。
/// </summary>
public partial class MainWindow : Window
{
    private readonly AppState _state = AppState.Current;
    private MessagesPage? _messagesPage;
    private DevicesPage? _devicesPage;
    private SettingsPage? _settingsPage;

    private bool _reallyClosing;
    private bool _trayHintShown;

    public MainWindow()
    {
        InitializeComponent();

        VersionLabel.Text = $"{AppInfo.ProductName} · {AppInfo.VersionLabel}";
        FooterVersionText.Text = $"{AppInfo.ProductName} · {AppInfo.VersionLabel}";
        Title = $"{AppInfo.ProductName} · {AppInfo.VersionLabel}";

        _state.Changed += OnStateChanged;
        _state.ConnectionChanged += OnConnectionChanged;

        StateChanged += OnWindowStateChanged;
        Closing += OnClosing;

        ShowPage("messages");
        RefreshChrome();
    }

    // ===================== 页面切换 =====================

    private void OnNavChecked(object sender, RoutedEventArgs e)
    {
        if (sender is RadioButton rb && rb.Tag is string tag && PageHost is not null)
        {
            ShowPage(tag);
        }
    }

    private void ShowPage(string tag)
    {
        switch (tag)
        {
            case "devices":
                _devicesPage ??= new DevicesPage();
                PageHost.Content = _devicesPage;
                break;
            case "settings":
                _settingsPage ??= new SettingsPage();
                PageHost.Content = _settingsPage;
                break;
            default:
                _messagesPage ??= new MessagesPage();
                PageHost.Content = _messagesPage;
                break;
        }
    }

    /// <summary>外部（托盘菜单）跳转到指定页。</summary>
    public void NavigateTo(string tag)
    {
        switch (tag)
        {
            case "devices":
                NavDevices.IsChecked = true;
                break;
            case "settings":
                NavSettings.IsChecked = true;
                break;
            default:
                NavMessages.IsChecked = true;
                break;
        }

        ShowPage(tag);
    }

    // ===================== 状态刷新 =====================

    private void OnStateChanged() => Dispatcher.BeginInvoke(new Action(RefreshChrome));

    private void OnConnectionChanged(bool ok, string text)
        => Dispatcher.BeginInvoke(new Action(() => ApplyConnection(ok, text)));

    private void RefreshChrome()
    {
        UnreadPillText.Text = _state.Unread > 99 ? "99+" : _state.Unread.ToString();
        UnreadPill.Visibility = _state.Unread > 0 ? Visibility.Visible : Visibility.Collapsed;

        UserText.Text = _state.User is null
            ? "未登录"
            : _state.User.Label;

        FooterStatusText.Text = _state.StatusText;
        ApplyConnection(!_state.StatusText.StartsWith("连接异常", StringComparison.Ordinal) &&
                        _state.StatusText.StartsWith("已连接", StringComparison.Ordinal), _state.StatusText);
    }

    private void ApplyConnection(bool ok, string text)
    {
        StatusText.Text = text;
        string brushKey = ok ? "Brush.Success" : "Brush.TextMuted";
        if (TryFindResource(brushKey) is Brush brush)
        {
            StatusDot.Fill = brush;
        }
    }

    // ===================== 托盘行为 =====================

    private void OnWindowStateChanged(object? sender, EventArgs e)
    {
        if (WindowState == WindowState.Minimized)
        {
            HideToTray();
        }
    }

    /// <summary>收缩到托盘。</summary>
    public void HideToTray()
    {
        ShowInTaskbar = false;
        Hide();

        if (!_trayHintShown)
        {
            _trayHintShown = true;
            App.Notifications.NotifyInfo(
                AppInfo.ProductName,
                "已收缩到系统托盘常驻，双击托盘图标可重新打开。",
                important: false);
        }
    }

    /// <summary>从托盘恢复显示。</summary>
    public void ShowFromTray()
    {
        ShowInTaskbar = true;
        Show();

        if (WindowState == WindowState.Minimized)
        {
            WindowState = WindowState.Normal;
        }

        Activate();
        Focus();
        Topmost = true;
        Topmost = false;
    }

    private void OnClosing(object? sender, CancelEventArgs e)
    {
        if (_reallyClosing)
        {
            return;
        }

        // 关闭按钮 → 收缩到托盘
        e.Cancel = true;
        HideToTray();
    }

    /// <summary>真正退出（托盘菜单「退出」调用）。</summary>
    public void RequestExit()
    {
        _reallyClosing = true;
        _state.Changed -= OnStateChanged;
        _state.ConnectionChanged -= OnConnectionChanged;
        Close();
    }
}
