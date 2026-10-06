using System.Net;
using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Globalization;
using Avalonia.Media;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using RbwrOverlay.Core.Calculations;
using RbwrOverlay.Core.Models;
using RbwrOverlay.Core.Services;
using RbwrOverlay.Platform;

namespace RbwrOverlay.UI.ViewModels;

public enum HudTab
{
    Monitor,
    ServerSync,
    Settings,
    Feedback
}

public partial class MainOverlayViewModel : ViewModelBase, IDisposable
{
    public const string AppVersion = "2.1.0";

    private readonly Calculator _calc;
    private readonly ISettingsService _settingsService;
    private readonly IApiClient _apiClient;
    private readonly IProcessMonitor _processMonitor;
    private readonly ILoggingService _logger;
    private readonly AppSettings _settings;

    private readonly SemaphoreSlim _connectLock = new(1, 1);
    public int MaxConnectionRetries { get; set; } = 2;
    public int ConnectionRetryDelayMs { get; set; } = 1000;

    private readonly DispatcherTimer _dtlTimer;
    private bool _isUpdatingFields;
    private bool _isDisposed;

    private ServerInfo? _activeServer;
    private List<ServerInfo> _cachedServers = new();
    private DateTimeOffset? _heartbeatTimestamp;
    private double _initialDtl;
    private double? _lastSyncedDemand;
    private double? _lastSwitchedNextDemand;
    private double? _pendingDemandValue;
    private bool _nextDemandSwitched;
    private bool _demandChangedWaitingHeartbeat;
    private bool _zeroSecRefetchDone;
    private DateTime _lastServerPollTime = DateTime.MinValue;
    private bool _turbineAlertTriggered;


    [ObservableProperty]
    private HudTab _currentTab = HudTab.Monitor;

    [ObservableProperty]
    private bool _isMonitorTabActive = true;

    [ObservableProperty]
    private bool _isSyncTabActive;

    [ObservableProperty]
    private bool _isSettingsTabActive;

    [ObservableProperty]
    private bool _isFeedbackTabActive;


    [ObservableProperty]
    private int _selectedUnit = 1;

    [ObservableProperty]
    private string _unitSuffix = "APRM";

    [ObservableProperty]
    private bool _isUnit1Active = true;

    [ObservableProperty]
    private bool _isUnit2Active;

    [ObservableProperty]
    private string _demandInput = "0";

    [ObservableProperty]
    private string _rtpInput = "0.000";

    [ObservableProperty]
    private string _generatorLoadText = "0.00 MWe";

    [ObservableProperty]
    private string _feedwaterFlowText = "0.00 kg/s";

    [ObservableProperty]
    private string _auxUsageText = "61.32 MWe";

    [ObservableProperty]
    private string _mainStatusPowerText = "0.00% APRM";

    [ObservableProperty]
    private string _mainStatusSubText = "APRM REACTOR POWER STATUS";

    [ObservableProperty]
    private double _thermalPowerPercent;

    [ObservableProperty]
    private IBrush _mainPowerBrush = new SolidColorBrush(Color.Parse("#00f0ff"));

    [ObservableProperty]
    private IBrush _powerBarBrush = new SolidColorBrush(Color.Parse("#00f0ff"));

    [ObservableProperty]
    private string _compactRtpText = "0.0% APRM";

    [ObservableProperty]
    private string _compactFlowText = "[0 kg/s]";

    [ObservableProperty]
    private bool _isOverpowerRisk;

    [ObservableProperty]
    private bool _isError;

    [ObservableProperty]
    private string _recircIndicatorText = string.Empty;

    [ObservableProperty]
    private bool _isRecircOverrideActive;


    [ObservableProperty]
    private bool _isCompact;

    [ObservableProperty]
    private bool _isTopmost = true;

    [ObservableProperty]
    private bool _topmostOnRoblox = true;

    [ObservableProperty]
    private double _overlayOpacity = 0.90;

    [ObservableProperty]
    private double _uiScale = 1.0;

    [ObservableProperty]
    private double _uiScalePreview = 1.0;

    [ObservableProperty]
    private double _compactUiScale = 1.0;

    [ObservableProperty]
    private double _compactUiScalePreview = 1.0;

    public double ActiveUiScale => IsCompact ? CompactUiScale : UiScale;

    [ObservableProperty]
    private string _pinSymbol = "UNPIN";

    [ObservableProperty]
    private string _connectionStatusText = "UNSYNCED";

    [ObservableProperty]
    private IBrush _connectionStatusBrush = new SolidColorBrush(Color.Parse("#73839c"));

    [ObservableProperty]
    private string _heartbeatAgeText = "No Server Connected";

    [ObservableProperty]
    private string _currentJobId = string.Empty;

    [ObservableProperty]
    private string _jobIdInput = string.Empty;

    [ObservableProperty]
    private ObservableCollection<string> _cachedJobIds = new();

    [ObservableProperty]
    private string _serverDtlText = "---";

    [ObservableProperty]
    private string _compactServerDtlText = "--";

    [ObservableProperty]
    private bool _showNextDemandInCompact;

    [ObservableProperty]
    private string _compactDisplayCounterText = "--s";

    [ObservableProperty]
    private string _compactCounterTooltip = "Not Synced: No server connected. Click to toggle target/countdown or open Server Sync tab.";

    [ObservableProperty]
    private bool _isSynced;

    [ObservableProperty]
    private bool _isSyncError;

    [ObservableProperty]
    private bool _hasSyncIssue = true;

    [ObservableProperty]
    private IBrush _compactCounterBrush = new SolidColorBrush(Color.Parse("#73839c"));

    [ObservableProperty]
    private IBrush _compactErrorIndicatorBrush = new SolidColorBrush(Color.Parse("#ffaa00"));

    [ObservableProperty]
    private IBrush _serverDtlBrush = new SolidColorBrush(Color.Parse("#73839c"));

    [ObservableProperty]
    private double _demandTimeLeftSeconds;

    [ObservableProperty]
    private string _dtlCountdownText = "--s";

    [ObservableProperty]
    private double _dtlProgressPercent = 100.0;

    [ObservableProperty]
    private string _customCalibInput = string.Empty;

    [ObservableProperty]
    private string _syncStatusMessage = string.Empty;

