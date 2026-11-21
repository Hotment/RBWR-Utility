using System.Diagnostics;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Threading;
using RbwrOverlay.Core.Services;
using RbwrThemeCreator.ViewModels;
using RbwrThemeCreator.Views;

namespace RbwrThemeCreator.Services;

public static class CreatorCrashHandler
{
    private static bool _hasHandledFatalCrash;
    private static readonly object _syncLock = new();

    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern int MessageBoxW(IntPtr hWnd, string text, string caption, uint type);

    private const uint MB_OKCANCEL = 0x00000001;
    private const uint MB_ICONERROR = 0x00000010;
    private const uint MB_TOPMOST = 0x00040000;
    private const int IDOK = 1;

    public static string ReportVersionTag => $"ThemeCreator v{MainViewModel.AppVersion}";

    public static string FormatExceptionDetails(Exception ex, string contextMessage, ILoggingService? logger = null)
    {
        var sb = new StringBuilder();
        sb.AppendLine($"=== RBWR THEME CREATOR CRASH: {DateTime.Now:yyyy-MM-dd HH:mm:ss.fff} ===");
        sb.AppendLine($"Context: {contextMessage}");
        sb.AppendLine($"App Version: {MainViewModel.AppVersion}");
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
                        sb.AppendLine(loaderEx.StackTrace);
                }
            }
        }

        string exStr = ex.ToString();
        if (exStr.Contains("SkiaSharp", StringComparison.OrdinalIgnoreCase) || exStr.Contains("libSkiaSharp", StringComparison.OrdinalIgnoreCase))
        {
            sb.AppendLine();
            sb.AppendLine("=== TROUBLESHOOTING SUGGESTION ===");
            sb.AppendLine("SkiaSharp native rendering library failed to initialize.");
            sb.AppendLine("1. Ensure 'libSkiaSharp.dll' (Windows) or 'libSkiaSharp.so' (Linux) is present.");
            sb.AppendLine("2. On Windows, verify that the Microsoft Visual C++ 2015-2022 Redistributable (x64) is installed.");
        }

        var log = logger ?? CreatorLogging.Instance;
        return log.SanitizeString(sb.ToString());
    }

    public static string WriteCrashReportFile(string formattedDetails, string? directoryOverride = null)
    {
        string targetDir = directoryOverride ?? CreatorSettings.FolderPath;
        string reportPath = Path.Combine(targetDir, "RBWR_Theme_Creator_Crash_Report.txt");
        try
        {
            Directory.CreateDirectory(targetDir);
            File.WriteAllText(reportPath, formattedDetails);
            return reportPath;
        }
        catch
        {
            try
            {
                string tempPath = Path.Combine(Path.GetTempPath(), "RBWR_Theme_Creator_Crash_Report.txt");
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

        var logger = CreatorLogging.Instance;
        logger.Critical($"Fatal application crash: {contextMessage}", ex);

        string formattedDetails = FormatExceptionDetails(ex, contextMessage, logger);
        string reportFilePath = WriteCrashReportFile(formattedDetails);

        try
        {
            var apiClient = new ApiClient(logger: logger);
            string logData = logger.GetLogContent();
            string osInfo = $"{RuntimeInformation.OSDescription} ({RuntimeInformation.OSArchitecture})";
            _ = Task.Run(async () =>
            {
                using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(3));
                await apiClient.SubmitCrashReportAsync(ReportVersionTag, formattedDetails, logData, osInfo, cts.Token);
            });
        }
        catch
        {
            // Best-effort reporting
        }

        if (!TryShowAvaloniaCrashWindow(formattedDetails, reportFilePath))
            ShowNativeFallbackDialog(ex, contextMessage, reportFilePath);
    }

    private static bool TryShowAvaloniaCrashWindow(string formattedDetails, string reportFilePath)
    {
        try
        {
            if (Application.Current?.ApplicationLifetime is not IClassicDesktopStyleApplicationLifetime desktop)
                return false;

            void ShowWindow()
            {
                var crashWin = new CreatorCrashReportWindow
                {
                    DataContext = new CreatorCrashReportViewModel(formattedDetails, reportFilePath)
                };
                if (desktop.MainWindow != null && desktop.MainWindow != crashWin)
                {
                    try { desktop.MainWindow.Hide(); } catch { }
                }
                desktop.MainWindow = crashWin;
                crashWin.Show();
            }

            if (Dispatcher.UIThread.CheckAccess())
                ShowWindow();
            else
                Dispatcher.UIThread.InvokeAsync(ShowWindow).GetAwaiter().GetResult();

            return true;
        }
        catch
        {
            return false;
        }
    }

    private static void ShowNativeFallbackDialog(Exception ex, string contextMessage, string reportFilePath)
    {
        string simpleError = $"{ex.GetType().Name}: {ex.Message}";
        if (ex.InnerException != null)
            simpleError += $"\nInner Exception: {ex.InnerException.GetType().Name}: {ex.InnerException.Message}";

        bool isNonInteractive = !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("CI")) ||
                                !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("RBWR_NON_INTERACTIVE")) ||
                                Environment.GetCommandLineArgs().Any(a =>
                                    a.Equals("--no-modal", StringComparison.OrdinalIgnoreCase) ||
                                    a.Equals("--headless", StringComparison.OrdinalIgnoreCase));

        if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows) && !isNonInteractive)
        {
            string message =
                $"RBWR Theme Creator encountered a fatal crash during execution.\n\n" +
                $"Context: {contextMessage}\n" +
                $"Error: {simpleError}\n\n" +
                $"A full diagnostic crash report has been saved to:\n{reportFilePath}\n\n" +
                $"Click OK to open the crash report file, or Cancel to exit.";

            int result = MessageBoxW(IntPtr.Zero, message, "RBWR Theme Creator - Fatal Application Crash", MB_OKCANCEL | MB_ICONERROR | MB_TOPMOST);
            if (result == IDOK)
            {
                try { Process.Start(new ProcessStartInfo(reportFilePath) { UseShellExecute = true }); } catch { }
            }
        }
        else
        {
            Console.Error.WriteLine("==================================================");
            Console.Error.WriteLine("RBWR THEME CREATOR - FATAL APPLICATION CRASH");
            Console.Error.WriteLine($"Context: {contextMessage}");
            Console.Error.WriteLine($"Error: {simpleError}");
            Console.Error.WriteLine($"Crash report saved to: {reportFilePath}");
            Console.Error.WriteLine("==================================================");
        }
    }
}
