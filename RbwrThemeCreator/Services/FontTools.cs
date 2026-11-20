using System.Security.Cryptography;
using System.Text;
using SkiaSharp;

namespace RbwrThemeCreator.Services;

public static class FontTools
{
    private static readonly string PreviewCacheDir = Path.Combine(Path.GetTempPath(), "RbwrThemeCreator", "preview-files");

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