    [ObservableProperty]
    private IBrush _syncStatusBrush = new SolidColorBrush(Color.Parse("#39ff14"));

    [ObservableProperty]
    private double _turbineHealthValue = 100.0;

    [ObservableProperty]
    private string _turbineHealthText = "Turbine Health: --%";

    [ObservableProperty]
    private IBrush _turbineHealthBrush = new SolidColorBrush(Color.Parse("#39ff14"));


    [ObservableProperty]
    private string _demandThresholdSecondsInput = "60";

    [ObservableProperty]
    private string _recircOverrideInput = string.Empty;

    [ObservableProperty]
    private bool _enableTurbineHealthAlert;

    [ObservableProperty]
    private string _turbineHealthThresholdInput = "65";

    [ObservableProperty]
    private string _topmostStatusText = "ENABLED";

    [ObservableProperty]
    private IBrush _topmostStatusBrush = new SolidColorBrush(Color.Parse("#39ff14"));

    [ObservableProperty]
    private string _turbineAlertStatusText = "DISABLED";

    [ObservableProperty]
    private IBrush _turbineAlertStatusBrush = new SolidColorBrush(Color.Parse("#ff003c"));


    [ObservableProperty]
    private string _feedbackAuthor = string.Empty;

    [ObservableProperty]
    private string _feedbackContent = string.Empty;

    [ObservableProperty]
    private bool _feedbackIsAnonymous = true;

    [ObservableProperty]
    private string _feedbackStatusMessage = string.Empty;

    [ObservableProperty]
    private IBrush _feedbackStatusBrush = new SolidColorBrush(Color.Parse("#00f0ff"));

    [ObservableProperty]
    private bool _isSubmittingFeedback;

    [ObservableProperty]
    private string _updateStatusText = "Checking for updates...";

    [ObservableProperty]
    private bool _isUpdateAvailable;

    [ObservableProperty]
    private string _latestVersionText = string.Empty;

    [ObservableProperty]
    private string _releaseNotesText = string.Empty;

    [ObservableProperty]
    private string _downloadUrl = string.Empty;

    [ObservableProperty]
    private string _downloadFileName = string.Empty;

    public event Action<string, string, bool>? RequestShowMessage;
    public event Action? RequestQuit;

    public MainOverlayViewModel(
        ISettingsService? settingsService = null,
        IApiClient? apiClient = null,
        IProcessMonitor? processMonitor = null,
        ILoggingService? logger = null)
    {
        _logger = logger ?? LoggingService.Instance;
        _settingsService = settingsService ?? new SettingsService(_logger);
        _settings = _settingsService.LoadSettings();
        _apiClient = apiClient ?? new ApiClient(logger: _logger);
        _processMonitor = processMonitor ?? ProcessMonitorFactory.Create(_logger);

        _calc = new Calculator(_settings.Usage)
        {
            SelectedUnit = _settings.SelectedUnit
        };

        _selectedUnit = _settings.SelectedUnit;
        _isCompact = _settings.IsCompact;
        _isTopmost = _settings.IsTopmost;
        _topmostOnRoblox = _settings.TopmostOnRoblox;
        _overlayOpacity = _settings.Opacity;
        _uiScale = _settings.UiScale <= 0 ? 1.0 : _settings.UiScale;
        _uiScalePreview = _uiScale;
        _compactUiScale = _settings.CompactUiScale <= 0 ? 1.0 : _settings.CompactUiScale;
        _compactUiScalePreview = _compactUiScale;
        _currentJobId = _settings.LastJobId;
        _jobIdInput = _settings.LastJobId;

        _demandThresholdSecondsInput = _settings.NextDemandThresholdSeconds.ToString();
        _enableTurbineHealthAlert = _settings.EnableTurbineHealthAlert;
        _turbineHealthThresholdInput = ((int)_settings.TurbineHealthThreshold).ToString();

        UpdatePinSymbol();
        UpdateUnitVisuals();
        UpdateSettingsVisuals();
        UpdateSyncVisuals();

        _dtlTimer = new DispatcherTimer
        {
            Interval = TimeSpan.FromSeconds(1)
        };
        _dtlTimer.Tick += OnDtlTimerTick;
        _dtlTimer.Start();

        _processMonitor.RobloxActiveChanged += OnRobloxActiveChanged;
        _processMonitor.StartMonitoring();

        UpdateCalculationsFromDemand(0.0);

        if (!string.IsNullOrEmpty(_currentJobId))
        {
            Dispatcher.UIThread.Post(async () => await ConnectServerAsync(_currentJobId, false));
        }

        _ = CheckUpdatesAsync();
    }


    partial void OnUiScaleChanged(double value)
    {
        _uiScalePreview = value;
        _settings.UiScale = Math.Round(value, 2);
        _settingsService.SaveSettings(_settings);
        OnPropertyChanged(nameof(ActiveUiScale));
    }

    partial void OnCompactUiScaleChanged(double value)
    {
        _compactUiScalePreview = value;
        _settings.CompactUiScale = Math.Round(value, 2);
        _settingsService.SaveSettings(_settings);
        OnPropertyChanged(nameof(ActiveUiScale));
    }

    partial void OnIsCompactChanged(bool value)
    {
        OnPropertyChanged(nameof(ActiveUiScale));
    }

    partial void OnDemandInputChanged(string value)
    {
        if (_isUpdatingFields) return;
        if (double.TryParse(value, NumberStyles.Any, CultureInfo.InvariantCulture, out double dem))
        {
            _demandChangedWaitingHeartbeat = true;
            _pendingDemandValue = dem;
            UpdateCalculationsFromDemand(dem);
        }
    }

    partial void OnRtpInputChanged(string value)
    {
        if (_isUpdatingFields) return;
        if (double.TryParse(value, NumberStyles.Any, CultureInfo.InvariantCulture, out double rtp))
        {
            UpdateCalculationsFromRtp(rtp);
        }
    }

    public void UpdateCalculationsFromDemand(double demand)
    {
        if (_isUpdatingFields) return;
        _isUpdatingFields = true;

        try
        {
            if (demand < 0)
            {
                SetErrorState();
            }
            else
            {
                double thermal = _calc.CalcThermal(demand);
                double flow = _calc.CalcFlow(thermal);
                double genLoad = _calc.CalcGenLoad(thermal);

                RtpInput = thermal.ToString("F3", CultureInfo.InvariantCulture);
                _settings.Usage = _calc.Usage;

                RenderOutputs(thermal, flow, genLoad);
            }
        }
        catch
        {
            SetErrorState();
        }
        finally
        {
            _isUpdatingFields = false;
        }
    }

