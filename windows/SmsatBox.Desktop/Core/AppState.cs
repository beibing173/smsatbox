using System.Collections.ObjectModel;
using System.Windows;
using SmsatBox.Desktop.Models;

namespace SmsatBox.Desktop.Core;

/// <summary>
/// 全局数据仓库：消息 / 设备 / 统计 / 当前用户。
/// App 定时轮询后写入这里，页面订阅 Changed 刷新。
/// </summary>
public sealed class AppState : ObservableObject
{
    private static readonly Lazy<AppState> LazyInstance = new(() => new AppState());

    private int _total;
    private int _unread;
    private int _today;
    private int _codes;
    private int _unreadCalls;
    private bool _isBusy;
    private string _statusText = "未连接";
    private UserInfo? _user;
    private bool _isLoggedIn;

    public static AppState Current => LazyInstance.Value;

    public ObservableCollection<MessageItem> Messages { get; } = new();

    public ObservableCollection<DeviceItem> Devices { get; } = new();

    public int Total { get => _total; private set => Set(ref _total, value); }

    public int Unread { get => _unread; private set => Set(ref _unread, value); }

    public int Today { get => _today; private set => Set(ref _today, value); }

    public int Codes { get => _codes; private set => Set(ref _codes, value); }

    public int UnreadCalls { get => _unreadCalls; private set => Set(ref _unreadCalls, value); }

    public bool IsBusy { get => _isBusy; set => Set(ref _isBusy, value); }

    public string StatusText { get => _statusText; set => Set(ref _statusText, value); }

    public UserInfo? User { get => _user; set { if (Set(ref _user, value)) { RaiseAll(nameof(UserLabel), nameof(UserRoleLabel)); } } }

    public bool IsLoggedIn { get => _isLoggedIn; set => Set(ref _isLoggedIn, value); }

    public string UserLabel => User is null ? "未登录" : User.Display;

    public string UserRoleLabel => User?.RoleLabel ?? "—";

    public int OnlineDevices => Devices.Count(d => d.Online);

    /// <summary>数据变化通知（UI 刷新）。</summary>
    public event Action? Changed;

    /// <summary>需要弹通知的新消息。</summary>
    public event Action<MessageItem, int>? NewMessageDetected;

    /// <summary>连接状态变化。</summary>
    public event Action<bool, string>? ConnectionChanged;

    private int _lastKnownMaxId;

    private bool _initialized;

    /// <summary>重置（退出登录）。</summary>
    public void Reset()
    {
        Messages.Clear();
        Devices.Clear();
        User = null;
        IsLoggedIn = false;
        Total = Unread = Today = Codes = UnreadCalls = 0;
        _initialized = false;
        _lastKnownMaxId = 0;
        StatusText = "未连接";
        Changed?.Invoke();
    }

    /// <summary>拉取全部数据并合并进集合。</summary>
    public async Task<RefreshOutcome> RefreshAsync(ApiClient api, bool emitNotifications, CancellationToken ct = default)
    {
        if (!api.IsConfigured)
        {
            return new RefreshOutcome(false, "尚未配置平台地址或 Token");
        }

        IsBusy = true;
        var newOnes = new List<MessageItem>();
        try
        {
            var messagesTask = api.GetMessagesAsync(limit: 100, offset: 0, ct: ct);
            var statsTask = api.GetStatsAsync(ct);
            var devicesTask = api.GetDevicesAsync(ct);

            await Task.WhenAll(messagesTask, statsTask, devicesTask).ConfigureAwait(true);

            var messages = messagesTask.Result;
            var stats = statsTask.Result;
            var devices = devicesTask.Result;

            Total = stats.Total;
            Unread = stats.Unread;
            Today = stats.Today;
            Codes = stats.Codes;
            UnreadCalls = stats.UnreadCalls;

            newOnes = MergeMessages(messages.Items ?? new List<MessageItem>());
            MergeDevices(devices.Items ?? new List<DeviceItem>());

            StatusText = $"已连接 · {Messages.Count} 条记录";
            IsLoggedIn = true;
            ConnectionChanged?.Invoke(true, StatusText);
            Changed?.Invoke();

            if (emitNotifications && newOnes.Count > 0)
            {
                foreach (var msg in newOnes.Take(3))
                {
                    NewMessageDetected?.Invoke(msg, newOnes.Count);
                }
            }

            return new RefreshOutcome(true, StatusText, newOnes.Count);
        }
        catch (OperationCanceledException)
        {
            return new RefreshOutcome(false, "已取消");
        }
        catch (ApiException ex)
        {
            StatusText = "连接异常：" + ex.Message;
            ConnectionChanged?.Invoke(false, StatusText);
            return new RefreshOutcome(false, ex.Message, 0, ex);
        }
        catch (Exception ex)
        {
            Log.Write("刷新数据失败", ex);
            StatusText = "连接异常：" + ex.Message;
            ConnectionChanged?.Invoke(false, StatusText);
            return new RefreshOutcome(false, ex.Message, 0, ex);
        }
        finally
        {
            IsBusy = false;
        }
    }

