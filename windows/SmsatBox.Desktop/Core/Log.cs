namespace SmsatBox.Desktop.Core;

/// <summary>极简日志：%APPDATA%\SMSATBOX\logs\app.log，方便排查 Toast / 升级问题。</summary>
public static class Log
{
    private static readonly object Gate = new();

    public static string LogDirectory => Path.Combine(ConfigStore.ConfigDirectory, "logs");

    public static string LogPath => Path.Combine(LogDirectory, "app.log");

    public static void Write(string message, Exception? ex = null)
    {
        try
        {
            lock (Gate)
            {
                Directory.CreateDirectory(LogDirectory);
                var line = $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {message}";
                if (ex is not null)
                {
                    line += Environment.NewLine + ex;
                }

                File.AppendAllText(LogPath, line + Environment.NewLine);

                // 简单轮转，超过 512KB 就截断旧内容
                var info = new FileInfo(LogPath);
                if (info.Length > 512 * 1024)
                {
                    var lines = File.ReadAllLines(LogPath);
                    File.WriteAllLines(LogPath, lines.Skip(lines.Length / 2));
                }
            }
        }
        catch
        {
            // 日志失败不能影响主流程
        }
    }
}
