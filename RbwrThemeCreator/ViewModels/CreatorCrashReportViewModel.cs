using System.Diagnostics;
using System.Runtime.InteropServices;
using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Input.Platform;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using RbwrOverlay.Core.Services;
using RbwrThemeCreator.Services;

namespace RbwrThemeCreator.ViewModels;

public partial class CreatorCrashReportViewModel : ObservableObject
{
    private readonly IApiClient _apiClient;
    private readonly ILoggingService _logger;
    private readonly string _reportFilePath;

    [ObservableProperty] private string _traceback = string.Empty;
    [ObservableProperty] private bool _isSending;
    [ObservableProperty] private string _statusText = string.Empty;
    [ObservableProperty] private string _copyButtonText = "COPY TRACEBACK";

    public CreatorCrashReportViewModel(
        string traceback,
        string? reportFilePath = null,
        IApiClient? apiClient = null,
        ILoggingService? logger = null)
    {
        _traceback = traceback;
        _reportFilePath = reportFilePath ?? string.Empty;
        _logger = logger ?? CreatorLogging.Instance;
        _apiClient = apiClient ?? new ApiClient(logger: _logger);
    }

    [RelayCommand]
    public async Task CopyTracebackAsync()
    {
        try
        {
            if (Application.Current?.ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
            {
                var target = desktop.Windows.FirstOrDefault(w => w is Views.CreatorCrashReportWindow)
                             ?? desktop.MainWindow
                             ?? desktop.Windows.FirstOrDefault();
                if (target?.Clipboard != null)
                {
                    await target.Clipboard.SetTextAsync(Traceback);
                    CopyButtonText = "COPIED";
                    await Task.Delay(2000);
                    CopyButtonText = "COPY TRACEBACK";
                }
            }
        }
        catch (Exception ex)
        {
            _logger.Error("Failed to copy crash traceback to clipboard", ex);
        }
    }

    [RelayCommand]
    public void OpenLog()
    {
        try
        {
            string path = _logger.GetLogFilePath();
            if (File.Exists(path))
                Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
            else if (!string.IsNullOrEmpty(_reportFilePath) && File.Exists(_reportFilePath))
                Process.Start(new ProcessStartInfo(_reportFilePath) { UseShellExecute = true });
        }
        catch (Exception ex)
        {
            _logger.Error("Failed to open log file", ex);
        }
    }

    [RelayCommand]
    public void ReportTicket()
    {
        try
        {
            const string url = "https://rbwr.hotment.dev/tickets?target=theme_creator&type=bug_report#submit-section";
            Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
        }
        catch (Exception ex)
        {
            _logger.Error("Failed to open ticket page", ex);
        }
    }

    [RelayCommand]
    public async Task SendReportAsync()
    {
        if (IsSending) return;
        IsSending = true;
        StatusText = "Sending crash report...";

        try
        {
            string logData = _logger.GetLogContent();
            string osInfo = $"{RuntimeInformation.OSDescription} ({RuntimeInformation.OSArchitecture})";
            bool success = await _apiClient.SubmitCrashReportAsync(
                CreatorCrashHandler.ReportVersionTag,
                Traceback,
                logData,
                osInfo);
            StatusText = success ? "Report sent." : "Failed to send report.";
        }
        catch (Exception ex)
        {
            _logger.Error("Manual crash report submission failed", ex);
            StatusText = "Failed to send report.";
        }
        finally
        {
            IsSending = false;
        }
    }

    [RelayCommand]
    public void ExitApp() => Environment.Exit(1);
}
