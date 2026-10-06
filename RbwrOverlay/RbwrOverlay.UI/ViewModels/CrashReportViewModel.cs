using System.Diagnostics;
using System.Runtime.InteropServices;
using Avalonia;
using Avalonia.Input.Platform;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using RbwrOverlay.Core.Services;

namespace RbwrOverlay.UI.ViewModels;

public partial class CrashReportViewModel : ViewModelBase
{
    private readonly IApiClient _apiClient;
    private readonly ILoggingService _logger;

    [ObservableProperty]
    private string _traceback = string.Empty;

    [ObservableProperty]
    private bool _isSending;

    [ObservableProperty]
    private string _statusText = string.Empty;

    [ObservableProperty]
    private string _copyButtonText = "Copy Traceback";

    public CrashReportViewModel(string traceback, IApiClient? apiClient = null, ILoggingService? logger = null)
    {
        _traceback = traceback;
        _logger = logger ?? LoggingService.Instance;
        _apiClient = apiClient ?? new ApiClient(logger: _logger);
    }

    [RelayCommand]
    public async Task CopyTracebackAsync()
    {
        try
        {
            Avalonia.Input.Platform.IClipboard? clipboard = null;
            if (Application.Current?.ApplicationLifetime is Avalonia.Controls.ApplicationLifetimes.IClassicDesktopStyleApplicationLifetime desktop)
            {
                var targetWindow = desktop.Windows.FirstOrDefault(w => w is Views.CrashReportWindow)
                    ?? desktop.Windows.FirstOrDefault(w => w.IsActive)
                    ?? desktop.MainWindow
                    ?? desktop.Windows.FirstOrDefault();

                clipboard = targetWindow?.Clipboard;
            }

            if (clipboard != null)
            {
                await clipboard.SetTextAsync(Traceback);
                CopyButtonText = "Copied!";
                await Task.Delay(2000);
                CopyButtonText = "Copy Traceback";
            }
        }
        catch (Exception ex)
        {
            _logger.Error("Failed to copy to clipboard", ex);
        }
    }

    [RelayCommand]
    public void ReportGitHub()
    {
        try
        {
            string safeTraceback = Traceback.Length > 1200
                ? Traceback.Substring(0, 1200) + "\n\n[Full traceback saved in RBWR_Crash_Report.txt]"
                : Traceback;

            string body = Uri.EscapeDataString($"Please describe what you were doing when the crash occurred:\n\n```\n{safeTraceback}\n```");
            string url = $"https://github.com/Hotment/RBWR-Utility/issues/new?body={body}";
            Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
        }
        catch (Exception ex)
        {
            _logger.Error("Failed to open GitHub issues", ex);
        }
    }

    [RelayCommand]
    public async Task SendReportAsync()
    {
        if (IsSending) return;
        IsSending = true;
        StatusText = "Sending Report...";

        try
        {
            string logData = _logger.GetLogContent();
            string osInfo = $"{RuntimeInformation.OSDescription} ({RuntimeInformation.OSArchitecture})";

            bool success = await _apiClient.SubmitCrashReportAsync(MainOverlayViewModel.AppVersion, Traceback, logData, osInfo);
            StatusText = success ? "Report Sent!" : "Send Failed!";
        }
        catch
        {
            StatusText = "Send Failed!";
        }
        finally
        {
            IsSending = false;
        }
    }

    [RelayCommand]
    public void ExitApp()
    {
        Environment.Exit(1);
    }
}