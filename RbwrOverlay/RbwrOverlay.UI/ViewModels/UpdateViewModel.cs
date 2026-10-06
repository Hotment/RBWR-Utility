using System.Diagnostics;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using RbwrOverlay.Core.Models;
using RbwrOverlay.Core.Services;

namespace RbwrOverlay.UI.ViewModels;

public partial class UpdateViewModel : ViewModelBase
{
    private readonly IApiClient _apiClient;
    private readonly ILoggingService _logger;
    private readonly Action<string> _onSkipVersion;

    [ObservableProperty]
    private string _latestVersion = string.Empty;

    [ObservableProperty]
    private string _currentVersion = string.Empty;

    [ObservableProperty]
    private string _releaseNotes = string.Empty;

    [ObservableProperty]
    private string _downloadFileName = string.Empty;

    [ObservableProperty]
    private string _downloadUrl = string.Empty;

    [ObservableProperty]
    private double _downloadProgress;

    [ObservableProperty]
    private bool _isDownloading;

    [ObservableProperty]
    private string _downloadStatus = string.Empty;

    public event EventHandler? RequestClose;

    public UpdateViewModel(
        IApiClient apiClient,
        UpdateInfo updateInfo,
        string currentVersion,
        Action<string> onSkipVersion,
        ILoggingService? logger = null)
    {
        _apiClient = apiClient;
        _logger = logger ?? LoggingService.Instance;
        _onSkipVersion = onSkipVersion;

        _latestVersion = updateInfo.Version;
        _currentVersion = currentVersion;
        _releaseNotes = updateInfo.ReleaseNotes;
        _downloadFileName = updateInfo.FileName;
        _downloadUrl = updateInfo.DownloadUrl;
    }

    [RelayCommand]
    public async Task UpdateNowAsync()
    {
        if (IsDownloading || string.IsNullOrEmpty(DownloadUrl)) return;

        IsDownloading = true;
        DownloadStatus = $"Downloading v{LatestVersion}...";

        try
        {
            string currentExe = Process.GetCurrentProcess().MainModule?.FileName ?? AppDomain.CurrentDomain.BaseDirectory;
            string exeDir = Path.GetDirectoryName(currentExe) ?? AppDomain.CurrentDomain.BaseDirectory;
            string newExePath = Path.Combine(exeDir, string.IsNullOrEmpty(DownloadFileName) ? $"RBWR_APRM_Calculator_v{LatestVersion}.exe" : DownloadFileName);

            var progressReporter = new Progress<double>(p =>
            {
                DownloadProgress = p * 100.0;
                DownloadStatus = $"Downloading: {DownloadProgress:F0}%";
            });

            await _apiClient.DownloadUpdateAsync(DownloadUrl, newExePath, progressReporter);

            DownloadStatus = "Rebooting into new version...";
            await Task.Delay(1000);

            if (OperatingSystem.IsWindows())
            {
                string cmdScript = $"timeout /t 2 /nobreak && del \"{currentExe}\" && start \"\" \"{newExePath}\"";
                Process.Start(new ProcessStartInfo
                {
                    FileName = "cmd.exe",
                    Arguments = $"/c {cmdScript}",
                    CreateNoWindow = true,
                    UseShellExecute = false
                });
            }
            else
            {
                Process.Start(new ProcessStartInfo(newExePath) { UseShellExecute = true });
            }

            Environment.Exit(0);
        }
        catch (Exception ex)
        {
            _logger.Error("Self-update failed", ex);
            DownloadStatus = $"Update failed: {ex.Message}";
            IsDownloading = false;
        }
    }

    [RelayCommand]
    public void SkipVersion()
    {
        _onSkipVersion?.Invoke(LatestVersion);
        RequestClose?.Invoke(this, EventArgs.Empty);
    }

    [RelayCommand]
    public void RemindLater()
    {
        RequestClose?.Invoke(this, EventArgs.Empty);
    }
}