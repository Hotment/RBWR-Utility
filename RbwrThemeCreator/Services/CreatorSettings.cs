using System.Text.Json;

namespace RbwrThemeCreator.Services;

/// <summary>Small per-user settings file in %AppData%/RbwrThemeCreator/settings.json.</summary>
public sealed class CreatorSettings
{
    public string OverlayThemesDirectory { get; set; } = string.Empty;
    public string LastAuthor { get; set; } = string.Empty;
    public int PreviewBackdrop { get; set; }
    public double PreviewZoom { get; set; } = 1.0;
    public bool PreviewFit { get; set; } = true;
    public int PreviewMode { get; set; }
    public string SkippedVersion { get; set; } = string.Empty;

    private static readonly string SettingsPath = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "RbwrThemeCreator", "settings.json");

    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };

    private static CreatorSettings? _current;
    public static CreatorSettings Current => _current ??= Load();

    private static CreatorSettings Load()
    {
        try
        {
            if (File.Exists(SettingsPath))
                return JsonSerializer.Deserialize<CreatorSettings>(File.ReadAllText(SettingsPath)) ?? new CreatorSettings();
        }
        catch
        {
            // corrupt settings: start fresh
        }
        return new CreatorSettings();
    }

    public void Save()
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(SettingsPath)!);
            File.WriteAllText(SettingsPath, JsonSerializer.Serialize(this, JsonOptions));
        }
        catch
        {
            // settings are a convenience; never fail the app over them
        }
    }
}
