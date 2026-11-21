using System.Collections.Concurrent;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using Avalonia.Markup.Xaml;
using Avalonia.Media;
using Avalonia.Media.Fonts;
using Avalonia.Media.Imaging;
using Avalonia.Styling;
using RbwrThemeCreator.Models;

namespace RbwrThemeCreator.Services;

/// <summary>
/// Registers local .ttf/.otf/.ttc font files with Avalonia's FontManager under a <c>fonts:</c> URI
/// (Avalonia's FontManager requires the <c>fonts:</c> scheme for custom collections and ignores raw
/// <c>file:///</c> font URIs).
/// </summary>
internal sealed class FileFontCollection(Uri key) : FontCollectionBase
{
    private static readonly ConcurrentDictionary<string, (Uri Key, string? FamilyName)> Registered = new(StringComparer.OrdinalIgnoreCase);

    public override Uri Key { get; } = key;

    public bool LoadFile(string filePath, out string? familyName)
    {
        familyName = null;
        if (!File.Exists(filePath)) return false;
        using var fs = File.OpenRead(filePath);
        if (!TryAddGlyphTypeface(fs, out var gt)) return false;
        familyName = gt?.FamilyName;
        return true;
    }

    public static (Uri Uri, string? FamilyName) EnsureRegistered(string fullPath)
    {
        string normalized = Path.GetFullPath(fullPath);
        if (Registered.TryGetValue(normalized, out var existing))
            return existing;

        if (!File.Exists(normalized))
            return (new Uri(normalized), null);

        string hash = Convert.ToHexString(SHA1.HashData(Encoding.UTF8.GetBytes(normalized)))[..12].ToLowerInvariant();
        var collectionUri = new Uri($"fonts:rbwr-font-{hash}");

        try
        {
            var collection = new FileFontCollection(collectionUri);
            if (collection.LoadFile(normalized, out var familyName))
            {
                FontManager.Current.AddFontCollection(collection);
                var entry = (collectionUri, familyName);
                Registered[normalized] = entry;
                return entry;
            }
        }
        catch
        {
            // Headless unit tests without an initialized FontManager: fall back to file:/// URI.
        }

        return (new Uri(normalized), null);
    }
}

