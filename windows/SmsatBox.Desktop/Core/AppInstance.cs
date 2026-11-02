namespace SmsatBox.Desktop.Core;

/// <summary>
/// 单实例控制：命名 Mutex 防重复启动 + 命名事件做"唤出已有窗口"。
/// 升级启动（--upgraded）时会等待旧进程释放 Mutex，避免新版本被自己挡掉。
/// </summary>
internal static class AppInstance
{
    private const string MutexName = @"Local\SMSATBOX.Desktop.SingleInstance";
    private const string EventName = @"Local\SMSATBOX.Desktop.Activate";

    private static Mutex? _mutex;
    private static EventWaitHandle? _activateEvent;
    private static Thread? _listener;

    /// <summary>第二个实例请求唤出主窗口时（在主实例内）触发。</summary>
    public static event Action? Activated;

    /// <summary>
    /// 返回 true 表示本进程是主实例。false 表示已有实例在跑（已经通知它显示窗口）。
    /// </summary>
    public static bool IsPrimary(bool upgradedLaunch, string[] args)
    {
        var deadline = DateTime.UtcNow +
                       (upgradedLaunch ? TimeSpan.FromSeconds(20) : TimeSpan.FromSeconds(2));

        while (true)
        {
            try
            {
                var mutex = new Mutex(initiallyOwned: true, MutexName, out var created);
                if (created)
                {
                    _mutex = mutex;
                    StartListener();
                    return true;
                }

                mutex.Dispose();
            }
            catch (UnauthorizedAccessException)
            {
                // 极少数权限异常场景，退化为允许启动
                StartListener();
                return true;
            }

            if (DateTime.UtcNow >= deadline)
            {
                break;
            }

            Thread.Sleep(250);
        }

        SignalExisting(args);
        return false;
    }

    private static void StartListener()
    {
        try
        {
            _activateEvent = new EventWaitHandle(false, EventResetMode.AutoReset, EventName);
        }
        catch (Exception ex)
        {
            Log.Write("创建激活事件失败", ex);
            return;
        }

        _listener = new Thread(() =>
        {
            while (true)
            {
                try
                {
                    if (!_activateEvent.WaitOne())
                    {
                        return;
                    }

                    Activated?.Invoke();
                }
                catch (ObjectDisposedException)
                {
                    return;
                }
                catch (Exception ex)
                {
                    Log.Write("激活监听异常", ex);
                    return;
                }
            }
        })
        {
            IsBackground = true,
            Name = "SMSATBOX-ActivateListener",
        };
        _listener.Start();
    }

    private static void SignalExisting(string[] args)
    {
        for (var i = 0; i < 6; i++)
        {
            try
            {
                using var handle = EventWaitHandle.OpenExisting(EventName);
                handle.Set();
                return;
            }
            catch (WaitHandleCannotBeOpenedException)
            {
                Thread.Sleep(200);
            }
            catch (Exception ex)
            {
                Log.Write("唤出已有实例失败", ex);
                return;
            }
        }
    }
}
