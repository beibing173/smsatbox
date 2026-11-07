using System.Windows;
using SmsatBox.Desktop.Models;

namespace SmsatBox.Desktop.Views;

/// <summary>卡槽编辑弹窗：备注、号码、显示/隐藏。</summary>
public partial class EditSlotDialog : Window
{
    private readonly SimSlot _slot;

    public EditSlotDialog(SimSlot slot)
    {
        InitializeComponent();
        _slot = slot;

        HeaderText.Text = slot.DisplayName;
        RemarkBox.Text = slot.Remark;
        NumberBox.Text = slot.PhoneNumber;
        VisibleCheck.IsChecked = slot.Visible;
        ModuleInfoText.Text = slot.Module.DetailText;
    }

    public string Remark => (RemarkBox.Text ?? "").Trim();

    public string PhoneNumber => (NumberBox.Text ?? "").Trim();

    public bool Visible => VisibleCheck.IsChecked == true;

    private void OnSaveClick(object sender, RoutedEventArgs e) => DialogResult = true;

    private void OnCancelClick(object sender, RoutedEventArgs e) => DialogResult = false;
}
