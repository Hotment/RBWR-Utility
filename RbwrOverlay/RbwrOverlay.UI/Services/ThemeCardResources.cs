using Avalonia;
using Avalonia.Controls;
using Avalonia.Markup.Xaml;
using Avalonia.Media;
using Avalonia.Styling;
using RbwrOverlay.Core.Models;

namespace RbwrOverlay.UI.Services;

/// <summary>
/// The colours and fonts of a theme, for drawing its card in the Theme Manager in that theme's own
/// look (Reactor Amber gets an amber card, Cyberpunk a cyan one, custom themes their colours).
///
/// The resources are read by loading the theme exactly like <see cref="ThemeService"/> does (same
/// XAML preparation and safety checks), on top of the base Cyberpunk resources so keys a theme does
/// not define fall back to the default look, not to the theme that happens to be active.
/// Results are cached per file timestamp. Must be used on the UI thread.
/// </summary>
public static class ThemeCardResources
{
    private const string CyberpunkUri = "avares://RbwrOverlay/Styles/CyberpunkTheme.axaml";
    private const string ReactorAmberUri = "avares://RbwrOverlay/Styles/ReactorAmberTheme.axaml";
    private const long MaxXamlBytes = 2L * 1024 * 1024;

    /// <summary>
    /// Extra key with the card's fill: the theme's main background (gradients included). When that is
    /// an image (not loaded for cards), the card background colour is used instead.
    /// </summary>
    public const string CardBackgroundKey = "ThemeCardBackground";

    private static IReadOnlyDictionary<object, object?>? _base;
    private static readonly Dictionary<string, (DateTime Stamp, IReadOnlyDictionary<object, object?>? Resources)> Cache =
        new(StringComparer.OrdinalIgnoreCase);

    /// <summary>All resources of the theme (base + theme), or null when it cannot be loaded.</summary>
    public static IReadOnlyDictionary<object, object?>? Get(InstalledThemeInfo info)
    {
        try
        {
            string key = info.IsBuiltIn ? "builtin:" + info.Id : info.Id + "|" + info.EntryFilePath;
            DateTime stamp = info.IsBuiltIn || string.IsNullOrWhiteSpace(info.EntryFilePath)
                ? DateTime.MinValue
                : File.GetLastWriteTimeUtc(info.EntryFilePath);
            if (Cache.TryGetValue(key, out var hit) && hit.Stamp == stamp)
                return hit.Resources;

            var resources = Build(info);
            if (resources != null)
                resources = WithCardBackground(resources);
            Cache[key] = (stamp, resources);
            return resources;
        }
        catch
        {
            return null; // the card simply keeps the active theme's look
        }
    }

    private static IReadOnlyDictionary<object, object?>? Build(InstalledThemeInfo info)
    {
        _base ??= Collect(Load(CyberpunkUri), null);

        if (info.IsBuiltIn)
        {
            return string.Equals(info.Id, ThemeService.ReactorAmberThemeId, StringComparison.OrdinalIgnoreCase)
                ? Collect(Load(ReactorAmberUri), _base)
                : _base;
        }

        if (string.IsNullOrWhiteSpace(info.EntryFilePath) || new FileInfo(info.EntryFilePath).Length > MaxXamlBytes)
            return null;

        string raw = File.ReadAllText(info.EntryFilePath);
        string prepared = ThemeService.PrepareThemeXaml(raw, info.DirectoryPath, out var assetFiles);
        var styles = AvaloniaRuntimeXamlLoader.Parse<Styles>(prepared);
        var result = Collect(styles, _base);

        // Images are not loaded for a card. Their keys are set to null so they can never pick up
        // an image of the active theme with the same generated key.
        foreach (var (assetKey, _) in assetFiles)
            result[assetKey] = null;
        return result;
    }

    private static IReadOnlyDictionary<object, object?> WithCardBackground(IReadOnlyDictionary<object, object?> resources)
    {
        var result = new Dictionary<object, object?>(resources);
        resources.TryGetValue("CyberMainBg", out var main);
        resources.TryGetValue("CyberCardBg", out var card);
        result[CardBackgroundKey] = main is ISolidColorBrush or IGradientBrush ? main : card;
        return result;
    }

    private static IStyle Load(string uri) =>
        AvaloniaXamlLoader.Load(new Uri(uri)) as IStyle ?? throw new InvalidOperationException($"Could not load {uri}.");

    /// <summary>Top-level resources of the theme (and of merged dictionaries) over <paramref name="fallback"/>.</summary>
    private static Dictionary<object, object?> Collect(IStyle style, IReadOnlyDictionary<object, object?>? fallback)
    {
        var result = fallback != null ? new Dictionary<object, object?>(fallback) : new Dictionary<object, object?>();
        if (style is Styles styles)
            Copy(styles.Resources, result);
        return result;
    }

    private static void Copy(IResourceDictionary source, Dictionary<object, object?> target)
    {
        foreach (var merged in source.MergedDictionaries.OfType<IResourceDictionary>())
            Copy(merged, target);
        foreach (var key in source.Keys)
        {
            if (source.TryGetValue(key, out var value))
                target[key] = value;
        }
    }
}
