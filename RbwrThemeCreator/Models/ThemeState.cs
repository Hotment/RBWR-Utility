using Avalonia.Media;
using RbwrOverlay.Core.Models;

namespace RbwrThemeCreator.Models;

/// <summary>
/// Value of a brush token. <see cref="Color"/> is the solid colour, or the first stop of the gradient.
/// </summary>
public sealed record TokenValue(Color Color, double Opacity = 1.0, GradientSpec? Gradient = null)
{
    /// <summary>Single representative colour (used for &lt;Color&gt; mirrors, glow and contrast).</summary>
    public Color Representative => Gradient == null ? Color : GradientSpec.Average(Color, Gradient);
}

/// <summary>
/// Linear gradient. The token's own colour is the first stop; <see cref="Colors"/> are the following
/// stops (1..<see cref="MaxExtraStops"/>), spread evenly along the gradient.
/// <see cref="Angle"/> is in degrees: 0 = left to right, 90 = top to bottom.
/// </summary>
public sealed record GradientSpec(IReadOnlyList<Color> Colors, double Angle, IReadOnlyList<double>? Offsets = null)
{
    /// <summary>Total stops allowed (start + extras). More than this rarely looks good and bloats the theme.</summary>
    public const int MaxStops = 6;
    public const int MaxExtraStops = MaxStops - 1;

    /// <summary>Angle normalised to [0, 360); NaN/infinity become 90 (top to bottom).</summary>
    public double SafeAngle => double.IsFinite(Angle) ? ((Angle % 360) + 360) % 360 : 90;

    /// <summary>The extra stops clamped to a valid count (at least one, at most <see cref="MaxExtraStops"/>).</summary>
    public IReadOnlyList<Color> SafeColors(Color start) =>
        Colors is { Count: > 0 } ? Colors.Take(MaxExtraStops).ToList() : [start];

    /// <summary>Start/end points in percent (0..100) of the element box for the angle.</summary>
    public (double Sx, double Sy, double Ex, double Ey) Points()
    {
        double rad = SafeAngle * Math.PI / 180;
        double dx = Math.Cos(rad), dy = Math.Sin(rad);
        static double R(double v) => Math.Round(Math.Clamp(v, 0, 100), 1);
        return (R(50 - 50 * dx), R(50 - 50 * dy), R(50 + 50 * dx), R(50 + 50 * dy));
    }

    /// <summary>
    /// All stops including the start colour. Uses <see cref="Offsets"/> (0..1, one per stop including the start)
    /// when present and valid, otherwise spreads the colours evenly. Offsets are always clamped to 0..1 and
    /// forced into ascending order, so a bad value can never produce an invalid brush.
    /// </summary>
    public IReadOnlyList<(double Offset, Color Color)> Stops(Color start)
    {
        var all = new List<Color> { start };
        all.AddRange(SafeColors(start));
        var offsets = SafeOffsets(all.Count) ?? EvenOffsets(all.Count);
        return all.Select((c, i) => (offsets[i], c)).ToList();
    }

    public static double[] EvenOffsets(int count) =>
        Enumerable.Range(0, count).Select(i => count <= 1 ? 0 : (double)i / (count - 1)).ToArray();

    /// <summary>Sanitised custom offsets, or null when there are none / they do not match the stop count.</summary>
    private double[]? SafeOffsets(int count)
    {
        if (Offsets == null || Offsets.Count != count)
            return null;
        var result = new double[count];
        double floor = 0;
        for (int i = 0; i < count; i++)
        {
            double v = double.IsFinite(Offsets[i]) ? Math.Clamp(Offsets[i], 0, 1) : (count <= 1 ? 0 : (double)i / (count - 1));
            v = Math.Max(v, floor); // keep ascending
            result[i] = Math.Round(v, 3);
            floor = result[i];
        }
        return result;
    }

    /// <summary>True when the offsets are just the default even spread (so nothing custom needs saving).</summary>
    public static bool IsEven(IReadOnlyList<double> offsets)
    {
        var even = EvenOffsets(offsets.Count);
        return offsets.Select((o, i) => Math.Abs(o - even[i]) < 0.0015).All(x => x);
    }

    public static Color Average(Color start, GradientSpec g)
    {
        var cs = g.Stops(start).Select(s => s.Color).ToList();
        return Color.FromArgb(
            (byte)cs.Average(c => c.A), (byte)cs.Average(c => c.R),
            (byte)cs.Average(c => c.G), (byte)cs.Average(c => c.B));
    }
}

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