    public void UpdateCalculationsFromRtp(double thermal)
    {
        if (_isUpdatingFields) return;
        _isUpdatingFields = true;

        try
        {
            if (thermal < 0 || thermal > 250)
            {
                SetErrorState();
            }
            else
            {
                double flow = _calc.CalcFlow(thermal);
                double genLoad = _calc.CalcGenLoad(thermal);

                var uCalc = _calc.SelectedUnit == 1 ? _calc.UsageCalc1 : _calc.UsageCalc2;
                _calc.Usage = uCalc.CalculateUsage(flow, thermal, _calc.RecircOverride);

                double demand = Math.Max(0.0, Math.Round(genLoad - _calc.Usage));
                DemandInput = ((int)Math.Round(demand)).ToString(CultureInfo.InvariantCulture);

                RenderOutputs(thermal, flow, genLoad);
            }
        }
        catch
        {
            SetErrorState();
        }
        finally
        {
            _isUpdatingFields = false;
        }
    }

    private void RenderOutputs(double thermal, double flow, double genLoad)
    {
        IsError = false;
        UnitSuffix = _calc.SelectedUnit == 1 ? "APRM" : "RTP";

        GeneratorLoadText = $"{genLoad:F2} MWe";
        FeedwaterFlowText = $"{flow:F2} kg/s";
        AuxUsageText = $"{_calc.Usage:F2} MWe";
        MainStatusPowerText = $"{thermal:F2}% {UnitSuffix}";
        CompactRtpText = $"{thermal:F1}% {UnitSuffix}";
        CompactFlowText = $"[{Math.Round(flow):F0} kg/s]";
        ThermalPowerPercent = Math.Clamp(thermal, 0.0, 120.0);

        const double limit = 108.0;
        if (thermal > limit)
        {
            IsOverpowerRisk = true;
            MainStatusSubText = $"SCRAM OVERPOWER RISK (>{limit:F0}%)";
            MainPowerBrush = new SolidColorBrush(Color.Parse("#ff003c"));
            PowerBarBrush = new SolidColorBrush(Color.Parse("#ff003c"));
        }
        else if (thermal >= 95.0)
        {
            IsOverpowerRisk = false;
            MainStatusSubText = "APPROACHING PEAK LOAD";
            MainPowerBrush = new SolidColorBrush(Color.Parse("#ffaa00"));
            PowerBarBrush = new SolidColorBrush(Color.Parse("#ffaa00"));
        }
        else
        {
            IsOverpowerRisk = false;
            MainStatusSubText = "APRM REACTOR POWER STATUS";
            MainPowerBrush = new SolidColorBrush(Color.Parse("#00f0ff"));
            PowerBarBrush = new SolidColorBrush(Color.Parse("#00f0ff"));
        }

        UpdateRecircIndicator();
    }

    private void SetErrorState()
    {
        IsError = true;
        GeneratorLoadText = "ERROR";
        FeedwaterFlowText = "ERROR";
        AuxUsageText = "---";
        MainStatusPowerText = "ERR";
        MainStatusSubText = "VALUE OUT OF RANGE";
        CompactRtpText = "ERR";
        CompactFlowText = "[---]";
        ThermalPowerPercent = 0;
        MainPowerBrush = new SolidColorBrush(Color.Parse("#ff003c"));
        PowerBarBrush = new SolidColorBrush(Color.Parse("#ff003c"));
        UpdateRecircIndicator();
    }

    private void UpdateRecircIndicator()
    {
        if (_calc.RecircOverride.HasValue)
        {
            IsRecircOverrideActive = true;
            RecircIndicatorText = $"OVR: {_calc.RecircOverride.Value:F0}%";
        }
        else
        {
            IsRecircOverrideActive = false;
            RecircIndicatorText = string.Empty;
        }
    }


    [RelayCommand]
    public void SwitchTab(string tabName)
    {
        CurrentTab = tabName switch
        {
            "Sync" => HudTab.ServerSync,
            "Settings" => HudTab.Settings,
            "Feedback" => HudTab.Feedback,
            _ => HudTab.Monitor
        };

        IsMonitorTabActive = CurrentTab == HudTab.Monitor;
        IsSyncTabActive = CurrentTab == HudTab.ServerSync;
        IsSettingsTabActive = CurrentTab == HudTab.Settings;
        IsFeedbackTabActive = CurrentTab == HudTab.Feedback;
    }


    [RelayCommand]
    public void SelectUnit(object? parameter)
    {
        int unit = 1;
        if (parameter is int i) unit = i;
        else if (parameter is string s && int.TryParse(s, out int parsed)) unit = parsed;
        else if (parameter is double d) unit = (int)d;

        if (unit != 1 && unit != 2) return;
        SelectedUnit = unit;
        _calc.SelectedUnit = unit;
        _settings.SelectedUnit = unit;
        _demandChangedWaitingHeartbeat = false;

        UpdateUnitVisuals();

        if (_activeServer != null)
        {
            var uState = unit == 1 ? _activeServer.Unit1 : _activeServer.Unit2;
            if (uState != null)
            {
                double? targetDem = _nextDemandSwitched ? uState.NextDemand : uState.Demand;
                if (targetDem.HasValue)
                {
                    _lastSyncedDemand = targetDem.Value;
                    double cVal = Math.Max(0, targetDem.Value);
                    DemandInput = ((int)Math.Round(cVal)).ToString(CultureInfo.InvariantCulture);
                    UpdateCalculationsFromDemand(cVal);
                }
            }
        }
        else
        {
            if (double.TryParse(DemandInput, NumberStyles.Any, CultureInfo.InvariantCulture, out double dVal))
            {
                UpdateCalculationsFromDemand(dVal);
            }
        }

        _settingsService.SaveSettings(_settings);
    }

