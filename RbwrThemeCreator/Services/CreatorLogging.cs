using RbwrOverlay.Core.Services;

namespace RbwrThemeCreator.Services;

/// <summary>
/// Dedicated file logger for RBWR Theme Creator (stored in %AppData%/RbwrThemeCreator/RBWR_Theme_Creator.log)
/// reusing RbwrOverlay.Core's privacy-sanitizing LoggingService.
/// </summary>
public static class CreatorLogging
{
    public static string DefaultLogPath => Path.Combine(CreatorSettings.FolderPath, "RBWR_Theme_Creator.log");

    private static readonly Lazy<LoggingService> _instance = new(() =>
        new LoggingService(DefaultLogPath, "RBWR Theme Creator"));

    public static ILoggingService Instance => _instance.Value;
}
