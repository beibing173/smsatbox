using System.Diagnostics;
using System.Net.Http;
using System.Text.Json.Serialization;

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
/// GET https://api.github.com/repos/beibing173/smsatbox/releases/latest
/// header: Accept: application/vnd.github+json, User-Agent
/// 在 assets 里找 .exe 资产，比较 tag_name（去 v 前缀）与本地版本。
/// </summary>
public static class UpdateService
{
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

            var latest = NormalizeVersion(release.TagName);
            var asset = release.Assets?
                .FirstOrDefault(a => a.Name.EndsWith(".exe", StringComparison.OrdinalIgnoreCase));

            var newer = IsNewer(latest, AppInfo.Version);

            return new UpdateCheckResult
            {
                HasUpdate = newer,
                LatestVersion = latest,
                ReleaseNotes = release.Body,
                ReleaseUrl = release.HtmlUrl,
                DownloadUrl = asset?.BrowserDownloadUrl,
                AssetName = asset?.Name,
                AssetSize = asset?.Size ?? 0,
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
            throw new InvalidOperationException("该 Release 没有 .exe 资产，无法自动升级");
        }

        var dir = Path.Combine(Path.GetTempPath(), "SMSATBOX-update");
        Directory.CreateDirectory(dir);

        // 清掉上次残留
        foreach (var old in Directory.GetFiles(dir, "SmsatBox*.exe"))
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