    [RelayCommand]
    public void AdjustDemand(object? parameter)
    {
        double delta = 0.0;
        if (parameter is double d) delta = d;
        else if (parameter is int i) delta = i;
        else if (parameter is string s && double.TryParse(s, NumberStyles.Any, CultureInfo.InvariantCulture, out double parsed)) delta = parsed;

        if (!double.TryParse(DemandInput, NumberStyles.Any, CultureInfo.InvariantCulture, out double val))
        {
            val = 0.0;
        }

        double newVal = Math.Max(0.0, Math.Round(val + delta));
        _demandChangedWaitingHeartbeat = true;
        _pendingDemandValue = newVal;
        DemandInput = ((int)newVal).ToString(CultureInfo.InvariantCulture);
        UpdateCalculationsFromDemand(newVal);
    }

    [RelayCommand]
    public void SetPresetDemand(object? parameter)
    {
        double presetValue = 0.0;
        if (parameter is double d) presetValue = d;
        else if (parameter is int i) presetValue = i;
        else if (parameter is string s && double.TryParse(s, NumberStyles.Any, CultureInfo.InvariantCulture, out double parsed)) presetValue = parsed;

        double rounded = Math.Round(presetValue);
        _demandChangedWaitingHeartbeat = true;
        _pendingDemandValue = rounded;
        DemandInput = ((int)rounded).ToString(CultureInfo.InvariantCulture);
        UpdateCalculationsFromDemand(rounded);
    }

    [RelayCommand]
    public void CommitUiScale()
    {
        double clamped = Math.Clamp(Math.Round(UiScalePreview, 2), 0.5, 3.0);
        UiScale = clamped;
        UiScalePreview = clamped;
    }

    [RelayCommand]
    public void CommitCompactUiScale()
    {
        double clamped = Math.Clamp(Math.Round(CompactUiScalePreview, 2), 0.5, 3.0);
        CompactUiScale = clamped;
        CompactUiScalePreview = clamped;
    }

    [RelayCommand]
    public void SetUiScalePreset(object? parameter)
    {
        double scale = 1.0;
        if (parameter is double d) scale = d;
        else if (parameter is string s && double.TryParse(s, NumberStyles.Any, CultureInfo.InvariantCulture, out double parsed)) scale = parsed;
        scale = Math.Clamp(scale, 0.5, 3.0);
        UiScalePreview = scale;
        UiScale = scale;
    }

    [RelayCommand]
    public void SetCompactUiScalePreset(object? parameter)
    {
        double scale = 1.0;
        if (parameter is double d) scale = d;
        else if (parameter is string s && double.TryParse(s, NumberStyles.Any, CultureInfo.InvariantCulture, out double parsed)) scale = parsed;
        scale = Math.Clamp(scale, 0.5, 3.0);
        CompactUiScalePreview = scale;
        CompactUiScale = scale;
    }

    [RelayCommand]
    public void ResetRecircOverride()
    {
        _calc.RecircOverride = null;
        RecircOverrideInput = string.Empty;
        UpdateRecircIndicator();
        if (double.TryParse(DemandInput, NumberStyles.Any, CultureInfo.InvariantCulture, out double dVal))
        {
            UpdateCalculationsFromDemand(dVal);
        }
    }

    [RelayCommand]
    public void ToggleCompact()
    {
        IsCompact = !IsCompact;
        _settings.IsCompact = IsCompact;
        _settingsService.SaveSettings(_settings);
    }

    [RelayCommand]
    public void ToggleTopmost()
    {
        IsTopmost = !IsTopmost;
        _settings.IsTopmost = IsTopmost;
        UpdatePinSymbol();
        _settingsService.SaveSettings(_settings);
    }

    [RelayCommand]
    public void Quit() => RequestQuit?.Invoke();


    [RelayCommand]
    public async Task ConnectServerFromInputAsync()
    {
        if (!string.IsNullOrWhiteSpace(JobIdInput))
        {
            await ConnectServerAsync(JobIdInput.Trim(), true);
        }
    }

