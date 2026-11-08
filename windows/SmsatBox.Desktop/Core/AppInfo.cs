using System.Reflection;

namespace SmsatBox.Desktop.Core;

/// <summary>全局常量：产品名、版本号、GitHub 升级仓库。版本号 v1.0.0 三端一致。</summary>
public static class AppInfo
{
    public const string ProductName = "SMSATBOX";
    public const string DisplayName = "SMSATBOX · 短信提醒盒子";
    public const string Tagline = "短信 / 未接来电 多卡提醒盒子";

    /// <summary>当前版本（与仓库根目录 VERSION 文件保持一致）。</summary>
    public const string Version = "1.0.2";

    /// <summary>底部版本号展示用。</summary>
    public static string VersionLabel => "v" + Version;

    /// <summary>请求头 X-Client-Version 用的客户端协议版本。</summary>
    public const string ClientVersion = "1.0.2";

    /// <summary>请求头 X-Client-Platform。</summary>
    public const string Platform = "windows";

    public const string RepoOwner = "beibing173";
    public const string RepoName = "smsatbox";
    public const string GitHubReleasesApi = "https://api.github.com/repos/beibing173/smsatbox/releases/latest";
    public const string GitHubReleasesPage = "https://github.com/beibing173/smsatbox/releases";

    /// <summary>运行时程序集版本（诊断用）。</summary>
    public static string AssemblyVersionText
    {
        get
        {
            try
            {
                var v = Assembly.GetExecutingAssembly().GetName().Version;
                return v?.ToString() ?? Version;
            }
            catch
            {
                return Version;
            }
        }
    }
}
