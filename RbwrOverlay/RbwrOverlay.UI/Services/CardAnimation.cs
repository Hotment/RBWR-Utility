using Avalonia;
using Avalonia.Media;

namespace RbwrOverlay.UI.Services;

/// <summary>
/// One animated colour of a theme, as the Theme Creator saves it: 2–4 colours, all at once or
/// flowing along (in the direction <see cref="Angle"/>), one loop every <see cref="Seconds"/>.
/// Used to animate a theme's card in the Theme Manager the same way the theme animates the overlay.
/// </summary>
public sealed record CardAnimation(IReadOnlyList<Color> Colors, bool Flow, double Seconds, double Angle)
{
    /// <summary>Key frame brushes: solid colours and back to the first, or a gradient whose colours move one place per frame.</summary>
    public IReadOnlyList<IBrush> Frames()
    {
        var colours = Colors.Take(4).ToList();
        var frames = new List<IBrush>();
        if (!Flow)
        {
            foreach (var c in colours.Append(colours[0]))
                frames.Add(new SolidColorBrush(c));
            return frames;
        }

        double rad = (double.IsFinite(Angle) ? Angle : 0) * Math.PI / 180;
        double dx = Math.Cos(rad), dy = Math.Sin(rad);
        var start = new RelativePoint(0.5 - 0.5 * dx, 0.5 - 0.5 * dy, RelativeUnit.Relative);
        var end = new RelativePoint(0.5 + 0.5 * dx, 0.5 + 0.5 * dy, RelativeUnit.Relative);
        int n = colours.Count;
        for (int shift = 0; shift <= n; shift++)
        {
            var brush = new LinearGradientBrush { StartPoint = start, EndPoint = end };
            for (int k = 0; k <= n; k++)
                brush.GradientStops.Add(new GradientStop(colours[(k + shift) % n], (double)k / n));
            frames.Add(brush);
        }
        return frames;
    }
}
