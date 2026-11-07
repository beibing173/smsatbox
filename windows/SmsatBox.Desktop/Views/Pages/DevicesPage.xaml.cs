using System.Windows;
using System.Windows.Controls;
using SmsatBox.Desktop.Core;
using SmsatBox.Desktop.Models;

namespace SmsatBox.Desktop.Views.Pages;

/// <summary>设备状态页：设备在线情况、网络、IP、固件版本、4G 模组状态与卡槽明细。</summary>
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
        var modules = _state.Devices.Sum(d => d.Modules.Count(m => m.Present));

        SubtitleText.Text = total == 0
            ? "尚未添加设备"
            : $"共 {total} 台设备，{online} 台在线，{slots} 个卡槽，检测到 {modules} 个模组";

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

    // ===================== 编辑 =====================

    /// <summary>点击卡槽「编辑」：改备注、号码、显示/隐藏。</summary>
    private async void OnEditSlotClick(object sender, RoutedEventArgs e)
    {
        if (sender is not FrameworkElement { Tag: SimSlot slot } || App.MainApi is null)
        {
            return;
        }

        var dialog = new EditSlotDialog(slot) { Owner = Window.GetWindow(this) };
        if (dialog.ShowDialog() != true)
        {
            return;
        }

        try
        {
            await App.MainApi.UpdateSlotAsync(
                slot.Id,
                remark: dialog.Remark,
                phoneNumber: dialog.PhoneNumber,
                visible: dialog.Visible);

            App.Toast("卡槽已更新");
            await App.RequestRefreshAsync();
        }
        catch (Exception ex)
        {
            MessageBox.Show("保存失败：" + ex.Message, AppInfo.ProductName,
                MessageBoxButton.OK, MessageBoxImage.Warning);
        }
    }

    /// <summary>点击「编辑设备」：改名称与备注。</summary>
    private async void OnEditDeviceClick(object sender, RoutedEventArgs e)
    {
        if (sender is not FrameworkElement { Tag: DeviceItem device } || App.MainApi is null)
        {
            return;
        }

        var dialog = new EditDeviceDialog(device) { Owner = Window.GetWindow(this) };
        if (dialog.ShowDialog() != true)
        {
            return;
        }

        try
        {
            await App.MainApi.UpdateDeviceAsync(
                device.Id,
                name: dialog.DeviceName,
                remark: dialog.Remark);

            App.Toast("设备信息已更新");
            await App.RequestRefreshAsync();
        }
        catch (Exception ex)
        {
            MessageBox.Show("保存失败：" + ex.Message, AppInfo.ProductName,
                MessageBoxButton.OK, MessageBoxImage.Warning);
        }
    }
}
