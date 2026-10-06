using System.Diagnostics;
using System.Reflection;
using System.Runtime.InteropServices;
using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Threading;
using RbwrOverlay.Core.Services;
using RbwrOverlay.UI.ViewModels;
using RbwrOverlay.UI.Views;

namespace RbwrOverlay.UI.Services;

public static class CrashHandler
{
    private static bool _hasHandledFatalCrash;
    private static readonly object _syncLock = new();

    #region Win32 Native MessageBox Fallback

    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern int MessageBoxW(IntPtr hWnd, string text, string caption, uint type);

    private const uint MB_OK = 0x00000000;
    private const uint MB_OKCANCEL = 0x00000001;
    private const uint MB_ICONERROR = 0x00000010;
    private const uint MB_TOPMOST = 0x00040000;
    private const int IDOK = 1;

    #endregion

    /// <summary>
    /// Formats a complete, detailed exception trace including all inner exceptions,
    /// type loader exceptions, and environment details.
    /// </summary>
    public static string FormatExceptionDetails(Exception ex, string contextMessage)
    {
        var sb = new System.Text.StringBuilder();
        sb.AppendLine($"=== CRASH OCCURRED: {DateTime.Now:yyyy-MM-dd HH:mm:ss.fff} ===");
        sb.AppendLine($"Context: {contextMessage}");
        sb.AppendLine($"App Version: {MainOverlayViewModel.AppVersion}");
        sb.AppendLine($"OS: {RuntimeInformation.OSDescription} ({RuntimeInformation.OSArchitecture})");
        sb.AppendLine($"Runtime: {RuntimeInformation.FrameworkDescription} [{RuntimeInformation.RuntimeIdentifier}]");
        sb.AppendLine($"Process Architecture: {RuntimeInformation.ProcessArchitecture}");
        sb.AppendLine($"Executable: {Environment.ProcessPath ?? AppDomain.CurrentDomain.FriendlyName}");
        sb.AppendLine($"Base Directory: {AppDomain.CurrentDomain.BaseDirectory}");
        sb.AppendLine();
        sb.AppendLine("=== EXCEPTION INFORMATION ===");
        sb.AppendLine(ex.ToString());

        if (ex is ReflectionTypeLoadException typeLoadEx)
        {
            sb.AppendLine();
            sb.AppendLine("=== TYPE LOADER EXCEPTIONS ===");
            foreach (var loaderEx in typeLoadEx.LoaderExceptions)
            {
                if (loaderEx != null)
                {
                    sb.AppendLine($"- {loaderEx.GetType().FullName}: {loaderEx.Message}");
                    if (!string.IsNullOrEmpty(loaderEx.StackTrace))
                    {
                        sb.AppendLine(loaderEx.StackTrace);
                    }
                }
            }
        }

        string exStr = ex.ToString();
        if (exStr.Contains("SkiaSharp") || exStr.Contains("libSkiaSharp"))
        {
            sb.AppendLine();
            sb.AppendLine("=== TROUBLESHOOTING SUGGESTION ===");
            sb.AppendLine("SkiaSharp native rendering library failed to initialize.");
            sb.AppendLine("1. Ensure 'libSkiaSharp.dll' (Windows) or 'libSkiaSharp.so' (Linux) is present in the application directory.");
            sb.AppendLine("2. On Windows, verify that the Microsoft Visual C++ 2015-2022 Redistributable (x64) is installed.");
        }

        return sb.ToString();
    }

    public static string WriteCrashReportFile(string formattedDetails)
    {
        string baseDir = AppDomain.CurrentDomain.BaseDirectory;
        string reportPath = Path.Combine(baseDir, "RBWR_Crash_Report.txt");

        try
        {
            File.WriteAllText(reportPath, formattedDetails);
            return reportPath;
        }
        catch
        {
            try
            {
                string tempPath = Path.Combine(Path.GetTempPath(), "RBWR_Crash_Report.txt");
                File.WriteAllText(tempPath, formattedDetails);
                return tempPath;
            }
            catch
            {
                return reportPath;
            }
        }
    }

