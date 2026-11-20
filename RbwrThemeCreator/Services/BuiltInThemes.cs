using System.Reflection;
using System.Text.RegularExpressions;
using Avalonia.Markup.Xaml;
using Avalonia.Media;
using Avalonia.Styling;
using RbwrOverlay.Core.Models;
using RbwrThemeCreator.Models;

namespace RbwrThemeCreator.Services;

public sealed record ThemePreset(string Name, string Description, Func<ThemeState> Create);

/// <summary>
/// Access to the overlay's real built-in themes (embedded from RbwrOverlay.UI/Styles at build time)
/// and the starter presets offered by "New theme".
/// </summary>
public static class BuiltInThemes
{
    private static string? _cyberpunkXaml;
    private static string? _amberXaml;
    private static ThemeState? _cyberpunkState;

    private static readonly Regex BehaviorsXmlnsRegex = new(@"\s+xmlns:behaviors=""[^""]*""", RegexOptions.Compiled);
    private static readonly Regex BehaviorsSetterRegex = new(@"^\s*<Setter[^>]*behaviors:[^>]*/>\s*$", RegexOptions.Compiled | RegexOptions.Multiline);

    public static string CyberpunkXaml => _cyberpunkXaml ??= ReadResource("Base.CyberpunkTheme.axaml");
    public static string ReactorAmberXaml => _amberXaml ??= ReadResource("Base.ReactorAmberTheme.axaml");

    /// <summary>The overlay's default theme as editable state (used as fallback for missing tokens).</summary>
    public static ThemeState Cyberpunk => _cyberpunkState ??= ThemeImporter.FromXaml(
        CyberpunkXaml,
        new ThemeManifest { Id = "default", Name = "Cyberpunk", Author = "Hotment" },
        HardFallback(),
        includeStyles: false);

    /// <summary>
    /// Loads the overlay's base Cyberpunk stylesheet for the preview. Overlay-only behavior setters are stripped,
    /// they do not affect visuals.
    /// </summary>
    public static Styles LoadPreviewBaseStyles()
    {
        string xaml = BehaviorsXmlnsRegex.Replace(CyberpunkXaml, string.Empty);
        xaml = BehaviorsSetterRegex.Replace(xaml, string.Empty);
        return AvaloniaRuntimeXamlLoader.Parse<Styles>(xaml);
    }

    public static IReadOnlyList<ThemePreset> Presets { get; } =
    [
        new("Cyberpunk", "The overlay's default neon cyan theme.", () => Fresh(Cyberpunk, "my-cyberpunk", "My Cyberpunk Theme", includeCustom: false)),
        new("Reactor Amber", "Warm amber CRT instrumentation look.", () => Fresh(ThemeImporter.FromXaml(
            ReactorAmberXaml, new ThemeManifest(), Cyberpunk, includeStyles: true), "my-amber", "My Amber Theme", includeCustom: true)),
        new("Arctic Slate", "Calm blue/slate palette (the overlay's template).", () => Fresh(ArcticSlate(), "my-arctic", "My Arctic Theme", includeCustom: false)),
        new("Synthwave (gradients)", "Purple-to-navy gradients with pink/cyan neon edges.", Synthwave),
        new("Blank (from accent)", "Pick one accent colour and the creator derives the rest.", () =>
        {
            var s = Fresh(Cyberpunk, "my-theme", "My Theme", includeCustom: false);
            PaletteGenerator.Apply(s, Color.Parse("#ff4fd8"), PaletteGenerator.Mood.Dark);
            return s;
        }),
    ];

    private static ThemeState Fresh(ThemeState source, string id, string name, bool includeCustom)
    {
        var s = new ThemeState
        {
            Manifest = new ThemeManifest
            {
                Id = id,
                Name = name,
                Author = CreatorSettings.Current.LastAuthor,
                Version = "1.0.0",
                Description = string.Empty,
                Entry = "theme.axaml",
                MinAppVersion = "2.3.0",
            },
            FontFamily = source.FontFamily,
            MonoFontFamily = source.MonoFontFamily,
            Tokens = new Dictionary<string, TokenValue>(source.Tokens, StringComparer.Ordinal),
            Shape = source.Shape.Clone(),
            CustomStyles = includeCustom ? source.CustomStyles : string.Empty,
            CustomResources = includeCustom ? source.CustomResources : string.Empty,
        };
        return s;
    }

