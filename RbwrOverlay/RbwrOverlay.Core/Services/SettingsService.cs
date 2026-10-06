using System.Text.Json;
using RbwrOverlay.Core.Models;

namespace RbwrOverlay.Core.Services;

public interface ISettingsService
{
    AppSettings LoadSettings();
    void SaveSettings(AppSettings settings);
}

public class SettingsService : ISettingsService
{
    private readonly string _filePath;
    private readonly ILoggingService _logger;
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        PropertyNameCaseInsensitive = true
    };

    public SettingsService(ILoggingService? logger = null, string? customPath = null)
    {
        _logger = logger ?? LoggingService.Instance;
        _filePath = customPath ?? Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "settings.json");
    }

    public AppSettings LoadSettings()
    {
        try
        {
            if (File.Exists(_filePath))
            {
                string json = File.ReadAllText(_filePath);
                var settings = JsonSerializer.Deserialize<AppSettings>(json, JsonOptions);
                if (settings != null)
                {
                    return settings;
                }
            }
        }
        catch (Exception ex)
        {
            _logger.Warning($"Failed to load settings from {_filePath}: {ex.Message}");
        }

        return AppSettings.CreateDefault();
    }

    public void SaveSettings(AppSettings settings)
    {
        try
        {
            string json = JsonSerializer.Serialize(settings, JsonOptions);
            File.WriteAllText(_filePath, json);
        }
        catch (Exception ex)
        {
            _logger.Error($"Failed to save settings to {_filePath}", ex);
        }
    }
}