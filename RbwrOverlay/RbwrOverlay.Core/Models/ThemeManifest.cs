using System.Text.Json.Serialization;

namespace RbwrOverlay.Core.Models;

public class ThemeManifest
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("author")]
    public string Author { get; set; } = string.Empty;

    [JsonPropertyName("version")]
    public string Version { get; set; } = "1.0.0";

    [JsonPropertyName("description")]
    public string Description { get; set; } = string.Empty;

    [JsonPropertyName("entry")]
    public string Entry { get; set; } = "theme.axaml";

    [JsonPropertyName("min_app_version")]
    public string MinAppVersion { get; set; } = string.Empty;
}

public class InstalledThemeInfo
{
    public string Id { get; init; } = string.Empty;
    public string Name { get; init; } = string.Empty;
    public string Author { get; init; } = string.Empty;
    public string Version { get; init; } = "1.0.0";
    public string Description { get; init; } = string.Empty;
    public string DirectoryPath { get; init; } = string.Empty;
    public string EntryFilePath { get; init; } = string.Empty;
    public bool IsBuiltIn { get; init; }
    public ThemeManifest? Manifest { get; init; }

    public string DisplayName => IsBuiltIn
        ? Name
        : (string.IsNullOrWhiteSpace(Author) ? Name : $"{Name} ({Author})");

    public override string ToString() => DisplayName;
}

public sealed record ThemeApplyResult(bool Success, string ThemeId, string? ErrorMessage = null);