    public static void HandleFatalException(Exception ex, string contextMessage)
    {
        lock (_syncLock)
        {
            if (_hasHandledFatalCrash) return;
            _hasHandledFatalCrash = true;
        }

        var logger = LoggingService.Instance;
        logger.Critical($"Fatal application crash: {contextMessage}", ex);

        string formattedDetails = FormatExceptionDetails(ex, contextMessage);
        string reportFilePath = WriteCrashReportFile(formattedDetails);

        try
        {
            var apiClient = new ApiClient(logger: logger);
            string logData = logger.GetLogContent();
            string osInfo = $"{RuntimeInformation.OSDescription} ({RuntimeInformation.OSArchitecture})";
            _ = Task.Run(async () =>
            {
                using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(3));
                await apiClient.SubmitCrashReportAsync(MainOverlayViewModel.AppVersion, formattedDetails, logData, osInfo, cts.Token);
            });
        }
        catch
        {
            // Best-effort reporting
        }

        bool uiDisplayed = TryShowAvaloniaCrashWindow(formattedDetails);
        if (!uiDisplayed)
        {
            ShowNativeFallbackDialog(ex, contextMessage, reportFilePath);
        }
    }

    public static bool TryShowAvaloniaCrashWindow(string formattedDetails)
    {
        try
        {
            if (Application.Current == null)
            {
                return false;
            }

            if (Application.Current.ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
            {
                void ShowWindow()
                {
                    try
                    {
                        var crashWin = new CrashReportWindow
                        {
                            DataContext = new CrashReportViewModel(formattedDetails)
                        };

                        if (desktop.MainWindow != null && desktop.MainWindow != crashWin)
                        {
                            try { desktop.MainWindow.Hide(); } catch { }
                        }

                        desktop.MainWindow = crashWin;
                        crashWin.Show();
                    }
                    catch
                    {
                        // Fall back to native dialog if window creation fails
                    }
                }

                if (Dispatcher.UIThread.CheckAccess())
                {
                    ShowWindow();
                    return true;
                }
                else
                {
                    var task = Dispatcher.UIThread.InvokeAsync(ShowWindow);
                    task.GetAwaiter().GetResult();
                    return true;
                }
            }
        }
        catch
        {
            // Avalonia UI is broken or tearing down
        }

        return false;
    }

    public static void ShowNativeFallbackDialog(Exception ex, string contextMessage, string reportFilePath)
    {
        string simpleError = $"{ex.GetType().Name}: {ex.Message}";
        if (ex.InnerException != null)
        {
            simpleError += $"\nInner Exception: {ex.InnerException.GetType().Name}: {ex.InnerException.Message}";
        }

        bool isNonInteractive = !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("CI")) ||
                                !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("RBWR_NON_INTERACTIVE")) ||
                                Environment.GetCommandLineArgs().Any(a => a.Equals("--no-modal", StringComparison.OrdinalIgnoreCase) || a.Equals("--headless", StringComparison.OrdinalIgnoreCase));

        if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows) && !isNonInteractive)
        {
            string message =
                $"RBWR APRM Calculator encountered a fatal crash during execution.\n\n" +
                $"Context: {contextMessage}\n" +
                $"Error: {simpleError}\n\n" +
                $"A full diagnostic crash report has been saved to:\n{reportFilePath}\n\n" +
                $"Click OK to view the crash report file, or Cancel to exit.";

            string caption = "RBWR APRM Calculator - Fatal Application Crash";

            int result = MessageBoxW(IntPtr.Zero, message, caption, MB_OKCANCEL | MB_ICONERROR | MB_TOPMOST);
            if (result == IDOK)
            {
                try
                {
                    Process.Start(new ProcessStartInfo(reportFilePath) { UseShellExecute = true });
                }
                catch
                {
                    // Ignore launch failure
                }
            }
        }
        else
        {
            Console.Error.WriteLine("==================================================");
            Console.Error.WriteLine("FATAL APPLICATION CRASH");
            Console.Error.WriteLine($"Context: {contextMessage}");
            Console.Error.WriteLine($"Error: {simpleError}");
            Console.Error.WriteLine($"Crash report saved to: {reportFilePath}");
            Console.Error.WriteLine("==================================================");
        }
    }
}