using System.Reflection;
using System.Runtime.InteropServices;
using Avalonia;
using RbwrOverlay.Core.Services;
using RbwrOverlay.UI.Services;

namespace RbwrOverlay.UI;

sealed class Program
{
    [STAThread]
    public static void Main(string[] args)
    {
        ConfigureNativeLibraryResolvers();

        var logger = LoggingService.Instance;
        logger.LogSystemInfo(ViewModels.MainOverlayViewModel.AppVersion);

        AppDomain.CurrentDomain.UnhandledException += (sender, e) =>
        {
            if (e.ExceptionObject is Exception ex)
            {
                CrashHandler.HandleFatalException(ex, "Unhandled AppDomain Exception");
            }
        };

        TaskScheduler.UnobservedTaskException += (sender, e) =>
        {
            logger.Error("Unobserved Task Exception", e.Exception);
            e.SetObserved();
        };

        if (args.Contains("--test-crash"))
        {
            throw new InvalidOperationException("RBWR APRM Calculator simulated test crash via --test-crash flag.");
        }

        try
        {
            BuildAvaloniaApp()
                .StartWithClassicDesktopLifetime(args);
        }
        catch (Exception ex)
        {
            CrashHandler.HandleFatalException(ex, "Fatal application exception during execution");
        }
    }

    public static AppBuilder BuildAvaloniaApp()
        => AppBuilder.Configure<App>()
            .UsePlatformDetect()
#if DEBUG
            .WithDeveloperTools()
#endif
            .WithInterFont()
            .LogToTrace();

    private static void ConfigureNativeLibraryResolvers()
    {
        try
        {
            NativeLibrary.SetDllImportResolver(typeof(SkiaSharp.SKImageInfo).Assembly, ResolveSkiaSharpDll);
        }
        catch
        {
            // Ignore if already set or unsupported
        }

        try
        {
            NativeLibrary.SetDllImportResolver(typeof(HarfBuzzSharp.Buffer).Assembly, ResolveHarfBuzzSharpDll);
        }
        catch
        {
            // Ignore if already set or unsupported
        }
    }

    private static IntPtr ResolveSkiaSharpDll(string libraryName, Assembly assembly, DllImportSearchPath? searchPath)
    {
        if (libraryName.Equals("libSkiaSharp", StringComparison.OrdinalIgnoreCase) ||
            libraryName.Equals("SkiaSharp", StringComparison.OrdinalIgnoreCase))
        {
            return TryLoadNativeBinary("libSkiaSharp");
        }
        return IntPtr.Zero;
    }

    private static IntPtr ResolveHarfBuzzSharpDll(string libraryName, Assembly assembly, DllImportSearchPath? searchPath)
    {
        if (libraryName.Equals("libHarfBuzzSharp", StringComparison.OrdinalIgnoreCase) ||
            libraryName.Equals("HarfBuzzSharp", StringComparison.OrdinalIgnoreCase))
        {
            return TryLoadNativeBinary("libHarfBuzzSharp");
        }
        return IntPtr.Zero;
    }

    private static IntPtr TryLoadNativeBinary(string baseName)
    {
        string baseDir = AppDomain.CurrentDomain.BaseDirectory;
        bool isWindows = RuntimeInformation.IsOSPlatform(OSPlatform.Windows);
        bool isLinux = RuntimeInformation.IsOSPlatform(OSPlatform.Linux);
        string ext = isWindows ? ".dll" : (isLinux ? ".so" : ".dylib");
        string nameWithExt = baseName.EndsWith(ext, StringComparison.OrdinalIgnoreCase) ? baseName : baseName + ext;

        string[] candidatePaths = [
            Path.Combine(baseDir, nameWithExt),
            Path.Combine(baseDir, "runtimes", "win-x64", "native", nameWithExt),
            Path.Combine(baseDir, "runtimes", "linux-x64", "native", nameWithExt)
        ];

        foreach (var path in candidatePaths)
        {
            if (File.Exists(path) && NativeLibrary.TryLoad(path, out IntPtr handle))
            {
                return handle;
            }
        }

        if (NativeLibrary.TryLoad(baseName, out IntPtr fallbackHandle))
        {
            return fallbackHandle;
        }

        return IntPtr.Zero;
    }
}