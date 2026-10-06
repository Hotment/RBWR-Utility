namespace RbwrOverlay.Platform;

public interface IProcessMonitor : IDisposable
{
    bool IsRobloxActive { get; }
    event EventHandler<bool>? RobloxActiveChanged;
    void StartMonitoring();
    void StopMonitoring();
    string GetForegroundWindowInfo();
}