    public async Task ConnectServerAsync(string query, bool isUserInitiated = false)
    {
        if (string.IsNullOrWhiteSpace(query)) return;

        if (isUserInitiated)
        {
            await _connectLock.WaitAsync();
        }
        else
        {
            if (!await _connectLock.WaitAsync(0))
            {
                return;
            }
        }

        try
        {
            CurrentJobId = query.Trim();
            JobIdInput = CurrentJobId;
            _settings.LastJobId = CurrentJobId;
            _settingsService.SaveSettings(_settings);

            if (isUserInitiated)
            {
                _demandChangedWaitingHeartbeat = false;
                _lastSyncedDemand = null;
            }

            int retriesAttempted = 0;
            ServerFetchResult fetchResult;

            while (true)
            {
                fetchResult = await _apiClient.GetLatestServersDetailedAsync();

                if (fetchResult.IsSuccess || fetchResult.ErrorKind != ServerFetchErrorKind.ConnectionLost || retriesAttempted >= MaxConnectionRetries)
                {
                    break;
                }

                retriesAttempted++;
                SetSyncStatus($"Connection lost with server. Retrying (attempt {retriesAttempted}/{MaxConnectionRetries})...", "#ffaa00");
                ConnectionStatusText = "RETRYING";
                ConnectionStatusBrush = new SolidColorBrush(Color.Parse("#ffaa00"));
                UpdateSyncVisuals();

                if (ConnectionRetryDelayMs > 0)
                {
                    await Task.Delay(ConnectionRetryDelayMs);
                }
            }

            if (fetchResult.IsSuccess)
            {
                var servers = fetchResult.Servers;
                if (servers.Count > 0)
                {
                    _cachedServers = servers;
                    CachedJobIds.Clear();
                    foreach (var s in servers)
                    {
                        if (!string.IsNullOrEmpty(s.JobId) && !CachedJobIds.Contains(s.JobId))
                        {
                            CachedJobIds.Add(s.JobId);
                        }
                    }

                    var matched = _apiClient.FindServerByIdOrJobId(servers, CurrentJobId);
                    if (matched != null)
                    {
                        var missing = matched.ValidateSync();
                        if (missing.Count == 0)
                        {
                            string syncMsg = retriesAttempted > 0
                                ? $"Server Synced Successfully (reconnected after {retriesAttempted} {(retriesAttempted == 1 ? "retry" : "retries")})"
                                : "Server Synced Successfully";
                            OnServerConnected(matched, syncMsg);
                        }
                        else
                        {
                            _activeServer = null;
                            IsSynced = false;
                            IsSyncError = true;
                            HasSyncIssue = true;
                            SetSyncStatus($"Sync Warning: Missing {string.Join(", ", missing)}", "#ffaa00");
                            ConnectionStatusText = "DESYNCED";
                            ConnectionStatusBrush = new SolidColorBrush(Color.Parse("#ffaa00"));
                            UpdateSyncVisuals();
                        }
                    }
                    else
                    {
                        _activeServer = null;
                        IsSynced = false;
                        IsSyncError = true;
                        HasSyncIssue = true;
                        SetSyncStatus($"Server '{CurrentJobId}' not found in public list", "#ff003c");
                        ConnectionStatusText = "DESYNCED";
                        ConnectionStatusBrush = new SolidColorBrush(Color.Parse("#ffaa00"));
                        UpdateSyncVisuals();
                    }
                }
                else
                {
                    _activeServer = null;
                    IsSynced = false;
                    IsSyncError = true;
                    HasSyncIssue = true;
                    SetSyncStatus("No active servers found on API", "#ff003c");
                    ConnectionStatusText = "UNSYNCED";
                    ConnectionStatusBrush = new SolidColorBrush(Color.Parse("#ff003c"));
                    UpdateSyncVisuals();
                }
            }
            else
            {
                _activeServer = null;
                IsSynced = false;
                IsSyncError = true;
                HasSyncIssue = true;
                ConnectionStatusText = "UNSYNCED";
                ConnectionStatusBrush = new SolidColorBrush(Color.Parse("#ff003c"));

                switch (fetchResult.ErrorKind)
                {
                    case ServerFetchErrorKind.ConnectionLost:
                        string retryInfo = retriesAttempted > 0
                            ? $" (retried {retriesAttempted}x)"
                            : " (retried)";
                        string detail = !string.IsNullOrWhiteSpace(fetchResult.ErrorMessage)
                            ? $": {fetchResult.ErrorMessage}"
                            : "";
                        SetSyncStatus($"Connection lost with server{retryInfo}{detail}", "#ff003c");
                        break;

                    case ServerFetchErrorKind.HttpError:
                        string httpMsg = fetchResult.StatusCode switch
                        {
                            HttpStatusCode.NotFound => "Server API endpoint not found (HTTP 404)",
                            HttpStatusCode.InternalServerError => "Server internal error (HTTP 500)",
                            (HttpStatusCode)429 => "Server API rate limited (HTTP 429)",
                            HttpStatusCode.Forbidden => "Server API access forbidden (HTTP 403)",
                            HttpStatusCode.Unauthorized => "Server API unauthorized (HTTP 401)",
                            _ => !string.IsNullOrWhiteSpace(fetchResult.ErrorMessage)
                                ? fetchResult.ErrorMessage
                                : $"Server API error: HTTP {(int?)fetchResult.StatusCode} ({fetchResult.StatusCode})"
                        };
                        SetSyncStatus(httpMsg, "#ff003c");
                        break;

                    case ServerFetchErrorKind.ParseError:
                        SetSyncStatus($"Invalid response format: {fetchResult.ErrorMessage ?? "Malformed JSON"}", "#ff003c");
                        break;

                    default:
                        SetSyncStatus(!string.IsNullOrWhiteSpace(fetchResult.ErrorMessage)
                            ? fetchResult.ErrorMessage
                            : "Failed to contact server API", "#ff003c");
                        break;
                }

                UpdateSyncVisuals();
            }
        }
        catch (Exception ex)
        {
            _logger.Warning($"Error during server connection sync: {ex.Message}");
            _activeServer = null;
            IsSynced = false;
            IsSyncError = true;
            HasSyncIssue = true;
            SetSyncStatus($"Error syncing server: {ex.Message}", "#ff003c");
            ConnectionStatusText = "UNSYNCED";
            ConnectionStatusBrush = new SolidColorBrush(Color.Parse("#ff003c"));
            UpdateSyncVisuals();
        }
        finally
        {
            _connectLock.Release();
        }
    }

