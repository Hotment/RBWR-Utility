using System.IO.Compression;
using System.Text.Json;
using System.Text.RegularExpressions;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Markup.Xaml;
using Avalonia.Media;
using Avalonia.Media.Imaging;
using Avalonia.Styling;
using Avalonia.Threading;
using RbwrOverlay.Core.Models;
using RbwrOverlay.Core.Services;

namespace RbwrOverlay.UI.Services;

public interface IThemeService
{
    string ThemesDirectory { get; }
    string ActiveThemeId { get; }
    event EventHandler<string>? ThemeChanged;
    IReadOnlyList<InstalledThemeInfo> DiscoverThemes();
    ThemeApplyResult ApplyTheme(string themeId);
    (bool Success, InstalledThemeInfo? Theme, string? ErrorMessage) InstallTheme(string sourcePath);
    InstalledThemeInfo CreateTemplateTheme(string id = "custom-template");
    (bool Success, string? ErrorMessage) DeleteTheme(string themeId);
}

public class ThemeService : IThemeService
{
    public const string DefaultThemeId = "default";
    public const string ReactorAmberThemeId = "reactor-amber";
    private const string ReactorAmberResourceUri = "avares://RbwrOverlay/Styles/ReactorAmberTheme.axaml";
    public const string AuroraDriftThemeId = "aurora-drift";
    // Kept as a plain (not compiled) resource: it is a Theme Creator theme with animated colours and is
    // loaded exactly like a custom theme (same preparation and safety checks).
    private const string AuroraDriftResourceName = "RbwrOverlay.BuiltInThemes.aurora-drift.theme";
    private const int MaxZipEntries = 200;
    private const long MaxZipUncompressedBytes = 50L * 1024 * 1024;

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        PropertyNameCaseInsensitive = true
    };

    private static readonly Regex DisallowedAssemblyNamespaceRegex = new(
        @"xmlns(?::[A-Za-z0-9_]+)?\s*=\s*[""'](?:clr-namespace:[^""']*|using:(?!(?:Avalonia(?:\.[A-Za-z0-9_.]+)?|RbwrOverlay\.UI\.(?:Behaviors|Converters))[""'])[^""']*)[""']",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex DisallowedXamlFeatureRegex = new(
        @"(?:\bx:Class\s*=|<\s*(?:[A-Za-z0-9_]+:)?(?:StyleInclude|ResourceInclude)\b)",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex RelativeFontPathRegex = new(
        @"(?<prefix>[>;\s,'""])(?<rel>(?:\./)?fonts/[^<""'\s;,)]+\.(?:ttf|otf|ttc)(?:#[^<""'\s;,)]*)?)",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex RelativeAssetImageRegex = new(
        @"Source\s*=\s*(?<quote>[""'])(?<rel>(?:\./)?assets/[^""'\s>]+\.(?:png|jpg|jpeg|webp|bmp|gif))\k<quote>",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex XmlCommentRegex = new(
        @"<!--[\s\S]*?-->",
        RegexOptions.Compiled);

    private static readonly Dictionary<string, IBrush> FallbackBrushCache = new(StringComparer.OrdinalIgnoreCase);

    private readonly ILoggingService _logger;
    private IStyle? _activeCustomStyle;
    private readonly List<Bitmap> _activeBitmaps = new();

    public string ThemesDirectory { get; }
    public string ActiveThemeId { get; private set; } = DefaultThemeId;

    public event EventHandler<string>? ThemeChanged;

    public ThemeService(ILoggingService? logger = null, string? themesDirectory = null)
    {
        _logger = logger ?? LoggingService.Instance;
        ThemesDirectory = themesDirectory ?? Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "themes");
        EnsureThemesDirectory();
    }

    public void EnsureThemesDirectory()
    {
        try
        {
            Directory.CreateDirectory(ThemesDirectory);
        }
        catch (Exception ex)
        {
            _logger.Warning($"Failed to create themes directory at '{ThemesDirectory}': {ex.Message}");
        }
    }

    public static InstalledThemeInfo CreateDefaultThemeInfo() => new()
    {
        Id = DefaultThemeId,
        Name = "Cyberpunk (Built-in)",
        Author = "Hotment",
        Version = "1.0.0",
        Description = "Built-in nuclear HUD cyberpunk theme.",
        IsBuiltIn = true
    };

    public static InstalledThemeInfo CreateReactorAmberThemeInfo() => new()
    {
        Id = ReactorAmberThemeId,
        Name = "Reactor Amber (Built-in)",
        Author = "Hotment",
        Version = "1.0.0",
        Description = "Built-in warm amber CRT nuclear instrumentation theme.",
        IsBuiltIn = true
    };

    public static InstalledThemeInfo CreateAuroraDriftThemeInfo() => new()
    {
        Id = AuroraDriftThemeId,
        Name = "Aurora Drift (Built-in)",
        Author = "Uranium-q2",
        Version = "1.0.0",
        Description = "Built-in animated northern lights theme.",
        IsBuiltIn = true
    };

    private static bool IsBuiltInThemeId(string? id) =>
        string.Equals(id, DefaultThemeId, StringComparison.OrdinalIgnoreCase)
        || string.Equals(id, ReactorAmberThemeId, StringComparison.OrdinalIgnoreCase)
        || string.Equals(id, AuroraDriftThemeId, StringComparison.OrdinalIgnoreCase);

    /// <summary>
    /// Source of a built-in theme that is stored as Theme Creator XAML (Aurora Drift), or null for the
    /// compiled built-ins (Cyberpunk, Reactor Amber).
    /// </summary>
    public static string? ReadBuiltInThemeXaml(string? id)
    {
        if (!string.Equals(id, AuroraDriftThemeId, StringComparison.OrdinalIgnoreCase))
            return null;
        using var stream = typeof(ThemeService).Assembly.GetManifestResourceStream(AuroraDriftResourceName)
            ?? throw new InvalidOperationException("The built-in Aurora Drift theme is missing.");
        using var reader = new StreamReader(stream);
        return reader.ReadToEnd();
    }

    /// <summary>
    /// Version used to decide which themes this overlay can run (themes whose Min. overlay is newer are
    /// hidden and cannot be installed). Settable for tests.
    /// </summary>
    public static string CurrentAppVersion { get; set; } = RbwrOverlay.UI.ViewModels.MainOverlayViewModel.AppVersion;

    /// <summary>True when this overlay is new enough for the theme (its manifest's Min. overlay).</summary>
    public static bool CanRun(InstalledThemeInfo theme) =>
        theme.IsBuiltIn || IsCompatibleWithAppVersion(theme.Manifest?.MinAppVersion, CurrentAppVersion);

    private static string NeedsNewerMessage(InstalledThemeInfo theme) =>
        $"'{theme.Name}' needs overlay v{theme.Manifest?.MinAppVersion?.Trim().TrimStart('v', 'V')} or newer "
        + $"(this is v{CurrentAppVersion}). Update the overlay to use it.";

    /// <summary>
    /// Themes in the themes folder that this overlay is too old for (e.g. themes with animated colours
    /// on an older overlay). They are left out of the theme list instead of failing when applied.
    /// </summary>
    public IReadOnlyList<InstalledThemeInfo> DiscoverTooNewThemes()
    {
        var result = new List<InstalledThemeInfo>();
        try
        {
            if (!Directory.Exists(ThemesDirectory)) return result;
            foreach (string dir in Directory.EnumerateDirectories(ThemesDirectory))
            {
                var info = TryReadThemeFromDirectory(dir);
                if (info != null && !IsBuiltInThemeId(info.Id) && !CanRun(info))
                    result.Add(info);
            }
        }
        catch (Exception ex)
        {
            _logger.Warning($"Could not check the themes folder: {ex.Message}");
        }
        return result;
    }

    public IReadOnlyList<InstalledThemeInfo> DiscoverThemes()
    {
        EnsureThemesDirectory();
        var list = new List<InstalledThemeInfo>
        {
            CreateDefaultThemeInfo(),
            CreateReactorAmberThemeInfo(),
            CreateAuroraDriftThemeInfo()
        };

        if (!Directory.Exists(ThemesDirectory))
            return list;

        var discovered = new List<InstalledThemeInfo>();
        foreach (string dir in Directory.EnumerateDirectories(ThemesDirectory))
        {
            var info = TryReadThemeFromDirectory(dir);
            if (info == null || IsBuiltInThemeId(info.Id))
                continue;
            // A theme made for a newer overlay is simply not listed (it could fail or crash here).
            if (!CanRun(info))
                continue;
            discovered.Add(info);
        }

        discovered.Sort((a, b) => string.Compare(a.Name, b.Name, StringComparison.OrdinalIgnoreCase));
        list.AddRange(discovered);
        return list;
    }

    private InstalledThemeInfo? TryReadThemeFromDirectory(string dir)
    {
        try
        {
            string folderName = Path.GetFileName(dir);
            string manifestPath = Path.Combine(dir, "theme.json");
            ThemeManifest? manifest = null;

            if (File.Exists(manifestPath))
            {
                string json = File.ReadAllText(manifestPath);
                manifest = JsonSerializer.Deserialize<ThemeManifest>(json, JsonOptions);
            }

            string id = SanitizeId(manifest?.Id ?? folderName);
            if (string.IsNullOrEmpty(id))
                return null;

            string entryRel = string.IsNullOrWhiteSpace(manifest?.Entry) ? "theme.axaml" : manifest!.Entry.Trim();
            string fullDir = Path.GetFullPath(dir);
            string entryFull = Path.GetFullPath(Path.Combine(fullDir, entryRel));
            if (!entryFull.StartsWith(fullDir + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)
                && !string.Equals(entryFull, fullDir, StringComparison.OrdinalIgnoreCase))
            {
                _logger.Warning($"Theme '{id}' entry path escapes theme directory: {entryRel}");
                return null;
            }

            if (!File.Exists(entryFull))
                return null;

            string name = string.IsNullOrWhiteSpace(manifest?.Name) ? folderName : manifest!.Name.Trim();
            return new InstalledThemeInfo
            {
                Id = id,
                Name = name,
                Author = manifest?.Author?.Trim() ?? string.Empty,
                Version = string.IsNullOrWhiteSpace(manifest?.Version) ? "1.0.0" : manifest!.Version.Trim(),
                Description = manifest?.Description?.Trim() ?? string.Empty,
                DirectoryPath = fullDir,
                EntryFilePath = entryFull,
                IsBuiltIn = false,
                Manifest = manifest
            };
        }
        catch (Exception ex)
        {
            _logger.Warning($"Skipping invalid theme directory '{dir}': {ex.Message}");
            return null;
        }
    }

    public ThemeApplyResult ApplyTheme(string themeId)
    {
        string targetId = string.IsNullOrWhiteSpace(themeId) ? DefaultThemeId : themeId.Trim();

        if (string.Equals(targetId, DefaultThemeId, StringComparison.OrdinalIgnoreCase))
        {
            ExecuteOnUiThread(() =>
            {
                var app = Application.Current;
                if (app != null && _activeCustomStyle != null)
                {
                    app.Styles.Remove(_activeCustomStyle);
                    _activeCustomStyle = null;
                }
                DisposeActiveBitmaps();
            });
            ActiveThemeId = DefaultThemeId;
            ThemeChanged?.Invoke(this, DefaultThemeId);
            return new ThemeApplyResult(true, DefaultThemeId);
        }

        if (string.Equals(targetId, ReactorAmberThemeId, StringComparison.OrdinalIgnoreCase))
        {
            try
            {
                ExecuteOnUiThread(() =>
                {
                    var app = Application.Current;
                    if (app == null) return;

                    if (AvaloniaXamlLoader.Load(new Uri(ReactorAmberResourceUri)) is IStyle loadedStyle)
                    {
                        if (_activeCustomStyle != null)
                        {
                            app.Styles.Remove(_activeCustomStyle);
                        }
                        DisposeActiveBitmaps();
                        app.Styles.Add(loadedStyle);
                        _activeCustomStyle = loadedStyle;
                    }
                });
                ActiveThemeId = ReactorAmberThemeId;
                ThemeChanged?.Invoke(this, ReactorAmberThemeId);
                _logger.Info("Applied built-in theme 'Reactor Amber'.");
                return new ThemeApplyResult(true, ReactorAmberThemeId);
            }
            catch (Exception ex)
            {
                _logger.Error("Failed to apply built-in Reactor Amber theme", ex);
                return new ThemeApplyResult(false, ActiveThemeId, ex.Message);
            }
        }

        if (string.Equals(targetId, AuroraDriftThemeId, StringComparison.OrdinalIgnoreCase))
        {
            try
            {
                string prepared = PrepareThemeXaml(ReadBuiltInThemeXaml(AuroraDriftThemeId)!, AppContext.BaseDirectory);
                var parsed = AvaloniaRuntimeXamlLoader.Parse<Styles>(prepared);
                ExecuteOnUiThread(() =>
                {
                    var app = Application.Current;
                    if (app == null) return;
                    if (_activeCustomStyle != null)
                        app.Styles.Remove(_activeCustomStyle);
                    DisposeActiveBitmaps();
                    app.Styles.Add(parsed);
                    _activeCustomStyle = parsed;
                });
                ActiveThemeId = AuroraDriftThemeId;
                ThemeChanged?.Invoke(this, AuroraDriftThemeId);
                _logger.Info("Applied built-in theme 'Aurora Drift'.");
                return new ThemeApplyResult(true, AuroraDriftThemeId);
            }
            catch (Exception ex)
            {
                _logger.Error("Failed to apply built-in Aurora Drift theme", ex);
                return new ThemeApplyResult(false, ActiveThemeId, ex.Message);
            }
        }

        var theme = DiscoverThemes().FirstOrDefault(t => string.Equals(t.Id, targetId, StringComparison.OrdinalIgnoreCase));
        if (theme == null || string.IsNullOrEmpty(theme.EntryFilePath) || !File.Exists(theme.EntryFilePath))
        {
            var tooNew = DiscoverTooNewThemes().FirstOrDefault(t => string.Equals(t.Id, targetId, StringComparison.OrdinalIgnoreCase));
            string msg = tooNew != null ? NeedsNewerMessage(tooNew) : $"Theme '{targetId}' was not found.";
            _logger.Warning(msg);
            return new ThemeApplyResult(false, ActiveThemeId, msg);
        }

        var loadedBitmaps = new List<Bitmap>();
        try
        {
            string rawXaml = File.ReadAllText(theme.EntryFilePath);
            string preparedXaml = PrepareThemeXaml(rawXaml, theme.DirectoryPath, out var assetFiles);
            var parsed = AvaloniaRuntimeXamlLoader.Parse<Styles>(preparedXaml);

            if (assetFiles.Count > 0 && Application.Current != null)
            {
                foreach (var (key, filePath) in assetFiles)
                {
                    var bmp = new Bitmap(filePath);
                    loadedBitmaps.Add(bmp);
                    parsed.Resources[key] = bmp;
                }
            }

            ExecuteOnUiThread(() =>
            {
                var app = Application.Current;
                if (app == null) return;

                if (_activeCustomStyle != null)
                {
                    app.Styles.Remove(_activeCustomStyle);
                }
                DisposeActiveBitmaps();

                app.Styles.Add(parsed);
                _activeCustomStyle = parsed;
                _activeBitmaps.AddRange(loadedBitmaps);
                loadedBitmaps.Clear();
            });

            ActiveThemeId = theme.Id;
            ThemeChanged?.Invoke(this, theme.Id);
            _logger.Info($"Applied theme '{theme.Name}' ({theme.Id}).");
            return new ThemeApplyResult(true, theme.Id);
        }
        catch (Exception ex)
        {
            foreach (var bmp in loadedBitmaps)
            {
                try { bmp.Dispose(); } catch { }
            }
            _logger.Error($"Failed to apply theme '{targetId}'", ex);
            return new ThemeApplyResult(false, ActiveThemeId, ex.Message);
        }
    }

    public static string PrepareThemeXaml(string rawXaml, string themeDirectory)
        => PrepareThemeXaml(rawXaml, themeDirectory, out _);

    public static string PrepareThemeXaml(string rawXaml, string themeDirectory, out List<(string Key, string FullPath)> assetFiles)
    {
        if (string.IsNullOrWhiteSpace(rawXaml))
            throw new InvalidOperationException("Theme XAML file is empty.");

        string strippedXaml = XmlCommentRegex.Replace(rawXaml, string.Empty);

        if (DisallowedAssemblyNamespaceRegex.IsMatch(strippedXaml))
            throw new InvalidOperationException("Theme XAML contains a disallowed assembly or CLR namespace reference.");

        if (DisallowedXamlFeatureRegex.IsMatch(strippedXaml))
            throw new InvalidOperationException("Theme XAML contains a disallowed x:Class or external StyleInclude/ResourceInclude directive.");

        string normalizedDir = Path.GetFullPath(themeDirectory).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        string baseFileUri = new Uri(normalizedDir + Path.DirectorySeparatorChar).AbsoluteUri;

        string withFonts = RelativeFontPathRegex.Replace(strippedXaml, m =>
        {
            string prefix = m.Groups["prefix"].Value;
            string rel = m.Groups["rel"].Value.TrimStart('.', '/').Replace('\\', '/');
            return $"{prefix}{baseFileUri}{rel}";
        });

        var assets = new List<(string Key, string FullPath)>();
        var seenPaths = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        string fullThemeRoot = normalizedDir + Path.DirectorySeparatorChar;

        string withAssets = RelativeAssetImageRegex.Replace(withFonts, m =>
        {
            string rel = m.Groups["rel"].Value.TrimStart('.', '/').Replace('/', Path.DirectorySeparatorChar);
            string fullAssetPath = Path.GetFullPath(Path.Combine(normalizedDir, rel));
            if (!fullAssetPath.StartsWith(fullThemeRoot, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException($"Theme asset path escapes theme directory: {rel}");
            if (!File.Exists(fullAssetPath))
                throw new FileNotFoundException($"Theme asset not found: {rel}", fullAssetPath);

            if (!seenPaths.TryGetValue(fullAssetPath, out string? key))
            {
                key = $"__theme_asset_{assets.Count}";
                seenPaths[fullAssetPath] = key;
                assets.Add((key, fullAssetPath));
            }
            return $"Source=\"{{DynamicResource {key}}}\"";
        });

        assetFiles = assets;
        return withAssets;
    }

    public (bool Success, InstalledThemeInfo? Theme, string? ErrorMessage) InstallTheme(string sourcePath)
    {
        if (string.IsNullOrWhiteSpace(sourcePath))
            return (false, null, "No source path provided.");

        EnsureThemesDirectory();

        try
        {
            if (Directory.Exists(sourcePath))
                return InstallFromDirectory(sourcePath);

            if (!File.Exists(sourcePath))
                return (false, null, $"File not found: {sourcePath}");

            string ext = Path.GetExtension(sourcePath);
            if (string.Equals(ext, ".zip", StringComparison.OrdinalIgnoreCase))
                return InstallFromZip(sourcePath);

            if (string.Equals(Path.GetFileName(sourcePath), "theme.json", StringComparison.OrdinalIgnoreCase))
                return InstallFromDirectory(Path.GetDirectoryName(sourcePath)!);

            if (string.Equals(ext, ".axaml", StringComparison.OrdinalIgnoreCase) || string.Equals(ext, ".xaml", StringComparison.OrdinalIgnoreCase))
                return InstallFromStandaloneAxaml(sourcePath);

            return (false, null, "Unsupported file type. Select a .zip theme pack, theme.json, or .axaml file.");
        }
        catch (Exception ex)
        {
            _logger.Error($"Failed to install theme from '{sourcePath}'", ex);
            return (false, null, ex.Message);
        }
    }

    private (bool Success, InstalledThemeInfo? Theme, string? ErrorMessage) InstallFromDirectory(string sourceDir)
    {
        var candidate = TryReadThemeFromDirectory(sourceDir);
        if (candidate == null)
            return (false, null, "Selected folder does not contain a valid theme.json or theme.axaml.");

        if (!CanRun(candidate))
            return (false, null, NeedsNewerMessage(candidate));

        if (IsBuiltInThemeId(candidate.Id))
            return (false, null, $"Theme ID '{candidate.Id}' is reserved for a built-in theme.");

        string destDir = Path.Combine(ThemesDirectory, candidate.Id);
        if (!string.Equals(Path.GetFullPath(sourceDir), Path.GetFullPath(destDir), StringComparison.OrdinalIgnoreCase))
        {
            if (Directory.Exists(destDir))
                Directory.Delete(destDir, recursive: true);
            CopyDirectory(sourceDir, destDir);
        }

        var installed = TryReadThemeFromDirectory(destDir);
        return installed != null
            ? (true, installed, null)
            : (false, null, "Installed theme failed validation.");
    }

    private (bool Success, InstalledThemeInfo? Theme, string? ErrorMessage) InstallFromStandaloneAxaml(string axamlPath)
    {
        string raw = File.ReadAllText(axamlPath);
        string slug = SanitizeId(Path.GetFileNameWithoutExtension(axamlPath));
        if (string.IsNullOrEmpty(slug) || IsBuiltInThemeId(slug))
            slug = "custom-theme";

        string destDir = Path.Combine(ThemesDirectory, slug);

        string prepared = PrepareThemeXaml(raw, destDir);
        _ = AvaloniaRuntimeXamlLoader.Parse<Styles>(prepared);

        Directory.CreateDirectory(destDir);
        File.WriteAllText(Path.Combine(destDir, "theme.axaml"), raw);

        var manifest = new ThemeManifest
        {
            Id = slug,
            Name = Path.GetFileNameWithoutExtension(axamlPath),
            Author = "Custom",
            Version = "1.0.0",
            Description = "Imported standalone AXAML stylesheet.",
            Entry = "theme.axaml"
        };
        File.WriteAllText(Path.Combine(destDir, "theme.json"), JsonSerializer.Serialize(manifest, JsonOptions));

        var installed = TryReadThemeFromDirectory(destDir);
        return installed != null
            ? (true, installed, null)
            : (false, null, "Failed to register standalone theme.");
    }

    private (bool Success, InstalledThemeInfo? Theme, string? ErrorMessage) InstallFromZip(string zipPath)
    {
        string tempDir = Path.Combine(Path.GetTempPath(), "rbwr_theme_" + Guid.NewGuid().ToString("N"));
        try
        {
            Directory.CreateDirectory(tempDir);
            string fullTempDir = Path.GetFullPath(tempDir) + Path.DirectorySeparatorChar;

            using (var archive = ZipFile.OpenRead(zipPath))
            {
                if (archive.Entries.Count > MaxZipEntries)
                    throw new InvalidOperationException($"Archive exceeds the maximum allowed entry count ({MaxZipEntries}).");

                long totalExtractedBytes = 0;
                byte[] buffer = new byte[81920];

                foreach (var entry in archive.Entries)
                {
                    if (string.IsNullOrEmpty(entry.Name))
                        continue;

                    if (entry.Length > MaxZipUncompressedBytes || totalExtractedBytes + entry.Length > MaxZipUncompressedBytes)
                        throw new InvalidOperationException("Archive exceeds the maximum allowed uncompressed size (50 MB).");

                    string destinationPath = Path.GetFullPath(Path.Combine(tempDir, entry.FullName));
                    if (!destinationPath.StartsWith(fullTempDir, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidOperationException("Archive contains unsafe path traversal entries.");

                    Directory.CreateDirectory(Path.GetDirectoryName(destinationPath)!);
                    using var entryStream = entry.Open();
                    using var outStream = File.Create(destinationPath);
                    int read;
                    while ((read = entryStream.Read(buffer, 0, buffer.Length)) > 0)
                    {
                        totalExtractedBytes += read;
                        if (totalExtractedBytes > MaxZipUncompressedBytes)
                            throw new InvalidOperationException("Archive exceeds the maximum allowed uncompressed size (50 MB).");
                        outStream.Write(buffer, 0, read);
                    }
                }
            }

            string themeRoot = tempDir;
            if (!File.Exists(Path.Combine(themeRoot, "theme.json")) && !File.Exists(Path.Combine(themeRoot, "theme.axaml")))
            {
                string[] subDirs = Directory.GetDirectories(tempDir);
                if (subDirs.Length == 1)
                {
                    themeRoot = subDirs[0];
                }
            }

            var candidate = TryReadThemeFromDirectory(themeRoot);
            if (candidate == null)
                return (false, null, "Archive does not contain theme.json / theme.axaml.");

            // Checked before the theme XAML is even parsed: it may use things this overlay does not have.
            if (!CanRun(candidate))
                return (false, null, NeedsNewerMessage(candidate));

            string raw = File.ReadAllText(candidate.EntryFilePath);
            string prepared = PrepareThemeXaml(raw, candidate.DirectoryPath);
            _ = AvaloniaRuntimeXamlLoader.Parse<Styles>(prepared);

            return InstallFromDirectory(themeRoot);
        }
        finally
        {
            try
            {
                if (Directory.Exists(tempDir))
                    Directory.Delete(tempDir, recursive: true);
            }
            catch
            {
            }
        }
    }

    public InstalledThemeInfo CreateTemplateTheme(string id = "custom-template")
    {
        EnsureThemesDirectory();
        string baseId = SanitizeId(id);
        if (string.IsNullOrEmpty(baseId) || IsBuiltInThemeId(baseId))
            baseId = "custom-template";

        string cleanId = baseId;
        int suffix = 1;
        while (Directory.Exists(Path.Combine(ThemesDirectory, cleanId)))
        {
            suffix++;
            cleanId = $"{baseId}-{suffix}";
        }

        string dir = Path.Combine(ThemesDirectory, cleanId);
        Directory.CreateDirectory(dir);
        Directory.CreateDirectory(Path.Combine(dir, "fonts"));
        Directory.CreateDirectory(Path.Combine(dir, "assets"));

        string templateName = suffix == 1 ? "Arctic Slate (Template)" : $"Arctic Slate (Template {suffix})";
        var manifest = new ThemeManifest
        {
            Id = cleanId,
            Name = templateName,
            Author = "Custom",
            Version = "1.0.0",
            Description = "Editable starter theme (Arctic Slate palette) with all RBWR Overlay selectors, classes, and resource tokens.",
            Entry = "theme.axaml",
            MinAppVersion = "2.3.0"
        };
        File.WriteAllText(Path.Combine(dir, "theme.json"), JsonSerializer.Serialize(manifest, JsonOptions));

        const string templateAxaml = """
<Styles xmlns="https://github.com/avaloniaui"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">

    <!--
      RBWR OVERLAY THEME TEMPLATE (Arctic Slate Starter)
      Avalonia styling docs (selectors, setters, transforms, templates):
        https://docs.avaloniaui.net/docs/basics/user-interface/styling/styles

      App-specific notes:
      - Custom fonts: place .ttf/.otf/.ttc files in ./fonts/ and reference them as:
          fonts/MyFont.ttf#Font Family Name
      - Custom images: place .png/.jpg/.webp/.bmp/.gif files in ./assets/ and reference them in ImageBrush:
          <ImageBrush x:Key="CyberMainBg" Source="assets/bg.png" Stretch="UniformToFill" Opacity="0.35" />
      - Edit this file and click "Reload" in the CONFIG tab to apply changes live.
      - Any Styles below override the built-in Cyberpunk theme.
    -->

    <!-- =========================================================
         1. ALL APP RESOURCE TOKENS (Fonts, Colors, Brushes)
         ========================================================= -->
    <Styles.Resources>
        <FontFamily x:Key="AppFontFamily">Consolas, 'Segoe UI', Inter, monospace</FontFamily>
        <FontFamily x:Key="AppMonoFontFamily">Consolas, monospace</FontFamily>

        <Color x:Key="CyberMainColor">#0b111a</Color>
        <Color x:Key="CyberCardColor">#131d2b</Color>
        <Color x:Key="CyberHeaderColor">#070b12</Color>
        <Color x:Key="CyberBorderColor">#2a3b52</Color>
        <Color x:Key="CyberBorderGlowColor">#60a5fa</Color>

        <Color x:Key="NeonCyanColor">#60a5fa</Color>
        <Color x:Key="NeonGreenColor">#4ade80</Color>
        <Color x:Key="NeonRedColor">#f87171</Color>
        <Color x:Key="NeonGoldColor">#facc15</Color>
        <Color x:Key="NeonPurpleColor">#a78bfa</Color>

        <Color x:Key="TextLightColor">#f1f5f9</Color>
        <Color x:Key="TextMutedColor">#94a3b8</Color>

        <SolidColorBrush x:Key="CyberMainBg" Color="#0b111a" Opacity="0.95" />
        <SolidColorBrush x:Key="CyberCardBg" Color="#131d2b" Opacity="0.88" />
        <SolidColorBrush x:Key="CyberHeaderBg" Color="#070b12" Opacity="0.97" />
        <SolidColorBrush x:Key="DarkPanelBg" Color="#0e1622" Opacity="0.92" />
        <SolidColorBrush x:Key="CyberBorder" Color="#2a3b52" />
        <SolidColorBrush x:Key="CyberBorderGlow" Color="#60a5fa" />

        <SolidColorBrush x:Key="NeonCyan" Color="#60a5fa" />
        <SolidColorBrush x:Key="NeonGreen" Color="#4ade80" />
        <SolidColorBrush x:Key="NeonRed" Color="#f87171" />
        <SolidColorBrush x:Key="NeonGold" Color="#facc15" />
        <SolidColorBrush x:Key="NeonPurple" Color="#a78bfa" />
        <SolidColorBrush x:Key="TextLight" Color="#f1f5f9" />
        <SolidColorBrush x:Key="TextMuted" Color="#94a3b8" />

        <SolidColorBrush x:Key="TooltipBg" Color="#f50b111a" />
        <SolidColorBrush x:Key="TooltipBorder" Color="#9960a5fa" />
        <SolidColorBrush x:Key="TooltipBodyBrush" Color="#e2e8f0" />

        <SolidColorBrush x:Key="ControlHoverBg" Color="#1b293d" />
        <SolidColorBrush x:Key="ControlActiveBg" Color="#233754" />
        <SolidColorBrush x:Key="ControlPressedBg" Color="#111b29" />
        <SolidColorBrush x:Key="TextBoxFocusBg" Color="#162336" />

        <SolidColorBrush x:Key="SliderTrackFill" Color="#2a3b52" />
        <SolidColorBrush x:Key="SliderTrackFillPointerOver" Color="#374d6b" />
        <SolidColorBrush x:Key="SliderTrackFillPressed" Color="#374d6b" />
        <SolidColorBrush x:Key="SliderTrackValueFill" Color="#60a5fa" />
        <SolidColorBrush x:Key="SliderTrackValueFillPointerOver" Color="#7ab6fc" />
        <SolidColorBrush x:Key="SliderTrackValueFillPressed" Color="#3b82f6" />
        <SolidColorBrush x:Key="SliderThumbBackground" Color="#60a5fa" />
        <SolidColorBrush x:Key="SliderThumbBackgroundPointerOver" Color="#93c5fd" />
        <SolidColorBrush x:Key="SliderThumbBackgroundPressed" Color="#bfdbfe" />
    </Styles.Resources>

    <!-- =========================================================
         2. SEMANTIC LAYOUT & HUD CLASSES
            overlay-shell, popup-shell, compact-shell, overlay-title,
            status-pill, sync-pill, hud-card, sub-panel, hud-header,
            nav-bar, power-banner, power-readout, power-subtext,
            preset-card, metric-card, hud-footer, config-card,
            sync-card, feedback-card
         ========================================================= -->
    <Style Selector="Border.overlay-shell">
        <Setter Property="CornerRadius" Value="10" />
        <Setter Property="BorderThickness" Value="1" />
    </Style>
    <Style Selector="Border.compact-shell">
        <Setter Property="CornerRadius" Value="14" />
    </Style>
    <Style Selector="TextBlock.overlay-title" />
    <Style Selector="Border.status-pill" />
    <Style Selector="Border.hud-card">
        <Setter Property="CornerRadius" Value="6" />
    </Style>
    <Style Selector="Border.nav-bar" />
    <Style Selector="Border.power-banner" />
    <Style Selector="TextBlock.power-readout" />
    <Style Selector="TextBlock.power-subtext" />
    <Style Selector="Border.preset-card" />
    <Style Selector="Border.metric-card" />
    <Style Selector="Border.hud-footer" />
    <Style Selector="Border.config-card" />

    <!-- =========================================================
         3. APP CONTROL CLASSES (Buttons, Inputs, Bars, Tablet HUD)
            States: :pointerover, :pressed, :focus, .active, .error
         ========================================================= -->
    <Style Selector="Button.cyber-nav:pointerover">
        <Setter Property="Background" Value="#182538" />
    </Style>
    <Style Selector="Button.cyber-nav.active">
        <Setter Property="Background" Value="#1e304a" />
    </Style>

    <Style Selector="Button.cyber:pointerover">
        <Setter Property="Background" Value="#1b293d" />
    </Style>
    <Style Selector="Button.cyber:pressed" />
    <Style Selector="Button.cyber.active">
        <Setter Property="Background" Value="#233754" />
    </Style>
    <Style Selector="Button.cyber.error" />
    <Style Selector="Button.cyber.error:pointerover" />

    <Style Selector="Button.cyber-blue" />
    <Style Selector="Button.cyber-blue:pointerover" />
    <Style Selector="Button.cyber-green" />
    <Style Selector="Button.cyber-green:pointerover" />
    <Style Selector="Button.cyber-gold" />
    <Style Selector="Button.cyber-gold:pointerover" />
    <Style Selector="Button.cyber-red" />
    <Style Selector="Button.cyber-red:pointerover" />
    <Style Selector="Button.cyber-header-btn" />
    <Style Selector="Button.cyber-header-btn:pointerover" />
    <Style Selector="Button.cyber-close, Button.cyber-close-btn" />
    <Style Selector="Button.cyber-close:pointerover, Button.cyber-close-btn:pointerover" />
    <Style Selector="Button.cyber-preset" />
    <Style Selector="Button.cyber-preset.active" />
    <Style Selector="Button.cyber-tick" />
    <Style Selector="Button.cyber-tick.active" />

    <Style Selector="TextBox.cyber" />
    <Style Selector="TextBox.cyber:focus" />
    <Style Selector="ComboBox.cyber" />
    <Style Selector="ComboBox.cyber /template/ Border#PopupBorder" />
    <Style Selector="ComboBox.cyber ComboBoxItem" />
    <Style Selector="ComboBox.cyber ComboBoxItem:pointerover /template/ ContentPresenter">
        <Setter Property="Background" Value="#1b293d" />
    </Style>
    <Style Selector="ComboBox.cyber ComboBoxItem:selected /template/ ContentPresenter">
        <Setter Property="Background" Value="#233754" />
    </Style>
    <Style Selector="ProgressBar.cyber-power" />
    <Style Selector="Slider" />
    <Style Selector="ToolTip" />

    <!-- Tablet HUD (Cyberpunk HUD mode) classes -->
    <Style Selector="TextBlock.cyber-head" />
    <Style Selector="TextBox.cyber-search" />
    <Style Selector="Slider.cyber-slider" />
    <Style Selector="Border.cyber-data-row" />

    <!-- =========================================================
         4. NAMED ELEMENTS (x:Name / #Id Selectors)
         ========================================================= -->
    <!-- MainWindow -->
    <Style Selector="Panel#RootHostPanel" />

    <!-- DetailedOverlayView -->
    <Style Selector="Border#DetailedShell" />
    <Style Selector="Grid#DetailedRootGrid" />
    <Style Selector="Grid#HeaderBar" />
    <Style Selector="TextBlock#OverlayTitle" />
    <Style Selector="Border#SyncBadge" />
    <Style Selector="Border#NavBar" />
    <Style Selector="Border#PowerBanner" />
    <Style Selector="TextBlock#MainPowerReadout" />
    <Style Selector="ProgressBar#MainPowerBar" />
    <Style Selector="TextBlock#MainPowerSubtext" />
    <Style Selector="Border#DemandPresetCard" />
    <Style Selector="Slider#DemandPresetSlider" />
    <Style Selector="Grid#MonitorMetricsGrid" />
    <Style Selector="Border#DemandInputCard" />
    <Style Selector="Border#CorePowerCard" />
    <Style Selector="Border#GenLoadCard" />
    <Style Selector="Border#FlowCard" />
    <Style Selector="Border#StatusFooterBar" />
    <Style Selector="Border#ThemeConfigCard" />
    <Style Selector="Slider#UiScaleSlider" />
    <Style Selector="Slider#CompactUiScaleSlider" />

    <!-- CompactOverlayView -->
    <Style Selector="Border#CompactShell" />
    <Style Selector="Grid#CompactRootGrid" />
    <Style Selector="TextBlock#CompactDragHandle" />
    <Style Selector="StackPanel#CompactUnitGroup" />
    <Style Selector="TextBox#CompactDemandInput" />
    <Style Selector="StackPanel#CompactPrimaryPanel" />
    <Style Selector="StackPanel#CompactSecondaryPanel" />
    <Style Selector="Button#CompactCounterButton" />
    <Style Selector="StackPanel#CompactWindowControls" />

</Styles>
""";
        File.WriteAllText(Path.Combine(dir, "theme.axaml"), templateAxaml);
        return TryReadThemeFromDirectory(dir)!;
    }

    public (bool Success, string? ErrorMessage) DeleteTheme(string themeId)
    {
        if (string.IsNullOrWhiteSpace(themeId) || IsBuiltInThemeId(themeId.Trim()))
            return (false, "Cannot delete a built-in theme.");

        var theme = DiscoverThemes().FirstOrDefault(t => string.Equals(t.Id, themeId.Trim(), StringComparison.OrdinalIgnoreCase));
        if (theme == null || theme.IsBuiltIn || string.IsNullOrWhiteSpace(theme.DirectoryPath))
            return (false, $"Theme '{themeId}' not found.");

        try
        {
            string fullRoot = Path.GetFullPath(ThemesDirectory).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
            string fullTarget = Path.GetFullPath(theme.DirectoryPath);
            if (!fullTarget.StartsWith(fullRoot, StringComparison.OrdinalIgnoreCase))
                return (false, "Invalid theme directory path.");

            if (string.Equals(ActiveThemeId, theme.Id, StringComparison.OrdinalIgnoreCase))
            {
                ApplyTheme(DefaultThemeId);
            }

            if (Directory.Exists(fullTarget))
            {
                Directory.Delete(fullTarget, recursive: true);
            }
            return (true, null);
        }
        catch (Exception ex)
        {
            _logger.Error($"Failed to delete theme '{themeId}'", ex);
            return (false, ex.Message);
        }
    }

    public static IBrush ResolveBrush(string resourceKey, string fallbackHex)
    {
        var app = Application.Current;
        if (app != null && app.TryGetResource(resourceKey, app.ActualThemeVariant, out object? res) && res is IBrush brush)
        {
            return brush;
        }

        lock (FallbackBrushCache)
        {
            if (!FallbackBrushCache.TryGetValue(fallbackHex, out var cached))
            {
                cached = new SolidColorBrush(Color.Parse(fallbackHex));
                FallbackBrushCache[fallbackHex] = cached;
            }
            return cached;
        }
    }

    public static IBrush ResolveBrushForHex(string hexColor)
    {
        if (string.IsNullOrWhiteSpace(hexColor))
            return ResolveBrush("TextLight", "#ffffff");

        string normalized = hexColor.Trim().ToLowerInvariant();
        string? resourceKey = normalized switch
        {
            "#00f0ff" => "NeonCyan",
            "#39ff14" => "NeonGreen",
            "#ff003c" => "NeonRed",
            "#ffaa00" => "NeonGold",
            "#b026ff" => "NeonPurple",
            "#73839c" => "TextMuted",
            "#ffffff" => "TextLight",
            _ => null
        };

        return resourceKey != null
            ? ResolveBrush(resourceKey, hexColor)
            : ResolveBrush(string.Empty, hexColor);
    }

    public static bool IsCompatibleWithAppVersion(string? minAppVersion, string currentAppVersion)
    {
        if (string.IsNullOrWhiteSpace(minAppVersion))
            return true;

        string cleanMin = minAppVersion.Trim().TrimStart('v', 'V').Split('-', '+')[0];
        string cleanCurrent = currentAppVersion.Trim().TrimStart('v', 'V').Split('-', '+')[0];

        if (Version.TryParse(cleanMin, out var minVer) && Version.TryParse(cleanCurrent, out var curVer))
        {
            return curVer >= minVer;
        }
        return true;
    }

    private void DisposeActiveBitmaps()
    {
        foreach (var bmp in _activeBitmaps)
        {
            try { bmp.Dispose(); } catch { }
        }
        _activeBitmaps.Clear();
    }

    private static string SanitizeId(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw))
            return string.Empty;
        string clean = Regex.Replace(raw.Trim().ToLowerInvariant(), @"[^a-z0-9_-]+", "-").Trim('-');
        return clean;
    }

    private static void CopyDirectory(string sourceDir, string destinationDir)
    {
        Directory.CreateDirectory(destinationDir);
        foreach (string file in Directory.EnumerateFiles(sourceDir))
        {
            File.Copy(file, Path.Combine(destinationDir, Path.GetFileName(file)), overwrite: true);
        }
        foreach (string subDir in Directory.EnumerateDirectories(sourceDir))
        {
            CopyDirectory(subDir, Path.Combine(destinationDir, Path.GetFileName(subDir)));
        }
    }

    private static void ExecuteOnUiThread(Action action)
    {
        if (Application.Current == null || Dispatcher.UIThread.CheckAccess())
        {
            action();
        }
        else
        {
            Dispatcher.UIThread.Invoke(action);
        }
    }
}