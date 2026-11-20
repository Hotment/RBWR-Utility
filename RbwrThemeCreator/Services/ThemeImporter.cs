using System.IO.Compression;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Xml.Linq;
using Avalonia.Media;
using RbwrOverlay.Core.Models;
using RbwrThemeCreator.Models;

namespace RbwrThemeCreator.Services;

/// <summary>
/// Reads an existing overlay theme (folder, theme.json, .zip or loose .axaml) back into a <see cref="ThemeState"/>.
/// Works with themes made by the creator (marker comments) and with hand-written themes
/// (unknown styles/resources are preserved as custom XAML).
/// </summary>
public static class ThemeImporter
{
    private static readonly XNamespace Ns = "https://github.com/avaloniaui";
    private static readonly XNamespace X = "http://schemas.microsoft.com/winfx/2006/xaml";

    private static readonly string[] FontExtensions = [".ttf", ".otf", ".ttc"];
    public static readonly string[] ImageExtensions = [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"];

    private static readonly JsonSerializerOptions JsonOptions = new() { PropertyNameCaseInsensitive = true };

    private static readonly Regex NamespaceDeclRegex = new(
        @"\s+xmlns(?::x)?=""(?:https://github\.com/avaloniaui|http://schemas\.microsoft\.com/winfx/2006/xaml)""",
        RegexOptions.Compiled);

    /// <summary>Loads from any supported path: folder, theme.json, theme .zip or .axaml file.</summary>
    public static ThemeState Load(string path, ThemeState fallback)
    {
        if (Directory.Exists(path))
            return LoadFolder(path, fallback);

        string ext = Path.GetExtension(path);
        if (ext.Equals(".zip", StringComparison.OrdinalIgnoreCase))
            return LoadZip(path, fallback);

        if (Path.GetFileName(path).Equals("theme.json", StringComparison.OrdinalIgnoreCase))
            return LoadFolder(Path.GetDirectoryName(path)!, fallback);

        if (ext.Equals(".axaml", StringComparison.OrdinalIgnoreCase) || ext.Equals(".xaml", StringComparison.OrdinalIgnoreCase))
        {
            string dir = Path.GetDirectoryName(path)!;
            if (File.Exists(Path.Combine(dir, "theme.json")))
                return LoadFolder(dir, fallback);

            string name = Path.GetFileNameWithoutExtension(path);
            var manifest = new ThemeManifest { Id = ThemeValidator.SanitizeId(name), Name = name, Author = "Custom" };
            var state = FromXaml(File.ReadAllText(path), manifest, fallback, includeStyles: true);
            CollectFiles(state, dir);
            return state;
        }

        throw new InvalidOperationException("Unsupported file. Choose a theme folder, theme.json, theme .zip or .axaml file.");
    }

    public static ThemeState LoadFolder(string dir, ThemeState fallback)
    {
        string manifestPath = Path.Combine(dir, "theme.json");
        ThemeManifest manifest;
        if (File.Exists(manifestPath))
        {
            manifest = JsonSerializer.Deserialize<ThemeManifest>(File.ReadAllText(manifestPath), JsonOptions) ?? new ThemeManifest();
        }
        else
        {
            manifest = new ThemeManifest { Name = Path.GetFileName(dir) };
        }

        if (string.IsNullOrWhiteSpace(manifest.Id))
            manifest.Id = ThemeValidator.SanitizeId(Path.GetFileName(dir));
        if (string.IsNullOrWhiteSpace(manifest.Name))
            manifest.Name = Path.GetFileName(dir);

        string entry = string.IsNullOrWhiteSpace(manifest.Entry) ? "theme.axaml" : manifest.Entry.Trim();
        string entryPath = Path.GetFullPath(Path.Combine(dir, entry));
        if (!File.Exists(entryPath))
            throw new FileNotFoundException($"Theme entry file not found: {entry}", entryPath);

        manifest.Entry = "theme.axaml"; // the creator always writes theme.axaml
        var state = FromXaml(File.ReadAllText(entryPath), manifest, fallback, includeStyles: true);
        CollectFiles(state, dir);
        return state;
    }

    private static ThemeState LoadZip(string zipPath, ThemeState fallback)
    {
        // Extract into a per-session working folder; fonts/assets are referenced from there until exported.
        string workDir = Path.Combine(Path.GetTempPath(), "RbwrThemeCreator", "imports", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(workDir);
        string fullWork = Path.GetFullPath(workDir) + Path.DirectorySeparatorChar;

        using (var archive = ZipFile.OpenRead(zipPath))
        {
            if (archive.Entries.Count > 200)
                throw new InvalidOperationException("Archive has too many entries (max 200).");
            long total = 0;
            foreach (var entry in archive.Entries)
            {
                if (string.IsNullOrEmpty(entry.Name)) continue;
                total += entry.Length;
                if (total > 50L * 1024 * 1024)
                    throw new InvalidOperationException("Archive is larger than 50 MB uncompressed.");
                string dest = Path.GetFullPath(Path.Combine(workDir, entry.FullName));
                if (!dest.StartsWith(fullWork, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("Archive contains unsafe paths.");
                Directory.CreateDirectory(Path.GetDirectoryName(dest)!);
                entry.ExtractToFile(dest, overwrite: true);
            }
        }

        string root = workDir;
        if (!File.Exists(Path.Combine(root, "theme.json")) && !File.Exists(Path.Combine(root, "theme.axaml")))
        {
            var subDirs = Directory.GetDirectories(workDir);
            if (subDirs.Length == 1) root = subDirs[0];
        }
        return LoadFolder(root, fallback);
    }

    private static void CollectFiles(ThemeState state, string dir)
    {
        string fontsDir = Path.Combine(dir, "fonts");
        if (Directory.Exists(fontsDir))
        {
            foreach (var f in Directory.EnumerateFiles(fontsDir)
                         .Where(f => FontExtensions.Contains(Path.GetExtension(f), StringComparer.OrdinalIgnoreCase))
                         .OrderBy(f => f, StringComparer.OrdinalIgnoreCase))
                state.Fonts.Add(new ThemeFile(Path.GetFileName(f), Path.GetFullPath(f)));
        }

        string assetsDir = Path.Combine(dir, "assets");
        if (Directory.Exists(assetsDir))
        {
            foreach (var f in Directory.EnumerateFiles(assetsDir)
                         .Where(f => ImageExtensions.Contains(Path.GetExtension(f), StringComparer.OrdinalIgnoreCase))
                         .OrderBy(f => f, StringComparer.OrdinalIgnoreCase))
                state.Assets.Add(new ThemeFile(Path.GetFileName(f), Path.GetFullPath(f)));
        }

        if (state.BackgroundImage != null && state.Assets.All(a => !a.FileName.Equals(state.BackgroundImage.FileName, StringComparison.OrdinalIgnoreCase)))
        {
            state.ImportWarnings.Add($"Background image assets/{state.BackgroundImage.FileName} is missing; background image removed.");
            state.BackgroundImage = null;
        }
    }

    /// <summary>Parses theme XAML text.</summary>
    /// <param name="includeStyles">When false, top-level styles that are not creator markers are dropped (used for presets).</param>
    public static ThemeState FromXaml(string xaml, ThemeManifest manifest, ThemeState fallback, bool includeStyles)
    {
        var state = new ThemeState
        {
            Manifest = manifest,
            FontFamily = fallback.FontFamily,
            MonoFontFamily = fallback.MonoFontFamily,
        };

        string rest = xaml;
        string? shapeXml = ExtractRegion(ref rest, ThemeXamlGenerator.ShapeBegin, ThemeXamlGenerator.ShapeEnd);
        string? customResources = ExtractRegion(ref rest, ThemeXamlGenerator.ResourcesBegin, ThemeXamlGenerator.ResourcesEnd);
        string? customStyles = ExtractRegion(ref rest, ThemeXamlGenerator.CustomBegin, ThemeXamlGenerator.CustomEnd);

        XDocument doc;
        try
        {
            doc = XDocument.Parse(rest, LoadOptions.PreserveWhitespace);
        }
        catch (Exception ex)
        {
            throw new InvalidOperationException($"theme.axaml is not valid XML: {ex.Message}", ex);
        }

        var root = doc.Root ?? throw new InvalidOperationException("theme.axaml has no root element.");
        if (root.Name != Ns + "Styles")
            throw new InvalidOperationException("theme.axaml root element must be <Styles>.");

        var mirrorColors = new Dictionary<string, Color>(StringComparer.Ordinal);
        var extraResources = new List<string>();

        var resources = root.Element(Ns + "Styles.Resources");
        if (resources != null)
        {
            foreach (var el in resources.Elements())
            {
                string? key = (string?)el.Attribute(X + "Key");
                string local = el.Name.LocalName;

                if (el.Name.Namespace == Ns && local == "FontFamily" && key == TokenCatalog.FontKey)
                {
                    state.FontFamily = el.Value.Trim();
                }
                else if (el.Name.Namespace == Ns && local == "FontFamily" && key == TokenCatalog.MonoFontKey)
                {
                    state.MonoFontFamily = el.Value.Trim();
                }
                else if (el.Name.Namespace == Ns && local == "Color" && key != null && TokenCatalog.ByMirrorColorKey.ContainsKey(key)
                         && ColorUtil.TryParse(el.Value, out var mirror))
                {
                    mirrorColors[key] = mirror;
                }
                else if (el.Name.Namespace == Ns && local == "SolidColorBrush" && key != null && TokenCatalog.ByKey.ContainsKey(key)
                         && ColorUtil.TryParse((string?)el.Attribute("Color"), out var brushColor)
                         && el.Attributes().All(a => a.IsNamespaceDeclaration || a.Name == X + "Key" || a.Name == "Color" || a.Name == "Opacity"))
                {
                    double opacity = Math.Clamp(ColorUtil.ParseDouble((string?)el.Attribute("Opacity"), 1.0), 0, 1);
                    state.Tokens[key] = new TokenValue(brushColor, opacity);
                }
                else if (el.Name.Namespace == Ns && local == "ImageBrush" && key == "CyberMainBg"
                         && ((string?)el.Attribute("Source"))?.Replace('\\', '/').TrimStart('.', '/') is { } src
                         && src.StartsWith("assets/", StringComparison.OrdinalIgnoreCase)
                         && !src[7..].Contains('/'))
                {
                    state.BackgroundImage = new BackgroundImageSettings
                    {
                        FileName = src[7..],
                        Opacity = Math.Clamp(ColorUtil.ParseDouble((string?)el.Attribute("Opacity"), 1.0), 0, 1),
                        Stretch = (string?)el.Attribute("Stretch") ?? "UniformToFill",
                    };
                }
                else if (el.Name.Namespace == Ns && local == "LinearGradientBrush" && key != null
                         && TokenCatalog.ByKey.TryGetValue(key, out var gdef) && gdef.SupportsGradient
                         && TryParseGradient(el, out var gradientValue))
                {
                    state.Tokens[key] = gradientValue;
                }
                else if (key != null && (TokenCatalog.ByKey.ContainsKey(key) || TokenCatalog.ByMirrorColorKey.ContainsKey(key)
                                         || key == TokenCatalog.FontKey || key == TokenCatalog.MonoFontKey))
                {
                    // A token the creator generates itself but cannot read in this form. Keeping it as an extra
                    // resource would duplicate the key and break the theme, so fall back to a safe value instead.
                    if (!TokenCatalog.ByMirrorColorKey.ContainsKey(key))
                        state.ImportWarnings.Add($"Could not read '{key}' ({local}); it was replaced with a default value.");
                }
                else
                {
                    extraResources.Add(Serialize(el));
                }
            }
        }

        // Fill missing tokens: mirror <Color> first, then the fallback theme.
        foreach (var def in TokenCatalog.Tokens)
        {
            if (state.Tokens.ContainsKey(def.Key))
                continue;
            if (def.MirrorColorKey != null && mirrorColors.TryGetValue(def.MirrorColorKey, out var mc))
                state.Tokens[def.Key] = new TokenValue(mc, fallback.Tokens.TryGetValue(def.Key, out var fb) ? fb.Opacity : 1);
            else if (fallback.Tokens.TryGetValue(def.Key, out var fbv))
                state.Tokens[def.Key] = fbv;
        }

        // Custom resources
        var resParts = new List<string>();
        if (!string.IsNullOrWhiteSpace(customResources)) resParts.Add(Dedent(customResources));
        resParts.AddRange(extraResources.Select(Dedent));
        state.CustomResources = string.Join(Environment.NewLine, resParts.Where(p => p.Trim().Length > 0));

        // Custom styles: marker region + any other top-level element written by hand.
        var styleParts = new List<string>();
        if (!string.IsNullOrWhiteSpace(customStyles)) styleParts.Add(Dedent(customStyles));
        if (includeStyles)
        {
            foreach (var el in root.Elements().Where(e => e.Name != Ns + "Styles.Resources"))
                styleParts.Add(Dedent(Serialize(el)));
        }
        state.CustomStyles = string.Join(Environment.NewLine + Environment.NewLine, styleParts.Where(p => p.Trim().Length > 0));

        if (!string.IsNullOrWhiteSpace(shapeXml))
            state.Shape = ParseShape(shapeXml);

        return state;
    }

    /// <summary>
    /// Reads a 2 or 3 stop &lt;LinearGradientBrush&gt;. Anything more exotic is rejected (the caller falls back to a solid colour).
    /// </summary>
    private static bool TryParseGradient(XElement el, out TokenValue value)
    {
        value = null!;
        var stops = new List<(double Offset, Color Color)>();
        foreach (var stop in el.Descendants(Ns + "GradientStop"))
        {
            if (!ColorUtil.TryParse((string?)stop.Attribute("Color"), out var c))
                return false;
            double off = ColorUtil.ParseDouble((string?)stop.Attribute("Offset"), 0);
            stops.Add((double.IsFinite(off) ? Math.Clamp(off, 0, 1) : 0, c));
        }
        if (stops.Count is < 2 or > 3)
            return false;
        stops.Sort((a, b) => a.Offset.CompareTo(b.Offset));

        if (!TryParseRelativePoint((string?)el.Attribute("StartPoint") ?? "0%,0%", out var sx, out var sy)
            || !TryParseRelativePoint((string?)el.Attribute("EndPoint") ?? "100%,100%", out var ex, out var ey))
            return false;
        double angle = Math.Abs(ex - sx) < 1e-9 && Math.Abs(ey - sy) < 1e-9 ? 90 : Math.Atan2(ey - sy, ex - sx) * 180 / Math.PI;
        angle = Math.Round(((angle % 360) + 360) % 360);

        double opacity = Math.Clamp(ColorUtil.ParseDouble((string?)el.Attribute("Opacity"), 1.0), 0, 1);
        Color? mid = stops.Count == 3 ? stops[1].Color : null;
        value = new TokenValue(stops[0].Color, opacity, new GradientSpec(stops[^1].Color, mid, angle));
        return true;
    }

    /// <summary>Parses "50%,0%" (relative) or "0.5,0" (treated as fractions) into percentages.</summary>
    private static bool TryParseRelativePoint(string text, out double x, out double y)
    {
        x = y = 0;
        var parts = text.Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length != 2) return false;
        static bool Part(string p, out double v)
        {
            bool percent = p.EndsWith('%');
            v = ColorUtil.ParseDouble(percent ? p[..^1] : p, double.NaN);
            if (!double.IsFinite(v)) return false;
            if (!percent) v *= 100;
            v = Math.Clamp(v, -1000, 1000);
            return true;
        }
        return Part(parts[0], out x) && Part(parts[1], out y);
    }

    private static ShapeSettings ParseShape(string regionXml)
    {
        var shape = new ShapeSettings();
        XElement root;
        try
        {
            root = XElement.Parse($"<Styles xmlns=\"{Ns}\" xmlns:x=\"{X}\">{regionXml}</Styles>");
        }
        catch
        {
            return shape;
        }

        foreach (var style in root.Elements(Ns + "Style"))
        {
            string selector = ((string?)style.Attribute("Selector") ?? string.Empty).Trim();
            var setters = style.Elements(Ns + "Setter")
                .Where(s => s.Attribute("Property") != null)
                .ToDictionary(s => (string)s.Attribute("Property")!, s => (string?)s.Attribute("Value") ?? string.Empty);

            double Get(string prop, double fallback) =>
                setters.TryGetValue(prop, out var v) ? ColorUtil.ParseDouble(v.Split(',')[0], fallback) : fallback;

            shape.Enabled = true;
            if (selector == "Border.overlay-shell")
            {
                shape.ShellCornerRadius = Get("CornerRadius", shape.ShellCornerRadius);
                shape.ShellBorderThickness = Get("BorderThickness", shape.ShellBorderThickness);
                if (setters.TryGetValue("BoxShadow", out var shadow))
                {
                    var parts = shadow.Split(' ', StringSplitOptions.RemoveEmptyEntries);
                    shape.ShellGlow = true;
                    if (parts.Length >= 3)
                        shape.ShellGlowBlur = ColorUtil.ParseDouble(parts[2], shape.ShellGlowBlur);
                }
            }
            else if (selector == "Border.compact-shell")
                shape.CompactCornerRadius = Get("CornerRadius", shape.CompactCornerRadius);
            else if (selector.StartsWith("Border.hud-card", StringComparison.Ordinal))
                shape.CardCornerRadius = Get("CornerRadius", shape.CardCornerRadius);
            else if (selector.StartsWith("Button.cyber", StringComparison.Ordinal))
                shape.ButtonCornerRadius = Get("CornerRadius", shape.ButtonCornerRadius);
        }
        return shape;
    }

    private static string? ExtractRegion(ref string text, string begin, string end)
    {
        int b = text.IndexOf(begin, StringComparison.Ordinal);
        if (b < 0) return null;
        int e = text.IndexOf(end, b + begin.Length, StringComparison.Ordinal);
        if (e < 0) return null;
        string inner = text.Substring(b + begin.Length, e - b - begin.Length);
        text = text[..b] + text[(e + end.Length)..];
        return inner;
    }

    private static string Serialize(XElement el)
    {
        string s = el.ToString(SaveOptions.DisableFormatting);
        return NamespaceDeclRegex.Replace(s, string.Empty);
    }

    /// <summary>Removes common leading indentation and surrounding blank lines.</summary>
    private static string Dedent(string text)
    {
        var lines = text.Replace("\r\n", "\n").Split('\n').ToList();
        while (lines.Count > 0 && lines[0].Trim().Length == 0) lines.RemoveAt(0);
        while (lines.Count > 0 && lines[^1].Trim().Length == 0) lines.RemoveAt(lines.Count - 1);
        if (lines.Count == 0) return string.Empty;

        // The first line of a serialized element carries no indentation of its own, so it only
        // counts when it is actually indented (text cut from a marker region).
        int firstIndent = lines[0].Length - lines[0].TrimStart(' ').Length;
        int common = lines.Skip(1).Where(l => l.Trim().Length > 0)
            .Select(l => l.Length - l.TrimStart(' ').Length)
            .DefaultIfEmpty(firstIndent)
            .Min();
        if (firstIndent > 0)
            common = Math.Min(common, firstIndent);

        return string.Join(Environment.NewLine, lines.Select((l, i) =>
        {
            if (l.Trim().Length == 0) return string.Empty;
            int lead = l.Length - l.TrimStart(' ').Length;
            return l[Math.Min(lead, common)..];
        }));
    }
}
