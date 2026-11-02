using System.Text.Json.Serialization;

namespace SmsatBox.Desktop.Core;

/// <summary>本地配置，持久化在 %APPDATA%\SMSATBOX\config.json。</summary>
public sealed class AppConfig
{
    /// <summary>公网中转平台地址，例如 http://1.2.3.4:8000（可带 /api/v1，程序会自动补全）。</summary>
    [JsonPropertyName("server_url")]
    public string ServerUrl { get; set; } = "";

    [JsonPropertyName("token")]
    public string Token { get; set; } = "";

    /// <summary>主题模式：system（跟随系统，默认）/ dark / light。</summary>
    [JsonPropertyName("theme")]
    public string Theme { get; set; } = "system";

    [JsonPropertyName("notify_enabled")]
    public bool NotifyEnabled { get; set; } = true;

    [JsonPropertyName("poll_seconds")]
    public int PollSeconds { get; set; } = 20;

    [JsonPropertyName("start_minimized")]
    public bool StartMinimized { get; set; }

    [JsonPropertyName("last_username")]
    public string LastUsername { get; set; } = "";

    [JsonIgnore]
    public bool HasCredentials =>
        !string.IsNullOrWhiteSpace(ServerUrl) && !string.IsNullOrWhiteSpace(Token);

    [JsonIgnore]
    public bool IsDarkTheme => ThemeManager.IsDark;

    /// <summary>主题模式枚举。</summary>
    [JsonIgnore]
    public ThemeMode ThemeMode
    {
        get => Theme.Trim().ToLowerInvariant() switch
        {
            "dark" => ThemeMode.Dark,
            "light" => ThemeMode.Light,
            _ => ThemeMode.System,
        };
        set => Theme = ThemeManager.SerializeMode(value);
    }

    public AppConfig Clone() => new()
    {
        ServerUrl = ServerUrl,
        Token = Token,
        Theme = Theme,
        NotifyEnabled = NotifyEnabled,
        PollSeconds = PollSeconds,
        StartMinimized = StartMinimized,
        LastUsername = LastUsername,
    };
}
