using RbwrOverlay.Core.Models;
using RbwrOverlay.Core.Services;
using RbwrOverlay.Platform;
using RbwrOverlay.UI.ViewModels;
using Xunit;

namespace RbwrOverlay.Tests;

public class ViewModelTests
{
    private class DummySettingsService : ISettingsService
    {
        public AppSettings Settings { get; set; } = new();

        public AppSettings LoadSettings() => Settings;
        public void SaveSettings(AppSettings settings) => Settings = settings;
    }


    private class DummyProcessMonitor : IProcessMonitor
    {
        public bool IsRobloxActive => false;
#pragma warning disable CS0067
        public event EventHandler<bool>? RobloxActiveChanged;
#pragma warning restore CS0067
        public void StartMonitoring() { }
        public void StopMonitoring() { }
        public string GetForegroundWindowInfo() => "RobloxPlayerBeta";
        public void Dispose() { }
    }

    private static MainOverlayViewModel CreateTestVm(DummySettingsService? settings = null)
    {
        settings ??= new DummySettingsService();
        var processMonitor = new DummyProcessMonitor();
        var logger = LoggingService.Instance;
        return new MainOverlayViewModel(settings, null, processMonitor, logger);
    }

    [Fact]
    public void TestTabSwitching()
    {
        var vm = CreateTestVm();
        
        Assert.True(vm.IsMonitorTabActive);
        Assert.False(vm.IsSyncTabActive);

        vm.SwitchTab("Sync");
        Assert.False(vm.IsMonitorTabActive);
        Assert.True(vm.IsSyncTabActive);

        vm.SwitchTab("Settings");
        Assert.True(vm.IsSettingsTabActive);
        Assert.False(vm.IsSyncTabActive);

        vm.SwitchTab("Feedback");
        Assert.True(vm.IsFeedbackTabActive);
        Assert.False(vm.IsSettingsTabActive);

        vm.SwitchTab("Monitor");
        Assert.True(vm.IsMonitorTabActive);
        Assert.False(vm.IsFeedbackTabActive);
    }

    [Fact]
    public void TestUnitSwitching()
    {
        var vm = CreateTestVm();
        
        Assert.True(vm.IsUnit1Active);
        Assert.False(vm.IsUnit2Active);
        Assert.Equal("APRM", vm.UnitSuffix);

        vm.SelectUnit("2");
        Assert.False(vm.IsUnit1Active);
        Assert.True(vm.IsUnit2Active);
        Assert.Equal("RTP", vm.UnitSuffix);

        vm.SelectUnit(1);
        Assert.True(vm.IsUnit1Active);
        Assert.False(vm.IsUnit2Active);
        Assert.Equal("APRM", vm.UnitSuffix);
    }

    [Fact]
    public void TestDemandAdjustmentsAndPresets()
    {
        var vm = CreateTestVm();
        
        vm.SetPresetDemand("40");
        Assert.Equal("40", vm.DemandInput);
        Assert.False(vm.IsError);
        Assert.True(vm.ThermalPowerPercent > 0);

        vm.AdjustDemand("10");
        Assert.Equal("50", vm.DemandInput);

        vm.AdjustDemand("-20");
        Assert.Equal("30", vm.DemandInput);

        vm.AdjustDemand("-50");
        Assert.Equal("0", vm.DemandInput);
        Assert.False(vm.IsError);
    }

    [Fact]
    public void TestOverpowerRiskDetection()
    {
        var vm = CreateTestVm();

        vm.UpdateCalculationsFromDemand(50.0);
        Assert.False(vm.IsOverpowerRisk);

        vm.UpdateCalculationsFromDemand(1600.0);
        Assert.True(vm.IsOverpowerRisk);
        Assert.Contains("SCRAM OVERPOWER RISK", vm.MainStatusSubText);
    }

    [Fact]
    public void TestCompactModeToggle()
    {
        var settingsService = new DummySettingsService();
        var vm = CreateTestVm(settingsService);

        Assert.False(vm.IsCompact);
        vm.ToggleCompact();
        Assert.True(vm.IsCompact);
        Assert.True(settingsService.Settings.IsCompact);

        vm.ToggleCompact();
        Assert.False(vm.IsCompact);
        Assert.False(settingsService.Settings.IsCompact);
    }

