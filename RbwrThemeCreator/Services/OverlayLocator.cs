using System.Diagnostics;

namespace RbwrThemeCreator.Services;

/// <summary>
/// Finds the overlay's themes folder. The overlay loads themes from "&lt;overlay exe folder&gt;/themes".
/// </summary>
public static class OverlayLocator
{
    private static readonly string[] OverlayExeNames = ["RbwrOverlay.exe", "RbwrOverlay"];

    public static string? Detect()
    {
        // 1. Saved choice
        string saved = CreatorSettings.Current.OverlayThemesDirectory;
        if (!string.IsNullOrWhiteSpace(saved) && Directory.Exists(Path.GetDirectoryName(saved.TrimEnd('\\', '/')) ?? saved))
            return saved;

        // 2. Running overlay process
        try
        {
            foreach (var p in Process.GetProcessesByName("RbwrOverlay"))
            {
                try
                {
                    string? exe = p.MainModule?.FileName;
                    if (!string.IsNullOrEmpty(exe))
                        return Path.Combine(Path.GetDirectoryName(exe)!, "themes");
                }
                catch
                {
                    // access denied etc.
                }
                finally
                {
                    p.Dispose();
                }
            }
        }
        catch
        {
            // process enumeration not available
        }

        // 3. Overlay next to the creator (shipped together) or one folder up
        string baseDir = AppContext.BaseDirectory;
        foreach (string dir in new[] { baseDir, Path.GetFullPath(Path.Combine(baseDir, "..")) })
        {
            if (OverlayExeNames.Any(n => File.Exists(Path.Combine(dir, n))))
                return Path.Combine(dir, "themes");
        }

        // 4. Developer layout: <repo>/RbwrThemeCreator/bin/... -> <repo>/RbwrOverlay/RbwrOverlay.UI/bin/<cfg>/net8.0
        var probe = new DirectoryInfo(baseDir);
        for (int i = 0; i < 6 && probe != null; i++, probe = probe.Parent)
        {
            string uiBin = Path.Combine(probe.FullName, "RbwrOverlay", "RbwrOverlay.UI", "bin");
            if (!Directory.Exists(uiBin)) continue;
            var exe = Directory.EnumerateFiles(uiBin, "RbwrOverlay.exe", SearchOption.AllDirectories)
                .Select(f => new FileInfo(f))
                .OrderByDescending(f => f.LastWriteTimeUtc)
                .FirstOrDefault();
            if (exe != null)
                return Path.Combine(exe.DirectoryName!, "themes");
        }

        return null;
    }

    /// <summary>Normalises a user selection (overlay exe, overlay folder or themes folder) to the themes folder.</summary>
    public static string NormaliseSelection(string path)
    {
        if (File.Exists(path))
            return Path.Combine(Path.GetDirectoryName(path)!, "themes");
        if (Path.GetFileName(path.TrimEnd('\\', '/')).Equals("themes", StringComparison.OrdinalIgnoreCase))
            return path;
        if (OverlayExeNames.Any(n => File.Exists(Path.Combine(path, n))))
            return Path.Combine(path, "themes");
        return path;
    }
}
