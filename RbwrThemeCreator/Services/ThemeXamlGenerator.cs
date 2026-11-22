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
    public const string AprmBoxBegin = "<!-- @creator:aprm-box-begin -->";
    public const string AprmBoxEnd = "<!-- @creator:aprm-box-end -->";
    public const string AprmBoxBorderKey = "PowerBannerBorder";
    public const string AprmBoxTextKey = "PowerBannerText";
    public const string ResourcesBegin = "<!-- @creator:custom-resources-begin -->";
    public const string ResourcesEnd = "<!-- @creator:custom-resources-end -->";
    public const string CustomBegin = "<!-- @creator:custom-begin -->";
    public const string CustomEnd = "<!-- @creator:custom-end -->";
    public const string TokenAnimationsBegin = "<!-- @creator:token-animations-begin -->";
    public const string TokenAnimationsEnd = "<!-- @creator:token-animations-end -->";
    /// <summary>Prefix of the comment that stores the animated tokens as JSON (read back by the importer).</summary>
    public const string TokenAnimationsPrefix = "@creator:token-animations ";
    /// <summary>
    /// Section of an earlier development build ("Animated colours" card). No longer written; the importer
    /// still removes it so such themes open cleanly.
    /// </summary>
    public const string AnimationBegin = "<!-- @creator:animation-begin -->";
    public const string AnimationEnd = "<!-- @creator:animation-end -->";

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
                foreach (var (offset, color) in g.Stops(value.Color))
                    sb.AppendLine($"            <GradientStop Offset=\"{Num(offset)}\" Color=\"{ColorUtil.ToHex(color)}\" />");
                sb.AppendLine("        </LinearGradientBrush>");
                continue;
            }

            sb.AppendLine($"        <SolidColorBrush x:Key=\"{def.Key}\" Color=\"{ColorUtil.ToHex(value.Color)}\"{opacity} />");
        }

        if (state.AprmBox.Enabled)
        {
            sb.AppendLine();
            sb.AppendLine($"        <SolidColorBrush x:Key=\"{AprmBoxBorderKey}\" Color=\"{ColorUtil.ToHex(state.AprmBox.BorderColor)}\" />");
            sb.AppendLine($"        <SolidColorBrush x:Key=\"{AprmBoxTextKey}\" Color=\"{ColorUtil.ToHex(state.AprmBox.TextColor)}\" />");
        }

        sb.AppendLine();
        sb.AppendLine("        " + ResourcesBegin);
        if (!string.IsNullOrWhiteSpace(state.CustomResources))
            sb.AppendLine(Indent(state.CustomResources.Trim('\r', '\n'), 8));
        sb.AppendLine("        " + ResourcesEnd);
        sb.AppendLine("    </Styles.Resources>");
        sb.AppendLine();

        // ---------- APRM power box independent override ----------
        sb.AppendLine("    " + AprmBoxBegin);
        if (state.AprmBox.Enabled)
        {
            sb.AppendLine("    <Style Selector=\"Border#PowerBanner\">");
            sb.AppendLine($"        <Setter Property=\"BorderBrush\" Value=\"{{DynamicResource {AprmBoxBorderKey}}}\" />");
            sb.AppendLine("    </Style>");
            sb.AppendLine("    <Style Selector=\"TextBlock#MainPowerReadout\">");
            sb.AppendLine($"        <Setter Property=\"Foreground\" Value=\"{{DynamicResource {AprmBoxTextKey}}}\" />");
            sb.AppendLine("    </Style>");
        }
        sb.AppendLine("    " + AprmBoxEnd);
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

        // ---------- Animated colour tokens (ANIMATE on a colour row) ----------
        sb.AppendLine("    " + TokenAnimationsBegin);
        AppendTokenAnimations(sb, state);
        sb.AppendLine("    " + TokenAnimationsEnd);
        sb.AppendLine();

        sb.AppendLine("</Styles>");
        return sb.ToString();
    }

    /// <summary>JSON stored in the theme for one animated token.</summary>
    public sealed record TokenAnimationJson(string[] Colors, bool Flow, double Seconds, double Angle = 0);

    private static void AppendTokenAnimations(StringBuilder sb, ThemeState state)
    {
        var animated = TokenCatalog.Tokens
            .Where(d => d.SupportsGradient && state.Tokens.TryGetValue(d.Key, out var v) && v.Animation is { Colors.Count: >= 2 })
            .Select(d => (d.Key, Value: state.Tokens[d.Key], Anim: state.Tokens[d.Key].Animation!))
            .ToList();
        if (animated.Count == 0) return;

        var json = animated.ToDictionary(t => t.Key, t => new TokenAnimationJson(
            t.Anim.Colors.Take(TokenAnimation.MaxColors).Select(ColorUtil.ToHex).ToArray(), t.Anim.Flow, Math.Clamp(t.Anim.Seconds, 1, 60), t.Anim.Angle));
        sb.AppendLine($"    <!-- {TokenAnimationsPrefix}{CommentSafe(System.Text.Json.JsonSerializer.Serialize(json))} -->");

        foreach (var (key, value, anim) in animated)
        {
            var usages = TokenUsages.For(key);
            if (usages.Count == 0) continue;
            string duration = TimeSpan.FromSeconds(Math.Clamp(anim.Seconds, 1, 60)).ToString("c", CultureInfo.InvariantCulture);
            var frames = TokenFrames(value, anim);

            sb.AppendLine($"    <!-- {CommentSafe(key)} -->");
            foreach (var group in usages.GroupBy(u => u.Selector))
            {
                string selector = SkipThemeCards(group.Key);
                if (state.AprmBox.Enabled
                    && string.Equals(key, "CyberBorder", StringComparison.Ordinal)
                    && string.Equals(group.Key, "Border.hud-card", StringComparison.Ordinal))
                {
                    selector += ":not(.power-banner)";
                }
                sb.AppendLine($"    <Style Selector=\"{Escape(selector)}\">");
                // Base value of the same kind as the frames (solid or gradient): older overlays without
                // the safe brush animator would otherwise crash when a solid colour animates into a gradient.
                foreach (var usage in group)
                    AppendSetter(sb, "        ", usage.Property, frames[0]);
                sb.AppendLine("        <Style.Animations>");
                sb.AppendLine($"            <Animation Duration=\"{duration}\" IterationCount=\"Infinite\">");
                for (int i = 0; i < frames.Count; i++)
                {
                    double cue = 100.0 * i / (frames.Count - 1);
                    sb.AppendLine($"                <KeyFrame Cue=\"{Num(cue)}%\">");
                    foreach (var usage in group)
                        AppendSetter(sb, "                    ", usage.Property, frames[i]);
                    sb.AppendLine("                </KeyFrame>");
                }
                sb.AppendLine("            </Animation>");
                sb.AppendLine("        </Style.Animations>");
                sb.AppendLine("    </Style>");
            }
        }
    }

    /// <summary>Class the overlay puts on the Theme Manager's theme cards (and the buttons on them).</summary>
    public const string ThemeCardClass = "theme-card";

    /// <summary>
    /// Adds :not(.theme-card) to every part of a selector, so the active theme's animations leave the
    /// Theme Manager's cards alone (each card shows its own theme). For "/template/" selectors the
    /// check goes on the control before "/template/".
    /// </summary>
    public static string SkipThemeCards(string selector)
    {
        string not = $":not(.{ThemeCardClass})";
        return string.Join(", ", selector.Split(',').Select(part =>
        {
            string p = part.Trim();
            int t = p.IndexOf(" /template/", StringComparison.Ordinal);
            return t >= 0 ? p[..t] + not + p[t..] : p + not;
        }));
    }

    /// <summary>A setter whose value is a colour ("#rrggbb") or a brush element ("&lt;LinearGradientBrush …").</summary>
    private static void AppendSetter(StringBuilder sb, string indent, string property, string value)
    {
        if (value.StartsWith('<'))
        {
            sb.AppendLine($"{indent}<Setter Property=\"{property}\">");
            sb.AppendLine($"{indent}    {value}");
            sb.AppendLine($"{indent}</Setter>");
        }
        else
        {
            sb.AppendLine($"{indent}<Setter Property=\"{property}\" Value=\"{value}\" />");
        }
    }

    /// <summary>
    /// Key frames of one animated token. All at once: solid colours and back to the first. Flow: the same
    /// gradient with its colours shifted one place per frame, so they travel along it and loop seamlessly.
    /// </summary>
    public static IReadOnlyList<string> TokenFrames(TokenValue value, TokenAnimation anim)
    {
        var colours = anim.Colors.Take(TokenAnimation.MaxColors).ToList();
        double opacity = Math.Clamp(value.Opacity, 0, 1);
        var frames = new List<string>();
        if (!anim.Flow)
        {
            foreach (var c in colours.Append(colours[0]))
                frames.Add(ColorUtil.ToHex(Avalonia.Media.Color.FromArgb((byte)Math.Round(c.A * opacity), c.R, c.G, c.B)));
            return frames;
        }

        double angle = anim.Angle;
        var (sx, sy, ex, ey) = new GradientSpec([colours[0]], angle).Points();
        string opacityAttr = opacity < 0.999 ? $" Opacity=\"{Num(opacity)}\"" : string.Empty;
        int n = colours.Count;
        for (int shift = 0; shift <= n; shift++)
        {
            var rb = new StringBuilder();
            rb.Append($"<LinearGradientBrush StartPoint=\"{Num(sx)}%,{Num(sy)}%\" EndPoint=\"{Num(ex)}%,{Num(ey)}%\"{opacityAttr}>");
            for (int k = 0; k <= n; k++) // n + 1 stops: the last repeats the first so the loop has no seam
            {
                var c = colours[(k + shift) % n];
                rb.Append($"<GradientStop Offset=\"{Num((double)k / n)}\" Color=\"{ColorUtil.ToHex(c)}\" />");
            }
            rb.Append("</LinearGradientBrush>");
            frames.Add(rb.ToString());
        }
        return frames;
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
