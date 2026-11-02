using System.Windows;
using System.Windows.Controls;
using SmsatBox.Desktop.Core;

namespace SmsatBox.Desktop.Views.Pages;

/// <summary>设备状态页：设备在线情况、网络、IP、固件版本、卡槽明细。</summary>
public partial class DevicesPage : UserControl
{
    private readonly AppState _state = AppState.Current;

    public DevicesPage()
    {
        InitializeComponent();
        Loaded += OnLoaded;
        Unloaded += OnUnloaded;
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        DeviceList.ItemsSource = _state.Devices;
        _state.Changed += OnStateChanged;
        RefreshUi();
    }

    private void OnUnloaded(object sender, RoutedEventArgs e)
    {
        _state.Changed -= OnStateChanged;
    }

    private void OnStateChanged() => Dispatcher.BeginInvoke(new Action(RefreshUi));

    private void RefreshUi()
    {
        var total = _state.Devices.Count;
        var online = _state.Devices.Count(d => d.Online);
        var slots = _state.Devices.Sum(d => d.Slots.Count);

        SubtitleText.Text = total == 0
            ? "尚未添加设备"
            : $"共 {total} 台设备，{online} 台在线，{slots} 个卡槽";

        EmptyPanel.Visibility = total == 0 ? Visibility.Visible : Visibility.Collapsed;
    }

    private void OnRefreshClick(object sender, RoutedEventArgs e)
    {
        if (App.MainApi is null)
        {
            return;
        }

        _ = App.RequestRefreshAsync();
    }
}
