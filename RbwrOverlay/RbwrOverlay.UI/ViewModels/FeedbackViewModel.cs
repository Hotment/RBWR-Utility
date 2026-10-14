using System.Diagnostics;
using System.Runtime.InteropServices;
using Avalonia.Media;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using RbwrOverlay.Core.Services;

namespace RbwrOverlay.UI.ViewModels;

public partial class FeedbackViewModel : ViewModelBase
{
    private readonly IApiClient _apiClient;
    private readonly ILoggingService _logger;

    [ObservableProperty]
    private string _authorName = string.Empty;

    [ObservableProperty]
    private bool _isAnonymous = true;

    [ObservableProperty]
    private string _feedbackContent = string.Empty;

    [ObservableProperty]
    private string _statusMessage = string.Empty;

    [ObservableProperty]
    private IBrush _statusBrush = new SolidColorBrush(Color.Parse("#00f0ff"));

    [ObservableProperty]
    private bool _isSubmitting;

    public event EventHandler? RequestClose;

    public FeedbackViewModel(IApiClient apiClient, ILoggingService? logger = null)
    {
        _apiClient = apiClient;
        _logger = logger ?? LoggingService.Instance;
    }

    [RelayCommand]
    public void OpenTicketsPage()
    {
        OpenBrowser("https://rbwr.hotment.dev/tickets");
    }

    [RelayCommand]
    public void OpenDiscordServer()
    {
        OpenBrowser("https://discord.gg/4eUQQcuv87");
    }

    private static void OpenBrowser(string url)
    {
        try
        {
            if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
            {
                Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
            }
            else if (RuntimeInformation.IsOSPlatform(OSPlatform.Linux))
            {
                Process.Start("xdg-open", url);
            }
            else if (RuntimeInformation.IsOSPlatform(OSPlatform.OSX))
            {
                Process.Start("open", url);
            }
            else
            {
                Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
            }
        }
        catch
        {
            try
            {
                Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
            }
            catch { }
        }
    }

    [RelayCommand]
    public async Task SubmitAsync()
    {
        if (IsSubmitting) return;

        if (string.IsNullOrWhiteSpace(FeedbackContent))
        {
            StatusMessage = "Error: Feedback details cannot be empty.";
            StatusBrush = new SolidColorBrush(Color.Parse("#ff003c"));
            return;
        }

        IsSubmitting = true;
        StatusMessage = "Sending feedback...";
        StatusBrush = new SolidColorBrush(Color.Parse("#00f0ff"));

        bool success = await _apiClient.SubmitSuggestionAsync(AuthorName, FeedbackContent, IsAnonymous);
        IsSubmitting = false;

        if (success)
        {
            StatusMessage = "Feedback submitted successfully!";
            StatusBrush = new SolidColorBrush(Color.Parse("#39ff14"));
            FeedbackContent = string.Empty;
            await Task.Delay(1500);
            RequestClose?.Invoke(this, EventArgs.Empty);
        }
        else
        {
            StatusMessage = "Error: Connection to server failed.";
            StatusBrush = new SolidColorBrush(Color.Parse("#ff003c"));
        }
    }

    [RelayCommand]
    public void Cancel()
    {
        RequestClose?.Invoke(this, EventArgs.Empty);
    }
}