    [Fact]
    public void TestTopmostToggle()
    {
        var settingsService = new DummySettingsService();
        settingsService.Settings.IsTopmost = true;
        var vm = CreateTestVm(settingsService);

        Assert.True(vm.IsTopmost);
        Assert.Equal("UNPIN", vm.PinSymbol);
        vm.ToggleTopmost();
        Assert.False(vm.IsTopmost);
        Assert.Equal("PIN", vm.PinSymbol);
        Assert.False(settingsService.Settings.IsTopmost);
    }

    [Fact]
    public void TestRecircOverrideAndReset()
    {
        var vm = CreateTestVm();
        
        vm.RecircOverrideInput = "75";
        Assert.True(vm.IsRecircOverrideActive);
        Assert.Contains("OVR: 75%", vm.RecircIndicatorText);

        vm.ResetRecircOverride();
        Assert.False(vm.IsRecircOverrideActive);
        Assert.Equal(string.Empty, vm.RecircIndicatorText);
        Assert.Equal(string.Empty, vm.RecircOverrideInput);
    }

    [Fact]
    public void TestToggleCompactCounter()
    {
        var vm = CreateTestVm();
        Assert.False(vm.ShowNextDemandInCompact);

        vm.ToggleCompactCounter();
        Assert.True(vm.ShowNextDemandInCompact);
        Assert.Contains("MW", vm.CompactDisplayCounterText);

        vm.ToggleCompactCounter();
        Assert.False(vm.ShowNextDemandInCompact);
        Assert.Contains("s", vm.CompactDisplayCounterText);
    }

    [Fact]
    public void TestUiScaleAndPresets()
    {
        var settingsService = new DummySettingsService();
        var vm = CreateTestVm(settingsService);

        Assert.Equal(1.0, vm.UiScale);
        Assert.Equal(1.0, vm.UiScalePreview);

        vm.UiScale = 1.25;
        Assert.Equal(1.25, vm.UiScale);
        Assert.Equal(1.25, vm.UiScalePreview);
        Assert.Equal(1.25, settingsService.Settings.UiScale);

        vm.SetUiScalePreset("1.5");
        Assert.Equal(1.5, vm.UiScale);
        Assert.Equal(1.5, vm.UiScalePreview);
        Assert.Equal(1.5, settingsService.Settings.UiScale);

        vm.SetUiScalePreset("5.0");
        Assert.Equal(3.0, vm.UiScale);

        vm.SetUiScalePreset("0.1");
        Assert.Equal(0.5, vm.UiScale);
    }

    [Fact]
    public void TestCompactUiScaleAndPresets()
    {
        var settingsService = new DummySettingsService();
        var vm = CreateTestVm(settingsService);

        Assert.Equal(1.0, vm.CompactUiScale);
        Assert.Equal(1.0, vm.CompactUiScalePreview);

        vm.CompactUiScale = 1.25;
        Assert.Equal(1.25, vm.CompactUiScale);
        Assert.Equal(1.25, vm.CompactUiScalePreview);
        Assert.Equal(1.25, settingsService.Settings.CompactUiScale);
        Assert.Equal(1.0, vm.UiScale);

        vm.SetCompactUiScalePreset("1.5");
        Assert.Equal(1.5, vm.CompactUiScale);
        Assert.Equal(1.5, vm.CompactUiScalePreview);
        Assert.Equal(1.5, settingsService.Settings.CompactUiScale);

        vm.SetCompactUiScalePreset("5.0");
        Assert.Equal(3.0, vm.CompactUiScale);

        vm.SetCompactUiScalePreset("0.1");
        Assert.Equal(0.5, vm.CompactUiScale);
    }

