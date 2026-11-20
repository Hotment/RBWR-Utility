using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using Avalonia.Threading;
using RbwrThemeCreator.ViewModels;
using RbwrThemeCreator.Views;

namespace RbwrThemeCreator;

public partial class App : Application
{
    private static readonly string ErrorLogPath = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "RbwrThemeCreator", "error.log");

    private MainViewModel? _vm;

    public override void Initialize() => AvaloniaXamlLoader.Load(this);

    public override void OnFrameworkInitializationCompleted()
    {
        // Safety net: an unexpected error on the UI thread is logged and shown in the status bar
        // instead of closing the app and losing the user's unsaved theme.
        Dispatcher.UIThread.UnhandledException += (_, e) =>
        {
            e.Handled = true;
            LogError("UI", e.Exception);
            _vm?.ReportUnexpectedError(e.Exception);
        };
        TaskScheduler.UnobservedTaskException += (_, e) =>
        {
            LogError("Task", e.Exception);
            e.SetObserved();
        };
        AppDomain.CurrentDomain.UnhandledException += (_, e) =>
        {
            if (e.ExceptionObject is Exception ex)
                LogError("Fatal", ex);
        };

        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            _vm = new MainViewModel();
            var window = new MainWindow { DataContext = _vm };
            desktop.MainWindow = window;

            // Allow "RbwrThemeCreator.exe <theme folder|zip|theme.json>" (e.g. drag a theme onto the exe).
            string? arg = desktop.Args?.FirstOrDefault();
            if (!string.IsNullOrWhiteSpace(arg) && (Directory.Exists(arg) || File.Exists(arg)))
                _vm.OpenPath(arg);
        }

        base.OnFrameworkInitializationCompleted();
    }

    private static void LogError(string source, Exception ex)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(ErrorLogPath)!);
            File.AppendAllText(ErrorLogPath, $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {source}: {ex}{Environment.NewLine}{Environment.NewLine}");
        }
        catch
        {
            // never let logging itself crash the app
        }
    }
}
