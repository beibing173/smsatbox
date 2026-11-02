using System.Windows;
using System.Windows.Media;
using Microsoft.Win32;

namespace SmsatBox.Desktop.Core;

/// <summary>深色 / 浅色主题，切换即时生效并记忆到配置。</summary>
public static class ThemeManager
{
    /// <summary>主题切换后触发，供自绘控件刷新。</summary>
    public static event Action<string>? ThemeChanged;

    public static bool IsDark { get; private set; } = true;

    public static string Current => IsDark ? "dark" : "light";

    public static void Apply(string? theme)
    {
        IsDark = !string.Equals(theme, "light", StringComparison.OrdinalIgnoreCase);
        ApplyToResources(IsDark);
        ThemeChanged?.Invoke(Current);
    }

    public static string Toggle()
    {
        IsDark = !IsDark;
        ApplyToResources(IsDark);
        ThemeChanged?.Invoke(Current);
        return Current;
    }

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

        // 系统主题色（标题栏 / 原生控件跟随）
        try
        {
            SetAppsUseLightTheme(!dark);
        }
        catch
        {
            // 无权限或旧系统，忽略
        }
    }

    /// <summary>写入 HKCU\...\Themes\Personalize\AppsUseLightTheme，让原生窗口边框跟随。</summary>
    private static void SetAppsUseLightTheme(bool light)
    {
        using var key = Registry.CurrentUser.OpenSubKey(
            @"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", writable: true);
        key?.SetValue("AppsUseLightTheme", light ? 1 : 0, RegistryValueKind.DWord);
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
