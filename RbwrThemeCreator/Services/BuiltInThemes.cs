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
