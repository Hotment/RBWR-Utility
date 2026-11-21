using System.Text.Json;
using RbwrThemeCreator.Models;

namespace RbwrThemeCreator.Services;

/// <summary>What the recovery copy is about (shown in the "Restore unsaved theme?" question).</summary>
public sealed record RecoveryInfo(string ThemeName, string? OriginalFolder, DateTime SavedAtUtc);

/// <summary>
/// Autosave / crash recovery: a copy of the unsaved theme (theme.json, theme.axaml, fonts, images and a
/// custom thumbnail) kept in the settings folder. It is written every 30 s while there are unsaved
/// changes and removed once the theme is saved or the changes are thrown away on purpose. If the creator
/// crashes or is killed, the copy is still there at the next start and can be restored.
/// </summary>
public sealed class RecoveryStore(string root)
{
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };

    /// <summary>%AppData%/RbwrThemeCreator/recovery</summary>
    public static RecoveryStore Default => new(Path.Combine(CreatorSettings.FolderPath, "recovery"));

    private string ThemeDir => Path.Combine(root, "theme");
    private string InfoPath => Path.Combine(root, "recovery.json");

    public bool Exists => File.Exists(InfoPath) && File.Exists(Path.Combine(ThemeDir, "theme.axaml"));

    /// <summary>Writes the copy. Files that did not change since the last copy are not copied again.</summary>
    public void Save(ThemeState state, string xaml, string? originalFolder, byte[]? customPreviewPng)
    {
        Directory.CreateDirectory(root);
        // The copy is a normal theme folder, so restoring it uses the regular theme loader.
        var copy = state.Clone();
        if (string.IsNullOrWhiteSpace(copy.Manifest.Id))
            copy.Manifest.Id = "recovered-theme";
        ThemeExporter.WriteFolder(copy, xaml, ThemeDir, copy.CustomPreviewPath != null ? customPreviewPng : null);

        var info = new RecoveryInfo(
            string.IsNullOrWhiteSpace(state.Manifest.Name) ? "Untitled" : state.Manifest.Name.Trim(),
            originalFolder,
            DateTime.UtcNow);
        string tmp = InfoPath + ".tmp";
        File.WriteAllText(tmp, JsonSerializer.Serialize(info, JsonOptions));
        File.Move(tmp, InfoPath, overwrite: true); // info last: a half-written copy is never offered
    }

    public RecoveryInfo? Peek()
    {
        try
        {
            return Exists ? JsonSerializer.Deserialize<RecoveryInfo>(File.ReadAllText(InfoPath)) : null;
        }
        catch
        {
            return null;
        }
    }

    /// <summary>
    /// Copies the recovery theme to a fresh temp folder and loads it from there, so the recovery copy
    /// can be removed later without pulling fonts or images out from under the editor.
    /// </summary>
    public ThemeState? Load()
    {
        if (!Exists) return null;
        string session = Path.Combine(Path.GetTempPath(), "RbwrThemeCreator", "restored", Guid.NewGuid().ToString("N"));
        CopyDirectory(ThemeDir, session);
        return ThemeImporter.Load(session, BuiltInThemes.Cyberpunk);
    }

    public void Clear()
    {
        try
        {
            if (File.Exists(InfoPath)) File.Delete(InfoPath);
            if (Directory.Exists(ThemeDir)) Directory.Delete(ThemeDir, recursive: true);
        }
        catch
        {
            // a locked file is cleared next time; never fail the app over the recovery copy
        }
    }

    private static void CopyDirectory(string from, string to)
    {
        Directory.CreateDirectory(to);
        foreach (string file in Directory.GetFiles(from))
            File.Copy(file, Path.Combine(to, Path.GetFileName(file)), overwrite: true);
        foreach (string dir in Directory.GetDirectories(from))
            CopyDirectory(dir, Path.Combine(to, Path.GetFileName(dir)));
    }
}