    [Fact]
    public void TestSliderDragAndCommitOnLetGo()
    {
        var settingsService = new DummySettingsService();
        var vm = CreateTestVm(settingsService);

        vm.CompactUiScalePreview = 1.35;
        Assert.Equal(1.0, vm.CompactUiScale);
        Assert.Equal(1.0, settingsService.Settings.CompactUiScale);

        vm.CommitCompactUiScale();
        Assert.Equal(1.35, vm.CompactUiScale);
        Assert.Equal(1.35, settingsService.Settings.CompactUiScale);

        vm.UiScalePreview = 1.75;
        Assert.Equal(1.0, vm.UiScale);
        Assert.Equal(1.0, settingsService.Settings.UiScale);

        vm.CommitUiScale();
        Assert.Equal(1.75, vm.UiScale);
        Assert.Equal(1.75, settingsService.Settings.UiScale);
    }

    [Fact]
    public void TestActiveUiScaleSwitching()
    {
        var settingsService = new DummySettingsService();
        var vm = CreateTestVm(settingsService);

        vm.UiScale = 1.25;
        vm.CompactUiScale = 0.85;

        vm.IsCompact = false;
        Assert.Equal(1.25, vm.ActiveUiScale);

        vm.IsCompact = true;
        Assert.Equal(0.85, vm.ActiveUiScale);

        vm.ToggleCompact();
        Assert.False(vm.IsCompact);
        Assert.Equal(1.25, vm.ActiveUiScale);
    }

    [Fact]
    public void TestDemandSwitchAt60sAnd0sCalculatedDtl()
    {
        var settingsService = new DummySettingsService();
        settingsService.Settings.NextDemandThresholdSeconds = 60;
        var vm = CreateTestVm(settingsService);

        var server = new ServerInfo
        {
            JobId = "test-job-id",
            HeartbeatTimestamp = DateTimeOffset.UtcNow,
            Unit1 = new UnitState
            {
                Demand = 500,
                NextDemand = 800,
                DemandTimeLeft = 100
            }
        };

        // 1. Initial connect at 100s DTL (> 60s threshold): Demand should be current demand (500)
        vm.OnServerConnected(server);
        Assert.Equal("500", vm.DemandInput);

        // 2. Ticking DTL when calculated DTL > 60s (e.g. 70s via -30s offset): Demand remains 500
        vm.CalibrateDtl(-30.0);
        Assert.Equal("500", vm.DemandInput);
        Assert.Equal("70s", vm.DtlCountdownText);

        // 3. Ticking DTL when calculated DTL reaches 60s (e.g. 59s via -11s offset): Demand switches to NextDemand (800)
        vm.CalibrateDtl(-11.0); // total offset is -41s -> 100 - 41 = 59s
        Assert.Equal("800", vm.DemandInput);
        Assert.Equal("59s", vm.DtlCountdownText);

        // 4. At 0s DTL (via -60s additional offset -> 0s), demand is set again to NextDemand (800)
        vm.DemandInput = "600";
        vm.CalibrateDtl(-60.0); // liveDtl becomes 0s
        Assert.Equal("800", vm.DemandInput);
        Assert.Equal("0s", vm.DtlCountdownText);

        // 5. When new heartbeat arrives with updated current demand (800) and new upcoming demand (950) with reset DTL (120s):
        settingsService.Settings.DtlCalibrationOffset = 0.0;
        var updatedServer = new ServerInfo
        {
            JobId = "test-job-id",
            HeartbeatTimestamp = DateTimeOffset.UtcNow,
            Unit1 = new UnitState
            {
                Demand = 800,
                NextDemand = 950,
                DemandTimeLeft = 120
            }
        };
        vm.OnServerConnected(updatedServer);
        Assert.Equal("800", vm.DemandInput);
        Assert.Equal("950 MWe", vm.ServerDtlText);
    }

