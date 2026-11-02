using System.Text.Json;

namespace SmsatBox.Desktop.Core;

/// <summary>配置读写：%APPDATA%\SMSATBOX\config.json。</summary>
public static class ConfigStore
{
    private static readonly JsonSerializerOptions Options = new()
    {
        WriteIndented = true,
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        PropertyNameCaseInsensitive = true,
    };

    public static string ConfigDirectory =>
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "SMSATBOX");

    public static string ConfigPath => Path.Combine(ConfigDirectory, "config.json");

    public static AppConfig Load()
    {
        try
        {
            if (!File.Exists(ConfigPath))
            {
                return new AppConfig();
            }

            var json = File.ReadAllText(ConfigPath);
            if (string.IsNullOrWhiteSpace(json))
            {
                return new AppConfig();
            }

            var cfg = JsonSerializer.Deserialize<AppConfig>(json, Options) ?? new AppConfig();
            cfg.ServerUrl = (cfg.ServerUrl ?? "").Trim();
            cfg.Token = (cfg.Token ?? "").Trim();
            cfg.Theme = string.Equals(cfg.Theme, "light", StringComparison.OrdinalIgnoreCase) ? "light" : "dark";
            cfg.PollSeconds = ClampPoll(cfg.PollSeconds);
            return cfg;
        }
        catch (Exception ex)
        {
            Log.Write("读取配置失败，使用默认配置", ex);
            return new AppConfig();
        }
    }

    public static void Save(AppConfig config)
    {
        try
        {
            Directory.CreateDirectory(ConfigDirectory);
            var json = JsonSerializer.Serialize(config, Options);
            var tmp = ConfigPath + ".tmp";
            File.WriteAllText(tmp, json);
            File.Move(tmp, ConfigPath, overwrite: true);
        }
        catch (Exception ex)
        {
            Log.Write("保存配置失败", ex);
            throw;
        }
    }

    public static int ClampPoll(int seconds)
    {
        if (seconds < 5)
        {
            return 5;
        }

        return seconds > 600 ? 600 : seconds;
    }
}
