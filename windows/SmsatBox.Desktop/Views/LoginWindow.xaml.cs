using System.Windows;
using System.Windows.Input;
using SmsatBox.Desktop.Core;

namespace SmsatBox.Desktop.Views;

/// <summary>手动填写「公网中转平台地址」+ Token，验证通过后保存到本机。</summary>
public partial class LoginWindow : Window
{
    private readonly AppConfig _config;
    private bool _showToken;

    public LoginWindow(AppConfig config)
    {
        InitializeComponent();
        _config = config;

        VersionText.Text = $"{AppInfo.ProductName} · {AppInfo.VersionLabel}";
        ServerTextBox.Text = config.ServerUrl;
        TokenPasswordBox.Password = config.Token;
        TokenTextBox.Text = config.Token;
        RememberCheckBox.IsChecked = true;

        Loaded += (_, _) =>
        {
            if (string.IsNullOrWhiteSpace(ServerTextBox.Text))
            {
                ServerTextBox.Focus();
            }
            else
            {
                TokenPasswordBox.Focus();
            }
        };
    }

    /// <summary>验证成功后返回的公网地址（已规整）。</summary>
    public string ResultServerUrl { get; private set; } = "";

    /// <summary>验证成功后的 Token。</summary>
    public string ResultToken { get; private set; } = "";

    /// <summary>验证成功后的用户信息。</summary>
    public Models.UserInfo? ResultUser { get; private set; }

    private string CurrentToken => _showToken ? TokenTextBox.Text : TokenPasswordBox.Password;

    private void SetBusy(bool busy)
    {
        LoginButton.IsEnabled = !busy;
        LoginButton.Content = busy ? "正在验证…" : "验证并登录";
        ServerTextBox.IsEnabled = !busy;
        TokenPasswordBox.IsEnabled = !busy;
        TokenTextBox.IsEnabled = !busy;
    }

    private void ShowError(string message)
    {
        ErrorText.Text = message;
        ErrorBorder.Visibility = Visibility.Visible;
    }

    private void HideError()
    {
        ErrorBorder.Visibility = Visibility.Collapsed;
    }

    private async void OnLoginClick(object sender, RoutedEventArgs e) => await TryLoginAsync();

    private async void OnServerKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter)
        {
            await TryLoginAsync();
        }
    }

    private async Task TryLoginAsync()
    {
        HideError();

        var rawServer = (ServerTextBox.Text ?? "").Trim();
        var token = (CurrentToken ?? "").Trim();

        if (string.IsNullOrWhiteSpace(rawServer))
        {
            ShowError("请填写公网中转平台地址，例如 https://smsat.example.com");
            ServerTextBox.Focus();
            return;
        }

        var baseUrl = ApiClient.NormalizeBase(rawServer);
        if (string.IsNullOrWhiteSpace(baseUrl))
        {
            ShowError("平台地址格式不正确，请检查（示例：http://1.2.3.4:8000）");
            ServerTextBox.Focus();
            return;
        }

        if (string.IsNullOrWhiteSpace(token))
        {
            ShowError("请填写 Token（Web 管理端 → 设置 → 客户端令牌 中生成）");
            TokenPasswordBox.Focus();
            return;
        }

        SetBusy(true);
        try
        {
            using var api = new ApiClient(baseUrl, token);
            var verify = await api.VerifyAsync();

            if (verify is null || !verify.Ok)
            {
                ShowError("中转平台返回验证失败，请确认 Token 是否正确。");
                return;
            }

            // 版本信息（失败不影响登录）
            string serverVersion = verify.Version;
            try
            {
                var ver = await api.GetServerVersionAsync();
                if (!string.IsNullOrWhiteSpace(ver.Version))
                {
                    serverVersion = ver.Version;
                }
            }
            catch
            {
                // 忽略：/version 是可选信息
            }

            ResultServerUrl = baseUrl;
            ResultToken = token;
            ResultUser = verify.User;

            if (RememberCheckBox.IsChecked == true)
            {
                _config.ServerUrl = baseUrl;
                _config.Token = token;
                _config.LastUsername = verify.User?.Username ?? "";
                try
                {
                    ConfigStore.Save(_config);
                }
                catch (Exception ex)
                {
                    ShowError("凭据保存失败：" + ex.Message);
                    return;
                }
            }
            else
            {
                _config.ServerUrl = baseUrl;
                _config.Token = "";
                ConfigStore.Save(_config);
            }

            Log.Write($"登录成功：{ApiClient.DisplayHost(baseUrl)}，服务端版本 {serverVersion}，" +
                      $"用户 {verify.User?.Username}/{verify.User?.Role}");
            DialogResult = true;
            Close();
        }
        catch (ApiException ex)
        {
            ShowError(ex.Message);
            Log.Write("登录失败：" + ex.Message, ex);
        }
        catch (Exception ex)
        {
            ShowError("登录异常：" + ex.Message);
            Log.Write("登录异常", ex);
        }
        finally
        {
            SetBusy(false);
        }
    }

    private void OnToggleTokenClick(object sender, RoutedEventArgs e)
    {
        _showToken = !_showToken;
        if (_showToken)
        {
            TokenTextBox.Text = TokenPasswordBox.Password;
            TokenPasswordBox.Visibility = Visibility.Collapsed;
            TokenTextBox.Visibility = Visibility.Visible;
            TokenTextBox.Focus();
            TokenTextBox.CaretIndex = TokenTextBox.Text.Length;
        }
        else
        {
            TokenPasswordBox.Password = TokenTextBox.Text;
            TokenTextBox.Visibility = Visibility.Collapsed;
            TokenPasswordBox.Visibility = Visibility.Visible;
            TokenPasswordBox.Focus();
        }

        ToggleTokenButton.ToolTip = _showToken ? "隐藏 Token" : "显示 Token";
    }

    private void OnExitClick(object sender, RoutedEventArgs e)
    {
        DialogResult = false;
        Close();
    }
}
