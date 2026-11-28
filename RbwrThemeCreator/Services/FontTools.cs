using System.Security.Cryptography;
using System.Text;
using SkiaSharp;

namespace RbwrThemeCreator.Services;

public static class FontTools
{
    public static bool IsFontFile(string path) =>
        Path.GetExtension(path).ToLowerInvariant() is ".ttf" or ".otf" or ".ttc";

    public static bool IsImageFile(string path) =>
        Path.GetExtension(path).ToLowerInvariant() is ".png" or ".jpg" or ".jpeg" or ".webp" or ".bmp" or ".gif";

    public static readonly string TempRootDir = Path.Combine(Path.GetTempPath(), "RbwrThemeCreator");
    private static readonly string PreviewCacheDir = Path.Combine(TempRootDir, "preview-files");

    /// <summary>Removes temporary import/export/preview folders older than <paramref name="maxAge"/>.</summary>
    public static int CleanupStaleTempFiles(TimeSpan? maxAge = null, string? rootOverride = null)
    {
        string root = rootOverride ?? TempRootDir;
        if (!Directory.Exists(root)) return 0;

        DateTime cutoff = DateTime.UtcNow - (maxAge ?? TimeSpan.FromHours(24));
        int removed = 0;

        foreach (string bucket in new[] { "imports", "preview-files", "export", "restored" })
        {
            string bucketPath = Path.Combine(root, bucket);
            if (!Directory.Exists(bucketPath)) continue;
            foreach (string sub in Directory.EnumerateDirectories(bucketPath))
            {
                try
                {
                    if (Directory.GetLastWriteTimeUtc(sub) < cutoff)
                    {
                        Directory.Delete(sub, recursive: true);
                        removed++;
                    }
                }
                catch
                {
                    // Ignore locked or in-use temp directories
                }
            }
        }

        string thumbDir = Path.Combine(root, "thumbnails");
        if (Directory.Exists(thumbDir))
        {
            foreach (string file in Directory.EnumerateFiles(thumbDir))
            {
                try
                {
                    if (File.GetLastWriteTimeUtc(file) < cutoff)
                    {
                        File.Delete(file);
                        removed++;
                    }
                }
                catch
                {
                    // Ignore locked or in-use thumbnail files
                }
            }
        }
        return removed;
    }

    /// <summary>Reads the font family name stored inside a .ttf/.otf/.ttc file.</summary>
    public static string ReadFamilyName(string path)
    {
        try
        {
            using var typeface = SKTypeface.FromFile(path);
            return typeface?.FamilyName ?? string.Empty;
        }
        catch
        {
            return string.Empty;
        }
    }

    /// <summary>
    /// Returns a temp copy of a file for the live preview so fonts/images loaded by the preview never lock
    /// the user's files (which would break saving over them).
    /// </summary>
    public static string GetPreviewCopy(string sourcePath)
    {
        var info = new FileInfo(sourcePath);
        string hash = Convert.ToHexString(SHA1.HashData(Encoding.UTF8.GetBytes(
            $"{info.FullName}|{info.Length}|{info.LastWriteTimeUtc.Ticks}")))[..12].ToLowerInvariant();
        string dir = Path.Combine(PreviewCacheDir, hash);
        string dest = Path.Combine(dir, info.Name);
        if (!File.Exists(dest))
        {
            Directory.CreateDirectory(dir);
            File.Copy(sourcePath, dest, overwrite: true);
        }
        return dest;
    }
}
