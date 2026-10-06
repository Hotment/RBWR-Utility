using System.Runtime.InteropServices;
using RbwrOverlay.Core.Services;

namespace RbwrOverlay.Platform;

public static class ProcessMonitorFactory
{
    public static IProcessMonitor Create(ILoggingService? logger = null)
    {
        if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
        {
            return new WindowsProcessMonitor(logger);
        }
        else if (RuntimeInformation.IsOSPlatform(OSPlatform.OSX))
        {
            return new MacProcessMonitor(logger);
        }
        else
        {
            return new LinuxProcessMonitor(logger);
        }
    }
}