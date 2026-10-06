using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using RbwrOverlay.Core.Services;

namespace RbwrOverlay.Platform;

public partial class WindowsProcessMonitor : IProcessMonitor
{
    private readonly ILoggingService _logger;
    private readonly CancellationTokenSource _cts = new();
    private Task? _monitorTask;
    private bool _isRobloxActive;
    private bool _isDisposed;
    private IntPtr _lastLoggedHwnd = IntPtr.Zero;

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

    public WindowsProcessMonitor(ILoggingService? logger = null)
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
        int ourPid = Environment.ProcessId;

        while (!_cts.Token.IsCancellationRequested)
        {
            try
            {
                IntPtr hwnd = GetForegroundWindow();
                if (hwnd != IntPtr.Zero)
                {
                    GetWindowThreadProcessId(hwnd, out uint activePid);
                    string windowTitle = GetWindowTitle(hwnd);
                    string className = GetWindowClassName(hwnd);
                    string processName = GetProcessName(activePid);

                    string titleLower = windowTitle.ToLowerInvariant();
                    string procLower = processName.ToLowerInvariant();
                    string classLower = className.ToLowerInvariant();

                    bool isRoblox = procLower.Contains("roblox") ||
                                    procLower.Contains("robloxplayerbeta") ||
                                    className == "WINDOWSCLIENT" ||
                                    className == "RobloxApp" ||
                                    className == "RobloxPlayerBeta" ||
                                    classLower.Contains("roblox") ||
                                    titleLower.Contains("roblox") ||
                                    titleLower.Contains("realistic") ||
                                    titleLower.Contains("rbwr");

                    bool isOurs = activePid == ourPid;

                    // If user is currently focused on our own window, maintain the previous Roblox state
                    // so the overlay does not vanish while clicking settings / sync / input
                    bool newRobloxActive = isRoblox || (isOurs && _isRobloxActive);

                    if (hwnd != _lastLoggedHwnd)
                    {
                        _lastLoggedHwnd = hwnd;
                    }

                    IsRobloxActive = newRobloxActive;
                }
            }
            catch (Exception ex)
            {
                _logger.Warning($"Error in Windows process monitor: {ex.Message}");
            }

            try
            {
                await Task.Delay(200, _cts.Token);
            }
            catch (OperationCanceledException)
            {
                break;
            }
        }
    }

    public string GetForegroundWindowInfo()
    {
        IntPtr hwnd = GetForegroundWindow();
        if (hwnd == IntPtr.Zero) return "None";
        GetWindowThreadProcessId(hwnd, out uint pid);
        return $"HWND={hwnd}, PID={pid}, Title='{GetWindowTitle(hwnd)}', Class='{GetWindowClassName(hwnd)}', Proc='{GetProcessName(pid)}'";
    }

    private static string GetWindowTitle(IntPtr hwnd)
    {
        int length = GetWindowTextLengthW(hwnd);
        if (length <= 0) return string.Empty;
        var sb = new StringBuilder(length + 1);
        GetWindowTextW(hwnd, sb, sb.Capacity);
        return sb.ToString().Trim();
    }

    private static string GetWindowClassName(IntPtr hwnd)
    {
        var sb = new StringBuilder(256);
        GetClassNameW(hwnd, sb, sb.Capacity);
        return sb.ToString().Trim();
    }

    private static string GetProcessName(uint pid)
    {
        if (pid == 0) return string.Empty;

        // Try QueryFullProcessImageNameW
        foreach (uint mask in new[] { 0x1000u, 0x0410u }) // PROCESS_QUERY_LIMITED_INFORMATION, PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
        {
            IntPtr hProc = OpenProcess(mask, false, pid);
            if (hProc != IntPtr.Zero)
            {
                try
                {
                    var sb = new StringBuilder(1024);
                    int size = sb.Capacity;
                    if (QueryFullProcessImageNameW(hProc, 0, sb, ref size))
                    {
                        return Path.GetFileName(sb.ToString());
                    }
                }
                finally
                {
                    CloseHandle(hProc);
                }
            }
        }

        try
        {
            using var proc = Process.GetProcessById((int)pid);
            return proc.ProcessName;
        }
        catch
        {
            return string.Empty;
        }
    }

    public void Dispose()
    {
        if (_isDisposed) return;
        _isDisposed = true;
        _cts.Cancel();
        _cts.Dispose();
        GC.SuppressFinalize(this);
    }

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern int GetWindowTextW(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern int GetWindowTextLengthW(IntPtr hWnd);

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern int GetClassNameW(IntPtr hWnd, StringBuilder lpClassName, int nMaxCount);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr OpenProcess(uint processAccess, bool bInheritHandle, uint processId);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool QueryFullProcessImageNameW(IntPtr hProcess, int flags, StringBuilder lpExeName, ref int lpdwSize);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CloseHandle(IntPtr hObject);
}