using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using RbwrOverlay.UI.ViewModels;
using RbwrOverlay.UI.Views;

namespace RbwrOverlay.UI;

public partial class App : Application
{
    private MainOverlayViewModel? _mainViewModel;

    public override void Initialize()
    {
        AvaloniaXamlLoader.Load(this);
    }

    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            string[] appArgs = desktop.Args ?? Array.Empty<string>();
            if (appArgs.Contains("--test-crash-ui"))
            {
                var testEx = new InvalidOperationException("Simulated exception to verify CrashReportWindow UI rendering and interaction.");
                string testDetails = Services.CrashHandler.FormatExceptionDetails(testEx, "Simulated UI Crash Test");
                desktop.MainWindow = new CrashReportWindow
                {
                    DataContext = new CrashReportViewModel(testDetails)
                };
                base.OnFrameworkInitializationCompleted();
                return;
            }

            try
            {
                _mainViewModel = new MainOverlayViewModel();
                desktop.MainWindow = new MainWindow
                {
                    DataContext = _mainViewModel
                };
            }
            catch (Exception ex)
            {
                RbwrOverlay.Core.Services.LoggingService.Instance.Critical("Exception during UI framework initialization", ex);
                string details = Services.CrashHandler.FormatExceptionDetails(ex, "UI Framework Initialization");
                Services.CrashHandler.WriteCrashReportFile(details);

                var crashWin = new CrashReportWindow
                {
                    DataContext = new CrashReportViewModel(details)
                };
                desktop.MainWindow = crashWin;
            }
        }

        base.OnFrameworkInitializationCompleted();
    }

    private void OnTrayIconClicked(object? sender, EventArgs e)
    {
        RestoreMainWindow();
    }

    private void OnTrayRestoreClicked(object? sender, EventArgs e)
    {
        RestoreMainWindow();
    }

    private void OnTrayExitClicked(object? sender, EventArgs e)
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            desktop.Shutdown();
        }
    }

    private void RestoreMainWindow()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop && desktop.MainWindow != null)
        {
            desktop.MainWindow.Show();
            desktop.MainWindow.WindowState = Avalonia.Controls.WindowState.Normal;
            desktop.MainWindow.Activate();
        }
    }
}