namespace RbwrOverlay.Platform;

public interface IProcessMonitor : IDisposable
{
    bool IsRobloxActive { get; }
    event EventHandler<bool>? RobloxActiveChanged;

    bool IsRobloxRunning => IsRobloxActive;

    long? CurrentPlaceId => null;
    void StartMonitoring();
    void StopMonitoring();
    string GetForegroundWindowInfo();
}