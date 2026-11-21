using Avalonia;
using Avalonia.Animation;
using Avalonia.Animation.Animators;
using Avalonia.Media;

namespace RbwrThemeCreator.Services;

/// <summary>
/// Brush animator for themes with animated colours. Avalonia's own brush animator crashes
/// (InvalidCastException) when a solid colour animates into a gradient or the other way round, for
/// example a theme that animates a colour on an element whose normal colour is a gradient. This one
/// blends any combination: solid ↔ solid, gradient ↔ gradient (any number of stops), solid ↔ gradient.
/// Registered once at start-up (<see cref="Register"/>).
/// Copy of RbwrOverlay.UI/Services/SafeBrushAnimator.cs (the overlay uses the same one); keep the two the same.
/// </summary>
public sealed class SafeBrushAnimator : InterpolatingAnimator<IBrush>
{
    private static bool _registered;

    public static void Register()
    {
        if (_registered) return;
        _registered = true;
        Animation.RegisterCustomAnimator<IBrush, SafeBrushAnimator>();
    }

    public override IBrush Interpolate(double progress, IBrush oldValue, IBrush newValue)
    {
        double p = Math.Clamp(progress, 0, 1);
        var from = oldValue ?? Brushes.Transparent;
        var to = newValue ?? Brushes.Transparent;

        if (from is ISolidColorBrush a && to is ISolidColorBrush b)
            return new SolidColorBrush(Lerp(a.Color, b.Color, p), Lerp(a.Opacity, b.Opacity, p));

        // Anything else that is not a colour or a gradient (e.g. an image) just switches halfway.
        if (!IsColourBrush(from) || !IsColourBrush(to))
            return p < 0.5 ? from : to;

        // Solid ↔ gradient or gradient ↔ gradient: blend two gradients with the same number of stops.
        var shape = (to as ILinearGradientBrush) ?? (from as ILinearGradientBrush);
        var fromStops = StopsOf(from);
        var toStops = StopsOf(to);
        int count = Math.Max(fromStops.Count, toStops.Count);

        var brush = new LinearGradientBrush
        {
            StartPoint = Point(from as ILinearGradientBrush, to as ILinearGradientBrush, p, start: true, shape),
            EndPoint = Point(from as ILinearGradientBrush, to as ILinearGradientBrush, p, start: false, shape),
            Opacity = Lerp(from.Opacity, to.Opacity, p),
        };
        for (int i = 0; i < count; i++)
        {
            double t = count == 1 ? 0 : (double)i / (count - 1);
            brush.GradientStops.Add(new GradientStop(
                Lerp(Sample(fromStops, t), Sample(toStops, t), p),
                t));
        }
        return brush;
    }

    private static bool IsColourBrush(IBrush b) => b is ISolidColorBrush or IGradientBrush;

    /// <summary>The colours of a brush as (offset, colour) pairs; a solid colour is one flat stop.</summary>
    private static IReadOnlyList<(double Offset, Color Color)> StopsOf(IBrush brush) => brush switch
    {
        ISolidColorBrush s => [(0, s.Color), (1, s.Color)],
        IGradientBrush g when g.GradientStops.Count > 0 =>
            g.GradientStops.OrderBy(s => s.Offset).Select(s => (Math.Clamp(s.Offset, 0, 1), s.Color)).ToList(),
        _ => [(0, Colors.Transparent), (1, Colors.Transparent)],
    };

    /// <summary>Colour of the gradient at position <paramref name="t"/> (0..1).</summary>
    private static Color Sample(IReadOnlyList<(double Offset, Color Color)> stops, double t)
    {
        if (t <= stops[0].Offset) return stops[0].Color;
        for (int i = 1; i < stops.Count; i++)
        {
            if (t <= stops[i].Offset)
            {
                double span = stops[i].Offset - stops[i - 1].Offset;
                return span <= 0 ? stops[i].Color : Lerp(stops[i - 1].Color, stops[i].Color, (t - stops[i - 1].Offset) / span);
            }
        }
        return stops[^1].Color;
    }

    private static RelativePoint Point(ILinearGradientBrush? from, ILinearGradientBrush? to, double p, bool start, ILinearGradientBrush? shape)
    {
        var fallback = shape != null ? (start ? shape.StartPoint : shape.EndPoint)
                                     : (start ? RelativePoint.TopLeft : RelativePoint.BottomRight);
        var a = from != null ? (start ? from.StartPoint : from.EndPoint) : fallback;
        var b = to != null ? (start ? to.StartPoint : to.EndPoint) : fallback;
        if (a.Unit != b.Unit) return p < 0.5 ? a : b;
        return new RelativePoint(Lerp(a.Point.X, b.Point.X, p), Lerp(a.Point.Y, b.Point.Y, p), a.Unit);
    }

    private static double Lerp(double a, double b, double p) => a + (b - a) * p;

    private static Color Lerp(Color a, Color b, double p) => Color.FromArgb(
        (byte)Math.Round(Lerp(a.A, b.A, p)),
        (byte)Math.Round(Lerp(a.R, b.R, p)),
        (byte)Math.Round(Lerp(a.G, b.G, p)),
        (byte)Math.Round(Lerp(a.B, b.B, p)));
}
