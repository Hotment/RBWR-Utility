using System.Diagnostics;
using RbwrOverlay.Core.Services;

namespace RbwrOverlay.Platform;

public class MacProcessMonitor : IProcessMonitor
{
    private readonly ILoggingService _logger;
    private readonly CancellationTokenSource _cts = new();
    private Task? _monitorTask;
    private bool _isRobloxActive;
    private bool _isDisposed;

    public bool IsRobloxActive
    {
        get => _isRobloxActive;
        private set
        {
            if (_isRobloxActive != value)
            {
                _isRobloxActive = value;
                RobloxActiveChanged?.Invoke(this, value);
            }
        }
    }

    public event EventHandler<bool>? RobloxActiveChanged;

    public MacProcessMonitor(ILoggingService? logger = null)
    {
        _logger = logger ?? LoggingService.Instance;
    }

    public void StartMonitoring()
    {
        if (_monitorTask != null) return;
        _monitorTask = Task.Run(MonitorLoopAsync);
    }

    public void StopMonitoring()
    {
        _cts.Cancel();
    }

    private async Task MonitorLoopAsync()
    {
        while (!_cts.Token.IsCancellationRequested)
        {
            try
            {
                bool isRobloxRunning = Process.GetProcesses().Any(p =>
                {
                    try
                    {
                        string name = p.ProcessName.ToLowerInvariant();
                        return name.Contains("roblox") || name.Contains("rbwr");
                    }
                    catch
                    {
                        return false;
                    }
                });

                IsRobloxActive = isRobloxRunning;
            }
            catch (Exception ex)
            {
                _logger.Warning($"Error in macOS process monitor: {ex.Message}");
            }

            try
            {
                await Task.Delay(500, _cts.Token);
            }
            catch (OperationCanceledException)
            {
                break;
            }
        }
    }

    public string GetForegroundWindowInfo() => "macOS Process Monitor";

    public void Dispose()
    {
        if (_isDisposed) return;
        _isDisposed = true;
        _cts.Cancel();
        _cts.Dispose();
        GC.SuppressFinalize(this);
    }
}