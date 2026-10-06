namespace RbwrOverlay.Core.Models;

public class UpdateInfo
{
    public string Version { get; set; } = string.Empty;
    public string ReleaseNotes { get; set; } = string.Empty;
    public string DownloadUrl { get; set; } = string.Empty;
    public string FileName { get; set; } = string.Empty;
    public bool IsAvailable { get; set; }
}