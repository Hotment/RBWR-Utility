using Avalonia.Media;
using RbwrThemeCreator.Models;

namespace RbwrThemeCreator.Services;

/// <summary>
/// Derives a full, consistent token palette from a single accent colour.
/// </summary>
public static class PaletteGenerator
{
    public enum Mood
    {
        /// <summary>Near-black backgrounds tinted with the accent hue.</summary>
        Dark,
        /// <summary>Lighter, more saturated tinted backgrounds.</summary>
        Tinted,
        /// <summary>Neutral grey backgrounds; only accents carry colour.</summary>
        Neutral,
    }

    public static void Apply(ThemeState state, Color accent, Mood mood, bool keepStatusColours = true)
    {
        var (h, s, _) = ColorUtil.ToHsl(accent);
        double bgSat = mood switch { Mood.Dark => Math.Min(s, 0.5) * 0.8, Mood.Tinted => Math.Min(s, 0.6), _ => 0.06 };
        double lift = mood == Mood.Tinted ? 0.04 : 0;

        Color Bg(double l) => ColorUtil.FromHsl(h, bgSat, l + lift);

        void Set(string key, Color c, double? opacity = null)
        {
            double op = opacity ?? (state.Tokens.TryGetValue(key, out var old) ? old.Opacity : 1);
            state.Tokens[key] = new TokenValue(c, op);
        }

        var main = Bg(0.045);
        var card = Bg(0.085);
        var border = ColorUtil.FromHsl(h, Math.Min(bgSat + 0.1, 0.5), 0.2 + lift);
        var text = ColorUtil.FromHsl(h, Math.Min(s, 0.35), 0.96);
        var muted = ColorUtil.FromHsl(h, Math.Min(s, 0.18), 0.55);

        Set("CyberMainBg", main, 0.94);
        Set("CyberCardBg", card, 0.86);
        Set("CyberHeaderBg", Bg(0.03), 0.96);
        Set("DarkPanelBg", Bg(0.07), 0.92);
        Set("CyberBorder", border);
        Set("CyberBorderGlow", accent);

        Set("NeonCyan", accent);
        if (!keepStatusColours)
        {
            Set("NeonGreen", ColorUtil.FromHsl(130, 0.85, 0.55));
            Set("NeonRed", ColorUtil.FromHsl(350, 0.95, 0.58));
            Set("NeonGold", ColorUtil.FromHsl(42, 0.95, 0.55));
            Set("NeonPurple", ColorUtil.FromHsl(h + 150, 0.85, 0.65));
        }

        Set("TextLight", text);
        Set("TextMuted", muted);

        Set("ControlHoverBg", Bg(0.15));
        Set("ControlActiveBg", Bg(0.19));
        Set("ControlPressedBg", Bg(0.08));
        Set("TextBoxFocusBg", Bg(0.12));

        Set("TooltipBg", ColorUtil.WithAlpha(main, 0xF5));
        Set("TooltipBorder", ColorUtil.WithAlpha(accent, 0x99));
        Set("TooltipBodyBrush", ColorUtil.FromHsl(h, Math.Min(s, 0.3), 0.88));

        Set("SliderTrackFill", border);
        Set("SliderTrackFillPointerOver", ColorUtil.Lighten(border, 0.07));
        Set("SliderTrackFillPressed", ColorUtil.Lighten(border, 0.07));
        Set("SliderTrackValueFill", accent);
        Set("SliderTrackValueFillPointerOver", ColorUtil.Lighten(accent, 0.08));
        Set("SliderTrackValueFillPressed", ColorUtil.Lighten(accent, -0.1));
        Set("SliderThumbBackground", accent);
        Set("SliderThumbBackgroundPointerOver", ColorUtil.Lighten(accent, 0.15));
        Set("SliderThumbBackgroundPressed", ColorUtil.Lighten(accent, 0.28));
    }
}