    /// <summary>按 id 合并消息，保留对象实例（已读状态不会闪回），返回真正新增的消息。</summary>
    private List<MessageItem> MergeMessages(List<MessageItem> incoming)
    {
        var added = new List<MessageItem>();
        var byId = Messages.ToDictionary(m => m.Id);
        var incomingIds = new HashSet<int>(incoming.Select(m => m.Id));

        // 删掉服务端已经不在第一页的旧项
        for (var i = Messages.Count - 1; i >= 0; i--)
        {
            if (!incomingIds.Contains(Messages[i].Id))
            {
                Messages.RemoveAt(i);
            }
        }

        for (var index = 0; index < incoming.Count; index++)
        {
            var fresh = incoming[index];
            if (byId.TryGetValue(fresh.Id, out var existing))
            {
                // 保留本地 is_read（本地刚点过已读，服务端可能还没回写）
                if (existing.IsRead != fresh.IsRead && !existing.IsRead)
                {
                    fresh.IsRead = true;
                }

                var target = Messages.IndexOf(existing);
                if (target != index && index < Messages.Count)
                {
                    Messages.Move(target, index);
                }

                if (existing.Content != fresh.Content || existing.Code != fresh.Code ||
                    existing.IsRead != fresh.IsRead || existing.Sender != fresh.Sender)
                {
                    existing.Content = fresh.Content;
                    existing.Code = fresh.Code;
                    existing.IsRead = fresh.IsRead;
                    existing.Sender = fresh.Sender;
                    existing.ReceivedAt = fresh.ReceivedAt;
                    existing.DeviceName = fresh.DeviceName;
                    existing.SlotIndex = fresh.SlotIndex;
                    existing.SlotNumber = fresh.SlotNumber;
                    existing.Kind = fresh.Kind;
                    existing.RaiseRefresh();
                }
            }
            else
            {
                Messages.Insert(Math.Min(index, Messages.Count), fresh);
                added.Add(fresh);
            }
        }

        var maxId = Messages.Count == 0 ? 0 : Messages.Max(m => m.Id);
        if (!_initialized)
        {
            // 首次加载：把已有数据视为"已知"，避免一登录就弹一屏通知
            _initialized = true;
            _lastKnownMaxId = maxId;
            added.Clear();
        }
        else
        {
            var reallyNew = added.Where(m => m.Id > _lastKnownMaxId && !m.IsRead).ToList();
            _lastKnownMaxId = Math.Max(_lastKnownMaxId, maxId);
            added = reallyNew;
        }

        return added;
    }

    private void MergeDevices(List<DeviceItem> incoming)
    {
        Devices.Clear();
        foreach (var device in incoming)
        {
            Devices.Add(device);
        }
    }

    /// <summary>本地标记已读（先改 UI，再异步回写服务端）。</summary>
    public async Task<bool> MarkReadAsync(ApiClient api, MessageItem message, CancellationToken ct = default)
    {
        if (message.IsRead)
        {
            return true;
        }

        message.IsRead = true;
        Unread = Math.Max(0, Unread - 1);
        Changed?.Invoke();

        try
        {
            await api.MarkReadAsync(message.Id, true, ct).ConfigureAwait(true);
            return true;
        }
        catch (Exception ex)
        {
            Log.Write($"标记消息 {message.Id} 已读失败", ex);
            message.IsRead = false;
            Unread++;
            Changed?.Invoke();
            return false;
        }
    }
}

/// <summary>一次刷新的结果。</summary>
public sealed record RefreshOutcome(bool Ok, string Message, int NewCount = 0, Exception? Error = null);
