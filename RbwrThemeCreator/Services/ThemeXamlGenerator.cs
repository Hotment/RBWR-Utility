using System.Globalization;
using System.Security;
using System.Text;
using RbwrThemeCreator.Models;

namespace RbwrThemeCreator.Services;

/// <summary>
/// Turns a <see cref="ThemeState"/> into the theme.axaml format the overlay's ThemeService loads.
/// Generated sections are wrapped in "@creator:" marker comments so the importer can read them back.
/// </summary>
public static class ThemeXamlGenerator
{
    public const string ShapeBegin = "<!-- @creator:shape-begin -->";
    public const string ShapeEnd = "<!-- @creator:shape-end -->";
    public const string ResourcesBegin = "<!-- @creator:custom-resources-begin -->";
    public const string ResourcesEnd = "<!-- @creator:custom-resources-end -->";
    public const string CustomBegin = "<!-- @creator:custom-begin -->";
    public const string CustomEnd = "<!-- @creator:custom-end -->";

    private const string BackgroundToken = "CyberMainBg";

    public static string Generate(ThemeState state)
    {
        var sb = new StringBuilder();
        var m = state.Manifest;

        sb.AppendLine("<Styles xmlns=\"https://github.com/avaloniaui\"");
        sb.AppendLine("        xmlns:x=\"http://schemas.microsoft.com/winfx/2006/xaml\">");
        sb.AppendLine();
        sb.AppendLine("    <!--");
        sb.AppendLine($"      {CommentSafe(m.Name)} v{CommentSafe(m.Version)}{(string.IsNullOrWhiteSpace(m.Author) ? "" : " by " + CommentSafe(m.Author))}");
        sb.AppendLine("      Generated with RBWR Theme Creator. You can reopen this folder in the creator,");
        sb.AppendLine("      or edit by hand: keep the @creator markers so the creator can read your changes back.");
        sb.AppendLine("    -->");
        sb.AppendLine();

        // ---------- Resources ----------
        sb.AppendLine("    <Styles.Resources>");
        sb.AppendLine($"        <FontFamily x:Key=\"{TokenCatalog.FontKey}\">{Escape(state.FontFamily)}</FontFamily>");
        sb.AppendLine($"        <FontFamily x:Key=\"{TokenCatalog.MonoFontKey}\">{Escape(state.MonoFontFamily)}</FontFamily>");
        sb.AppendLine();

        foreach (var def in TokenCatalog.Tokens.Where(t => t.MirrorColorKey != null))
        {
            var value = GetToken(state, def.Key);
            sb.AppendLine($"        <Color x:Key=\"{def.MirrorColorKey}\">{ColorUtil.ToHex(value.Representative)}</Color>");
        }
        sb.AppendLine();

        string? currentGroup = null;
        foreach (var def in TokenCatalog.Tokens)
        {
            if (currentGroup != null && currentGroup != def.Group)
                sb.AppendLine();
            currentGroup = def.Group;

            var value = GetToken(state, def.Key);

            if (def.Key == BackgroundToken && state.BackgroundImage is { FileName.Length: > 0 } bg)
            {
                sb.AppendLine($"        <ImageBrush x:Key=\"{BackgroundToken}\" Source=\"assets/{Escape(bg.FileName)}\" Stretch=\"{bg.Stretch}\" Opacity=\"{Num(bg.Opacity)}\" />");
                continue;
            }

            double op = double.IsFinite(value.Opacity) ? Math.Clamp(value.Opacity, 0, 1) : 1;
            string opacity = op < 0.999 ? $" Opacity=\"{Num(op)}\"" : string.Empty;

            if (value.Gradient is { } g && def.SupportsGradient)
            {
                var (sx, sy, ex, ey) = g.Points();
                sb.AppendLine($"        <LinearGradientBrush x:Key=\"{def.Key}\" StartPoint=\"{Num(sx)}%,{Num(sy)}%\" EndPoint=\"{Num(ex)}%,{Num(ey)}%\"{opacity}>");
                sb.AppendLine($"            <GradientStop Offset=\"0\" Color=\"{ColorUtil.ToHex(value.Color)}\" />");
                if (g.Mid is { } mid)
                    sb.AppendLine($"            <GradientStop Offset=\"0.5\" Color=\"{ColorUtil.ToHex(mid)}\" />");
                sb.AppendLine($"            <GradientStop Offset=\"1\" Color=\"{ColorUtil.ToHex(g.End)}\" />");
                sb.AppendLine("        </LinearGradientBrush>");
                continue;
            }

            sb.AppendLine($"        <SolidColorBrush x:Key=\"{def.Key}\" Color=\"{ColorUtil.ToHex(value.Color)}\"{opacity} />");
        }

        sb.AppendLine();
        sb.AppendLine("        " + ResourcesBegin);
        if (!string.IsNullOrWhiteSpace(state.CustomResources))
            sb.AppendLine(Indent(state.CustomResources.Trim('\r', '\n'), 8));
        sb.AppendLine("        " + ResourcesEnd);
        sb.AppendLine("    </Styles.Resources>");
        sb.AppendLine();

        // ---------- Custom styles ----------
        sb.AppendLine("    " + CustomBegin);
        if (!string.IsNullOrWhiteSpace(state.CustomStyles))
            sb.AppendLine(Indent(state.CustomStyles.Trim('\r', '\n'), 4));
        sb.AppendLine("    " + CustomEnd);
        sb.AppendLine();
        // ---------- Shape (last, so the sliders win over custom styles when enabled) ----------
        sb.AppendLine("    " + ShapeBegin);
        if (state.Shape.Enabled)
        {
            var s = state.Shape;
            sb.AppendLine("    <Style Selector=\"Border.overlay-shell\">");
            sb.AppendLine($"        <Setter Property=\"CornerRadius\" Value=\"{Num(s.ShellCornerRadius)}\" />");
            sb.AppendLine($"        <Setter Property=\"BorderThickness\" Value=\"{Num(s.ShellBorderThickness)}\" />");
            if (s.ShellGlow)
            {
                var glow = GetToken(state, "CyberBorderGlow").Representative;
                var glowColor = Avalonia.Media.Color.FromArgb(0x88, glow.R, glow.G, glow.B);
                sb.AppendLine($"        <Setter Property=\"BoxShadow\" Value=\"0 0 {Num(s.ShellGlowBlur)} 0 {ColorUtil.ToHex(glowColor)}\" />");
            }
            sb.AppendLine("    </Style>");
            sb.AppendLine("    <Style Selector=\"Border.compact-shell\">");
            sb.AppendLine($"        <Setter Property=\"CornerRadius\" Value=\"{Num(s.CompactCornerRadius)}\" />");
            sb.AppendLine("    </Style>");
            sb.AppendLine("    <Style Selector=\"Border.hud-card, Border.hud-footer\">");
            sb.AppendLine($"        <Setter Property=\"CornerRadius\" Value=\"{Num(s.CardCornerRadius)}\" />");
            sb.AppendLine("    </Style>");
            sb.AppendLine("    <Style Selector=\"Button.cyber, Button.cyber-blue, Button.cyber-green, Button.cyber-gold, Button.cyber-red, TextBox.cyber, ComboBox.cyber\">");
            sb.AppendLine($"        <Setter Property=\"CornerRadius\" Value=\"{Num(s.ButtonCornerRadius)}\" />");
            sb.AppendLine("    </Style>");
        }
        sb.AppendLine("    " + ShapeEnd);
        sb.AppendLine();

        sb.AppendLine("</Styles>");
        return sb.ToString();
    }

    private static TokenValue GetToken(ThemeState state, string key) =>
        state.Tokens.TryGetValue(key, out var v) ? v : new TokenValue(Avalonia.Media.Colors.Magenta);

    private static string Num(double value) => Math.Round(value, 3).ToString(CultureInfo.InvariantCulture);

    private static string Escape(string? value) => SecurityElement.Escape(value ?? string.Empty) ?? string.Empty;

    private static string CommentSafe(string? value) => (value ?? string.Empty).Replace("--", "-").Replace("\r", " ").Replace("\n", " ");

    /// <summary>Re-indents a user snippet so its least-indented line sits at <paramref name="indent"/> spaces.</summary>
    private static string Indent(string text, int indent)
    {
        var lines = text.Replace("\r\n", "\n").Split('\n');
        int common = lines.Where(l => l.Trim().Length > 0)
            .Select(l => l.Length - l.TrimStart(' ').Length)
            .DefaultIfEmpty(0)
            .Min();
        string pad = new(' ', indent);
        return string.Join(Environment.NewLine, lines.Select(l =>
            l.Trim().Length == 0 ? string.Empty : pad + (l.Length >= common ? l[common..] : l.TrimStart())));
    }
}
