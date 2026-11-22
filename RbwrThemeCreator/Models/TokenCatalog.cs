namespace RbwrThemeCreator.Models;

/// <summary>
/// Describes one brush resource token used by the RBWR overlay.
/// </summary>
/// <param name="Key">Resource key used in theme.axaml (x:Key).</param>
/// <param name="Group">UI group name.</param>
/// <param name="Label">Human-friendly name.</param>
/// <param name="Hint">Where the overlay uses this token.</param>
/// <param name="MirrorColorKey">Optional &lt;Color&gt; resource that mirrors this brush.</param>
/// <param name="SupportsOpacity">Whether the brush exposes a separate Opacity value in the editor.</param>
public sealed record TokenDefinition(
    string Key,
    string Group,
    string Label,
    string Hint,
    string? MirrorColorKey = null,
    bool SupportsOpacity = false)
{
    /// <summary>Whether a gradient makes sense for this token (backgrounds, borders, accents; not body text).</summary>
    public bool SupportsGradient => TokenCatalog.GradientKeys.Contains(Key);
}

public static class TokenCatalog
{
    public const string GroupSurfaces = "SURFACES";
    public const string GroupAccents = "ACCENTS";
    public const string GroupText = "TEXT";
    public const string GroupControls = "CONTROL STATES";
    public const string GroupTooltip = "TOOLTIPS";
    public const string GroupSlider = "SLIDERS";

    public static readonly IReadOnlyList<string> Groups =
    [
        GroupSurfaces, GroupAccents, GroupText, GroupControls, GroupTooltip, GroupSlider
    ];

    public static readonly IReadOnlyDictionary<string, string> GroupDescriptions = new Dictionary<string, string>
    {
        [GroupSurfaces] = "Window, card, header and panel backgrounds plus borders.",
        [GroupAccents] = "Neon accent colours. 'Primary accent' (NeonCyan) drives titles, active tabs and focus.",
        [GroupText] = "Main and secondary text colours.",
        [GroupControls] = "Button / tab / input backgrounds for hover, active, pressed and focus states.",
        [GroupTooltip] = "Hover tooltip background, border and body text.",
        [GroupSlider] = "Slider track, filled value and thumb colours (normal / hover / pressed).",
    };

    public static readonly IReadOnlyList<TokenDefinition> Tokens =
    [
        new("CyberMainBg", GroupSurfaces, "Main background", "Overlay window shell + compact pill", "CyberMainColor", true),
        new("CyberCardBg", GroupSurfaces, "Card background", "HUD cards, standard buttons, inputs", "CyberCardColor", true),
        new("CyberHeaderBg", GroupSurfaces, "Header background", "Header strips", "CyberHeaderColor", true),
        new("DarkPanelBg", GroupSurfaces, "Panel background", "Sub panels, footer, combo boxes, progress track", null, true),
        new("CyberBorder", GroupSurfaces, "Border", "Card and control borders", "CyberBorderColor", true),
        new("CyberBorderGlow", GroupSurfaces, "Shell border (glow)", "Outer border of the main overlay window", "CyberBorderGlowColor", true),

        new("NeonCyan", GroupAccents, "Primary accent", "Titles, active tabs/buttons, focus, progress bar", "NeonCyanColor"),
        new("NeonGreen", GroupAccents, "Success / OK", "Green buttons, healthy values", "NeonGreenColor"),
        new("NeonRed", GroupAccents, "Danger / alarm", "Close button hover, alarms", "NeonRedColor"),
        new("NeonGold", GroupAccents, "Warning / flow", "Gold buttons, flow values, DTL bar", "NeonGoldColor"),
        new("NeonPurple", GroupAccents, "Special", "Override badges, misc highlights", "NeonPurpleColor"),

        new("TextLight", GroupText, "Main text", "Default text colour", "TextLightColor"),
        new("TextMuted", GroupText, "Muted text", "Labels, captions, inactive tabs", "TextMutedColor"),

        new("ControlHoverBg", GroupControls, "Hover background", "Buttons and tabs under the mouse"),
        new("ControlActiveBg", GroupControls, "Active background", "Selected tab / unit / preset"),
        new("ControlPressedBg", GroupControls, "Pressed background", "Button while pressed"),
        new("TextBoxFocusBg", GroupControls, "Input focus background", "Text box while typing"),

        new("TooltipBg", GroupTooltip, "Tooltip background", "Hover tooltip fill (alpha supported)"),
        new("TooltipBorder", GroupTooltip, "Tooltip border", "Hover tooltip outline"),
        new("TooltipBodyBrush", GroupTooltip, "Tooltip body text", "Tooltip description text"),

        new("SliderTrackFill", GroupSlider, "Track", "Unfilled slider track"),
        new("SliderTrackFillPointerOver", GroupSlider, "Track (hover)", "Unfilled track under mouse"),
        new("SliderTrackFillPressed", GroupSlider, "Track (pressed)", "Unfilled track while dragging"),
        new("SliderTrackValueFill", GroupSlider, "Value fill", "Filled part of the slider"),
        new("SliderTrackValueFillPointerOver", GroupSlider, "Value fill (hover)", "Filled part under mouse"),
        new("SliderTrackValueFillPressed", GroupSlider, "Value fill (pressed)", "Filled part while dragging"),
        new("SliderThumbBackground", GroupSlider, "Thumb", "Slider knob"),
        new("SliderThumbBackgroundPointerOver", GroupSlider, "Thumb (hover)", "Knob under mouse"),
        new("SliderThumbBackgroundPressed", GroupSlider, "Thumb (pressed)", "Knob while dragging"),
    ];

    public static readonly IReadOnlyDictionary<string, TokenDefinition> ByKey =
        Tokens.ToDictionary(t => t.Key, StringComparer.Ordinal);

    public static readonly IReadOnlyDictionary<string, TokenDefinition> ByMirrorColorKey =
        Tokens.Where(t => t.MirrorColorKey != null).ToDictionary(t => t.MirrorColorKey!, StringComparer.Ordinal);

    /// <summary>
    /// Tokens that may be gradients. Text colours stay solid so labels remain readable,
    /// and slider states other than the filled value stay solid to keep the control crisp.
    /// </summary>
    public static readonly HashSet<string> GradientKeys = new(StringComparer.Ordinal)
    {
        "CyberMainBg", "CyberCardBg", "CyberHeaderBg", "DarkPanelBg", "CyberBorder", "CyberBorderGlow",
        "NeonCyan", "NeonGreen", "NeonRed", "NeonGold", "NeonPurple",
        "ControlHoverBg", "ControlActiveBg", "TooltipBg", "TooltipBorder", "SliderTrackValueFill",
    };

    public const string FontKey = "AppFontFamily";
    public const string MonoFontKey = "AppMonoFontFamily";

    /// <summary>Built-in overlay theme IDs that a custom theme may not use.</summary>
    public static readonly IReadOnlyList<string> ReservedIds = ["default", "reactor-amber", "aurora-drift"];
}
