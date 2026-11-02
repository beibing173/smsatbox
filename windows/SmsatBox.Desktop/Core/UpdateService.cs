using System.Diagnostics;
using System.Net.Http;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace SmsatBox.Desktop.Core;

/// <summary>GitHub Release 响应（只取需要的字段）。</summary>
public sealed class GitHubRelease
{
    [JsonPropertyName("tag_name")]
    public string TagName { get; set; } = "";

    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("body")]
    public string Body { get; set; } = "";

    [JsonPropertyName("html_url")]
    public string HtmlUrl { get; set; } = "";

    [JsonPropertyName("published_at")]
    public string PublishedAt { get; set; } = "";

    [JsonPropertyName("prerelease")]
    public bool Prerelease { get; set; }

    [JsonPropertyName("assets")]
    public List<GitHubAsset> Assets { get; set; } = new();
}

public sealed class GitHubAsset
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("browser_download_url")]
    public string BrowserDownloadUrl { get; set; } = "";

    [JsonPropertyName("size")]
    public long Size { get; set; }
}

/// <summary>检查更新结果。</summary>
public sealed class UpdateCheckResult
{
    public bool HasUpdate { get; init; }

    public string CurrentVersion { get; init; } = AppInfo.Version;

    public string? LatestVersion { get; init; }

    public string? ReleaseNotes { get; init; }

    public string? ReleaseUrl { get; init; }

    public string? DownloadUrl { get; init; }

    public string? AssetName { get; init; }

    public long AssetSize { get; init; }

    public string Message { get; init; } = "";

    public bool IsError { get; init; }

    public Exception? Error { get; init; }
}

