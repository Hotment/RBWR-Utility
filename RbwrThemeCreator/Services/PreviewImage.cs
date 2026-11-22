using System.Buffers.Binary;
using Avalonia.Media.Imaging;

namespace RbwrThemeCreator.Services;

/// <summary>
/// Loads a theme's preview.png as a small bitmap for lists. Files that are too big, not real PNGs
/// or declare huge dimensions are skipped instead of decoded (same rules as the overlay's Theme Manager),
/// so a replaced image can never exhaust memory.
/// </summary>
public static class PreviewImage
{
    private const long MaxBytes = 8L * 1024 * 1024;
    private const int MaxSide = 8192;
    private const long MaxPixels = 32L * 1024 * 1024;

    public static Bitmap? TryLoad(string path, int decodeWidth)
    {
        try
        {
            var file = new FileInfo(path);
            if (!file.Exists || file.Length is 0 or > MaxBytes)
                return null;
            using var fs = file.OpenRead();
            if (!IsSafePng(fs))
                return null;
            fs.Position = 0;
            return Bitmap.DecodeToWidth(fs, decodeWidth, BitmapInterpolationMode.HighQuality);
        }
        catch
        {
            return null;
        }
    }

    /// <summary>Image files the user can pick as a custom thumbnail.</summary>
    public static readonly string[] PickPatterns = ["*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp"];

    private const long MaxSourceBytes = 20L * 1024 * 1024;
    private const int ThumbnailWidth = 705; // same width as the rendered thumbnails

    /// <summary>
    /// Turns any picked image into a thumbnail-sized PNG in the temp folder (so preview.png is always a
    /// normal PNG the overlay accepts). Returns the new file, or null with <paramref name="error"/>.
    /// </summary>
    public static string? MakeThumbnail(string sourcePath, out string error)
    {
        error = string.Empty;
        try
        {
            var file = new FileInfo(sourcePath);
            if (!file.Exists) { error = "The file does not exist."; return null; }
            if (file.Length > MaxSourceBytes) { error = "The image is larger than 20 MB."; return null; }

            using var fs = file.OpenRead();
            if (Path.GetExtension(sourcePath).Equals(".png", StringComparison.OrdinalIgnoreCase))
            {
                if (!IsSafePng(fs)) { error = "This PNG is broken or its size is too large (max 8192 px per side)."; return null; }
                fs.Position = 0;
            }
            using var bitmap = Bitmap.DecodeToWidth(fs, ThumbnailWidth, BitmapInterpolationMode.HighQuality);

            string dir = Path.Combine(Path.GetTempPath(), "RbwrThemeCreator", "thumbnails");
            Directory.CreateDirectory(dir);
            string target = Path.Combine(dir, Guid.NewGuid().ToString("N") + ".png");
            using (var output = File.Create(target))
                bitmap.Save(output, new Avalonia.Media.Imaging.PngBitmapEncoderOptions());
            return target;
        }
        catch (Exception ex)
        {
            error = $"Could not read the image: {ex.Message}";
            return null;
        }
    }

    /// <summary>True when the stream starts with a PNG header of a reasonable size.</summary>
    public static bool IsSafePng(Stream stream)
    {
        Span<byte> header = stackalloc byte[24];
        int read = 0;
        while (read < header.Length)
        {
            int n = stream.Read(header[read..]);
            if (n == 0) return false;
            read += n;
        }

        ReadOnlySpan<byte> signature = [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A];
        if (!header[..8].SequenceEqual(signature)) return false;
        if (header[12] != (byte)'I' || header[13] != (byte)'H' || header[14] != (byte)'D' || header[15] != (byte)'R')
            return false;

        long width = BinaryPrimitives.ReadUInt32BigEndian(header[16..20]);
        long height = BinaryPrimitives.ReadUInt32BigEndian(header[20..24]);
        return width is > 0 and <= MaxSide && height is > 0 and <= MaxSide && width * height <= MaxPixels;
    }
}
