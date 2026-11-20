using System.Diagnostics;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using RbwrOverlay.Core.Models;
using RbwrThemeCreator.Services;

namespace RbwrThemeCreator.ViewModels;

public partial class CreatorUpdateViewModel : ObservableObject
{
    private readonly ICreatorUpdateService _updateService;
    private readonly Action<string> _onSkipVersion;

    [ObservableProperty] private string _latestVersion = string.Empty;
    [ObservableProperty] private string _currentVersion = string.Empty;

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(EffectiveReleaseNotes))]
    private string _releaseNotes = string.Empty;

    [ObservableProperty] private string _downloadFileName = string.Empty;
    [ObservableProperty] private string _downloadUrl = string.Empty;
    [ObservableProperty] private double _downloadProgress;
    [ObservableProperty] private bool _isDownloading;

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(HasDownloadStatus))]
    [NotifyPropertyChangedFor(nameof(IsDownloadError))]
    private string _downloadStatus = string.Empty;

    public bool HasDownloadStatus => !string.IsNullOrWhiteSpace(DownloadStatus);
    public bool IsDownloadError => DownloadStatus.StartsWith("Update failed", StringComparison.OrdinalIgnoreCase);

    public string EffectiveReleaseNotes => string.IsNullOrWhiteSpace(ReleaseNotes)
        ? "Improvements, bug fixes, and visual refinements."
        : ReleaseNotes.Trim();

    public event EventHandler? RequestClose;

    public CreatorUpdateViewModel(
        ICreatorUpdateService updateService,
        UpdateInfo updateInfo,
        string currentVersion,
        Action<string> onSkipVersion)
    {
        _updateService = updateService;
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
        if (IsDownloading || string.IsNullOrEmpty(DownloadUrl))
            return;

        IsDownloading = true;
        DownloadStatus = $"Downloading v{LatestVersion}...";

        try
        {
            string currentExe = Process.GetCurrentProcess().MainModule?.FileName ?? AppDomain.CurrentDomain.BaseDirectory;
            string exeDir = Path.GetDirectoryName(currentExe) ?? AppDomain.CurrentDomain.BaseDirectory;
            string fileName = string.IsNullOrEmpty(DownloadFileName)
                ? $"RBWR_Theme_Creator_v{LatestVersion}.exe"
                : DownloadFileName;
            string newExePath = Path.Combine(exeDir, fileName);
            string tempDownloadPath = newExePath + ".download.tmp";

            var progress = new Progress<double>(p =>
            {
                DownloadProgress = p * 100.0;
                DownloadStatus = $"Downloading release package... {DownloadProgress:F0}%";
            });

            await _updateService.DownloadUpdateAsync(DownloadUrl, tempDownloadPath, progress);

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
                    UseShellExecute = false,
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
            DownloadStatus = $"Update failed: {ex.Message}";
            IsDownloading = false;
        }
    }

    [RelayCommand]
    public void SkipVersion()
    {
        _onSkipVersion(LatestVersion);
        RequestClose?.Invoke(this, EventArgs.Empty);
    }

    [RelayCommand]
    public void RemindLater()
    {
        if (!IsDownloading)
            RequestClose?.Invoke(this, EventArgs.Empty);
    }
}