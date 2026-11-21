namespace RbwrThemeCreator.Views;

/// <summary>
/// Where each colour token is most visible in the live preview: which preview view to show
/// and which named mock elements (see OverlayPreview.axaml) to highlight.
/// </summary>
public static class TokenLocations
{
    private const int Monitor = OverlayPreview.ModeMonitor;
    private const int Config = OverlayPreview.ModeConfig;
    private const int Compact = OverlayPreview.ModeCompact;

    private static readonly string[] MetricCards = ["DemandInputCard", "CorePowerCard", "GenLoadCard", "FlowCard"];
    private static readonly string[] Slider = ["DemandPresetSlider"];

    private static readonly Dictionary<string, (int Mode, string[] Names)> Map = new(StringComparer.Ordinal)
    {
        ["CyberMainBg"] = (Monitor, ["DetailedShell"]),
        ["CyberCardBg"] = (Monitor, [.. MetricCards, "DemandPresetCard", "NavBar"]),
        ["CyberHeaderBg"] = (Monitor, ["HeaderBar"]),
        ["DarkPanelBg"] = (Monitor, ["StatusFooterBar", "SyncBadge", "MainPowerBar"]),
        ["CyberBorder"] = (Monitor, [.. MetricCards, "NavBar", "DemandPresetCard"]),
        ["CyberBorderGlow"] = (Monitor, ["DetailedShell"]),

        ["NeonCyan"] = (Monitor, ["OverlayTitle", "NavMonitorTab", "Unit1Button", "GenLoadValue"]),
        ["NeonGreen"] = (Monitor, ["SyncBadge", "PowerBanner"]),
        ["NeonRed"] = (Config, ["ResetButton"]),
        ["NeonGold"] = (Monitor, ["FlowValue", "DtlText"]),
        ["NeonPurple"] = (Config, ["SpecialText"]),

        ["TextLight"] = (Config, ["MainTextSample", "ThemeCombo"]),
        ["TextMuted"] = (Monitor, ["NavBar", "MainPowerSubtext", "StatusFooterBar"]),

        ["ControlHoverBg"] = (Monitor, ["UnitButtons"]),
        ["ControlActiveBg"] = (Monitor, ["NavMonitorTab", "Unit1Button"]),
        ["ControlPressedBg"] = (Monitor, ["UnitButtons"]),
        ["TextBoxFocusBg"] = (Monitor, ["DemandTextBox"]),

        ["TooltipBg"] = (Compact, ["TooltipSample"]),
        ["TooltipBorder"] = (Compact, ["TooltipSample"]),
        ["TooltipBodyBrush"] = (Compact, ["TooltipSample"]),

        ["SliderTrackFill"] = (Monitor, Slider),
        ["SliderTrackFillPointerOver"] = (Monitor, Slider),
        ["SliderTrackFillPressed"] = (Monitor, Slider),
        ["SliderTrackValueFill"] = (Monitor, Slider),
        ["SliderTrackValueFillPointerOver"] = (Monitor, Slider),
        ["SliderTrackValueFillPressed"] = (Monitor, Slider),
        ["SliderThumbBackground"] = (Monitor, Slider),
        ["SliderThumbBackgroundPointerOver"] = (Monitor, Slider),
        ["SliderThumbBackgroundPressed"] = (Monitor, Slider),
    };

    /// <summary>Reverse map: preview element name -> tokens that colour it (catalogue order).</summary>
    private static readonly Dictionary<string, string[]> ByElement = Map
        .SelectMany(kv => kv.Value.Names.Select(name => (Name: name, Key: kv.Key)))
        .GroupBy(x => x.Name, StringComparer.Ordinal)
        .ToDictionary(g => g.Key, g => g.Select(x => x.Key).Distinct().ToArray(), StringComparer.Ordinal);

    /// <summary>Slider tokens, used when the user clicks any slider in the preview.</summary>
    public static readonly string[] SliderTokens = Map.Keys.Where(k => k.StartsWith("Slider", StringComparison.Ordinal)).ToArray();

    /// <summary>Tokens that colour the named preview element (used by "click an element to find its colour").</summary>
    public static bool TryGetTokensForElement(string? elementName, out string[] keys)
    {
        if (!string.IsNullOrEmpty(elementName) && ByElement.TryGetValue(elementName, out var found))
        {
            keys = found;
            return true;
        }
        keys = [];
        return false;
    }

    public static bool TryGet(string key, out int mode, out string[] names)
    {
        if (Map.TryGetValue(key, out var entry))
        {
            mode = entry.Mode;
            names = entry.Names;
            return true;
        }
        mode = Monitor;
        names = [];
        return false;
    }
}
