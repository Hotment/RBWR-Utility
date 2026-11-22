using System.Globalization;
using Avalonia.Data.Converters;
using RbwrOverlay.Core.Models;
using RbwrOverlay.UI.Services;

namespace RbwrOverlay.UI.Converters;

/// <summary>Helpers for showing a theme in the CONFIG tab's theme list.</summary>
public sealed class ThemeInfoConverters : IValueConverter
{
    private enum Kind { Thumbnail, HasThumbnail, Subtitle, ThumbnailAnimation }

    /// <summary>The animation the thumbnail's frame plays for an animated theme (null = still).</summary>
    public static readonly ThemeInfoConverters ThumbnailAnimation = new(Kind.ThumbnailAnimation);

    /// <summary>The theme's preview.png (or the built-in thumbnail), null when it has none.</summary>
    public static readonly ThemeInfoConverters Thumbnail = new(Kind.Thumbnail);

    /// <summary>True when the theme has a thumbnail (hides the image box otherwise).</summary>
    public static readonly ThemeInfoConverters HasThumbnail = new(Kind.HasThumbnail);

    /// <summary>"BUILT-IN · by Hotment", "CUSTOM · by Uranium" or "CUSTOM".</summary>
    public static readonly ThemeInfoConverters Subtitle = new(Kind.Subtitle);

    private readonly Kind _kind;

    private ThemeInfoConverters(Kind kind) => _kind = kind;

    public object? Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        if (value is not InstalledThemeInfo info)
            return _kind == Kind.HasThumbnail ? false : null;

        return _kind switch
        {
            Kind.Thumbnail => ThemeThumbnailService.Get(info),
            Kind.HasThumbnail => ThemeThumbnailService.Get(info) != null,
            Kind.ThumbnailAnimation => ThemeCardResources.GetThumbnailAnimation(info),
            _ => (info.IsBuiltIn ? "BUILT-IN" : "CUSTOM")
                 + (string.IsNullOrWhiteSpace(info.Author) ? string.Empty : $"  ·  by {info.Author.Trim()}"),
        };
    }

    public object? ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}
