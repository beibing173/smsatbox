using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using SmsatBox.Desktop.Core;
using SmsatBox.Desktop.Models;

namespace SmsatBox.Desktop.Views.Pages;

/// <summary>消息列表页：卡片列表、验证码一键复制、已读标记、统计。</summary>
public partial class MessagesPage : UserControl
{
    private readonly AppState _state = AppState.Current;
    private int _filter; // 0=全部 1=未读 2=验证码 3=未接来电

    public MessagesPage()
    {
        InitializeComponent();
        Loaded += OnLoaded;
        Unloaded += OnUnloaded;
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        MessageList.ItemsSource = _state.Messages;
        _state.Changed += OnStateChanged;
        _state.Messages.CollectionChanged += OnMessagesCollectionChanged;
        RefreshUi();
    }

    private void OnUnloaded(object sender, RoutedEventArgs e)
    {
        _state.Changed -= OnStateChanged;
        _state.Messages.CollectionChanged -= OnMessagesCollectionChanged;
    }

    private void OnMessagesCollectionChanged(object? sender, System.Collections.Specialized.NotifyCollectionChangedEventArgs e)
        => RefreshUi();

    private void OnStateChanged() => Dispatcher.BeginInvoke(new Action(RefreshUi));

    private void RefreshUi()
    {
        TotalText.Text = _state.Total.ToString();
        UnreadText.Text = _state.Unread.ToString();
        TodayText.Text = _state.Today.ToString();
        CodesText.Text = _state.Codes.ToString();

        SubtitleText.Text = _filter switch
        {
            1 => $"仅显示未读 · 共 {_state.Unread} 条",
            2 => $"含验证码的消息 · 共 {_state.Codes} 条",
            3 => "未接来电",
            _ => $"共 {_state.Total} 条记录，最近 {_state.Messages.Count} 条已加载",
        };

        ApplyFilter();
        EmptyPanel.Visibility = MessageList.Items.Count == 0 ? Visibility.Visible : Visibility.Collapsed;
    }

    private void ApplyFilter()
    {
        var view = System.Windows.Data.CollectionViewSource.GetDefaultView(_state.Messages);
        if (view is null)
        {
            return;
        }

        // 用 ItemsSource 直连时不能设 Filter，改为手动控制可见集合太重；这里用 CollectionView 过滤
        try
        {
            view.Filter = _filter switch
            {
                1 => o => o is MessageItem m && !m.IsRead,
                2 => o => o is MessageItem m && m.HasCode,
                3 => o => o is MessageItem m && m.IsCall,
                _ => null,
            };
        }
        catch (Exception ex)
        {
            Log.Write("应用消息过滤失败", ex);
        }
    }

    private MessageItem? ItemFromSender(object sender)
    {
        var element = sender as FrameworkElement;
        return element?.DataContext as MessageItem;
    }

    private void OnCopyCodeClick(object sender, RoutedEventArgs e)
    {
        e.Handled = true;
        var item = ItemFromSender(sender);
        if (item is null || string.IsNullOrWhiteSpace(item.Code))
        {
            return;
        }

        CopyToClipboard(item.Code!, $"验证码 {item.Code} 已复制到剪贴板");
        _ = _state.MarkReadAsync(App.MainApi!, item);
    }

    private void OnCopyCodeMenuClick(object sender, RoutedEventArgs e)
    {
        var item = ItemFromContextMenu(sender);
        if (item is null || string.IsNullOrWhiteSpace(item.Code))
        {
            return;
        }

        CopyToClipboard(item.Code!, $"验证码 {item.Code} 已复制到剪贴板");
    }

    private void OnCopyContentMenuClick(object sender, RoutedEventArgs e)
    {
        var item = ItemFromContextMenu(sender);
        if (item is null)
        {
            return;
        }

        CopyToClipboard(item.Content, "消息全文已复制");
    }

    private void OnMarkReadMenuClick(object sender, RoutedEventArgs e)
    {
        var item = ItemFromContextMenu(sender);
        if (item is null || item.IsRead || App.MainApi is null)
        {
            return;
        }

        _ = _state.MarkReadAsync(App.MainApi, item);
    }

    private static MessageItem? ItemFromContextMenu(object sender)
    {
        if (sender is MenuItem mi && mi.DataContext is MessageItem m)
        {
            return m;
        }

        // ContextMenu 的数据上下文来自 PlacementTarget
        return null;
    }

    private async void OnCardClick(object sender, MouseButtonEventArgs e)
    {
        // 点击卡片本体 = 标记已读（点到验证码按钮时 e.Handled 已置位）
        if (e.OriginalSource is not FrameworkElement)
        {
            return;
        }

        var item = ItemFromSender(sender);
        if (item is null || item.IsRead || App.MainApi is null)
        {
            return;
        }

        await _state.MarkReadAsync(App.MainApi, item);
    }

    private void OnRefreshClick(object sender, RoutedEventArgs e)
    {
        if (App.MainApi is null)
        {
            return;
        }

        _ = App.RequestRefreshAsync();
    }

    private void OnMarkAllReadClick(object sender, RoutedEventArgs e)
    {
        if (App.MainApi is null)
        {
            return;
        }

        var unread = _state.Messages.Where(m => !m.IsRead).ToList();
        if (unread.Count == 0)
        {
            App.Toast("没有未读消息");
            return;
        }

        foreach (var item in unread)
        {
            _ = _state.MarkReadAsync(App.MainApi, item);
        }

        App.Toast($"正在把 {unread.Count} 条标记为已读");
    }

    private static void CopyToClipboard(string text, string toast)
    {
        try
        {
            Clipboard.SetText(text);
            App.Toast(toast);
        }
        catch (Exception ex)
        {
            Log.Write("复制到剪贴板失败", ex);
            App.Toast("复制失败：" + ex.Message);
        }
    }

    /// <summary>供外部（托盘/通知）设置过滤。</summary>
    public void SetFilter(int filter)
    {
        _filter = filter;
        RefreshUi();
    }
}
