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