    internal void OnServerConnected(ServerInfo server, string? syncStatus = null)
    {
        _activeServer = server;
        _heartbeatTimestamp = server.HeartbeatTimestamp ?? DateTimeOffset.UtcNow;
        IsSynced = true;
        IsSyncError = false;
        HasSyncIssue = false;
        UpdateSyncVisuals();

        var uState = _calc.SelectedUnit == 1 ? server.Unit1 : server.Unit2;
        _initialDtl = uState?.DemandTimeLeft ?? 0.0;
        double? curDem = uState?.Demand;
        double? nextDem = uState?.NextDemand;

        ConnectionStatusText = "SYNCED";
        ConnectionStatusBrush = new SolidColorBrush(Color.Parse("#39ff14"));

        var now = DateTimeOffset.UtcNow;
        var hb = _heartbeatTimestamp ?? now;
        double elapsed = (now - hb).TotalSeconds;
        double liveDtl = Math.Max(0.0, _initialDtl - elapsed + _settings.DtlCalibrationOffset);

        if (liveDtl > 0.0)
        {
            _zeroSecRefetchDone = false;
        }

        int thresh = _settings.NextDemandThresholdSeconds;

        if (_nextDemandSwitched)
        {
            if (nextDem.HasValue && nextDem.Value != _lastSwitchedNextDemand)
            {
                _nextDemandSwitched = false;
                _logger.Info($"New upcoming demand detected ({nextDem.Value} MWe) - updating Next Demand display.");
            }
            else if (liveDtl > thresh)
            {
                _nextDemandSwitched = false;
            }
        }

        if (_demandChangedWaitingHeartbeat)
        {
            if (curDem.HasValue && (_pendingDemandValue == null || Math.Abs(curDem.Value - _pendingDemandValue.Value) < 1.0 || curDem.Value != _lastSyncedDemand))
            {
                _demandChangedWaitingHeartbeat = false;
                _nextDemandSwitched = false;
                _lastSyncedDemand = curDem.Value;
                double calcVal = Math.Max(0.0, Math.Round(curDem.Value));
                DemandInput = ((int)calcVal).ToString(CultureInfo.InvariantCulture);
                UpdateCalculationsFromDemand(calcVal);
            }
        }
        else
        {
            if (liveDtl >= thresh)
            {
                if (curDem.HasValue && curDem.Value != _lastSyncedDemand)
                {
                    _lastSyncedDemand = curDem.Value;
                    double calcVal = Math.Max(0.0, Math.Round(curDem.Value));
                    DemandInput = ((int)calcVal).ToString(CultureInfo.InvariantCulture);
                    UpdateCalculationsFromDemand(calcVal);
                }
            }
            else
            {
                if (!_nextDemandSwitched)
                {
                    _nextDemandSwitched = true;
                    _demandChangedWaitingHeartbeat = true;
                    if (nextDem.HasValue)
                    {
                        double calcVal = Math.Max(0.0, Math.Round(nextDem.Value));
                        _lastSwitchedNextDemand = nextDem.Value;
                        _pendingDemandValue = calcVal;
                        DemandInput = ((int)calcVal).ToString(CultureInfo.InvariantCulture);
                        UpdateCalculationsFromDemand(calcVal);
                    }
                }
            }
        }

        double? tHealth = server.Unit2?.TurbineHealth ?? server.Unit1?.TurbineHealth;
        if (tHealth.HasValue)
        {
            TurbineHealthValue = Math.Clamp(tHealth.Value, 0.0, 100.0);
            TurbineHealthText = $"Turbine Health: {tHealth.Value:F1}%";
            TurbineHealthBrush = tHealth.Value > _settings.TurbineHealthThreshold
                ? new SolidColorBrush(Color.Parse("#39ff14"))
                : new SolidColorBrush(Color.Parse("#ff003c"));

            if (tHealth.Value > _settings.TurbineHealthThreshold)
            {
                _turbineAlertTriggered = false;
            }
            else if (_settings.EnableTurbineHealthAlert && !_turbineAlertTriggered)
            {
                _turbineAlertTriggered = true;
                string unitLabel = server.Unit2?.TurbineHealth != null ? "Unit 2" : "Unit 1";
                RequestShowMessage?.Invoke("TURBINE HEALTH WARNING",
                    $"{unitLabel} Turbine Health is LOW ({tHealth.Value:F1}%)!\nAlert Threshold: {_settings.TurbineHealthThreshold:F1}%.",
                    true);
            }
        }

        TickDtlCountdown();
        SetSyncStatus(syncStatus ?? "Server Synced Successfully", "#39ff14");
    }

    [RelayCommand]
    public void CalibrateDtl(object? parameter)
    {
        double seconds = 0.0;
        if (parameter is double d) seconds = d;
        else if (parameter is int i) seconds = i;
        else if (parameter is string s && double.TryParse(s, NumberStyles.Any, CultureInfo.InvariantCulture, out double parsed)) seconds = parsed;

        if (_activeServer == null) return;
        _settings.DtlCalibrationOffset += seconds;
        _settingsService.SaveSettings(_settings);
        TickDtlCountdown();
    }

    [RelayCommand]
    public void ApplyCustomCalib()
    {
        if (_activeServer == null) return;
        if (double.TryParse(CustomCalibInput.Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out double targetDtl))
        {
            double elapsed = (DateTimeOffset.UtcNow - (_heartbeatTimestamp ?? DateTimeOffset.UtcNow)).TotalSeconds;
            _settings.DtlCalibrationOffset = targetDtl - _initialDtl + elapsed;
            _settingsService.SaveSettings(_settings);
            CustomCalibInput = string.Empty;
            TickDtlCountdown();
        }
    }

    private void OnDtlTimerTick(object? sender, EventArgs e)
    {
        TickDtlCountdown();
    }

    internal void TickDtlCountdown()
    {
        if (_activeServer == null)
        {
            HeartbeatAgeText = "No Server Connected";
            UpdateSyncVisuals();
            return;
        }

        var now = DateTimeOffset.UtcNow;
        var hb = _heartbeatTimestamp ?? now;
        double elapsed = (now - hb).TotalSeconds;

        HeartbeatAgeText = elapsed < 60 ? $"Updated {elapsed:F0}s ago" : $"Updated {(elapsed / 60):F1}m ago";

        double liveDtl = Math.Max(0.0, _initialDtl - elapsed + _settings.DtlCalibrationOffset);
        DemandTimeLeftSeconds = liveDtl;
        DtlCountdownText = $"{Math.Round(liveDtl):F0}s";
        DtlProgressPercent = Math.Clamp((liveDtl / 120.0) * 100.0, 0.0, 100.0);

        if (liveDtl > 0.0)
        {
            _zeroSecRefetchDone = false;
        }

        var uState = _calc.SelectedUnit == 1 ? _activeServer.Unit1 : _activeServer.Unit2;
        double? nextDem = uState?.NextDemand;

        string formatDemand(double? dem, bool compact)
        {
            if (!dem.HasValue) return compact ? "--" : "--- MWe";
            double v = dem.Value;
            if (v == -4) return "Evac";
            if (v == -3) return "RST";
            if (v == -2) return "LOOP";
            if (v == -1) return "Maint";
            return compact ? $"{v:F0}" : $"{v:F0} MWe";
        }

        ServerDtlText = formatDemand(nextDem, false);
        CompactServerDtlText = formatDemand(nextDem, true);
        UpdateCompactCounterDisplay(liveDtl, nextDem);

        int thresh = _settings.NextDemandThresholdSeconds;

        if (_nextDemandSwitched)
        {
            if (nextDem.HasValue && nextDem.Value != _lastSwitchedNextDemand)
            {
                _nextDemandSwitched = false;
            }
            else if (liveDtl > thresh)
            {
                _nextDemandSwitched = false;
            }
        }

        if (liveDtl <= thresh && !_nextDemandSwitched)
        {
            _nextDemandSwitched = true;
            _demandChangedWaitingHeartbeat = true;
            if (nextDem.HasValue)
            {
                double calcVal = Math.Max(0.0, Math.Round(nextDem.Value));
                _lastSwitchedNextDemand = nextDem.Value;
                _pendingDemandValue = calcVal;
                DemandInput = ((int)calcVal).ToString(CultureInfo.InvariantCulture);
                UpdateCalculationsFromDemand(calcVal);
            }
            _ = ConnectServerAsync(CurrentJobId);
        }

        if (liveDtl <= 0.0 && !_zeroSecRefetchDone)
        {
            _zeroSecRefetchDone = true;
            _demandChangedWaitingHeartbeat = true;
            if (nextDem.HasValue)
            {
                double calcVal = Math.Max(0.0, Math.Round(nextDem.Value));
                _lastSwitchedNextDemand = nextDem.Value;
                _pendingDemandValue = calcVal;
                DemandInput = ((int)calcVal).ToString(CultureInfo.InvariantCulture);
                UpdateCalculationsFromDemand(calcVal);
            }
            _ = ConnectServerAsync(CurrentJobId);
        }

        if (_nextDemandSwitched && (DateTime.UtcNow - _lastServerPollTime).TotalSeconds >= 10.0)
        {
            _lastServerPollTime = DateTime.UtcNow;
            _ = ConnectServerAsync(CurrentJobId);
        }
    }

