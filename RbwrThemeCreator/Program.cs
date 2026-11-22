using Avalonia;
using RbwrThemeCreator.Services;
using RbwrThemeCreator.ViewModels;

namespace RbwrThemeCreator;

internal sealed class Program
{
    [STAThread]
    public static void Main(string[] args)
    {
        var logger = CreatorLogging.Instance;
        logger.LogSystemInfo(MainViewModel.AppVersion);

        AppDomain.CurrentDomain.UnhandledException += (_, e) =>
        {
            if (e.ExceptionObject is Exception ex)
                CreatorCrashHandler.HandleFatalException(ex, "Unhandled AppDomain Exception", isTerminating: e.IsTerminating);
        };

        Avalonia.Threading.Dispatcher.UIThread.UnhandledException += (_, e) =>
        {
            e.Handled = true;
            CreatorCrashHandler.HandleFatalException(e.Exception, "Unhandled UI Thread Exception", isTerminating: false);
        };

        TaskScheduler.UnobservedTaskException += (_, e) =>
        {
            logger.Error("Unobserved Task Exception", e.Exception);
            e.SetObserved();
        };

        if (args.Contains("--test-crash"))
        {
            CreatorCrashHandler.HandleFatalException(
                new InvalidOperationException("RBWR Theme Creator simulated test crash via --test-crash flag."),
                "Simulated Test Crash");
            return;
        }

        try
        {
            BuildAvaloniaApp().StartWithClassicDesktopLifetime(args);
        }
        catch (Exception ex)
        {
            CreatorCrashHandler.HandleFatalException(ex, "Fatal application exception during execution");
        }
    }

    public static AppBuilder BuildAvaloniaApp()
        => AppBuilder.Configure<App>()
            .UsePlatformDetect()
            .WithInterFont()
            .LogToTrace();
}
