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
    public static readonly CornerRadiusEdgeConverter TopOnly = new(isTop: true);
    public static readonly CornerRadiusEdgeConverter BottomOnly = new(isTop: false);

    private readonly bool _isTop;

    private CornerRadiusEdgeConverter(bool isTop) => _isTop = isTop;

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        if (value is CornerRadius r)
        {
            return _isTop
                ? new CornerRadius(Math.Max(0, r.TopLeft - 1), Math.Max(0, r.TopRight - 1), 0, 0)
                : new CornerRadius(0, 0, Math.Max(0, r.BottomRight - 1), Math.Max(0, r.BottomLeft - 1));
        }
        return new CornerRadius(0);
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}
