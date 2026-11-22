using Avalonia.Media.Imaging;
using Avalonia.Platform;
using RbwrOverlay.Core.Models;

namespace RbwrOverlay.UI.Services;

/// <summary>
/// Thumbnails for the Theme Manager list.
///  - Custom themes: the theme folder's preview.png (the Theme Creator writes it on save/export/install).
///  - Built-in themes: the same kind of image, shipped in Assets/ThemePreviews.
///  - No image: no thumbnail (older themes keep working exactly as before).
/// A preview.png that is too big, not a real PNG or broken is ignored (no thumbnail) instead of
/// being decoded, so a replaced huge image can never exhaust memory or crash the Theme Manager.
/// Images are cached because the list is rebuilt on every search keystroke.
/// </summary>
public static class ThemeThumbnailService
{
    public const string PreviewFileName = "preview.png";

    private const long MaxPreviewBytes = 8L * 1024 * 1024;
    private const int MaxPreviewSide = 8192;
    private const long MaxPreviewPixels = 32L * 1024 * 1024;

    /// <summary>Decoded width: the list shows ~56 px wide, this keeps it sharp on 200% displays.</summary>
    private const int DecodeWidth = 128;

    private static readonly Dictionary<string, (DateTime Stamp, Bitmap? Image)> Cache = new(StringComparer.OrdinalIgnoreCase);

    public static Bitmap? Get(InstalledThemeInfo info)
    {
        try
        {
            return info.IsBuiltIn ? GetBuiltIn(info) : GetCustom(info);
        }
        catch
        {
            return null;
        }
    }

    private static Bitmap? GetBuiltIn(InstalledThemeInfo info)
    {
        string key = "builtin:" + info.Id;
        if (Cache.TryGetValue(key, out var hit))
            return hit.Image;

        var uri = new Uri($"avares://RbwrOverlay/Assets/ThemePreviews/{info.Id}.png");
        Bitmap? image = null;
        if (AssetLoader.Exists(uri))
        {
            using var stream = AssetLoader.Open(uri);
            image = Bitmap.DecodeToWidth(stream, DecodeWidth, BitmapInterpolationMode.HighQuality);
        }
        Cache[key] = (DateTime.MinValue, image);
        return image;
    }

    private static Bitmap? GetCustom(InstalledThemeInfo info)
    {
        if (string.IsNullOrWhiteSpace(info.DirectoryPath))
            return null;

        var file = new FileInfo(Path.Combine(info.DirectoryPath, PreviewFileName));
        DateTime stamp = file.Exists ? file.LastWriteTimeUtc : DateTime.MinValue;
        if (Cache.TryGetValue(file.FullName, out var hit) && hit.Stamp == stamp)
            return hit.Image;

        Bitmap? image = null;
        if (file.Exists && file.Length is > 0 and <= MaxPreviewBytes)
        {
            try
            {
                using var fs = file.OpenRead();
                if (IsSafePng(fs))
                {
                    fs.Position = 0;
                    image = Bitmap.DecodeToWidth(fs, DecodeWidth, BitmapInterpolationMode.HighQuality);
                }
            }
            catch
            {
                image = null; // broken image: just no thumbnail
            }
        }
        // The previous bitmap is not disposed: an open Theme Manager may still be showing it.
        Cache[file.FullName] = (stamp, image);
        return image;
    }

    /// <summary>
    /// True when the stream starts with a PNG header whose size is reasonable. Checked before decoding
    /// because a small file can declare enormous dimensions (e.g. 30000x30000) and decoding it would
    /// allocate gigabytes. Anything that is not a PNG is rejected too.
    /// </summary>
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
        // The first chunk must be IHDR: 4-byte length, "IHDR", then width and height (big-endian).
        if (header[12] != (byte)'I' || header[13] != (byte)'H' || header[14] != (byte)'D' || header[15] != (byte)'R')
            return false;

        long width = System.Buffers.Binary.BinaryPrimitives.ReadUInt32BigEndian(header[16..20]);
        long height = System.Buffers.Binary.BinaryPrimitives.ReadUInt32BigEndian(header[20..24]);
        return width is > 0 and <= MaxPreviewSide
            && height is > 0 and <= MaxPreviewSide
            && width * height <= MaxPreviewPixels;
    }
}
