using Avalonia;
using Avalonia.Media.Imaging;

namespace RbwrThemeCreator.Services.Ai;

public enum AttachmentKind { Image, Pdf, Text }

public sealed class ChatAttachment
{
    public const int MaxImageSide = 1568;
    public const int MaxTextChars = 30000;
    public const long MaxFileBytes = 10 * 1024 * 1024;

    private static readonly HashSet<string> ImageExt = new(StringComparer.OrdinalIgnoreCase) { ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif" };

    private static readonly HashSet<string> TextExt = new(StringComparer.OrdinalIgnoreCase)
    {
        ".txt", ".md", ".json", ".axaml", ".xaml", ".xml", ".theme", ".cs", ".css", ".html", ".js", ".ts", ".py", ".csv", ".log", ".yaml", ".yml", ".toml", ".ini",
    };

    public string Name { get; init; } = string.Empty;
    public AttachmentKind Kind { get; init; }
    public string MediaType { get; init; } = "text/plain";
    public byte[] Data { get; init; } = [];
    public string Text { get; init; } = string.Empty;
    public Bitmap? Thumbnail { get; init; }
    public bool IsFont { get; init; }

    public string Base64 => Convert.ToBase64String(Data);
    public string DataUrl => $"data:{MediaType};base64,{Base64}";
    public string Label => Kind switch
    {
        AttachmentKind.Image => $"🖼 {Name}",
        AttachmentKind.Pdf => $"📄 {Name}",
        _ when IsFont => $"🔤 {Name}",
        _ => $"📝 {Name}",
    };

    // =====================================================================
    // Factories
    // =====================================================================

    public static ChatAttachment FromFile(string path)
    {
        var info = new FileInfo(path);
        if (!info.Exists) throw new FileNotFoundException(path);
        if (info.Length > MaxFileBytes) throw new InvalidOperationException($"{info.Name} is larger than 10 MB.");
        string ext = info.Extension;

        if (ImageExt.Contains(ext))
        {
            using var bmp = new Bitmap(path);
            return FromBitmap(bmp, info.Name);
        }
        if (ext.Equals(".pdf", StringComparison.OrdinalIgnoreCase))
            return new ChatAttachment { Name = info.Name, Kind = AttachmentKind.Pdf, MediaType = "application/pdf", Data = File.ReadAllBytes(path) };

        string text = File.ReadAllText(path);
        if (!TextExt.Contains(ext) && text.Contains('\0')) throw new InvalidOperationException($"{info.Name}: unsupported file type.");
        if (text.Length > MaxTextChars) text = text[..MaxTextChars] + "\n…(truncated)";
        return new ChatAttachment { Name = info.Name, Kind = AttachmentKind.Text, Text = text };
    }

    public static ChatAttachment FromBitmap(Bitmap source, string name)
    {
        var size = source.PixelSize;
        double scale = Math.Min(1.0, (double)MaxImageSide / Math.Max(size.Width, size.Height));
        Bitmap scaled = scale < 1.0
            ? source.CreateScaledBitmap(new PixelSize(Math.Max(1, (int)(size.Width * scale)), Math.Max(1, (int)(size.Height * scale))), BitmapInterpolationMode.HighQuality)
            : source;

        using var ms = new MemoryStream();
        scaled.Save(ms, new JpegBitmapEncoderOptions { Quality = 85 });
        var thumbSize = scaled.PixelSize;
        double t = Math.Min(1.0, 160.0 / Math.Max(thumbSize.Width, thumbSize.Height));
        var thumb = scaled.CreateScaledBitmap(new PixelSize(Math.Max(1, (int)(thumbSize.Width * t)), Math.Max(1, (int)(thumbSize.Height * t))));
        if (!ReferenceEquals(scaled, source)) scaled.Dispose();

        return new ChatAttachment { Name = name, Kind = AttachmentKind.Image, MediaType = "image/jpeg", Data = ms.ToArray(), Thumbnail = thumb };
    }
}
