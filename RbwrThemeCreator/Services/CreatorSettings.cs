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

    /// <summary>Theme folders opened or saved recently, newest first (THEME tab → Recent themes).</summary>
    public List<string> RecentThemes { get; set; } = new();

    // ---------- SETTINGS tab ----------
    /// <summary>Author put into new themes. Empty = the last author a theme was saved with.</summary>
    public string DefaultAuthor { get; set; } = string.Empty;

    /// <summary>The author a new theme starts with.</summary>
    [System.Text.Json.Serialization.JsonIgnore]
    public string AuthorForNewThemes => string.IsNullOrWhiteSpace(DefaultAuthor) ? LastAuthor : DefaultAuthor.Trim();

    /// <summary>Open the most recent theme folder when the creator starts.</summary>
    public bool OpenLastThemeAtStart { get; set; }

    /// <summary>Create missing preview.png thumbnails (installed themes at start-up, opened themes).</summary>
    public bool AutoCreateThumbnails { get; set; } = true;

    /// <summary>Keep a recovery copy of unsaved work every 30 s (restored after a crash).</summary>
    public bool AutosaveEnabled { get; set; } = true;

    /// <summary>Look for a new creator version when it starts.</summary>
    public bool CheckUpdatesAtStart { get; set; } = true;

    /// <summary>COLOURS tab: show the gradient tip box.</summary>
    public bool ShowGradientTip { get; set; } = true;

    /// <summary>COLOURS tab: show the contrast check box.</summary>
    public bool ShowContrastCheck { get; set; } = true;

    /// <summary>Changed keyboard shortcuts: action id -> gesture ("" = none). Missing = default.</summary>
    public Dictionary<string, string> Shortcuts { get; set; } = new();

    /// <summary>Folder that holds settings.json (SETTINGS → Open settings folder).</summary>
    public static string FolderPath => Path.GetDirectoryName(SettingsPath)!;

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
