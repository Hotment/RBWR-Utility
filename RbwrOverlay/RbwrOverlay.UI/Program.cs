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

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate int SkVersionGetMilestoneDelegate();

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

    private static bool IsSkiaSharpCompatible(IntPtr handle)
    {
        try
        {
            if (NativeLibrary.TryGetExport(handle, "sk_version_get_milestone", out IntPtr exportPtr))
            {
                var getMilestone = Marshal.GetDelegateForFunctionPointer<SkVersionGetMilestoneDelegate>(exportPtr);
                int milestone = getMilestone();
                return milestone >= 119 && milestone < 120;
            }
        }
        catch
        {
            // Ignore
        }
        return false;
    }

    private static IntPtr ResolveSkiaSharpDll(string libraryName, Assembly assembly, DllImportSearchPath? searchPath)
    {
        if (libraryName.Equals("libSkiaSharp", StringComparison.OrdinalIgnoreCase) ||
            libraryName.Equals("SkiaSharp", StringComparison.OrdinalIgnoreCase))
        {
            return TryLoadSkiaSharpNative();
        }
        return IntPtr.Zero;
    }

    private static IntPtr ResolveHarfBuzzSharpDll(string libraryName, Assembly assembly, DllImportSearchPath? searchPath)
    {
        if (libraryName.Equals("libHarfBuzzSharp", StringComparison.OrdinalIgnoreCase) ||
            libraryName.Equals("HarfBuzzSharp", StringComparison.OrdinalIgnoreCase))
        {
            return TryLoadHarfBuzzSharpNative();
        }
        return IntPtr.Zero;
    }

    private static IntPtr TryLoadSkiaSharpNative()
    {
        string baseDir = AppDomain.CurrentDomain.BaseDirectory;
        bool isWindows = RuntimeInformation.IsOSPlatform(OSPlatform.Windows);
        bool isLinux = RuntimeInformation.IsOSPlatform(OSPlatform.Linux);
        string ext = isWindows ? ".dll" : (isLinux ? ".so" : ".dylib");
        string fileName = "libSkiaSharp" + ext;

        string? nativeDirs = AppContext.GetData("NATIVE_DLL_SEARCH_DIRECTORIES") as string;
        if (!string.IsNullOrEmpty(nativeDirs))
        {
            foreach (string dir in nativeDirs.Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
            {
                string path = Path.Combine(dir, fileName);
                if (File.Exists(path) && NativeLibrary.TryLoad(path, out IntPtr handle))
                {
                    if (IsSkiaSharpCompatible(handle))
                        return handle;
                    NativeLibrary.Free(handle);
                }
            }
        }

        string rid = RuntimeInformation.ProcessArchitecture switch
        {
            Architecture.Arm64 => isWindows ? "win-arm64" : (isLinux ? "linux-arm64" : "osx-arm64"),
            Architecture.X64 => isWindows ? "win-x64" : (isLinux ? "linux-x64" : "osx-x64"),
            _ => isWindows ? "win-x64" : "linux-x64"
        };

        string[] candidatePaths = [
            Path.Combine(baseDir, "runtimes", rid, "native", fileName),
            Path.Combine(baseDir, "runtimes", "win-x64", "native", fileName),
            Path.Combine(baseDir, "runtimes", "linux-x64", "native", fileName),
            Path.Combine(baseDir, rid, fileName)
        ];

        foreach (var path in candidatePaths)
        {
            if (File.Exists(path) && NativeLibrary.TryLoad(path, out IntPtr handle))
            {
                if (IsSkiaSharpCompatible(handle))
                    return handle;
                NativeLibrary.Free(handle);
            }
        }

        string localDll = Path.Combine(baseDir, fileName);
        if (File.Exists(localDll) && NativeLibrary.TryLoad(localDll, out IntPtr localHandle))
        {
            if (IsSkiaSharpCompatible(localHandle))
            {
                return localHandle;
            }

            NativeLibrary.Free(localHandle);
            try
            {
                string quarantinePath = localDll + ".incompatible";
                if (File.Exists(quarantinePath)) File.Delete(quarantinePath);
                File.Move(localDll, quarantinePath);
            }
            catch
            {
                // Non-fatal if locked
            }
        }

        return IntPtr.Zero;
    }

    private static IntPtr TryLoadHarfBuzzSharpNative()
    {
        string baseDir = AppDomain.CurrentDomain.BaseDirectory;
        bool isWindows = RuntimeInformation.IsOSPlatform(OSPlatform.Windows);
        bool isLinux = RuntimeInformation.IsOSPlatform(OSPlatform.Linux);
        string ext = isWindows ? ".dll" : (isLinux ? ".so" : ".dylib");
        string fileName = "libHarfBuzzSharp" + ext;

        string? nativeDirs = AppContext.GetData("NATIVE_DLL_SEARCH_DIRECTORIES") as string;
        if (!string.IsNullOrEmpty(nativeDirs))
        {
            foreach (string dir in nativeDirs.Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
            {
                string path = Path.Combine(dir, fileName);
                if (File.Exists(path) && NativeLibrary.TryLoad(path, out IntPtr handle))
                {
                    return handle;
                }
            }
        }

        string rid = RuntimeInformation.ProcessArchitecture switch
        {
            Architecture.Arm64 => isWindows ? "win-arm64" : (isLinux ? "linux-arm64" : "osx-arm64"),
            Architecture.X64 => isWindows ? "win-x64" : (isLinux ? "linux-x64" : "osx-x64"),
            _ => isWindows ? "win-x64" : "linux-x64"
        };

        string[] candidatePaths = [
            Path.Combine(baseDir, "runtimes", rid, "native", fileName),
            Path.Combine(baseDir, "runtimes", "win-x64", "native", fileName),
            Path.Combine(baseDir, "runtimes", "linux-x64", "native", fileName),
            Path.Combine(baseDir, fileName)
        ];

        foreach (var path in candidatePaths)
        {
            if (File.Exists(path) && NativeLibrary.TryLoad(path, out IntPtr handle))
            {
                return handle;
            }
        }

        return IntPtr.Zero;
    }
}