    [Fact]
    public async Task TestNextDemandButtonSyncErrorIndicators()
    {
        var dummyApi = new DummyApiClient();
        var settingsService = new DummySettingsService();
        var vm = new MainOverlayViewModel(settingsService, dummyApi, new DummyProcessMonitor(), LoggingService.Instance);

        // 1. Initial / Unsynced state
        Assert.True(vm.HasSyncIssue);
        Assert.False(vm.IsSynced);
        Assert.False(vm.IsSyncError);
        Assert.Contains("Not Synced", vm.CompactCounterTooltip);
        Assert.Equal("--s", vm.CompactDisplayCounterText);
        Assert.Equal("---", vm.ServerDtlText);

        // Toggle counter in unsynced state keeps HasSyncIssue = true
        vm.ToggleCompactCounter();
        Assert.True(vm.HasSyncIssue);
        Assert.Equal("-- MW", vm.CompactDisplayCounterText);
        Assert.Contains("Not Synced", vm.CompactCounterTooltip);

        // 2. Connected state
        var server = new ServerInfo
        {
            JobId = "job-123",
            HeartbeatTimestamp = DateTimeOffset.UtcNow,
            Unit1 = new UnitState
            {
                Demand = 500,
                NextDemand = 800,
                DemandTimeLeft = 100
            }
        };
        vm.OnServerConnected(server);
        Assert.False(vm.HasSyncIssue);
        Assert.True(vm.IsSynced);
        Assert.False(vm.IsSyncError);
        Assert.Equal("800 MW", vm.CompactDisplayCounterText);
        Assert.Contains("Next Demand Target", vm.CompactCounterTooltip);

        // Toggle counter in synced state switches to countdown
        vm.ToggleCompactCounter();
        Assert.False(vm.HasSyncIssue);
        Assert.Equal("100s", vm.CompactDisplayCounterText);

        // 3. Sync failure (Server not found in list)
        dummyApi.ServersToReturn = new List<ServerInfo>();
        await vm.ConnectServerAsync("nonexistent-job");
        Assert.True(vm.HasSyncIssue);
        Assert.False(vm.IsSynced);
        Assert.True(vm.IsSyncError);
        Assert.Equal("ERR", vm.ServerDtlText);
        Assert.Contains("Sync Error", vm.CompactCounterTooltip);
    }

    [Fact]
    public async Task Test_ConnectServer_ConnectionLoss_RetriesAndShowsRetriedOnFailure()
    {
        var dummyApi = new DummyApiClient();
        dummyApi.CustomDetailedResult = ServerFetchResult.ConnectionFailure("Network unreachable");

        using var vm = new MainOverlayViewModel(new DummySettingsService(), dummyApi, new DummyProcessMonitor(), LoggingService.Instance);
        vm.ConnectionRetryDelayMs = 0;
        vm.MaxConnectionRetries = 2;

        await vm.ConnectServerAsync("job-lost", isUserInitiated: true);

        Assert.Equal(3, dummyApi.FetchDetailedCalls); // 1 initial + 2 retries
        Assert.True(vm.HasSyncIssue);
        Assert.True(vm.IsSyncError);
        Assert.False(vm.IsSynced);
        Assert.Equal("UNSYNCED", vm.ConnectionStatusText);
        Assert.Contains("retried 2x", vm.SyncStatusMessage);
        Assert.Contains("Network unreachable", vm.SyncStatusMessage);
        Assert.Contains("Connection lost with server", vm.SyncStatusMessage);
    }

    [Fact]
    public async Task Test_ConnectServer_ConnectionLoss_RetriesAndRecovers()
    {
        var dummyApi = new DummyApiClient();
        var validServer = new ServerInfo
        {
            JobId = "job-retry-ok",
            HeartbeatTimestamp = DateTimeOffset.UtcNow,
            Unit1 = new UnitState
            {
                Demand = 400,
                NextDemand = 500,
                DemandTimeLeft = 60
            },
            Unit2 = new UnitState
            {
                Demand = 400,
                NextDemand = 500,
                DemandTimeLeft = 60
            }
        };

        // Attempt 1 fails with connection lost, attempt 2 succeeds
        dummyApi.ResultQueue.Enqueue(ServerFetchResult.ConnectionFailure("Connection reset"));
        dummyApi.ResultQueue.Enqueue(ServerFetchResult.Success(new List<ServerInfo> { validServer }));

        using var vm = new MainOverlayViewModel(new DummySettingsService(), dummyApi, new DummyProcessMonitor(), LoggingService.Instance);
        vm.ConnectionRetryDelayMs = 0;
        vm.MaxConnectionRetries = 2;

        await vm.ConnectServerAsync("job-retry-ok", isUserInitiated: true);

        Assert.Equal(2, dummyApi.FetchDetailedCalls);
        Assert.False(vm.HasSyncIssue);
        Assert.True(vm.IsSynced);
        Assert.False(vm.IsSyncError);
        Assert.Equal("SYNCED", vm.ConnectionStatusText);
        Assert.Contains("reconnected after 1 retry", vm.SyncStatusMessage);
    }

