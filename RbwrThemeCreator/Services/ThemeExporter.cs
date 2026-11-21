using System.IO.Compression;
using System.Text.Json;
using RbwrThemeCreator.Models;

namespace RbwrThemeCreator.Services;

/// <summary>
/// Writes a theme in the overlay's pack format:
///   &lt;id&gt;/theme.json, &lt;id&gt;/theme.axaml, &lt;id&gt;/fonts/*, &lt;id&gt;/assets/*
/// plus an optional &lt;id&gt;/preview.png thumbnail (the overlay ignores files it does not know).
/// </summary>
public static class ThemeExporter
{
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };

    /// <summary>File name of the thumbnail written next to theme.json.</summary>
    public const string PreviewFileName = "preview.png";

    /// <summary>
    /// Marker next to preview.png: the thumbnail is a custom image, so the creator keeps it instead of
    /// rendering a new one. The overlay ignores this file.
    /// </summary>
    public const string CustomPreviewMarker = "preview.custom";

    /// <summary>
    /// Writes the theme into <paramref name="themeDir"/> (created if needed). When
    /// <paramref name="previewPng"/> is given it is saved as preview.png. Returns warnings.
    /// </summary>
    public static List<string> WriteFolder(ThemeState state, string xaml, string themeDir, byte[]? previewPng = null)
    {
        var warnings = new List<string>();
        Directory.CreateDirectory(themeDir);
        string fontsDir = Path.Combine(themeDir, "fonts");
        string assetsDir = Path.Combine(themeDir, "assets");
        Directory.CreateDirectory(fontsDir);
        Directory.CreateDirectory(assetsDir);

        state.Manifest.Entry = "theme.axaml";
        File.WriteAllText(Path.Combine(themeDir, "theme.json"), JsonSerializer.Serialize(state.Manifest, JsonOptions));
        File.WriteAllText(Path.Combine(themeDir, "theme.axaml"), xaml);

        SyncFiles(state.Fonts, fontsDir, warnings);
        SyncFiles(state.Assets, assetsDir, warnings);

        if (previewPng is { Length: > 0 })
        {
            try
            {
                File.WriteAllBytes(Path.Combine(themeDir, PreviewFileName), previewPng);
            }
            catch (Exception ex)
            {
                warnings.Add($"Could not write {PreviewFileName}: {ex.Message}");
            }
        }

        string marker = Path.Combine(themeDir, CustomPreviewMarker);
        try
        {
            if (state.CustomPreviewPath != null && previewPng is { Length: > 0 })
                File.WriteAllText(marker, "This theme uses a custom preview.png (RBWR Theme Creator keeps it instead of rendering one).");
            else if (File.Exists(marker))
                File.Delete(marker);
        }
        catch (Exception ex)
        {
            warnings.Add($"Could not update {CustomPreviewMarker}: {ex.Message}");
        }
        return warnings;
    }

    /// <summary>Creates a .zip theme pack that the overlay's "Install" button accepts.</summary>
    public static List<string> WriteZip(ThemeState state, string xaml, string zipPath, byte[]? previewPng = null)
    {
        string staging = Path.Combine(Path.GetTempPath(), "RbwrThemeCreator", "export", Guid.NewGuid().ToString("N"));
        try
        {
            string themeDir = Path.Combine(staging, state.Manifest.Id);
            var warnings = WriteFolder(state, xaml, themeDir, previewPng);
            if (File.Exists(zipPath))
                File.Delete(zipPath);
            ZipFile.CreateFromDirectory(staging, zipPath, CompressionLevel.Optimal, includeBaseDirectory: false);
            return warnings;
        }
        finally
        {
            try { Directory.Delete(staging, recursive: true); } catch { /* temp cleanup */ }
        }
    }

    /// <summary>Same size and the copy is not older than the source (File.Copy keeps the write time).</summary>
    private static bool IsSameFile(string source, string dest)
    {
        try
        {
            var s = new FileInfo(source);
            var d = new FileInfo(dest);
            return s.Exists && d.Exists && s.Length == d.Length && d.LastWriteTimeUtc >= s.LastWriteTimeUtc;
        }
        catch
        {
            return false;
        }
    }

    private static void SyncFiles(IEnumerable<ThemeFile> files, string targetDir, List<string> warnings)
    {
        var wanted = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var file in files)
        {
            string dest = Path.Combine(targetDir, file.FileName);
            wanted.Add(file.FileName);
            if (string.Equals(Path.GetFullPath(file.SourcePath), Path.GetFullPath(dest), StringComparison.OrdinalIgnoreCase))
                continue;
            if (IsSameFile(file.SourcePath, dest))
                continue; // already there (e.g. autosave every 30 s): do not copy big images again
            try
            {
                File.Copy(file.SourcePath, dest, overwrite: true);
            }
            catch (Exception ex)
            {
                warnings.Add($"Could not copy {file.FileName}: {ex.Message}");
            }
        }

        // Remove files that were deleted from the theme in the editor.
        foreach (string existing in Directory.EnumerateFiles(targetDir))
        {
            if (wanted.Contains(Path.GetFileName(existing))) continue;
            try
            {
                File.Delete(existing);
            }
            catch (Exception ex)
            {
                warnings.Add($"Could not remove old file {Path.GetFileName(existing)}: {ex.Message}");
            }
        }
    }
}