/// <summary>
/// 独立升级：直接查 GitHub Release API，绝不经过 SMSATBOX Server。
///
/// 【关键设计】一个 Release 同时承载 APK 与 EXE，两端的版本号各自独立。
/// 因此**不能**用 Release 的 tag 作为版本依据（tag 只是快照标识），
/// 而是从**自己那个附件文件名**里解析版本：
///     smsatbox-windows-1.0.5.exe   → 1.0.5
///     smsatbox-android-1.2.0.apk   → 1.2.0
/// 这样 Windows 升级不会被 Android 的版本号误导，反之亦然。
/// </summary>
public static class UpdateService
{
    /// <summary>Windows 端产物文件名模式。</summary>
    private static readonly Regex WindowsAssetPattern = new(
        @"^smsatbox-windows-(?<ver>\d+\.\d+\.\d+)\.exe$",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    /// <summary>兼容旧的命名：smsatbox-v1.0.0.exe / SmsatBox.exe。</summary>
    private static readonly Regex LegacyAssetPattern = new(
        @"^(?:smsatbox-v?(?<ver>\d+\.\d+\.\d+)|smsatbox)\.exe$",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly HttpClient Http;

    static UpdateService()
    {
        var handler = new HttpClientHandler { AllowAutoRedirect = true };
        Http = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(30) };
        Http.DefaultRequestHeaders.TryAddWithoutValidation("Accept", "application/vnd.github+json");
        Http.DefaultRequestHeaders.TryAddWithoutValidation("User-Agent", $"{AppInfo.ProductName}-Windows/{AppInfo.Version}");
    }

    /// <summary>去掉版本前缀 v/V 与空白（含大小写混写、重复前缀等异常情况）。</summary>
    public static string NormalizeVersion(string? tag)
    {
        var t = (tag ?? "").Trim();
        while (t.Length > 0 && (t[0] == 'v' || t[0] == 'V'))
        {
            t = t[1..].Trim();
        }

        return t;
    }

    /// <summary>比较版本：返回 true 表示 latest 比 current 新。支持 1.0.0 / 1.0 / 1.0.0.1。</summary>
    public static bool IsNewer(string? latest, string? current)
    {
        var l = ParseVersion(latest);
        var c = ParseVersion(current);
        if (l is null || c is null)
        {
            return false;
        }

        return l > c;
    }

    public static Version? ParseVersion(string? text)
    {
        var t = NormalizeVersion(text);
        if (string.IsNullOrWhiteSpace(t))
        {
            return null;
        }

        // 去掉 -beta / +build 之类后缀
        var cut = t.IndexOfAny(new[] { '-', '+' });
        if (cut >= 0)
        {
            t = t[..cut];
        }

        var parts = t.Split('.', StringSplitOptions.RemoveEmptyEntries);
        var nums = new List<int>();
        foreach (var p in parts)
        {
            if (int.TryParse(p, out var n) && n >= 0)
            {
                nums.Add(n);
            }
            else
            {
                break;
            }
        }

        if (nums.Count == 0)
        {
            return null;
        }

        while (nums.Count < 4)
        {
            nums.Add(0);
        }

        return new Version(nums[0], nums[1], nums[2], nums[3]);
    }

    /// <summary>从附件文件名里解析 Windows 端版本号；解析不出返回 null。</summary>
    public static string? VersionFromAssetName(string? assetName)
    {
        if (string.IsNullOrWhiteSpace(assetName))
        {
            return null;
        }

        var m = WindowsAssetPattern.Match(assetName);
        if (m.Success && m.Groups["ver"].Success)
        {
            return m.Groups["ver"].Value;
        }

        var legacy = LegacyAssetPattern.Match(assetName);
        if (legacy.Success && legacy.Groups["ver"].Success)
        {
            return legacy.Groups["ver"].Value;
        }

        return null;
    }

    /// <summary>在资产列表里挑出属于 Windows 端的 .exe（优先新命名）。</summary>
    private static GitHubAsset? PickWindowsAsset(List<GitHubAsset>? assets)
    {
        if (assets is null || assets.Count == 0)
        {
            return null;
        }

        // 1) 新命名，且能解析出版本
        var preferred = assets
            .Where(a => WindowsAssetPattern.IsMatch(a.Name))
            .OrderByDescending(a => ParseVersion(VersionFromAssetName(a.Name)) ?? new Version(0, 0))
            .FirstOrDefault();
        if (preferred is not null)
        {
            return preferred;
        }

        // 2) 兼容旧命名
        return assets.FirstOrDefault(a => a.Name.EndsWith(".exe", StringComparison.OrdinalIgnoreCase));
    }

    public static async Task<UpdateCheckResult> CheckAsync(CancellationToken ct = default)
    {
        try
        {
            using var req = new HttpRequestMessage(HttpMethod.Get, AppInfo.GitHubReleasesApi);
            using var resp = await Http.SendAsync(req, ct).ConfigureAwait(false);

            if (resp.StatusCode == System.Net.HttpStatusCode.NotFound)
            {
                return new UpdateCheckResult
                {
                    HasUpdate = false,
                    Message = "GitHub 仓库暂无 Release（404）",
                };
            }

            if (!resp.IsSuccessStatusCode)
            {
                return new UpdateCheckResult
                {
                    IsError = true,
                    Message = $"GitHub API 返回 {(int)resp.StatusCode} {resp.ReasonPhrase}",
                };
            }

            var json = await resp.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
            var release = System.Text.Json.JsonSerializer.Deserialize<GitHubRelease>(
                json,
                new System.Text.Json.JsonSerializerOptions { PropertyNameCaseInsensitive = true });

            if (release is null)
            {
                return new UpdateCheckResult { IsError = true, Message = "GitHub 返回内容无法解析" };
            }

            var asset = PickWindowsAsset(release.Assets);
            if (asset is null)
            {
                // 这个 Release 里没有 Windows 产物（可能只发了 Android 侧）
                return new UpdateCheckResult
                {
                    HasUpdate = false,
                    Message = "当前 Release 未包含 Windows 安装包",
                    ReleaseUrl = release.HtmlUrl,
                };
            }

            // ★ 版本依据 = 附件文件名里的版本，而不是 Release tag
            var latest = VersionFromAssetName(asset.Name) ?? NormalizeVersion(release.TagName);
            var newer = IsNewer(latest, AppInfo.Version);

            return new UpdateCheckResult
            {
                HasUpdate = newer,
                LatestVersion = latest,
                ReleaseNotes = release.Body,
                ReleaseUrl = release.HtmlUrl,
                DownloadUrl = asset.BrowserDownloadUrl,
                AssetName = asset.Name,
                AssetSize = asset.Size,
                Message = newer
                    ? $"发现新版本 v{latest}"
                    : $"已是最新版本 v{AppInfo.Version}",
            };
        }
        catch (TaskCanceledException) when (!ct.IsCancellationRequested)
        {
            return new UpdateCheckResult { IsError = true, Message = "连接 GitHub 超时，请检查网络" };
        }
        catch (Exception ex)
        {
            Log.Write("检查更新失败", ex);
            return new UpdateCheckResult
            {
                IsError = true,
                Message = "检查更新失败：" + ex.Message,
                Error = ex,
            };
        }
    }

    /// <summary>下载新版本到临时目录，返回本地 exe 路径。</summary>
    public static async Task<string> DownloadAsync(UpdateCheckResult result, IProgress<double>? progress = null, CancellationToken ct = default)
    {
        if (string.IsNullOrWhiteSpace(result.DownloadUrl))
        {
            throw new InvalidOperationException("该 Release 没有可用的 .exe 资产，无法自动升级");
        }

        var dir = Path.Combine(Path.GetTempPath(), "SMSATBOX-update");
        Directory.CreateDirectory(dir);

        // 清掉上次残留
        foreach (var old in Directory.GetFiles(dir, "*.exe"))
        {
            try
            {
                File.Delete(old);
            }
            catch
            {
                // 占用中则忽略
            }
        }

        var fileName = string.IsNullOrWhiteSpace(result.AssetName) ? "SmsatBox.exe" : result.AssetName!;
        var target = Path.Combine(dir, fileName);

        using var resp = await Http.GetAsync(result.DownloadUrl, HttpCompletionOption.ResponseHeadersRead, ct).ConfigureAwait(false);
        resp.EnsureSuccessStatusCode();

        var total = resp.Content.Headers.ContentLength ?? result.AssetSize;
        await using var stream = await resp.Content.ReadAsStreamAsync(ct).ConfigureAwait(false);
        await using var fs = new FileStream(target, FileMode.Create, FileAccess.Write, FileShare.None);

        var buffer = new byte[81920];
        long done = 0;
        int read;
        while ((read = await stream.ReadAsync(buffer, ct).ConfigureAwait(false)) > 0)
        {
            await fs.WriteAsync(buffer.AsMemory(0, read), ct).ConfigureAwait(false);
            done += read;
            if (total > 0)
            {
                progress?.Report(Math.Clamp(done * 100.0 / total, 0, 100));
            }
        }

        await fs.FlushAsync(ct).ConfigureAwait(false);
        Log.Write($"新版本已下载：{target}（{done} bytes）");
        return target;
    }

    /// <summary>启动新 exe 并退出当前进程。</summary>
    public static void LaunchAndExit(string newExePath)
    {
        if (!File.Exists(newExePath))
        {
            throw new FileNotFoundException("升级文件不存在", newExePath);
        }

        var psi = new ProcessStartInfo
        {
            FileName = newExePath,
            UseShellExecute = true,
            WorkingDirectory = Path.GetDirectoryName(newExePath) ?? Environment.CurrentDirectory,
            Arguments = "--upgraded",
        };

        Process.Start(psi);
        Log.Write("已启动新版本，准备退出当前进程");

        // 给新进程一点时间接管，再退出自己
        System.Windows.Application.Current?.Dispatcher.BeginInvoke(new Action(() =>
        {
            System.Windows.Application.Current?.Shutdown();
        }));
    }
}
