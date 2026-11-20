using Avalonia.Media;
using RbwrOverlay.Core.Models;

namespace RbwrThemeCreator.Models;

public sealed record TokenValue(Color Color, double Opacity = 1.0);

public sealed record ThemeFile(string FileName, string SourcePath);

public sealed class ShapeSettings
{
    public bool Enabled { get; set; }
    public double ShellCornerRadius { get; set; } = 8;
    public double ShellBorderThickness { get; set; } = 1;
    public double CardCornerRadius { get; set; } = 4;
    public double ButtonCornerRadius { get; set; } = 4;
    public double CompactCornerRadius { get; set; } = 18;
    public bool ShellGlow { get; set; }
    public double ShellGlowBlur { get; set; } = 14;

    public ShapeSettings Clone() => (ShapeSettings)MemberwiseClone();
}

public sealed class BackgroundImageSettings
{
    /// <summary>File name inside assets/ (e.g. bg.png).</summary>
    public string FileName { get; set; } = string.Empty;
    public double Opacity { get; set; } = 0.35;
    public string Stretch { get; set; } = "UniformToFill";

    public BackgroundImageSettings Clone() => (BackgroundImageSettings)MemberwiseClone();
}

/// <summary>
/// Complete, UI-independent description of a theme. The generator turns it into theme.axaml,
/// the importer rebuilds it from an existing theme folder.
/// </summary>
public sealed class ThemeState
{
    public ThemeManifest Manifest { get; set; } = new();
    public string FontFamily { get; set; } = "Consolas, 'Segoe UI', Inter, monospace";
    public string MonoFontFamily { get; set; } = "Consolas, monospace";
    public Dictionary<string, TokenValue> Tokens { get; set; } = new(StringComparer.Ordinal);
    public ShapeSettings Shape { get; set; } = new();
    public BackgroundImageSettings? BackgroundImage { get; set; }

    /// <summary>Font files that end up in fonts/.</summary>
    public List<ThemeFile> Fonts { get; set; } = new();

    /// <summary>Image files that end up in assets/.</summary>
    public List<ThemeFile> Assets { get; set; } = new();

    /// <summary>Raw XAML placed inside &lt;Styles.Resources&gt; (extra resources).</summary>
    public string CustomResources { get; set; } = string.Empty;

    /// <summary>Raw XAML &lt;Style&gt; elements appended after the generated sections.</summary>
    public string CustomStyles { get; set; } = string.Empty;

    /// <summary>Non-fatal notes produced while importing.</summary>
    public List<string> ImportWarnings { get; } = new();
}
