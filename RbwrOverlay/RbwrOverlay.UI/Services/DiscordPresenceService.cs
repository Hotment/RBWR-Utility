using DiscordRPC;
using DiscordRPC.Logging;
using RbwrOverlay.Core.Services;

namespace RbwrOverlay.UI.Services;

public sealed class PresenceSnapshot
{
    public string Details { get; init; } = string.Empty;
    public string State { get; init; } = string.Empty;
    public string SmallImageText { get; init; } = string.Empty;
}

public sealed class DiscordPresenceService : IDisposable
{
    public const string DefaultApplicationId = "1547513762087436288";

    private const string LargeImageKey = "icon";
    private const string ReleasesUrl = "https://github.com/Hotment/RBWR-Utility/releases/latest";
    private static readonly TimeSpan MinUpdateInterval = TimeSpan.FromSeconds(5);

    private readonly ILoggingService _logger;
    private readonly Timestamps _startTimestamps = Timestamps.Now;
    private DiscordRpcClient? _client;
    private PresenceSnapshot? _lastSent;
    private DateTime _lastSentAt = DateTime.MinValue;
    private bool _enabled;
    private bool _disposed;

    public string ApplicationId { get; }
    public bool IsConfigured => ApplicationId.Length > 0 && ApplicationId.All(char.IsDigit);

    public DiscordPresenceService(ILoggingService? logger = null)
    {
        _logger = logger ?? LoggingService.Instance;
        var fromEnv = Environment.GetEnvironmentVariable("RBWR_DISCORD_APP_ID");
        ApplicationId = (string.IsNullOrWhiteSpace(fromEnv) ? DefaultApplicationId : fromEnv).Trim();
    }

    public void SetEnabled(bool enabled)
    {
        if (_disposed || enabled == _enabled) return;
        _enabled = enabled;

        if (enabled) Start();
        else Stop();
    }

    public void Update(PresenceSnapshot snapshot)
    {
        if (_disposed || !_enabled || _client == null) return;

        if (_lastSent != null
            && _lastSent.Details == snapshot.Details
            && _lastSent.State == snapshot.State
            && _lastSent.SmallImageText == snapshot.SmallImageText)
            return;

        if (DateTime.UtcNow - _lastSentAt < MinUpdateInterval) return;

        try
        {
            _client.SetPresence(new RichPresence
            {
                Details = Truncate(snapshot.Details),
                State = Truncate(snapshot.State),
                Timestamps = _startTimestamps,
                Assets = new Assets
                {
                    LargeImageKey = LargeImageKey,
                    LargeImageText = $"RBWR Overlay v{ViewModels.MainOverlayViewModel.AppVersion}",
                    SmallImageText = Truncate(snapshot.SmallImageText)
                },
                Buttons = new[]
                {
                    new Button { Label = "Get RBWR Overlay", Url = ReleasesUrl }
                }
            });
            _lastSent = snapshot;
            _lastSentAt = DateTime.UtcNow;
        }
        catch (Exception ex)
        {
            _logger.Warning($"Discord presence update failed: {ex.Message}");
        }
    }

    private void Start()
    {
        if (!IsConfigured)
        {
            _logger.Warning("Discord Rich Presence is enabled but no valid application id is set (set RBWR_DISCORD_APP_ID); skipping.");
            return;
        }

        try
        {
            _client = new DiscordRpcClient(ApplicationId) { Logger = new NullLogger() };
            _client.Initialize();
            _logger.Info("Discord Rich Presence started.");
        }
        catch (Exception ex)
        {
            _logger.Warning($"Discord Rich Presence failed to start: {ex.Message}");
            _client?.Dispose();
            _client = null;
        }
    }

    private void Stop()
    {
        try
        {
            _client?.ClearPresence();
            _client?.Dispose();
        }
        catch (Exception ex)
        {
            _logger.Warning($"Discord Rich Presence failed to stop cleanly: {ex.Message}");
        }
        _client = null;
        _lastSent = null;
        _lastSentAt = DateTime.MinValue;
    }

    private static string? Truncate(string? s) => string.IsNullOrWhiteSpace(s) ? null : s.Length <= 120 ? s : s[..120];

    public void Dispose()
    {
        if (_disposed) return;
        Stop();
        _disposed = true;
    }
}