    [Fact]
    public async Task Test_ConnectServer_DifferentErrorMessages()
    {
        var dummyApi = new DummyApiClient();
        using var vm = new MainOverlayViewModel(new DummySettingsService(), dummyApi, new DummyProcessMonitor(), LoggingService.Instance);
        vm.ConnectionRetryDelayMs = 0;

        // HTTP 404
        dummyApi.CustomDetailedResult = ServerFetchResult.HttpFailure(System.Net.HttpStatusCode.NotFound, "Not Found");
        await vm.ConnectServerAsync("job-test", isUserInitiated: true);
        Assert.Contains("HTTP 404", vm.SyncStatusMessage);

        // HTTP 500
        dummyApi.CustomDetailedResult = ServerFetchResult.HttpFailure(System.Net.HttpStatusCode.InternalServerError, "Server Error");
        await vm.ConnectServerAsync("job-test", isUserInitiated: true);
        Assert.Contains("HTTP 500", vm.SyncStatusMessage);

        // HTTP 429
        dummyApi.CustomDetailedResult = ServerFetchResult.HttpFailure((System.Net.HttpStatusCode)429, "Too Many Requests");
        await vm.ConnectServerAsync("job-test", isUserInitiated: true);
        Assert.Contains("HTTP 429", vm.SyncStatusMessage);

        // Parse Error
        dummyApi.CustomDetailedResult = ServerFetchResult.ParseFailure("Unexpected token in JSON");
        await vm.ConnectServerAsync("job-test", isUserInitiated: true);
        Assert.Contains("Invalid response format", vm.SyncStatusMessage);
        Assert.Contains("Unexpected token in JSON", vm.SyncStatusMessage);

        // Server not found in populated list
        dummyApi.CustomDetailedResult = null;
        dummyApi.ServersToReturn = new List<ServerInfo>
        {
            new ServerInfo { JobId = "other-job" }
        };
        await vm.ConnectServerAsync("my-missing-job", isUserInitiated: true);
        Assert.Contains("my-missing-job", vm.SyncStatusMessage);
        Assert.Contains("not found in public list", vm.SyncStatusMessage);
    }

    private class DummyApiClient : IApiClient
    {
        public List<ServerInfo> ServersToReturn { get; set; } = new();
        public ServerFetchResult? CustomDetailedResult { get; set; }
        public Queue<ServerFetchResult> ResultQueue { get; } = new();
        public int FetchDetailedCalls { get; private set; }

        public Task<ServerFetchResult> GetLatestServersDetailedAsync(CancellationToken ct = default)
        {
            FetchDetailedCalls++;
            if (ResultQueue.Count > 0)
                return Task.FromResult(ResultQueue.Dequeue());
            if (CustomDetailedResult != null)
                return Task.FromResult(CustomDetailedResult);
            return Task.FromResult(ServerFetchResult.Success(ServersToReturn));
        }

        public Task<List<ServerInfo>> GetLatestServersAsync(CancellationToken ct = default)
            => Task.FromResult(ServersToReturn);

        public ServerInfo? FindServerByIdOrJobId(IEnumerable<ServerInfo> servers, string query)
            => servers.FirstOrDefault(s => s.JobId == query);

        public Task<bool> SubmitSuggestionAsync(string name, string suggestion, bool anonymous, CancellationToken ct = default)
            => Task.FromResult(true);

        public Task<bool> SubmitCrashReportAsync(string version, string traceback, string logData, string osInfo, CancellationToken ct = default)
            => Task.FromResult(true);

        public Task<UpdateInfo> CheckForUpdatesAsync(string currentVersion, string skippedVersion, CancellationToken ct = default)
            => Task.FromResult(new UpdateInfo { IsAvailable = false, Version = currentVersion });

        public Task DownloadUpdateAsync(string downloadUrl, string destinationPath, IProgress<double>? progress = null, CancellationToken ct = default)
            => Task.CompletedTask;
    }
}