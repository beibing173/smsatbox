using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;

namespace SmsatBox.Desktop.Core;

/// <summary>
/// 运行时代码生成托盘图标（不依赖 .ico 文件，单文件发布也不会丢资源）。
/// 画一个圆角的蓝色鲸鱼信封：蓝底 + 白色信封线 + 一点尾鳍，尺寸 32x32。
/// </summary>
public static class TrayIconFactory
{
    private const int Size = 32;

    public static Icon Create()
    {
        using var bmp = new Bitmap(Size, Size, PixelFormat.Format32bppArgb);
        using (var g = Graphics.FromImage(bmp))
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.InterpolationMode = InterpolationMode.HighQualityBicubic;
            g.Clear(Color.Transparent);

            // 圆角方形底：深蓝 → 亮蓝渐变
            var rect = new Rectangle(1, 1, Size - 2, Size - 2);
            using var path = RoundedRect(rect, 8);
            using (var brush = new LinearGradientBrush(rect, Color.FromArgb(255, 20, 96, 168), Color.FromArgb(255, 63, 169, 245), 55f))
            {
                g.FillPath(brush, path);
            }

            // 信封主体
            using (var pen = new Pen(Color.White, 2.2f) { LineJoin = LineJoin.Round })
            {
                var envelope = new RectangleF(7f, 10.5f, 18f, 13f);
                using var envPath = RoundedRectF(envelope, 2.4f);
                var old = g.Clip;
                g.SetClip(envPath);
                g.DrawPath(pen, envPath);
                g.ResetClip();

                // 信封折线
                g.DrawLine(pen, envelope.Left + 1.2f, envelope.Top + 1.5f, envelope.Left + envelope.Width / 2f, envelope.Top + 8.2f);
                g.DrawLine(pen, envelope.Right - 1.2f, envelope.Top + 1.5f, envelope.Left + envelope.Width / 2f, envelope.Top + 8.2f);
            }

            // 信号弧（右侧两道），暗示"短信提醒"
            using (var pen = new Pen(Color.FromArgb(235, 255, 255, 255), 1.7f) { StartCap = LineCap.Round, EndCap = LineCap.Round })
            {
                g.DrawArc(pen, 20f, 4.5f, 8f, 8f, -55f, 110f);
                g.DrawArc(pen, 23.5f, 1.5f, 10f, 13f, -55f, 110f);
            }
        }

        return FromBitmap(bmp);
    }

    /// <summary>一个高亮的"有新消息"变体（右上角红点），用于未读数角标场景。</summary>
    public static Icon CreateWithBadge()
    {
        using var bmp = new Bitmap(Size, Size, PixelFormat.Format32bppArgb);
        using (var g = Graphics.FromImage(bmp))
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.Clear(Color.Transparent);

            var rect = new Rectangle(1, 1, Size - 2, Size - 2);
            using var path = RoundedRect(rect, 8);
            using (var brush = new LinearGradientBrush(rect, Color.FromArgb(255, 20, 96, 168), Color.FromArgb(255, 63, 169, 245), 55f))
            {
                g.FillPath(brush, path);
            }

            using (var pen = new Pen(Color.White, 2.2f) { LineJoin = LineJoin.Round })
            {
                var envelope = new RectangleF(7f, 10.5f, 18f, 13f);
                g.DrawRectangle(pen, envelope.X, envelope.Y, envelope.Width, envelope.Height);
                g.DrawLine(pen, envelope.Left + 1.2f, envelope.Top + 1.5f, envelope.Left + envelope.Width / 2f, envelope.Top + 8.2f);
                g.DrawLine(pen, envelope.Right - 1.2f, envelope.Top + 1.5f, envelope.Left + envelope.Width / 2f, envelope.Top + 8.2f);
            }

            using (var dot = new SolidBrush(Color.FromArgb(255, 255, 86, 86)))
            {
                g.FillEllipse(dot, 21f, 1f, 10f, 10f);
            }

            using (var ring = new Pen(Color.White, 1.6f))
            {
                g.DrawEllipse(ring, 21f, 1f, 10f, 10f);
            }
        }

        return FromBitmap(bmp);
    }

    private static Icon FromBitmap(Bitmap bmp)
    {
        var hIcon = bmp.GetHicon();
        try
        {
            // 用 Icon.FromHandle 的副本，避免句柄被 GDI 释放后失效
            using var tmp = Icon.FromHandle(hIcon);
            return (Icon)tmp.Clone();
        }
        finally
        {
            DestroyIcon(hIcon);
        }
    }

    private static GraphicsPath RoundedRect(Rectangle r, int radius)
        => RoundedRectF(new RectangleF(r.X, r.Y, r.Width, r.Height), radius);

    private static GraphicsPath RoundedRectF(RectangleF r, float radius)
    {
        var path = new GraphicsPath();
        var d = radius * 2f;
        path.AddArc(r.Left, r.Top, d, d, 180, 90);
        path.AddArc(r.Right - d, r.Top, d, d, 270, 90);
        path.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
        path.AddArc(r.Left, r.Bottom - d, d, d, 90, 90);
        path.CloseFigure();
        return path;
    }

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool DestroyIcon(IntPtr handle);
}