/// <summary>
/// Mirrors the overlay's ThemeService loading rules (RbwrOverlay.UI/Services/ThemeService.cs) so a theme that
/// works in the creator's preview also loads in the overlay. Keep the regexes in sync with that file.
/// </summary>
public static class ThemeValidator
{
    private static readonly Regex DisallowedAssemblyNamespaceRegex = new(
        @"xmlns(?::[A-Za-z0-9_]+)?\s*=\s*[""'](?:clr-namespace:[^""']*|using:(?!(?:Avalonia(?:\.[A-Za-z0-9_.]+)?|RbwrOverlay\.UI\.(?:Behaviors|Converters))[""'])[^""']*)[""']",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex DisallowedXamlFeatureRegex = new(
        @"(?:\bx:Class\s*=|<\s*(?:[A-Za-z0-9_]+:)?(?:StyleInclude|ResourceInclude)\b)",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex RelativeFontPathRegex = new(
        @"(?<prefix>[>;\s,'""])(?<rel>(?:\./)?fonts/[^<""'\s;,)]+\.(?:ttf|otf|ttc)(?:#[^<""';,)]*)?)",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex RelativeAssetImageRegex = new(
        @"Source\s*=\s*(?<quote>[""'])(?<rel>(?:\./)?assets/[^""'\s>]+\.(?:png|jpg|jpeg|webp|bmp|gif))\k<quote>",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex XmlCommentRegex = new(@"<!--[\s\S]*?-->", RegexOptions.Compiled);

    private static readonly Regex BehaviorsUsageRegex = new(@"using:RbwrOverlay\.UI\.(?:Behaviors|Converters)", RegexOptions.Compiled);

    /// <summary>True when the XAML references overlay-only namespaces (allowed by the overlay, not previewable here).</summary>
    public static bool UsesOverlayOnlyNamespaces(string xaml) => BehaviorsUsageRegex.IsMatch(XmlCommentRegex.Replace(xaml, string.Empty));

    public static string SanitizeId(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw))
            return string.Empty;
        return Regex.Replace(raw.Trim().ToLowerInvariant(), @"[^a-z0-9_-]+", "-").Trim('-');
    }

    /// <summary>Checks manifest fields; returns a list of human-readable problems (empty = OK).</summary>
    public static List<string> ValidateManifest(ThemeState state)
    {
        var problems = new List<string>();
        var m = state.Manifest;
        if (string.IsNullOrWhiteSpace(m.Name))
            problems.Add("Theme name is empty.");
        string id = SanitizeId(m.Id);
        if (string.IsNullOrEmpty(id))
            problems.Add("Theme ID is empty (use letters, digits, '-' or '_').");
        else if (TokenCatalog.ReservedIds.Contains(id))
            problems.Add($"Theme ID '{id}' is reserved for a built-in overlay theme.");
        else if (!string.Equals(id, m.Id, StringComparison.Ordinal))
            problems.Add($"Theme ID must be lowercase letters, digits, '-' or '_' (suggested: '{id}').");
        if (!string.IsNullOrWhiteSpace(m.Version) && !Version.TryParse(m.Version.Split('-', '+')[0], out _))
            problems.Add("Version should look like 1.0.0.");
        return problems;
    }

    /// <summary>
    /// Applies the overlay's security checks and resolves fonts/ and assets/ references.
    /// </summary>
    /// <param name="resolve">Maps a relative path ("fonts/a.ttf", "assets/bg.png") to a full local path, or null if missing.</param>
    public static string Prepare(string rawXaml, Func<string, string?> resolve, out List<(string Key, string FullPath)> assetFiles)
    {
        if (string.IsNullOrWhiteSpace(rawXaml))
            throw new InvalidOperationException("Theme XAML is empty.");

        string stripped = XmlCommentRegex.Replace(rawXaml, string.Empty);

        if (DisallowedAssemblyNamespaceRegex.IsMatch(stripped))
            throw new InvalidOperationException("Theme XAML contains a disallowed assembly or CLR namespace reference (only Avalonia namespaces are allowed).");

        if (DisallowedXamlFeatureRegex.IsMatch(stripped))
            throw new InvalidOperationException("Theme XAML contains a disallowed x:Class or StyleInclude/ResourceInclude directive.");

        string withFonts = RelativeFontPathRegex.Replace(stripped, m =>
        {
            string rel = m.Groups["rel"].Value.TrimStart('.', '/').Replace('\\', '/');
            string filePart = rel.Split('#')[0];
            string fragment = rel.Length > filePart.Length ? rel[filePart.Length..].TrimEnd() : string.Empty;
            string full = resolve(filePart) ?? throw new FileNotFoundException($"Font not found: {filePart}. Add it in the Fonts section.");
            var (fontUri, detectedFamily) = FileFontCollection.EnsureRegistered(full);
            if (string.IsNullOrEmpty(fragment) && !string.IsNullOrWhiteSpace(detectedFamily))
                fragment = $"#{detectedFamily}";
            return $"{m.Groups["prefix"].Value}{fontUri.AbsoluteUri}{fragment}";
        });

        var assets = new List<(string Key, string FullPath)>();
        var seen = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        string withAssets = RelativeAssetImageRegex.Replace(withFonts, m =>
        {
            string rel = m.Groups["rel"].Value.TrimStart('.', '/').Replace('\\', '/');
            string full = resolve(rel) ?? throw new FileNotFoundException($"Image not found: {rel}. Add it in the Images section.");
            if (!seen.TryGetValue(full, out var key))
            {
                key = $"__theme_asset_{assets.Count}";
                seen[full] = key;
                assets.Add((key, full));
            }
            return $"Source=\"{{DynamicResource {key}}}\"";
        });

        assetFiles = assets;
        return withAssets;
    }

    /// <summary>
    /// Fully loads the theme like the overlay does. Returns the parsed styles (with bitmaps attached) for the preview.
    /// The caller owns the returned bitmaps.
    /// </summary>
    public static (Styles Styles, List<Bitmap> Bitmaps) Load(string rawXaml, Func<string, string?> resolve)
    {
        string prepared = Prepare(rawXaml, resolve, out var assetFiles);
        if (UsesOverlayOnlyNamespaces(prepared))
            throw new InvalidOperationException("This theme uses RbwrOverlay.UI behaviors/converters, which only exist inside the overlay. It can still be exported, but the creator cannot preview it.");
        var parsed = AvaloniaRuntimeXamlLoader.Parse<Styles>(prepared);
        var bitmaps = new List<Bitmap>();
        try
        {
            foreach (var (key, path) in assetFiles)
            {
                // Read through a memory stream so the image file is never locked by the preview.
                using var ms = new MemoryStream(File.ReadAllBytes(path));
                var bmp = new Bitmap(ms);
                bitmaps.Add(bmp);
                parsed.Resources[key] = bmp;
            }
        }
        catch
        {
            foreach (var b in bitmaps) b.Dispose();
            throw;
        }
        return (parsed, bitmaps);
    }
}
