using System.Collections.ObjectModel;
using System.Globalization;
using Avalonia.Media;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using RbwrOverlay.Core.Models;
using RbwrOverlay.Core.Services;

namespace RbwrOverlay.UI.ViewModels;

public partial class ServerSyncViewModel : ViewModelBase
{
    private readonly IApiClient _apiClient;
    private readonly ILoggingService _logger;
    private readonly Action<string> _onSyncRequested;
    private readonly Action<double, bool> _onCalibrateRequested;

    [ObservableProperty]
    private string _jobIdInput = string.Empty;

    [ObservableProperty]
    private ObservableCollection<string> _availableJobIds = new();

    [ObservableProperty]
    private string _demandTimeLeftText = "Demand Time Left: --s";

    [ObservableProperty]
    private string _customCalibInput = string.Empty;

    [ObservableProperty]
    private string _syncStatusText = string.Empty;

    [ObservableProperty]
    private IBrush _syncStatusBrush = new SolidColorBrush(Color.Parse("#39ff14"));

    [ObservableProperty]
    private bool _isSyncing;

    public event EventHandler? RequestClose;

    public ServerSyncViewModel(
        IApiClient apiClient,
        string currentJobId,
        IEnumerable<string> cachedJobIds,
        Action<string> onSyncRequested,
        Action<double, bool> onCalibrateRequested,
        ILoggingService? logger = null)
    {
        _apiClient = apiClient;
        _logger = logger ?? LoggingService.Instance;
        _jobIdInput = currentJobId;
        _onSyncRequested = onSyncRequested;
        _onCalibrateRequested = onCalibrateRequested;

        foreach (var jid in cachedJobIds)
        {
            if (!string.IsNullOrWhiteSpace(jid) && !_availableJobIds.Contains(jid))
            {
                _availableJobIds.Add(jid);
            }
        }
    }

    [RelayCommand]
    public void Sync()
    {
        if (string.IsNullOrWhiteSpace(JobIdInput)) return;
        _onSyncRequested?.Invoke(JobIdInput.Trim());
    }

    [RelayCommand]
    public void CalibrateMinusOne()
    {
        _onCalibrateRequested?.Invoke(-1.0, true);
    }

    [RelayCommand]
    public void CalibratePlusOne()
    {
        _onCalibrateRequested?.Invoke(1.0, true);
    }

    [RelayCommand]
    public void ApplyCustomCalib()
    {
        if (double.TryParse(CustomCalibInput.Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out double val))
        {
            _onCalibrateRequested?.Invoke(val, false);
            CustomCalibInput = string.Empty;
        }
    }

    [RelayCommand]
    public void Close()
    {
        RequestClose?.Invoke(this, EventArgs.Empty);
    }

    public void UpdateCountdown(double liveDtl)
    {
        DemandTimeLeftText = $"Demand Time Left: {Math.Max(0, (int)liveDtl)}s";
    }

    public void SetStatus(string message, string hexColor)
    {
        SyncStatusText = message;
        SyncStatusBrush = new SolidColorBrush(Color.Parse(hexColor));
    }
}