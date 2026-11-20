using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using RbwrThemeCreator.ViewModels;
using RbwrThemeCreator.Views;

namespace RbwrThemeCreator;

public partial class App : Application
{
    public override void Initialize() => AvaloniaXamlLoader.Load(this);

    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            var vm = new MainViewModel();
            var window = new MainWindow { DataContext = vm };
            desktop.MainWindow = window;

            // Allow "RbwrThemeCreator.exe <theme folder|zip|theme.json>" (e.g. drag a theme onto the exe).
            string? arg = desktop.Args?.FirstOrDefault();
            if (!string.IsNullOrWhiteSpace(arg) && (Directory.Exists(arg) || File.Exists(arg)))
                vm.OpenPath(arg);
        }

        base.OnFrameworkInitializationCompleted();
    }
}
