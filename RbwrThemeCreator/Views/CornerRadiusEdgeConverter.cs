using System.Globalization;
using Avalonia;
using Avalonia.Data.Converters;

namespace RbwrThemeCreator.Views;

/// <summary>
/// Derives top-only or bottom-only inner corner radii from a shell Border's CornerRadius so
/// edge-flush headers/footers never poke outside rounded shell corners.
/// </summary>
public sealed class CornerRadiusEdgeConverter : IValueConverter
{
    private enum Edge { Top, Bottom, Left, Right }

    public static readonly CornerRadiusEdgeConverter TopOnly = new(Edge.Top);
    public static readonly CornerRadiusEdgeConverter BottomOnly = new(Edge.Bottom);
    public static readonly CornerRadiusEdgeConverter LeftOnly = new(Edge.Left);
    public static readonly CornerRadiusEdgeConverter RightOnly = new(Edge.Right);

    private readonly Edge _edge;

    private CornerRadiusEdgeConverter(Edge edge) => _edge = edge;

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        if (value is CornerRadius r)
        {
            return _edge switch
            {
                Edge.Top => new CornerRadius(Math.Max(0, r.TopLeft - 1), Math.Max(0, r.TopRight - 1), 0, 0),
                Edge.Bottom => new CornerRadius(0, 0, Math.Max(0, r.BottomRight - 1), Math.Max(0, r.BottomLeft - 1)),
                Edge.Left => new CornerRadius(Math.Max(0, r.TopLeft - 1), 0, 0, Math.Max(0, r.BottomLeft - 1)),
                Edge.Right => new CornerRadius(0, Math.Max(0, r.TopRight - 1), Math.Max(0, r.BottomRight - 1), 0),
                _ => new CornerRadius(0),
            };
        }
        return new CornerRadius(0);
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}