    private void SetSyncStatus(string msg, string hexColor)
    {
        SyncStatusMessage = msg;
        SyncStatusBrush = new SolidColorBrush(Color.Parse(hexColor));
    }


    partial void OnOverlayOpacityChanged(double value)
    {
        _settings.Opacity = Math.Clamp(value, 0.20, 1.00);
        _settingsService.SaveSettings(_settings);
    }

    [RelayCommand]
    public void ToggleRobloxTopmost()
    {
        TopmostOnRoblox = !TopmostOnRoblox;
        _settings.TopmostOnRoblox = TopmostOnRoblox;
        UpdateSettingsVisuals();
        _settingsService.SaveSettings(_settings);
    }

    [RelayCommand]
    public void ToggleTurbineAlertSetting()
    {
        EnableTurbineHealthAlert = !EnableTurbineHealthAlert;
        _settings.EnableTurbineHealthAlert = EnableTurbineHealthAlert;
        UpdateSettingsVisuals();
        _settingsService.SaveSettings(_settings);
    }

    partial void OnDemandThresholdSecondsInputChanged(string value)
    {
        if (int.TryParse(value, out int thresh))
        {
            _settings.NextDemandThresholdSeconds = Math.Max(0, thresh);
            _settingsService.SaveSettings(_settings);
        }
    }

    partial void OnTurbineHealthThresholdInputChanged(string value)
    {
        if (double.TryParse(value, NumberStyles.Any, CultureInfo.InvariantCulture, out double thresh))
        {
            _settings.TurbineHealthThreshold = Math.Clamp(thresh, 0.0, 100.0);
            _settingsService.SaveSettings(_settings);
        }
    }

    partial void OnRecircOverrideInputChanged(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            _calc.RecircOverride = null;
        }
        else if (double.TryParse(value, NumberStyles.Any, CultureInfo.InvariantCulture, out double v))
        {
            _calc.RecircOverride = Math.Clamp(v, 0.0, 100.0);
        }

        UpdateRecircIndicator();
        if (double.TryParse(DemandInput, NumberStyles.Any, CultureInfo.InvariantCulture, out double dVal))
        {
            UpdateCalculationsFromDemand(dVal);
        }
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
    public async Task SubmitFeedbackAsync()
    {
        if (IsSubmittingFeedback) return;

        if (string.IsNullOrWhiteSpace(FeedbackContent))
        {
            FeedbackStatusMessage = "Error: Suggestion text cannot be empty.";
            FeedbackStatusBrush = new SolidColorBrush(Color.Parse("#ff003c"));
            return;
        }

        IsSubmittingFeedback = true;
        FeedbackStatusMessage = "Transmitting to RBWR server...";
        FeedbackStatusBrush = new SolidColorBrush(Color.Parse("#00f0ff"));

        bool success = await _apiClient.SubmitSuggestionAsync(FeedbackAuthor, FeedbackContent, FeedbackIsAnonymous);
        IsSubmittingFeedback = false;

        if (success)
        {
            FeedbackStatusMessage = "Feedback submitted successfully!";
            FeedbackStatusBrush = new SolidColorBrush(Color.Parse("#39ff14"));
            FeedbackContent = string.Empty;
        }
        else
        {
            FeedbackStatusMessage = "Error: Failed to reach feedback server.";
            FeedbackStatusBrush = new SolidColorBrush(Color.Parse("#ff003c"));
        }
    }


    [RelayCommand]
    public async Task CheckUpdatesAsync()
    {
        UpdateStatusText = "Checking for latest release...";
        var info = await _apiClient.CheckForUpdatesAsync(AppVersion, _settings.SkippedVersion);
        if (info.IsAvailable)
        {
            IsUpdateAvailable = true;
            LatestVersionText = $"Version {info.Version} is available!";
            ReleaseNotesText = info.ReleaseNotes;
            DownloadUrl = info.DownloadUrl;
            DownloadFileName = info.FileName;
            UpdateStatusText = "Update ready to install.";
        }
        else
        {
            IsUpdateAvailable = false;
            UpdateStatusText = $"Application is up to date (v{AppVersion}).";
        }
    }

    [RelayCommand]
    public async Task UpdateNowAsync()
    {
        if (string.IsNullOrEmpty(DownloadUrl)) return;

        UpdateStatusText = "Downloading update package...";
        try
        {
            string currentExe = Process.GetCurrentProcess().MainModule?.FileName ?? AppDomain.CurrentDomain.BaseDirectory;
            string exeDir = Path.GetDirectoryName(currentExe) ?? AppDomain.CurrentDomain.BaseDirectory;
            string newExePath = Path.Combine(exeDir, string.IsNullOrEmpty(DownloadFileName) ? $"RBWR_APRM_Calculator_v{LatestVersionText}.exe" : DownloadFileName);

            await _apiClient.DownloadUpdateAsync(DownloadUrl, newExePath);

            UpdateStatusText = "Restarting into updated version...";
            await Task.Delay(1000);

            if (OperatingSystem.IsWindows())
            {
                string cmdScript = $"timeout /t 2 /nobreak && del \"{currentExe}\" && start \"\" \"{newExePath}\"";
                Process.Start(new ProcessStartInfo
                {
                    FileName = "cmd.exe",
                    Arguments = $"/c {cmdScript}",
                    CreateNoWindow = true,
                    UseShellExecute = false
                });
            }
            else
            {
                Process.Start(new ProcessStartInfo(newExePath) { UseShellExecute = true });
            }

            Environment.Exit(0);
        }
        catch (Exception ex)
        {
            _logger.Error("Self-update failed", ex);
            UpdateStatusText = $"Update failed: {ex.Message}";
        }
    }


