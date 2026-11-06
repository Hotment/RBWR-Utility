namespace RbwrOverlay.Platform;

public interface IProcessMonitor : IDisposable
{
    bool IsRobloxActive { get; }
    event EventHandler<bool>? RobloxActiveChanged;

    /// <summary>True when VS Code is the foreground window.</summary>
    bool IsEditorActive => false;
    event EventHandler<bool>? EditorActiveChanged { add { } remove { } }

    /// <summary>True when a Roblox player process exists, regardless of which window is focused.</summary>
    bool IsRobloxRunning => IsRobloxActive;

    /// <summary>Place id of the experience Roblox most recently joined, if it can be determined.</summary>
    long? CurrentPlaceId => null;
    void StartMonitoring();
    void StopMonitoring();
    string GetForegroundWindowInfo();
}