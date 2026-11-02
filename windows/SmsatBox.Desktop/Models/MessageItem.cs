using System.Text.Json.Serialization;
using SmsatBox.Desktop.Core;

namespace SmsatBox.Desktop.Models;

/// <summary>消息（短信 / 未接来电 / 系统），字段严格对应服务端 message_to_client 输出的 snake_case。</summary>
public sealed class MessageItem : ObservableObject
{
    private bool _isRead;

    [JsonPropertyName("id")]
    public int Id { get; set; }

    [JsonPropertyName("device_id")]
    public int DeviceId { get; set; }

    [JsonPropertyName("device_name")]
    public string DeviceName { get; set; } = "";

    [JsonPropertyName("slot_id")]
    public int? SlotId { get; set; }

    [JsonPropertyName("slot_index")]
    public int? SlotIndex { get; set; }

    [JsonPropertyName("slot_number")]
    public string SlotNumber { get; set; } = "";

    [JsonPropertyName("kind")]
    public string Kind { get; set; } = "sms";

    [JsonPropertyName("sender")]
    public string Sender { get; set; } = "";

    [JsonPropertyName("content")]
    public string Content { get; set; } = "";

    [JsonPropertyName("code")]
    public string? Code { get; set; }

    [JsonPropertyName("received_at")]
    public string ReceivedAt { get; set; } = "";

    [JsonPropertyName("is_read")]
    public bool IsRead
    {
        get => _isRead;
        set
        {
            if (Set(ref _isRead, value))
            {
                RaiseAll(nameof(UnreadBadge), nameof(RowOpacity));
            }
        }
    }

    /// <summary>附加字段：服务端可能返回 raw，忽略即可。</summary>
    /// <summary>内容被服务端刷新后，让派生属性全部重新求值。</summary>
    public void RaiseRefresh()
        => RaiseAll(nameof(Content), nameof(Code), nameof(Sender), nameof(ReceivedAt),
            nameof(DeviceName), nameof(SlotIndex), nameof(SlotNumber), nameof(Kind),
            nameof(IsRead), nameof(IsUnread), nameof(HasCode), nameof(KindLabel),
            nameof(SlotLabel), nameof(NumberLabel), nameof(TimeLocal), nameof(TimeAgo),
            nameof(UnreadBadge), nameof(RowOpacity), nameof(ContentPreview),
            nameof(IsSms), nameof(IsCall), nameof(IsSystem));

    [JsonIgnore]
    public bool IsUnread => !IsRead;

    [JsonIgnore]
    public bool HasCode => !string.IsNullOrWhiteSpace(Code);

    [JsonIgnore]
    public bool IsSms => string.Equals(Kind, "sms", StringComparison.OrdinalIgnoreCase);

    [JsonIgnore]
    public bool IsCall => string.Equals(Kind, "call", StringComparison.OrdinalIgnoreCase);

    [JsonIgnore]
    public bool IsSystem => string.Equals(Kind, "system", StringComparison.OrdinalIgnoreCase);

    [JsonIgnore]
    public string KindLabel => IsCall ? "未接来电" : IsSystem ? "系统" : "短信";

    [JsonIgnore]
    public string SlotLabel => SlotIndex is > 0 ? $"卡槽{SlotIndex}" : SlotId is > 0 ? $"#{SlotId}" : "—";

    [JsonIgnore]
    public string NumberLabel => string.IsNullOrWhiteSpace(SlotNumber) ? "无号码" : SlotNumber;

    /// <summary>UTC ISO → 本地时间显示。</summary>
    [JsonIgnore]
    public string TimeLocal => FormatLocal(ReceivedAt, "MM-dd HH:mm:ss");

    [JsonIgnore]
    public string TimeAgo => RelativeTime(ReceivedAt);

    [JsonIgnore]
    public string UnreadBadge => IsRead ? "" : "●";

    [JsonIgnore]
    public double RowOpacity => IsRead ? 0.72 : 1.0;

    [JsonIgnore]
    public string ContentPreview
    {
        get
        {
            var text = (Content ?? "").Replace("\r", " ").Replace("\n", " ").Trim();
            if (text.Length <= 90)
            {
                return text;
            }

            return text[..90] + "…";
        }
    }

