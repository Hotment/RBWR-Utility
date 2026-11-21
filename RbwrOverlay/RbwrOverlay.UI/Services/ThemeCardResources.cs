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

    // ===================== Animated colours (Theme Creator "ANIMATED") =====================

    private static readonly System.Text.RegularExpressions.Regex AnimationsComment = new(
        @"<!--\s*@creator:token-animations\s+(?<json>\{.*?\})\s*-->",
        System.Text.RegularExpressions.RegexOptions.Singleline | System.Text.RegularExpressions.RegexOptions.CultureInvariant,
        TimeSpan.FromMilliseconds(200));

    private sealed record AnimationJson(string[]? Colors, bool Flow, double Seconds, double Angle = 0);

    private static readonly Dictionary<string, (DateTime Stamp, IReadOnlyDictionary<string, CardAnimation> Map)> AnimationCache =
        new(StringComparer.OrdinalIgnoreCase);

    /// <summary>
    /// The animated colours of a theme (key → animation), read from the settings the Theme Creator stores
    /// in theme.axaml. Empty for built-in themes, themes without animations or unreadable files.
    /// </summary>
    public static IReadOnlyDictionary<string, CardAnimation> GetAnimations(InstalledThemeInfo info)
    {
        try
        {
            if (!TryGetSource(info, out string key, out DateTime stamp, out var read))
                return new Dictionary<string, CardAnimation>();
            if (AnimationCache.TryGetValue(key, out var hit) && hit.Stamp == stamp)
                return hit.Map;

            var map = new Dictionary<string, CardAnimation>(StringComparer.Ordinal);
            var m = AnimationsComment.Match(read());
            if (m.Success)
            {
                var parsed = System.Text.Json.JsonSerializer.Deserialize<Dictionary<string, AnimationJson>>(m.Groups["json"].Value);
                foreach (var (token, json) in parsed ?? new Dictionary<string, AnimationJson>())
                {
                    var colours = (json.Colors ?? []).Select(h => Color.TryParse(h, out var c) ? (Color?)c : null)
                        .OfType<Color>().Take(4).ToList();
                    if (colours.Count >= 2)
                        map[token] = new CardAnimation(colours, json.Flow, Math.Clamp(json.Seconds, 1, 60), json.Angle);
                }
            }
            AnimationCache[key] = (stamp, map);
            return map;
        }
        catch
        {
            return new Dictionary<string, CardAnimation>(); // a card without animation, never an error
        }
    }

    /// <summary>
    /// The animation styles of a theme (the Theme Creator's "token animations" section of theme.axaml),
    /// as a &lt;Styles&gt; document, or null. Attached to the inside of the theme's card so its buttons,
    /// badges and frames animate exactly like the overlay does with that theme.
    /// </summary>
    public static string? GetAnimationStylesXaml(InstalledThemeInfo info)
    {
        try
        {
            if (!TryGetSource(info, out _, out _, out var read))
                return null;
            string text = read();
            const string begin = "<!-- @creator:token-animations-begin -->";
            const string end = "<!-- @creator:token-animations-end -->";
            int b = text.IndexOf(begin, StringComparison.Ordinal);
            int e = b < 0 ? -1 : text.IndexOf(end, b, StringComparison.Ordinal);
            if (b < 0 || e < 0) return null;
            string inner = text.Substring(b + begin.Length, e - b - begin.Length);
            if (!inner.Contains("<Style", StringComparison.Ordinal)) return null;
            // Inside its own card the theme's animations must apply, so the ":not(.theme-card)" the
            // Theme Creator adds (to keep the active theme off other cards) is removed here.
            inner = inner.Replace(":not(.theme-card)", string.Empty, StringComparison.Ordinal);
            string xaml = "<Styles xmlns=\"https://github.com/avaloniaui\" xmlns:x=\"http://schemas.microsoft.com/winfx/2006/xaml\">"
                          + inner + "</Styles>";
            // Same safety rules as a full theme (no clr-namespace, x:Class, includes).
            return ThemeService.PrepareThemeXaml(xaml, info.IsBuiltIn ? AppContext.BaseDirectory : info.DirectoryPath);
        }
        catch
        {
            return null; // the card simply does not animate inside
        }
    }

    /// <summary>
    /// Where a theme's Theme Creator XAML comes from: theme.axaml of a custom theme, or the resource of a
    /// built-in Theme Creator theme (Aurora Drift). False for the compiled built-ins and unreadable files.
    /// </summary>
    private static bool TryGetSource(InstalledThemeInfo info, out string key, out DateTime stamp, out Func<string> read)
    {
        key = string.Empty; stamp = DateTime.MinValue; read = () => string.Empty;
        if (info.IsBuiltIn)
        {
            if (ThemeService.ReadBuiltInThemeXaml(info.Id) is not { } xaml)
                return false;
            key = "builtin:" + info.Id;
            read = () => xaml;
            return true;
        }
        if (string.IsNullOrWhiteSpace(info.EntryFilePath))
            return false;
        var file = new FileInfo(info.EntryFilePath);
        if (!file.Exists || file.Length > MaxXamlBytes)
            return false;
        key = info.Id + "|" + info.EntryFilePath;
        stamp = file.LastWriteTimeUtc;
        read = () => File.ReadAllText(file.FullName);
        return true;
    }

    /// <summary>The animation for a thumbnail's frame: the window outline, else the main background, else any.</summary>
    public static CardAnimation? GetThumbnailAnimation(InstalledThemeInfo info)
    {
        var map = GetAnimations(info);
        return map.GetValueOrDefault("CyberBorderGlow") ?? map.GetValueOrDefault("CyberMainBg") ?? map.Values.FirstOrDefault();
    }

    private static IReadOnlyDictionary<object, object?>? Build(InstalledThemeInfo info)
    {
        _base ??= Collect(Load(CyberpunkUri), null);

        if (ThemeService.ReadBuiltInThemeXaml(info.Id) is { } builtInXaml)
            return Collect(AvaloniaRuntimeXamlLoader.Parse<Styles>(ThemeService.PrepareThemeXaml(builtInXaml, AppContext.BaseDirectory)), _base);

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