    private static ThemeState Synthwave()
    {
        var s = Fresh(Cyberpunk, "my-synthwave", "My Synthwave Theme", includeCustom: false);
        Color C(string hex) => Color.Parse(hex);
        void Set(string key, string start, string end, double angle, double opacity = 1, string? mid = null) =>
            s.Tokens[key] = new TokenValue(C(start), opacity, new GradientSpec(C(end), mid == null ? null : C(mid), angle));
        void Solid(string key, string hex, double opacity = 1) => s.Tokens[key] = new TokenValue(C(hex), opacity);

        Set("CyberMainBg", "#1a0b2e", "#08122b", 120, 0.95);
        Set("CyberCardBg", "#22113d", "#0f1838", 135, 0.86);
        Solid("CyberHeaderBg", "#120822", 0.96);
        Set("DarkPanelBg", "#180c2c", "#0c1430", 90, 0.92);
        Set("CyberBorder", "#4b2a78", "#1f3a6e", 0);
        Set("CyberBorderGlow", "#ff4fd8", "#00e5ff", 45, 1, "#a64dff");

        Set("NeonCyan", "#00e5ff", "#7a9cff", 0);
        Solid("NeonGreen", "#4dffb8");
        Solid("NeonRed", "#ff3b6b");
        Solid("NeonGold", "#ffb86b");
        Set("NeonPurple", "#ff4fd8", "#a64dff", 0);
        Solid("TextLight", "#f6efff");
        Solid("TextMuted", "#9a8fbf");

        Solid("ControlHoverBg", "#2c1650");
        Set("ControlActiveBg", "#3a1a66", "#1c2f66", 0);
        Solid("ControlPressedBg", "#1a0d30");
        Solid("TextBoxFocusBg", "#24123f");

        Set("TooltipBg", "#f51a0b2e", "#f508122b", 90);
        Set("TooltipBorder", "#99ff4fd8", "#9900e5ff", 0);
        Solid("TooltipBodyBrush", "#e8ddff");

        Solid("SliderTrackFill", "#3a2560");
        Solid("SliderTrackFillPointerOver", "#4a3075");
        Solid("SliderTrackFillPressed", "#4a3075");
        Set("SliderTrackValueFill", "#ff4fd8", "#00e5ff", 0);
        Solid("SliderTrackValueFillPointerOver", "#ff7ae2");
        Solid("SliderTrackValueFillPressed", "#d93cb8");
        Solid("SliderThumbBackground", "#ff4fd8");
        Solid("SliderThumbBackgroundPointerOver", "#ff8fe6");
        Solid("SliderThumbBackgroundPressed", "#ffc2f2");

        s.Shape = new ShapeSettings { Enabled = true, ShellCornerRadius = 12, CardCornerRadius = 8, ButtonCornerRadius = 6, CompactCornerRadius = 18, ShellGlow = true, ShellGlowBlur = 18 };
        return s;
    }

    private static ThemeState ArcticSlate()
    {
        var s = new ThemeState
        {
            FontFamily = Cyberpunk.FontFamily,
            MonoFontFamily = Cyberpunk.MonoFontFamily,
            Tokens = new Dictionary<string, TokenValue>(StringComparer.Ordinal)
            {
                ["CyberMainBg"] = new(Color.Parse("#0b111a"), 0.95),
                ["CyberCardBg"] = new(Color.Parse("#131d2b"), 0.88),
                ["CyberHeaderBg"] = new(Color.Parse("#070b12"), 0.97),
                ["DarkPanelBg"] = new(Color.Parse("#0e1622"), 0.92),
                ["CyberBorder"] = new(Color.Parse("#2a3b52")),
                ["CyberBorderGlow"] = new(Color.Parse("#60a5fa")),
                ["NeonCyan"] = new(Color.Parse("#60a5fa")),
                ["NeonGreen"] = new(Color.Parse("#4ade80")),
                ["NeonRed"] = new(Color.Parse("#f87171")),
                ["NeonGold"] = new(Color.Parse("#facc15")),
                ["NeonPurple"] = new(Color.Parse("#a78bfa")),
                ["TextLight"] = new(Color.Parse("#f1f5f9")),
                ["TextMuted"] = new(Color.Parse("#94a3b8")),
                ["TooltipBg"] = new(Color.Parse("#f50b111a")),
                ["TooltipBorder"] = new(Color.Parse("#9960a5fa")),
                ["TooltipBodyBrush"] = new(Color.Parse("#e2e8f0")),
                ["ControlHoverBg"] = new(Color.Parse("#1b293d")),
                ["ControlActiveBg"] = new(Color.Parse("#233754")),
                ["ControlPressedBg"] = new(Color.Parse("#111b29")),
                ["TextBoxFocusBg"] = new(Color.Parse("#162336")),
                ["SliderTrackFill"] = new(Color.Parse("#2a3b52")),
                ["SliderTrackFillPointerOver"] = new(Color.Parse("#374d6b")),
                ["SliderTrackFillPressed"] = new(Color.Parse("#374d6b")),
                ["SliderTrackValueFill"] = new(Color.Parse("#60a5fa")),
                ["SliderTrackValueFillPointerOver"] = new(Color.Parse("#7ab6fc")),
                ["SliderTrackValueFillPressed"] = new(Color.Parse("#3b82f6")),
                ["SliderThumbBackground"] = new(Color.Parse("#60a5fa")),
                ["SliderThumbBackgroundPointerOver"] = new(Color.Parse("#93c5fd")),
                ["SliderThumbBackgroundPressed"] = new(Color.Parse("#bfdbfe")),
            },
            Shape = new ShapeSettings { Enabled = true, ShellCornerRadius = 10, CardCornerRadius = 6, CompactCornerRadius = 14 },
        };
        return s;
    }

    /// <summary>Last-resort values if the embedded theme could not be read.</summary>
    private static ThemeState HardFallback()
    {
        var s = new ThemeState();
        foreach (var def in TokenCatalog.Tokens)
            s.Tokens[def.Key] = new TokenValue(Colors.Gray);
        return s;
    }

    private static string ReadResource(string name)
    {
        using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream(name)
            ?? throw new InvalidOperationException($"Embedded resource '{name}' not found.");
        using var reader = new StreamReader(stream);
        return reader.ReadToEnd();
    }
}
