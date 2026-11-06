namespace RbwrOverlay.Platform;

public interface IProcessMonitor : IDisposable
{
    bool IsRobloxActive { get; }
    event EventHandler<bool>? RobloxActiveChanged;

    bool IsEditorActive => false;
    event EventHandler<bool>? EditorActiveChanged { add { } remove { } }

    bool IsRobloxRunning => IsRobloxActive;

    long? CurrentPlaceId => null;
    void StartMonitoring();
    void StopMonitoring();
    string GetForegroundWindowInfo();
}