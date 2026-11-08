using System.Collections.ObjectModel;
using System.Globalization;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using RbwrOverlay.Core.Models;
using RbwrOverlay.Core.Services;
using RbwrOverlay.Platform;
using RbwrOverlay.UI.Tablet.Models;
using RbwrOverlay.UI.Tablet.Services;

namespace RbwrOverlay.UI.Tablet.ViewModels;

public partial class TabletViewModel : ObservableObject, IDisposable
{
    private readonly ILoggingService _logger;
    private readonly AppSettings _settings;
    private readonly ISettingsService _settingsService;
    private readonly IProcessMonitor _monitor;
    private readonly Func<string> _getJobId;
    private readonly TabletApiClient _api = new();
    private readonly DispatcherTimer _pollTimer;
    private readonly DispatcherTimer _tickTimer;
    private readonly SemaphoreSlim _refreshLock = new(1, 1);

    private List<TabletServer> _servers = new();
    private string? _lastError;
    private int _dtlUnit = 1;
    private bool _topmostFromRoblox;

    private bool _nextDemandSwitched;
    private bool _zeroRefetchDone;
    private double? _switchedFromDemand;
    private double? _switchedNextDemand;

    [ObservableProperty] private string _selectedTab = "u1";
    [ObservableProperty] private string _searchText = string.Empty;
    [ObservableProperty] private bool _isTopmost;
    [ObservableProperty] private bool _isHudStyle;
    [ObservableProperty] private bool _topmostOnRoblox;
    [ObservableProperty] private double _uiScale = 1.0;
    [ObservableProperty] private double _uiScalePreview = 1.0;
    [ObservableProperty] private string _emptyTitle = string.Empty;
    [ObservableProperty] private string _emptyPrefix = string.Empty;
    [ObservableProperty] private string _emptyJobId = string.Empty;
    [ObservableProperty] private string _emptySuffix = string.Empty;

    public ObservableCollection<TabletRow> Rows { get; } = new();

    public bool IsU1 => SelectedTab == "u1";
    public bool IsU2 => SelectedTab == "u2";
    public bool IsMisc => SelectedTab == "misc";
    public bool IsClassicStyle => !IsHudStyle;
    public bool IsConfig => SelectedTab == "config";
    public bool IsDataTab => !IsConfig;
    private bool IsUnitTab => SelectedTab is "u1" or "u2";
    public bool HasEmptyText => !string.IsNullOrEmpty(EmptyTitle);
    public bool HasEmptyJobId => !string.IsNullOrEmpty(EmptyJobId);
    public string PinLabel => IsTopmost ? "UNPIN" : "PIN";
    public string RobloxTopmostLabel => TopmostOnRoblox ? "TOPMOST ON ROBLOX: ON" : "TOPMOST ON ROBLOX: OFF";
    public string UiScaleText => $"{UiScalePreview:P0}";

    public string CurrentJobId { get; private set; } = string.Empty;

    public TabletViewModel(AppSettings settings, ISettingsService settingsService, IProcessMonitor monitor,
                           ILoggingService logger, Func<string> getJobId)
    {
        _settings = settings;
        _settingsService = settingsService;
        _monitor = monitor;
        _logger = logger;
        _getJobId = getJobId;

        _isTopmost = settings.TabletTopmost;
        _isHudStyle = settings.TabletHudStyle;
        _topmostOnRoblox = settings.TabletTopmostOnRoblox;
        _uiScale = Math.Clamp(settings.TabletUiScale <= 0 ? 1.0 : settings.TabletUiScale, 0.75, 2.0);
        _uiScalePreview = _uiScale;
        CurrentJobId = getJobId().Trim();

        _monitor.RobloxActiveChanged += OnRobloxActiveChanged;

        _pollTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(10) };
        _pollTimer.Tick += async (_, _) => await RefreshAsync();
        _pollTimer.Start();

        _tickTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        _tickTimer.Tick += (_, _) => Tick();
        _tickTimer.Start();

