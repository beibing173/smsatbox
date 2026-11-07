using System.Windows;
using SmsatBox.Desktop.Models;

namespace SmsatBox.Desktop.Views;

/// <summary>设备编辑弹窗：名称与备注。</summary>
public partial class EditDeviceDialog : Window
{
    public EditDeviceDialog(DeviceItem device)
    {
        InitializeComponent();

        HeaderText.Text = device.NameLabel;
        SubText.Text = $"设备 #{device.Id} · {device.StatusLabel} · 固件 {device.FirmwareVersion}";
        NameBox.Text = device.DeviceName;
        RemarkBox.Text = device.Remark;
    }

    public string DeviceName => (NameBox.Text ?? "").Trim();

    public string Remark => (RemarkBox.Text ?? "").Trim();

    private void OnSaveClick(object sender, RoutedEventArgs e) => DialogResult = true;

    private void OnCancelClick(object sender, RoutedEventArgs e) => DialogResult = false;
}
