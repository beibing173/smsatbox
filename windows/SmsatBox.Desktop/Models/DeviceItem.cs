using System.Text.Json.Serialization;
using SmsatBox.Desktop.Core;

namespace SmsatBox.Desktop.Models;

/// <summary>SIM 卡槽，对应 Device.slots[]。</summary>
public sealed class SimSlot
{
    [JsonPropertyName("id")]
    public int Id { get; set; }

    [JsonPropertyName("slot_index")]
    public int SlotIndex { get; set; }

    [JsonPropertyName("phone_number")]
    public string PhoneNumber { get; set; } = "";

    [JsonPropertyName("carrier")]
    public string Carrier { get; set; } = "";

    [JsonPropertyName("signal_dbm")]
    public int SignalDbm { get; set; }

    [JsonPropertyName("plan_name")]
    public string PlanName { get; set; } = "";

    [JsonPropertyName("plan_expire_at")]
    public string PlanExpireAt { get; set; } = "";

    [JsonIgnore]
    public string Title => $"卡槽 {SlotIndex}";

    [JsonIgnore]
    public string NumberLabel => string.IsNullOrWhiteSpace(PhoneNumber) ? "未配置号码" : PhoneNumber;

    [JsonIgnore]
    public string CarrierLabel => string.IsNullOrWhiteSpace(Carrier) ? "未知运营商" : Carrier;

    /// <summary>dBm → 格数（0-5）。-50 极好，-110 极差。</summary>
    [JsonIgnore]
    public int SignalBars => SignalDbm switch
    {
        >= -60 => 5,
        >= -70 => 4,
        >= -80 => 3,
        >= -90 => 2,
        >= -100 => 1,
        _ => 0,
    };

    [JsonIgnore]
    public string SignalLabel => SignalDbm == 0 ? "—" : $"{SignalDbm} dBm";

    [JsonIgnore]
    public string SignalStars
    {
        get
        {
            if (SignalDbm == 0)
            {
                return "—";
            }

            var bars = SignalBars;
            return new string('▮', bars) + new string('▯', 5 - bars);
        }
    }

    [JsonIgnore]
    public string PlanExpireLabel
    {
        get
        {
            var utc = MessageItem.ParseUtc(PlanExpireAt);
            if (utc is null)
            {
                return string.IsNullOrWhiteSpace(PlanExpireAt) ? "长期有效" : PlanExpireAt;
            }

            return utc.Value.ToLocalTime().ToString("yyyy-MM-dd");
        }
    }
}

/// <summary>设备，对应 GET /devices 的 items[]。</summary>
public sealed class DeviceItem
{
    [JsonPropertyName("id")]
    public int Id { get; set; }

    [JsonPropertyName("device_name")]
    public string DeviceName { get; set; } = "";

    [JsonPropertyName("online")]
    public bool Online { get; set; }

    [JsonPropertyName("firmware_version")]
    public string FirmwareVersion { get; set; } = "";

    [JsonPropertyName("net_mode")]
    public string? NetMode { get; set; }

    [JsonPropertyName("local_ip")]
    public string? LocalIp { get; set; }

    [JsonPropertyName("wifi_rssi")]
    public int WifiRssi { get; set; }

    [JsonPropertyName("last_seen_at")]
    public string? LastSeenAt { get; set; }

    [JsonPropertyName("slots")]
    public List<SimSlot> Slots { get; set; } = new();

    [JsonIgnore]
    public string NameLabel => string.IsNullOrWhiteSpace(DeviceName) ? $"设备 #{Id}" : DeviceName;

    [JsonIgnore]
    public string StatusLabel => Online ? "在线" : "离线";

    [JsonIgnore]
    public string OnlineBadge => Online ? "●" : "○";

    [JsonIgnore]
    public string NetModeLabel => (NetMode ?? "none").ToLowerInvariant() switch
    {
        "wifi" => "Wi-Fi",
        "4g" => "4G",
        "none" => "未连接",
        var other => other,
    };

    [JsonIgnore]
    public string IpLabel => string.IsNullOrWhiteSpace(LocalIp) ? "—" : LocalIp!;

    [JsonIgnore]
    public string LastSeenLabel => MessageItem.RelativeTime(LastSeenAt);

    [JsonIgnore]
    public string LastSeenExact => MessageItem.FormatLocal(LastSeenAt, "yyyy-MM-dd HH:mm:ss");

    [JsonIgnore]
    public string WifiRssiLabel => WifiRssi == 0 ? "—" : $"{WifiRssi} dBm";

    [JsonIgnore]
    public string SlotCountLabel => $"{Slots.Count} 个卡槽";
}

/// <summary>GET /devices 响应。</summary>
public sealed class DeviceListResponse
{
    [JsonPropertyName("items")]
    public List<DeviceItem> Items { get; set; } = new();
}
