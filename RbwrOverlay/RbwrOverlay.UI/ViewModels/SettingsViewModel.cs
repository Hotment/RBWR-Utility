using System.Diagnostics;
using System.Globalization;
using Avalonia.Media;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using RbwrOverlay.Core.Models;
using RbwrOverlay.Core.Services;

namespace RbwrOverlay.UI.ViewModels;

public partial class SettingsViewModel : ViewModelBase
{
    private readonly ISettingsService _settingsService;
    private readonly ILoggingService _logger;
    private readonly AppSettings _settings;
    private readonly Action<AppSettings> _onSettingsSaved;
    private readonly Action _openFeedbackAction;

    [ObservableProperty]
    private double _usage;

    [ObservableProperty]
    private double _overlayOpacity;

    [ObservableProperty]
    private bool _topmostOnRoblox;

    [ObservableProperty]
    private string _topmostStatusText = "ENABLED";

    [ObservableProperty]
    private IBrush _topmostStatusBrush = Brushes.LimeGreen;

    [ObservableProperty]
    private string _demandThresholdSeconds = "60";

    [ObservableProperty]
    private string _recircOverride = string.Empty;

    [ObservableProperty]
    private bool _enableTurbineHealthAlert;

    [ObservableProperty]
    private string _turbineAlertStatusText = "DISABLED";

    [ObservableProperty]
    private IBrush _turbineAlertStatusBrush = Brushes.Crimson;

    [ObservableProperty]
    private string _turbineHealthThreshold = "65";

    [ObservableProperty]
    private double _uiScale = 1.0;

    [ObservableProperty]
    private double _compactUiScale = 1.0;

    public string VersionText => $"Version: {MainOverlayViewModel.AppVersion}";

    public event EventHandler? RequestClose;

    public SettingsViewModel(
        ISettingsService settingsService,
        AppSettings currentSettings,
        double currentUsage,
        double? currentRecircOverride,
        Action<AppSettings> onSettingsSaved,
        Action openFeedbackAction,
        ILoggingService? logger = null)
    {
        _settingsService = settingsService;
        _settings = currentSettings;
        _onSettingsSaved = onSettingsSaved;
        _openFeedbackAction = openFeedbackAction;
        _logger = logger ?? LoggingService.Instance;

        _usage = currentUsage;
        _overlayOpacity = _settings.Opacity;
        _uiScale = _settings.UiScale <= 0 ? 1.0 : _settings.UiScale;
        _compactUiScale = _settings.CompactUiScale <= 0 ? 1.0 : _settings.CompactUiScale;
        _topmostOnRoblox = _settings.TopmostOnRoblox;
        _demandThresholdSeconds = _settings.NextDemandThresholdSeconds.ToString();
        _recircOverride = currentRecircOverride.HasValue ? currentRecircOverride.Value.ToString("F0") : string.Empty;
        _enableTurbineHealthAlert = _settings.EnableTurbineHealthAlert;
        _turbineHealthThreshold = ((int)_settings.TurbineHealthThreshold).ToString();

        UpdateTopmostVisual();
        UpdateTurbineAlertVisual();
    }

    partial void OnOverlayOpacityChanged(double value)
    {
        _settings.Opacity = Math.Clamp(value, 0.1, 1.0);
        SaveAndNotify();
    }

    partial void OnDemandThresholdSecondsChanged(string value)
    {
        if (int.TryParse(value, out int thresh))
        {
            _settings.NextDemandThresholdSeconds = Math.Max(0, thresh);
            SaveAndNotify();
        }
    }

    partial void OnTurbineHealthThresholdChanged(string value)
    {
        if (double.TryParse(value, NumberStyles.Any, CultureInfo.InvariantCulture, out double thresh))
        {
            _settings.TurbineHealthThreshold = Math.Clamp(thresh, 0.0, 100.0);
            SaveAndNotify();
        }
    }

    [RelayCommand]
    public void ToggleRobloxTopmost()
    {
        TopmostOnRoblox = !TopmostOnRoblox;
        _settings.TopmostOnRoblox = TopmostOnRoblox;
        UpdateTopmostVisual();
        SaveAndNotify();
    }

    [RelayCommand]
    public void ToggleTurbineAlert()
    {
        EnableTurbineHealthAlert = !EnableTurbineHealthAlert;
        _settings.EnableTurbineHealthAlert = EnableTurbineHealthAlert;
        UpdateTurbineAlertVisual();
        SaveAndNotify();
    }

    [RelayCommand]
    public void ResetRecircOverride()
    {
        RecircOverride = string.Empty;
        SaveAndNotify();
    }

    [RelayCommand]
    public void OpenLog()
    {
        try
        {
            string path = _logger.GetLogFilePath();
            if (File.Exists(path))
            {
                Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
            }
        }
        catch (Exception ex)
        {
            _logger.Error("Failed to open log file", ex);
        }
    }

    [RelayCommand]
    public void OpenFeedback()
    {
        _openFeedbackAction?.Invoke();
    }

    [RelayCommand]
    public void Close()
    {
        RequestClose?.Invoke(this, EventArgs.Empty);
    }

    private void UpdateTopmostVisual()
    {
        TopmostStatusText = TopmostOnRoblox ? "ENABLED" : "DISABLED";
        TopmostStatusBrush = TopmostOnRoblox ? new SolidColorBrush(Color.Parse("#39ff14")) : new SolidColorBrush(Color.Parse("#ff003c"));
    }

    private void UpdateTurbineAlertVisual()
    {
        TurbineAlertStatusText = EnableTurbineHealthAlert ? "ENABLED" : "DISABLED";
        TurbineAlertStatusBrush = EnableTurbineHealthAlert ? new SolidColorBrush(Color.Parse("#39ff14")) : new SolidColorBrush(Color.Parse("#ff003c"));
    }

    private void SaveAndNotify()
    {
        _settingsService.SaveSettings(_settings);
        _onSettingsSaved?.Invoke(_settings);
    }
}