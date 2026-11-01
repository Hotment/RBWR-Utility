using System.Diagnostics;
using Avalonia.Media;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using RbwrOverlay.Core.Models;
using RbwrOverlay.Core.Services;

namespace RbwrOverlay.UI.ViewModels;

public partial class UpdateViewModel : ViewModelBase
{
    private static readonly IBrush CyanStatusBrush = new SolidColorBrush(Color.Parse("#00f0ff"));
    private static readonly IBrush RedStatusBrush = new SolidColorBrush(Color.Parse("#ff003c"));

    private readonly IApiClient _apiClient;
    private readonly ILoggingService _logger;
    private readonly Action<string> _onSkipVersion;

    [ObservableProperty]
    private string _latestVersion = string.Empty;

    [ObservableProperty]
    private string _currentVersion = string.Empty;

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(EffectiveReleaseNotes))]
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
    [NotifyPropertyChangedFor(nameof(HasDownloadStatus))]
    [NotifyPropertyChangedFor(nameof(IsDownloadError))]
    [NotifyPropertyChangedFor(nameof(DownloadStatusBrush))]
    private string _downloadStatus = string.Empty;

    public bool HasDownloadStatus => !string.IsNullOrWhiteSpace(DownloadStatus);

    public bool IsDownloadError => DownloadStatus.StartsWith("Update failed", StringComparison.OrdinalIgnoreCase);

    public IBrush DownloadStatusBrush => IsDownloadError ? RedStatusBrush : CyanStatusBrush;

    public string EffectiveReleaseNotes => string.IsNullOrWhiteSpace(ReleaseNotes)
        ? "Performance improvements, stability fixes, and operational refinements."
        : ReleaseNotes.Trim();

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
            string tempDownloadPath = newExePath + ".download.tmp";

            var progressReporter = new Progress<double>(p =>
            {
                DownloadProgress = p * 100.0;
                DownloadStatus = $"Downloading release package... {DownloadProgress:F0}%";
            });

            await _apiClient.DownloadUpdateAsync(DownloadUrl, tempDownloadPath, progressReporter);

            DownloadStatus = "Download complete. Restarting into new build...";
            await Task.Delay(1000);

            if (OperatingSystem.IsWindows())
            {
                string cmdScript = $"timeout /t 2 /nobreak && del \"{currentExe}\" && move /y \"{tempDownloadPath}\" \"{newExePath}\" && start \"\" \"{newExePath}\"";
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
                File.Move(tempDownloadPath, newExePath, overwrite: true);
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