        _ = RefreshAsync();
    }

    private void SaveSettings() => _settingsService.SaveSettings(_settings);

    partial void OnSelectedTabChanged(string value)
    {
        int prevUnit = _dtlUnit;
        if (value == "u1") _dtlUnit = 1;
        else if (value == "u2") _dtlUnit = 2;
        if (prevUnit != _dtlUnit) ResetDemandSwitch();

        OnPropertyChanged(nameof(IsU1));
        OnPropertyChanged(nameof(IsU2));
        OnPropertyChanged(nameof(IsMisc));
        OnPropertyChanged(nameof(IsConfig));
        OnPropertyChanged(nameof(IsDataTab));
        SearchText = string.Empty;
        BuildRows();
    }

    partial void OnSearchTextChanged(string value) => BuildRows();
    partial void OnEmptyTitleChanged(string value) => OnPropertyChanged(nameof(HasEmptyText));
    partial void OnEmptyJobIdChanged(string value) => OnPropertyChanged(nameof(HasEmptyJobId));

    private void SetEmpty(string title, string prefix, string jobId = "", string suffix = "")
    {
        EmptyTitle = title;
        EmptyPrefix = prefix;
        EmptyJobId = jobId;
        EmptySuffix = suffix;
    }

    [RelayCommand] private void SwitchTab(string tab) => SelectedTab = tab;

    [RelayCommand] private void SetStyle(string style) => IsHudStyle = style == "hud";

    partial void OnIsHudStyleChanged(bool value)
    {
        OnPropertyChanged(nameof(IsClassicStyle));
        _settings.TabletHudStyle = value;
        SaveSettings();
    }

    [RelayCommand] private void TogglePin() => IsTopmost = !IsTopmost;
    [RelayCommand] private void ToggleRobloxTopmost() => TopmostOnRoblox = !TopmostOnRoblox;

    partial void OnIsTopmostChanged(bool value)
    {
        OnPropertyChanged(nameof(PinLabel));
        if (_topmostFromRoblox) return;
        _settings.TabletTopmost = value;
        SaveSettings();
    }

    private void OnRobloxActiveChanged(object? sender, bool isRoblox)
    {
        Dispatcher.UIThread.Post(() =>
        {
            if (!TopmostOnRoblox) return;
            _topmostFromRoblox = true;
            try { IsTopmost = isRoblox; }
            finally { _topmostFromRoblox = false; }
        });
    }

    partial void OnTopmostOnRobloxChanged(bool value)
    {
        OnPropertyChanged(nameof(RobloxTopmostLabel));
        _settings.TabletTopmostOnRoblox = value;
        if (!value)
        {
            _topmostFromRoblox = true;
            try { IsTopmost = _settings.TabletTopmost; }
            finally { _topmostFromRoblox = false; }
        }
        SaveSettings();
    }

    partial void OnUiScaleChanged(double value)
    {
        double v = Math.Clamp(Math.Round(value, 2), 0.75, 2.0);
        if (v != value) { UiScale = v; return; }
        UiScalePreview = v;
        _settings.TabletUiScale = v;
        SaveSettings();
    }

    partial void OnUiScalePreviewChanged(double value) => OnPropertyChanged(nameof(UiScaleText));

    public void CommitUiScale() => UiScale = UiScalePreview;

    [RelayCommand]
    private void SetUiScale(string scale)
    {
        if (double.TryParse(scale, NumberStyles.Any, CultureInfo.InvariantCulture, out double s)) UiScale = s;
    }

    private TabletServer? ActiveServer() =>
        string.IsNullOrEmpty(CurrentJobId) ? null : TabletApiClient.Find(_servers, CurrentJobId);

    public async Task RefreshAsync()
    {
        if (!await _refreshLock.WaitAsync(0)) return;
        try
        {
            CurrentJobId = _getJobId().Trim();
            var result = await _api.GetServersAsync();
            if (result.Ok)
            {
                _servers = result.Servers;
                _lastError = null;
            }
            else
            {
                _lastError = result.Error;
                _logger.Warning($"Tablet server fetch failed: {result.Error}");
            }
            BuildRows();
        }
        finally
        {
            _refreshLock.Release();
        }
    }

    private double? LiveDtl()
    {
        var srv = ActiveServer();
        if (srv == null) return null;
        var init = TabletServer.DemandTimeLeft(_dtlUnit == 2 ? srv.Unit2 : srv.Unit1);
        if (init is not double d) return null;
        double elapsed = srv.Heartbeat is DateTimeOffset hb ? (DateTimeOffset.UtcNow - hb).TotalSeconds : 0;
        return Math.Max(0.0, d - elapsed + _settings.DtlCalibrationOffset);
    }

    private (double? Cur, double? Next) UnitDemands()
    {
        var srv = ActiveServer();
        if (srv == null) return (null, null);
        var unit = _dtlUnit == 2 ? srv.Unit2 : srv.Unit1;
        string sfx = _dtlUnit == 2 ? "U2" : "U1";
        return (TabletServer.Num(unit, "Demand" + sfx), TabletServer.Num(unit, "NextDemand" + sfx));
    }

    private void ResetDemandSwitch()
    {
        _nextDemandSwitched = false;
        _zeroRefetchDone = false;
        _switchedFromDemand = _switchedNextDemand = null;
    }

    private void Tick()
    {
        string job = _getJobId().Trim();
        if (!string.Equals(job, CurrentJobId, StringComparison.Ordinal))
        {
            CurrentJobId = job;
            ResetDemandSwitch();
            BuildRows();
            _ = RefreshAsync();
        }

        double? live = LiveDtl();
        RunDemandSwitchLogic(live);

        if (IsUnitTab && live is double lv)
        {
            string txt = ((int)Math.Round(lv)).ToString(CultureInfo.InvariantCulture);
            for (int i = 0; i < Rows.Count; i++)
            {
                if (Rows[i].Label == "Demand Time Left" && Rows[i].Value != txt)
                    Rows[i] = Rows[i] with { Value = txt };
            }
        }
    }

    private void RunDemandSwitchLogic(double? live)
    {
        if (live is not double dtl) { ResetDemandSwitch(); return; }
        var (cur, next) = UnitDemands();
        int thresh = _settings.NextDemandThresholdSeconds;

        if (dtl > 0) _zeroRefetchDone = false;

        if (_nextDemandSwitched && (dtl > thresh || (next.HasValue && next != _switchedNextDemand)))
        {
            ResetDemandSwitch();
            BuildRows();
        }

        if (dtl <= thresh && !_nextDemandSwitched)
        {
            _nextDemandSwitched = true;
            _switchedFromDemand = cur;
            _switchedNextDemand = next;
            BuildRows();
            _ = RefreshAsync();
        }

        if (dtl <= 0 && !_zeroRefetchDone)
        {
            _zeroRefetchDone = true;
            _ = RefreshAsync();
        }
    }

    private void BuildRows()
    {
        Rows.Clear();
        SetEmpty(string.Empty, string.Empty);
        if (!IsDataTab) return;

        var srv = ActiveServer();
        if (srv == null)
        {
            if (string.IsNullOrEmpty(CurrentJobId))
                SetEmpty("No Server Selected", "Sync a server in the overlay (Server Sync tab) to see its data here.");
            else if (_lastError != null && _servers.Count == 0)
                SetEmpty("Cannot Reach Server API", $"Request failed: {_lastError}");
            else
                SetEmpty("Job ID Not Found in Server Data", "The Job ID or Server ID ", CurrentJobId,
                         " was not found in active server data. Sync an active server in the overlay.");
            return;
        }

        var (fields, data) = SelectedTab switch
        {
            "u2" => (TabletFields.Unit2, srv.Unit2),
            "misc" => (TabletFields.Misc, srv.Misc),
            _ => (TabletFields.Unit1, srv.Unit1),
        };

        string q = SearchText.Trim();
        foreach (var f in fields)
        {
            if (q.Length > 0 &&
                !f.Label.Contains(q, StringComparison.OrdinalIgnoreCase) &&
                !f.Key.Contains(q, StringComparison.OrdinalIgnoreCase))
                continue;

            string val = TabletFields.Format(f, data);
            if (f.Label == "Demand Time Left" && IsUnitTab && LiveDtl() is double liveDtl)
                val = ((int)Math.Round(liveDtl)).ToString(CultureInfo.InvariantCulture);

            if (_nextDemandSwitched && f.Label == "Demand" && IsUnitTab &&
                _switchedNextDemand.HasValue && TabletServer.Num(data, f.Key) == _switchedFromDemand)
            {
                var nf = fields.First(x => x.Label == "Next Demand");
                val = TabletFields.Format(nf, data);
            }
            Rows.Add(new TabletRow(f.Label, val));
        }

        if (Rows.Count == 0) SetEmpty("No Matching Parameters", "No parameters match ", q);
    }

    public void Dispose()
    {
        _pollTimer.Stop();
        _tickTimer.Stop();
        _monitor.RobloxActiveChanged -= OnRobloxActiveChanged;
        _api.Dispose();
    }
}
