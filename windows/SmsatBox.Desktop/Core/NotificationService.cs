using System.Windows.Forms;
using Microsoft.Toolkit.Uwp.Notifications;

namespace SmsatBox.Desktop.Core;

/// <summary>
/// 通知服务：优先 Windows 原生 Toast（Microsoft.Toolkit.Uwp.Notifications），
/// 若当前系统/环境不支持（例如未安装 App 注册、旧版系统），自动降级为托盘气泡通知。
/// </summary>
public sealed class NotificationService
{
    private readonly NotifyIcon _notifyIcon;
    private bool _toastAvailable = true;
    private bool _toastWarned;
    private int _retryAfterFail;

    public NotificationService(NotifyIcon notifyIcon)
    {
        _notifyIcon = notifyIcon;

        try
        {
            ToastNotificationManagerCompat.OnActivated += OnToastActivated;
            _toastAvailable = OperatingSystem.IsWindowsVersionAtLeast(10, 0, 17763);
        }
        catch (Exception ex)
        {
            _toastAvailable = false;
            Log.Write("Toast 初始化失败，将使用托盘气泡通知", ex);
        }
    }

    /// <summary>点击通知（或通知里的按钮）时触发，参数为参数串。</summary>
    public event Action<string>? ToastClicked;

    public bool Enabled { get; set; } = true;

    private void OnToastActivated(ToastNotificationActivatedEventArgsCompat e)
    {
        try
        {
            var args = e.Argument ?? "";
            ToastClicked?.Invoke(args);
        }
        catch (Exception ex)
        {
            Log.Write("处理 Toast 点击失败", ex);
        }
    }

    /// <summary>新消息通知。</summary>
    public void NotifyNewMessage(Models.MessageItem msg, int unreadCount)
    {
        if (!Enabled)
        {
            return;
        }

        var kindLabel = msg.KindLabel;
        var title = string.IsNullOrWhiteSpace(msg.Code)
            ? $"{kindLabel} · {msg.Sender}"
            : $"验证码 {msg.Code} · {msg.Sender}";

        var slotInfo = $"[{msg.SlotLabel} · {msg.NumberLabel}]";
        var body = msg.HasCode
            ? $"{slotInfo} {Trim(msg.Content, 120)}"
            : Trim(msg.Content, 160);

        Show(title, body, msg.HasCode, unreadCount, msg.Id);
    }

    /// <summary>通用通知（升级提示、错误提示等）。</summary>
    public void NotifyInfo(string title, string body, bool important = false)
    {
        if (!Enabled)
        {
            return;
        }

        Show(title, body, important, null, null);
    }

    private void Show(string title, string body, bool important, int? unreadCount, int? messageId)
    {
        if (TryToast(title, body, important, messageId))
        {
            return;
        }

        TryBalloon(title, body);
    }

    private bool TryToast(string title, string body, bool important, int? messageId)
    {
        if (!_toastAvailable)
        {
            // 之前失败过：这次再用一次（WinRT 首次激活失败往往是瞬时的，
            // 例如系统刚启动或通知服务尚未就绪），成功则恢复 Toast 通道。
            if (++_retryAfterFail > 3)
            {
                return false;
            }
        }

        try
        {
            var builder = new ToastContentBuilder()
                .AddArgument("action", "open")
                .AddArgument("messageId", messageId?.ToString() ?? "")
                .AddText(title)
                .AddText(body);

            if (important)
            {
                // 验证码类：用 Reminder 场景让它显眼（不会自动消失），
                // 显式指定一次提示音，避免 Reminder/Alarm 场景默认循环播放。
                builder.SetToastScenario(ToastScenario.Reminder)
                       .AddText("🔐 验证码消息，可在客户端一键复制")
                       .AddAudio(new Uri("ms-winsoundevent:Notification.Default"));
            }

            builder.AddAttributionText(AppInfo.DisplayName + " · " + AppInfo.VersionLabel);

            builder.Show();
            _toastAvailable = true;
            return true;
        }
        catch (Exception ex)
        {
            _toastAvailable = false;
            _retryAfterFail = 0;
            if (!_toastWarned)
            {
                _toastWarned = true;
                Log.Write("Toast 通知失败，本次降级为托盘气泡通知（后续会自动重试）", ex);
            }

            return false;
        }
    }

    private void TryBalloon(string title, string body)
    {
        try
        {
            if (_notifyIcon is null || !_notifyIcon.Visible)
            {
                return;
            }

            _notifyIcon.BalloonTipTitle = Trim(title, 60);
            _notifyIcon.BalloonTipText = Trim(body, 240);
            _notifyIcon.BalloonTipIcon = ToolTipIcon.Info;
            _notifyIcon.ShowBalloonTip(6000);
        }
        catch (Exception ex)
        {
            Log.Write("托盘气泡通知失败", ex);
        }
    }

    private static string Trim(string? text, int max)
    {
        var t = (text ?? "").Replace("\r", " ").Replace("\n", " ").Trim();
        return t.Length <= max ? t : t[..max] + "…";
    }
}