    private void OnRobloxActiveChanged(object? sender, bool isRoblox)
    {
        if (TopmostOnRoblox)
        {
            IsTopmost = isRoblox;
            UpdatePinSymbol();
        }
    }

    private void UpdatePinSymbol()
    {
        PinSymbol = IsTopmost ? "UNPIN" : "PIN";
    }

    private void UpdateSyncVisuals()
    {
        if (_activeServer == null)
        {
            HasSyncIssue = true;
            if (ConnectionStatusText == "RETRYING")
            {
                CompactErrorIndicatorBrush = new SolidColorBrush(Color.Parse("#ffaa00"));
                CompactCounterBrush = new SolidColorBrush(Color.Parse("#ffaa00"));
                ServerDtlBrush = new SolidColorBrush(Color.Parse("#ffaa00"));
                ServerDtlText = "RETRY";
                CompactServerDtlText = "RETRY";
                CompactCounterTooltip = string.IsNullOrWhiteSpace(SyncStatusMessage)
                    ? "Connection lost. Retrying server connection..."
                    : SyncStatusMessage;
                CompactDisplayCounterText = "...";
            }
            else if (IsSyncError)
            {
                CompactErrorIndicatorBrush = new SolidColorBrush(Color.Parse("#ff003c"));
                CompactCounterBrush = new SolidColorBrush(Color.Parse("#ff003c"));
                ServerDtlBrush = new SolidColorBrush(Color.Parse("#ff003c"));
                ServerDtlText = "ERR";
                CompactServerDtlText = "ERR";
                CompactCounterTooltip = string.IsNullOrWhiteSpace(SyncStatusMessage)
                    ? "Sync Error. Click to toggle target/countdown or check Server Sync tab."
                    : $"Sync Error: {SyncStatusMessage}. Click to toggle target/countdown or check Server Sync tab.";
                CompactDisplayCounterText = ShowNextDemandInCompact ? "-- MW" : "--s";
            }
            else
            {
                CompactErrorIndicatorBrush = new SolidColorBrush(Color.Parse("#ffaa00"));
                CompactCounterBrush = new SolidColorBrush(Color.Parse("#73839c"));
                ServerDtlBrush = new SolidColorBrush(Color.Parse("#73839c"));
                ServerDtlText = "---";
                CompactServerDtlText = "--";
                CompactCounterTooltip = ShowNextDemandInCompact
                    ? "Next Demand target (Not Synced). Click to switch to countdown or open Server Sync tab."
                    : "Demand Time Left countdown (Not Synced). Click to switch to Next Demand or open Server Sync tab.";
                CompactDisplayCounterText = ShowNextDemandInCompact ? "-- MW" : "--s";
            }
        }
        else
        {
            HasSyncIssue = false;
            CompactErrorIndicatorBrush = new SolidColorBrush(Color.Parse("#ffaa00"));
            CompactCounterBrush = new SolidColorBrush(Color.Parse("#ffaa00"));
            ServerDtlBrush = new SolidColorBrush(Color.Parse("#ffaa00"));
        }
    }

    private void UpdateCompactCounterDisplay(double liveDtl, double? nextDem)
    {
        if (_activeServer == null)
        {
            UpdateSyncVisuals();
            return;
        }

        HasSyncIssue = false;
        CompactCounterBrush = new SolidColorBrush(Color.Parse("#ffaa00"));
        ServerDtlBrush = new SolidColorBrush(Color.Parse("#ffaa00"));

        if (ShowNextDemandInCompact)
        {
            string formattedNext = nextDem.HasValue
                ? (nextDem.Value switch
                {
                    -4 => "Evac",
                    -3 => "RST",
                    -2 => "LOOP",
                    -1 => "Maint",
                    _ => $"{nextDem.Value:F0} MW"
                })
                : "-- MW";

            CompactDisplayCounterText = formattedNext;
            CompactCounterTooltip = "Next Demand Target. Click to switch to Demand Time Left (DTL) countdown.";
        }
        else
        {
            CompactDisplayCounterText = $"{Math.Round(liveDtl):F0}s";
            CompactCounterTooltip = "Demand Time Left countdown. Click to switch to Next Demand target.";
        }
    }

    [RelayCommand]
    public void ToggleCompactCounter()
    {
        ShowNextDemandInCompact = !ShowNextDemandInCompact;

        if (_activeServer != null)
        {
            var now = DateTimeOffset.UtcNow;
            var hb = _heartbeatTimestamp ?? now;
            double elapsed = (now - hb).TotalSeconds;
            double liveDtl = Math.Max(0.0, _initialDtl - elapsed + _settings.DtlCalibrationOffset);
            var uState = _calc.SelectedUnit == 1 ? _activeServer.Unit1 : _activeServer.Unit2;
            UpdateCompactCounterDisplay(liveDtl, uState?.NextDemand);
        }
        else
        {
            UpdateSyncVisuals();
        }
    }

    private void UpdateUnitVisuals()
    {
        IsUnit1Active = SelectedUnit == 1;
        IsUnit2Active = SelectedUnit == 2;
        UnitSuffix = SelectedUnit == 1 ? "APRM" : "RTP";
    }

    private void UpdateSettingsVisuals()
    {
        TopmostStatusText = TopmostOnRoblox ? "ENABLED" : "DISABLED";
        TopmostStatusBrush = TopmostOnRoblox ? new SolidColorBrush(Color.Parse("#39ff14")) : new SolidColorBrush(Color.Parse("#ff003c"));

        TurbineAlertStatusText = EnableTurbineHealthAlert ? "ENABLED" : "DISABLED";
        TurbineAlertStatusBrush = EnableTurbineHealthAlert ? new SolidColorBrush(Color.Parse("#39ff14")) : new SolidColorBrush(Color.Parse("#ff003c"));
    }

    public void Dispose()
    {
        if (_isDisposed) return;
        _isDisposed = true;
        _connectLock.Dispose();
        _dtlTimer.Stop();
        _processMonitor.RobloxActiveChanged -= OnRobloxActiveChanged;
        _processMonitor.Dispose();
        GC.SuppressFinalize(this);
    }
}