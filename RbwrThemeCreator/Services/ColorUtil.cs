using System.Globalization;
using Avalonia.Media;

namespace RbwrThemeCreator.Services;

public static class ColorUtil
{
    /// <summary>#rrggbb for opaque colours, #aarrggbb otherwise (same convention as the overlay themes).</summary>
    public static string ToHex(Color c) => c.A == 0xFF
        ? $"#{c.R:x2}{c.G:x2}{c.B:x2}"
        : $"#{c.A:x2}{c.R:x2}{c.G:x2}{c.B:x2}";

    public static bool TryParse(string? text, out Color color)
    {
        color = default;
        if (string.IsNullOrWhiteSpace(text))
            return false;
        string t = text.Trim();
        if (!t.StartsWith('#'))
        {
            // allow bare hex like "00f0ff"
            if (t.All(Uri.IsHexDigit) && (t.Length is 3 or 4 or 6 or 8))
                t = "#" + t;
        }
        return Color.TryParse(t, out color);
    }

    /// <summary>
    /// Parses a number the user typed: accepts "30", "30%", "30,5", " 120° ". Returns false for anything else
    /// (and for NaN/infinity), so callers can simply ignore bad input.
    /// </summary>
    public static bool TryParseUserNumber(string? text, out double value)
    {
        value = 0;
        if (string.IsNullOrWhiteSpace(text)) return false;
        string t = text.Trim().TrimEnd('%', '°').Trim().Replace(',', '.');
        return double.TryParse(t, NumberStyles.Float, CultureInfo.InvariantCulture, out value) && double.IsFinite(value);
    }

    public static string FormatNumber(double value) =>
        Math.Round(value, 1).ToString("0.#", CultureInfo.InvariantCulture);

    public static double ParseDouble(string? text, double fallback) =>
        double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out var v) ? v : fallback;

    // ---------- HSL helpers ----------

    public static (double H, double S, double L) ToHsl(Color c)
    {
        double r = c.R / 255.0, g = c.G / 255.0, b = c.B / 255.0;
        double max = Math.Max(r, Math.Max(g, b)), min = Math.Min(r, Math.Min(g, b));
        double h = 0, s, l = (max + min) / 2;
        double d = max - min;
        if (d < 1e-9)
        {
            s = 0;
        }
        else
        {
            s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
            if (max == r) h = (g - b) / d + (g < b ? 6 : 0);
            else if (max == g) h = (b - r) / d + 2;
            else h = (r - g) / d + 4;
            h *= 60;
        }
        return (h, s, l);
    }

    public static Color FromHsl(double h, double s, double l, byte alpha = 0xFF)
    {
        h = ((h % 360) + 360) % 360;
        s = Math.Clamp(s, 0, 1);
        l = Math.Clamp(l, 0, 1);
        double c = (1 - Math.Abs(2 * l - 1)) * s;
        double x = c * (1 - Math.Abs(h / 60 % 2 - 1));
        double m = l - c / 2;
        (double r, double g, double b) = h switch
        {
            < 60 => (c, x, 0d),
            < 120 => (x, c, 0d),
            < 180 => (0d, c, x),
            < 240 => (0d, x, c),
            < 300 => (x, 0d, c),
            _ => (c, 0d, x)
        };
        return Color.FromArgb(alpha,
            (byte)Math.Round((r + m) * 255),
            (byte)Math.Round((g + m) * 255),
            (byte)Math.Round((b + m) * 255));
    }

    public static Color WithAlpha(Color c, byte alpha) => Color.FromArgb(alpha, c.R, c.G, c.B);

    public static Color Lighten(Color c, double amount)
    {
        var (h, s, l) = ToHsl(c);
        return FromHsl(h, s, l + amount, c.A);
    }

    /// <summary>WCAG relative-luminance contrast ratio (1..21).</summary>
    public static double Contrast(Color a, Color b)
    {
        static double Lum(Color c)
        {
            static double Ch(byte v)
            {
                double s = v / 255.0;
                return s <= 0.03928 ? s / 12.92 : Math.Pow((s + 0.055) / 1.055, 2.4);
            }
            return 0.2126 * Ch(c.R) + 0.7152 * Ch(c.G) + 0.0722 * Ch(c.B);
        }
        double la = Lum(a), lb = Lum(b);
        return (Math.Max(la, lb) + 0.05) / (Math.Min(la, lb) + 0.05);
    }
}
