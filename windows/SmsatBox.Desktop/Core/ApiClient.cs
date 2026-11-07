using System.Net;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using SmsatBox.Desktop.Models;

namespace SmsatBox.Desktop.Core;

/// <summary>API 调用异常（带可读中文消息）。</summary>
public sealed class ApiException : Exception
{
    public ApiException(string message, HttpStatusCode? status = null, Exception? inner = null)
        : base(message, inner)
    {
        Status = status;
    }

    public HttpStatusCode? Status { get; }

    public bool IsUnauthorized => Status == HttpStatusCode.Unauthorized;
}

/// <summary>
/// SMSATBOX 中转平台 API 客户端。
/// Base = {serverUrl}/api/v1，统一带 X-Client-Version / X-Client-Platform / Authorization。
/// </summary>
public sealed class ApiClient : IDisposable
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        NumberHandling = System.Text.Json.Serialization.JsonNumberHandling.AllowReadingFromString,
    };

    private readonly HttpClient _http;

    public ApiClient(string? serverUrl, string? token)
    {
        ServerUrl = NormalizeBase(serverUrl);
        Token = (token ?? "").Trim();

        var handler = new HttpClientHandler
        {
            AutomaticDecompression = DecompressionMethods.GZip | DecompressionMethods.Deflate,
            AllowAutoRedirect = true,
        };

        _http = new HttpClient(handler)
        {
            Timeout = TimeSpan.FromSeconds(20),
        };
        _http.DefaultRequestHeaders.TryAddWithoutValidation("X-Client-Version", AppInfo.ClientVersion);
        _http.DefaultRequestHeaders.TryAddWithoutValidation("X-Client-Platform", AppInfo.Platform);
        _http.DefaultRequestHeaders.TryAddWithoutValidation("Accept", "application/json");
    }

    /// <summary>规整后的 base，例如 http://host:8000/api/v1 。</summary>
    public string ServerUrl { get; }

    public string Token { get; }

    public bool IsConfigured => !string.IsNullOrWhiteSpace(ServerUrl) && !string.IsNullOrWhiteSpace(Token);

    /// <summary>把用户输入的公网地址规整为 {base}/api/v1 形式。</summary>
    public static string NormalizeBase(string? raw)
    {
        var value = (raw ?? "").Trim();
        if (string.IsNullOrEmpty(value))
        {
            return "";
        }

        if (!value.Contains("://", StringComparison.Ordinal))
        {
            value = "http://" + value;
        }

        if (!Uri.TryCreate(value, UriKind.Absolute, out var uri))
        {
            return "";
        }

        var text = uri.GetLeftPart(UriPartial.Path).TrimEnd('/');

        // 用户可能填了 .../api/v1 或 .../api/v1/
        if (text.EndsWith("/api/v1", StringComparison.OrdinalIgnoreCase))
        {
            return text;
        }

        if (text.EndsWith("/api", StringComparison.OrdinalIgnoreCase))
        {
            return text + "/v1";
        }

        return text + "/api/v1";
    }

    /// <summary>仅用于界面显示的主机部分。</summary>
    public static string DisplayHost(string? raw)
    {
        var b = NormalizeBase(raw);
        if (string.IsNullOrEmpty(b))
        {
            return "未配置";
        }

        return Uri.TryCreate(b, UriKind.Absolute, out var uri) ? uri.Host + (uri.IsDefaultPort ? "" : ":" + uri.Port) : b;
    }

    private HttpRequestMessage Build(HttpMethod method, string path)
    {
        if (string.IsNullOrWhiteSpace(ServerUrl))
        {
            throw new ApiException("尚未填写公网中转平台地址");
        }

        var url = ServerUrl.TrimEnd('/') + path;
        var req = new HttpRequestMessage(method, url);
        if (!string.IsNullOrWhiteSpace(Token))
        {
            req.Headers.TryAddWithoutValidation("Authorization", "Bearer " + Token);
        }

        return req;
    }

    private async Task<T> SendAsync<T>(HttpMethod method, string path, object? body = null, CancellationToken ct = default)
    {
        using var req = Build(method, path);
        if (body is not null)
        {
            var json = JsonSerializer.Serialize(body, JsonOptions);
            req.Content = new StringContent(json, Encoding.UTF8, "application/json");
        }

        HttpResponseMessage resp;
        try
        {
            resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        }
        catch (TaskCanceledException) when (!ct.IsCancellationRequested)
        {
            throw new ApiException("请求超时，请检查平台地址与网络");
        }
        catch (HttpRequestException ex)
        {
            throw new ApiException("无法连接中转平台：" + ex.Message, null, ex);
        }

        using (resp)
        {
            var text = await resp.Content.ReadAsStringAsync(ct).ConfigureAwait(false);

            if (resp.StatusCode == HttpStatusCode.Unauthorized)
            {
                throw new ApiException("Token 无效或已过期，请重新填写", resp.StatusCode);
            }

            if (!resp.IsSuccessStatusCode)
            {
                throw new ApiException(
                    $"服务端返回 {(int)resp.StatusCode} {resp.ReasonPhrase}{(string.IsNullOrWhiteSpace(text) ? "" : "：" + Trim(text))}",
                    resp.StatusCode);
            }

            if (string.IsNullOrWhiteSpace(text))
            {
                return Activator.CreateInstance<T>();
            }

            try
            {
                var value = JsonSerializer.Deserialize<T>(text, JsonOptions);
                if (value is null)
                {
                    throw new ApiException("服务端返回了空响应");
                }

                return value;
            }
            catch (JsonException ex)
            {
                throw new ApiException("解析服务端响应失败：" + Trim(text), resp.StatusCode, ex);
            }
        }
    }

    private static string Trim(string text) => text.Length <= 200 ? text : text[..200] + "…";

    // ------------------------------------------------------------------ API --

    public Task<VerifyResponse> VerifyAsync(CancellationToken ct = default)
        => SendAsync<VerifyResponse>(HttpMethod.Get, "/auth/verify", null, ct);

    public Task<ServerVersionResponse> GetServerVersionAsync(CancellationToken ct = default)
        => SendAsync<ServerVersionResponse>(HttpMethod.Get, "/version", null, ct);

    public async Task<MessageListResponse> GetMessagesAsync(int limit = 100, int offset = 0, int? slotId = null, CancellationToken ct = default)
    {
        var path = $"/messages?limit={limit}&offset={offset}";
        if (slotId is > 0)
        {
            path += "&slot_id=" + slotId.Value;
        }

        return await SendAsync<MessageListResponse>(HttpMethod.Get, path, null, ct).ConfigureAwait(false);
    }

    public Task<StatsResponse> GetStatsAsync(CancellationToken ct = default)
        => SendAsync<StatsResponse>(HttpMethod.Get, "/messages/stats", null, ct);

    public async Task MarkReadAsync(int messageId, bool isRead = true, CancellationToken ct = default)
    {
        await SendAsync<JsonElement>(
            HttpMethod.Patch,
            $"/messages/{messageId}",
            new { is_read = isRead },
            ct).ConfigureAwait(false);
    }

    public Task<DeviceListResponse> GetDevicesAsync(CancellationToken ct = default)
        => SendAsync<DeviceListResponse>(HttpMethod.Get, "/devices", null, ct);

    /// <summary>修改卡槽：备注 / 号码 / 运营商 / 显示或隐藏。</summary>
    public async Task UpdateSlotAsync(
        int slotId,
        string? remark = null,
        string? phoneNumber = null,
        string? carrier = null,
        string? planName = null,
        bool? visible = null,
        CancellationToken ct = default)
    {
        var body = new Dictionary<string, object>();
        if (remark is not null) body["remark"] = remark;
        if (phoneNumber is not null) body["phone_number"] = phoneNumber;
        if (carrier is not null) body["carrier"] = carrier;
        if (planName is not null) body["plan_name"] = planName;
        if (visible is not null) body["is_active"] = visible.Value;

        await SendAsync<JsonElement>(HttpMethod.Patch, $"/devices/slots/{slotId}", body, ct)
            .ConfigureAwait(false);
    }

    /// <summary>修改设备名称 / 备注（需要超级管理员）。</summary>
    public async Task UpdateDeviceAsync(
        int deviceId,
        string? name = null,
        string? remark = null,
        CancellationToken ct = default)
    {
        var body = new Dictionary<string, object>();
        if (name is not null) body["device_name"] = name;
        if (remark is not null) body["remark"] = remark;

        await SendAsync<JsonElement>(HttpMethod.Patch, $"/devices/{deviceId}", body, ct)
            .ConfigureAwait(false);
    }

    public void Dispose() => _http.Dispose();
}
