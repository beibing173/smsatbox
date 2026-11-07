using System.Text.Json.Serialization;
using SmsatBox.Desktop.Core;

namespace SmsatBox.Desktop.Models;

/// <summary>4G 模组的实时状态，对应 slot.module（ESP32 上报）。</summary>
public sealed class ModuleStatus
{
    [JsonPropertyName("present")]
    public bool Present { get; set; }

    [JsonPropertyName("module_state")]
    public string ModuleState { get; set; } = "";

    [JsonPropertyName("sim_state")]
    public string SimState { get; set; } = "";

    [JsonPropertyName("registered")]
    public bool Registered { get; set; }

    [JsonPropertyName("reg_status")]
    public int RegStatus { get; set; } = 4;

    [JsonPropertyName("reg_text")]
    public string RegText { get; set; } = "";

    [JsonPropertyName("lac")]
    public string Lac { get; set; } = "";

    [JsonPropertyName("cell_id")]
    public string CellId { get; set; } = "";

    [JsonPropertyName("rssi_csq")]
    public int Csq { get; set; } = 99;

    [JsonPropertyName("signal_dbm")]
    public int? SignalDbm { get; set; }

    [JsonPropertyName("signal_level")]
    public int SignalLevel { get; set; }

    [JsonPropertyName("carrier")]
    public string Carrier { get; set; } = "";

    [JsonPropertyName("phone_number")]
    public string PhoneNumber { get; set; } = "";

    [JsonPropertyName("imsi")]
    public string Imsi { get; set; } = "";

    [JsonPropertyName("iccid")]
    public string Iccid { get; set; } = "";

    [JsonPropertyName("imei")]
    public string Imei { get; set; } = "";

    [JsonIgnore]
    public bool SimReady => SimState == "ready";

    [JsonIgnore]
    public bool HasSignal => Present && Csq is >= 0 and <= 31;

    /// <summary>模组状态徽标文案。</summary>
    [JsonIgnore]
    public string StateBadge
    {
        get
        {
            if (!Present) return "未检测到模组";
            if (ModuleState != "ready") return $"模组 {ModuleState}";
            if (!Registered) return string.IsNullOrWhiteSpace(RegText) ? "未注册网络" : RegText;
            return string.IsNullOrWhiteSpace(RegText) ? "已注册" : RegText;
        }
    }

    /// <summary>信号格（0-4）。</summary>
    [JsonIgnore]
    public string SignalBars
    {
        get
        {
            if (!HasSignal) return "▯▯▯▯";
            var n = Math.Clamp(SignalLevel, 0, 4);
            return new string('▮', n) + new string('▯', 4 - n);
        }
    }

    [JsonIgnore]
    public string SignalText =>
        !Present ? "无模组"
        : !HasSignal ? "无信号"
        : $"{SignalDbm?.ToString() ?? "—"} dBm";

    /// <summary>详情页展示的完整信息行。</summary>
    [JsonIgnore]
    public string DetailText
    {
        get
        {
            var parts = new List<string>
            {
                $"模组：{(Present ? "已检测" : "未检测")}",
                $"SIM：{(SimReady ? "就绪" : "未就绪")}",
                $"网络：{(Registered ? "已注册" : "未注册")}",
            };
            if (!string.IsNullOrWhiteSpace(RegText)) parts.Add(RegText);
            if (!string.IsNullOrWhiteSpace(Lac) || !string.IsNullOrWhiteSpace(CellId))
                parts.Add($"LAC/小区：{Lac}/{CellId}");
            if (HasSignal) parts.Add($"信号：{SignalDbm} dBm（CSQ {Csq}）");
            if (!string.IsNullOrWhiteSpace(Carrier)) parts.Add($"运营商：{Carrier}");
            if (!string.IsNullOrWhiteSpace(Imsi)) parts.Add($"IMSI：{Imsi}");
            if (!string.IsNullOrWhiteSpace(Iccid)) parts.Add($"ICCID：{Iccid}");
            if (!string.IsNullOrWhiteSpace(Imei)) parts.Add($"IMEI：{Imei}");
            return string.Join("　·　", parts);
        }
    }
}

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

    /// <summary>备注名称。</summary>
    [JsonPropertyName("remark")]
    public string Remark { get; set; } = "";

    /// <summary>是否在列表中显示。</summary>
    [JsonPropertyName("visible")]
    public bool Visible { get; set; } = true;

    /// <summary>4G 模组实时状态。</summary>
    [JsonPropertyName("module")]
    public ModuleStatus Module { get; set; } = new();

    [JsonIgnore]
    public string Title => $"卡槽 {SlotIndex}";

    /// <summary>卡片标题：优先备注，其次号码。</summary>
    [JsonIgnore]
    public string DisplayName =>
        !string.IsNullOrWhiteSpace(Remark) ? Remark
        : !string.IsNullOrWhiteSpace(PhoneNumber) ? PhoneNumber
        : $"卡槽 {SlotIndex}";

    [JsonIgnore]
    public string NumberLabel => string.IsNullOrWhiteSpace(PhoneNumber) ? "未配置号码" : PhoneNumber;

    [JsonIgnore]
    public string CarrierLabel =>
        !string.IsNullOrWhiteSpace(Module.Carrier) ? Module.Carrier
        : !string.IsNullOrWhiteSpace(Carrier) ? Carrier
        : "未知运营商";

    [JsonIgnore]
    public bool Hidden => !Visible;

    [JsonIgnore]
    public double Opacity => Visible ? 1.0 : 0.5;

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

    [JsonPropertyName("remark")]
    public string Remark { get; set; } = "";

    /// <summary>整机模组快照（ESP32 上报）。</summary>
    [JsonPropertyName("modules")]
    public List<ModuleStatus> Modules { get; set; } = new();

    [JsonPropertyName("slots")]
    public List<SimSlot> Slots { get; set; } = new();

    [JsonIgnore]
    public string NameLabel => string.IsNullOrWhiteSpace(DeviceName) ? $"设备 #{Id}" : DeviceName;

    [JsonIgnore]
    public bool HasRemark => !string.IsNullOrWhiteSpace(Remark);

    [JsonIgnore]
    public string StatusLabel => Online ? "在线" : "离线";

    [JsonIgnore]
    public string ModuleSummary
    {
        get
        {
            if (Modules.Count == 0) return "";
            var present = Modules.Count(m => m.Present);
            var reg = Modules.Count(m => m.Registered);
            return $"模组 {present}/{Modules.Count} · 已注册 {reg}";
        }
    }

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
