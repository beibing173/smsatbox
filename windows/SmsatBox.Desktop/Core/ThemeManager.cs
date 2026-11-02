using System.Windows;
using System.Windows.Media;
using Microsoft.Win32;

namespace SmsatBox.Desktop.Core;

/// <summary>主题模式：跟随系统 / 深色 / 浅色。</summary>
public enum ThemeMode
{
    /// <summary>跟随 Windows 系统的应用主题（默认）。</summary>
    System = 0,

    /// <summary>强制深色。</summary>
    Dark = 1,

    /// <summary>强制浅色。</summary>
    Light = 2,
}

/// <summary>
/// 主题管理：三种模式（跟随系统 / 深色 / 浅色），切换即时生效并记忆到配置。
///
/// 【重要】本类**只修改本应用自己的资源**，绝不写入系统注册表，
/// 不会改变用户的 Windows 外观设置。
/// </summary>
public static class ThemeManager
{
    /// <summary>主题切换后触发，供自绘控件刷新。参数为当前实际生效的 "dark" / "light"。</summary>
    public static event Action<string>? ThemeChanged;

    /// <summary>用户选择的模式。</summary>
    public static ThemeMode Mode { get; private set; } = ThemeMode.System;

    /// <summary>当前实际生效的是否深色（由 Mode 与系统设置共同决定）。</summary>
    public static bool IsDark { get; private set; }

    /// <summary>当前实际生效的主题："dark" / "light"。</summary>
    public static string Current => IsDark ? "dark" : "light";

    /// <summary>模式的中文名，供界面显示。</summary>
    public static string ModeLabel => Mode switch
    {
        ThemeMode.Dark => "深色",
        ThemeMode.Light => "浅色",
        _ => "跟随系统",
    };

    /// <summary>应用主题。参数可为 "system" / "dark" / "light"（兼容旧的 "dark"/"light" 配置）。</summary>
    public static void Apply(string? theme)
    {
        Mode = Parse(theme);
        ApplyFromMode();
    }

    /// <summary>在三种模式间循环切换（跟随系统 → 深色 → 浅色 → 跟随系统）。</summary>
    public static string Cycle()
    {
        Mode = Mode switch
        {
            ThemeMode.System => ThemeMode.Dark,
            ThemeMode.Dark => ThemeMode.Light,
            _ => ThemeMode.System,
        };
        ApplyFromMode();
        return ModeLabel;
    }

    /// <summary>直接设置模式。</summary>
    public static void SetMode(ThemeMode mode)
    {
        Mode = mode;
        ApplyFromMode();
    }

    /// <summary>系统主题变化时调用（仅当 Mode == System 才真正改变外观）。</summary>
    public static void OnSystemThemeChanged()
    {
        if (Mode == ThemeMode.System)
        {
            ApplyFromMode();
        }
    }

    private static void ApplyFromMode()
    {
        IsDark = Mode switch
        {
            ThemeMode.Dark => true,
            ThemeMode.Light => false,
            _ => IsSystemDark(),
        };

        ApplyToResources(IsDark);
        ThemeChanged?.Invoke(Current);
    }

    /// <summary>读取系统当前是否为深色应用模式。仅读取，不写入。</summary>
    public static bool IsSystemDark()
    {
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(
                @"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                writable: false);   // 关键：只读打开，绝不写入

            if (key?.GetValue("AppsUseLightTheme") is int light)
            {
                return light == 0;
            }
        }
        catch
        {
            // 读不到就当作浅色
        }

        return false;
    }

    private static ThemeMode Parse(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return ThemeMode.System;
        }

        return value.Trim().ToLowerInvariant() switch
        {
            "dark" => ThemeMode.Dark,
            "light" => ThemeMode.Light,
            _ => ThemeMode.System,
        };
    }

    /// <summary>把模式序列化成配置里存的值。</summary>
    public static string SerializeMode(ThemeMode mode) => mode switch
    {
        ThemeMode.Dark => "dark",
        ThemeMode.Light => "light",
        _ => "system",
    };

    private static void ApplyToResources(bool dark)
    {
        var app = Application.Current;
        if (app is null)
        {
            return;
        }

        var palette = dark ? Palette.Dark : Palette.Light;
        foreach (var kv in palette)
        {
            app.Resources[kv.Key] = kv.Value;
        }

        // 注意：这里刻意不调用任何写注册表的方法。
        // 本应用的配色只写在 App.Resources 里，系统外观保持用户原样。
    }

    /// <summary>调色板：key 与 App.xaml 中的 DynamicResource 名一致。</summary>
    public static class Palette
    {
        public static readonly Dictionary<string, object> Dark = new()
        {
            ["Brush.WindowBg"] = Solid("#0E1520"),
            ["Brush.Surface"] = Solid("#16202E"),
            ["Brush.SurfaceAlt"] = Solid("#1C2837"),
            ["Brush.SurfaceHover"] = Solid("#22303F"),
            ["Brush.Border"] = Solid("#243344"),
            ["Brush.Text"] = Solid("#E9F1FA"),
            ["Brush.TextSub"] = Solid("#93A6BA"),
            ["Brush.TextMuted"] = Solid("#6B7F94"),
            ["Brush.Accent"] = Solid("#3FA9F5"),
            ["Brush.AccentSoft"] = Solid("#1B3B57"),
            ["Brush.Danger"] = Solid("#FF6B6B"),
            ["Brush.Success"] = Solid("#4ADE80"),
            ["Brush.Warn"] = Solid("#FBBF24"),
            ["Brush.CodeBg"] = Solid("#123049"),
            ["Brush.CodeFg"] = Solid("#7FD4FF"),
            ["Brush.NavBg"] = Solid("#101A26"),
            ["Brush.NavActive"] = Solid("#1E3145"),
        };

        public static readonly Dictionary<string, object> Light = new()
        {
            ["Brush.WindowBg"] = Solid("#F2F5F9"),
            ["Brush.Surface"] = Solid("#FFFFFF"),
            ["Brush.SurfaceAlt"] = Solid("#F7FAFC"),
            ["Brush.SurfaceHover"] = Solid("#EDF3FA"),
            ["Brush.Border"] = Solid("#DCE5EF"),
            ["Brush.Text"] = Solid("#12212F"),
            ["Brush.TextSub"] = Solid("#4F6377"),
            ["Brush.TextMuted"] = Solid("#7C8FA3"),
            ["Brush.Accent"] = Solid("#0F7FD4"),
            ["Brush.AccentSoft"] = Solid("#DCEBFA"),
            ["Brush.Danger"] = Solid("#D93636"),
            ["Brush.Success"] = Solid("#12873F"),
            ["Brush.Warn"] = Solid("#B7791F"),
            ["Brush.CodeBg"] = Solid("#E4F2FF"),
            ["Brush.CodeFg"] = Solid("#0B5C94"),
            ["Brush.NavBg"] = Solid("#FFFFFF"),
            ["Brush.NavActive"] = Solid("#DCEBFA"),
        };

        private static SolidColorBrush Solid(string hex)
        {
            var brush = new SolidColorBrush((Color)ColorConverter.ConvertFromString(hex));
            brush.Freeze();
            return brush;
        }
    }
}