    public static DateTime? ParseUtc(string? iso)
    {
        if (string.IsNullOrWhiteSpace(iso))
        {
            return null;
        }

        var raw = iso.Trim();
        if (DateTimeOffset.TryParse(
                raw,
                System.Globalization.CultureInfo.InvariantCulture,
                System.Globalization.DateTimeStyles.AssumeUniversal | System.Globalization.DateTimeStyles.AdjustToUniversal,
                out var dto))
        {
            return dto.UtcDateTime;
        }

        if (DateTime.TryParse(raw, out var dt))
        {
            return dt.Kind == DateTimeKind.Unspecified
                ? DateTime.SpecifyKind(dt, DateTimeKind.Utc)
                : dt.ToUniversalTime();
        }

        return null;
    }

    public static string FormatLocal(string? iso, string format)
    {
        var utc = ParseUtc(iso);
        if (utc is null)
        {
            return string.IsNullOrWhiteSpace(iso) ? "—" : iso!;
        }

        return utc.Value.ToLocalTime().ToString(format);
    }

    public static string RelativeTime(string? iso)
    {
        var utc = ParseUtc(iso);
        if (utc is null)
        {
            return "—";
        }

        var span = DateTime.UtcNow - utc.Value;
        if (span.TotalSeconds < 0)
        {
            span = TimeSpan.Zero;
        }

        if (span.TotalSeconds < 60)
        {
            return "刚刚";
        }

        if (span.TotalMinutes < 60)
        {
            return $"{(int)span.TotalMinutes} 分钟前";
        }

        if (span.TotalHours < 24)
        {
            return $"{(int)span.TotalHours} 小时前";
        }

        if (span.TotalDays < 7)
        {
            return $"{(int)span.TotalDays} 天前";
        }

        return utc.Value.ToLocalTime().ToString("yyyy-MM-dd");
    }
}

/// <summary>GET /messages 响应。</summary>
public sealed class MessageListResponse
{
    [JsonPropertyName("items")]
    public List<MessageItem> Items { get; set; } = new();

    [JsonPropertyName("total")]
    public int Total { get; set; }
}

/// <summary>GET /messages/stats 响应。</summary>
public sealed class StatsResponse
{
    [JsonPropertyName("total")]
    public int Total { get; set; }

    [JsonPropertyName("unread")]
    public int Unread { get; set; }

    [JsonPropertyName("today")]
    public int Today { get; set; }

    [JsonPropertyName("codes")]
    public int Codes { get; set; }

    [JsonPropertyName("unread_calls")]
    public int UnreadCalls { get; set; }
}

/// <summary>GET /auth/verify 响应。</summary>
public sealed class VerifyResponse
{
    [JsonPropertyName("ok")]
    public bool Ok { get; set; }

    [JsonPropertyName("version")]
    public string Version { get; set; } = "";

    [JsonPropertyName("server")]
    public string Server { get; set; } = "";

    [JsonPropertyName("user")]
    public UserInfo? User { get; set; }
}

public sealed class UserInfo
{
    [JsonPropertyName("id")]
    public int Id { get; set; }

    [JsonPropertyName("username")]
    public string Username { get; set; } = "";

    [JsonPropertyName("display_name")]
    public string DisplayName { get; set; } = "";

    [JsonPropertyName("role")]
    public string Role { get; set; } = "";

    [JsonIgnore]
    public string Display => string.IsNullOrWhiteSpace(DisplayName) ? Username : DisplayName;

    [JsonIgnore]
    public string RoleLabel => Role switch
    {
        "superadmin" => "超级管理员",
        "admin" => "管理员",
        "operator" => "操作员",
        "viewer" => "只读",
        _ => string.IsNullOrWhiteSpace(Role) ? "用户" : Role,
    };

    /// <summary>侧边栏一行展示：显示名与角色重名时不重复。</summary>
    [JsonIgnore]
    public string Label => string.Equals(Display, RoleLabel, StringComparison.Ordinal)
        ? Display
        : $"{Display} · {RoleLabel}";
}

/// <summary>GET /version 响应。</summary>
public sealed class ServerVersionResponse
{
    [JsonPropertyName("product")]
    public string Product { get; set; } = "";

    [JsonPropertyName("version")]
    public string Version { get; set; } = "";
}
