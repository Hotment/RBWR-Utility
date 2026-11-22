using System.Runtime.InteropServices;
using System.Runtime.Versioning;

namespace RbwrThemeCreator.Services;

/// <summary>
/// Reads a small square of screen pixels around a point (physical screen coordinates) with GDI.
/// Used by the eyedropper. Works over any window, including games in borderless mode and the
/// overlay itself (layered windows are included via CAPTUREBLT).
/// </summary>
[SupportedOSPlatform("windows")]
internal sealed class ScreenSampler : IDisposable
{
    /// <summary>Width and height of the sampled square. Odd, so there is a centre pixel.</summary>
    public const int Size = 11;

    private readonly int[] _pixels = new int[Size * Size];
    private IntPtr _screenDc;
    private IntPtr _memDc;
    private IntPtr _dib;
    private IntPtr _oldObject;
    private readonly IntPtr _bits;

    public ScreenSampler()
    {
        _screenDc = GetDC(IntPtr.Zero);
        _memDc = CreateCompatibleDC(_screenDc);
        var info = new BITMAPINFOHEADER
        {
            biSize = (uint)Marshal.SizeOf<BITMAPINFOHEADER>(),
            biWidth = Size,
            biHeight = -Size, // top-down rows
            biPlanes = 1,
            biBitCount = 32,
            biCompression = 0, // BI_RGB
        };
        _dib = CreateDIBSection(_screenDc, ref info, 0, out _bits, IntPtr.Zero, 0);
        if (_screenDc == IntPtr.Zero || _memDc == IntPtr.Zero || _dib == IntPtr.Zero || _bits == IntPtr.Zero)
        {
            Dispose();
            throw new InvalidOperationException("Could not create a screen capture surface.");
        }
        _oldObject = SelectObject(_memDc, _dib);
    }

    /// <summary>
    /// Captures the square centred on (<paramref name="x"/>, <paramref name="y"/>). Pixels are
    /// 0x00RRGGBB, row-major, <see cref="Size"/> x <see cref="Size"/>. Areas off screen read as black.
    /// </summary>
    public ReadOnlySpan<int> Capture(int x, int y)
    {
        const int half = Size / 2;
        if (BitBlt(_memDc, 0, 0, Size, Size, _screenDc, x - half, y - half, SRCCOPY | CAPTUREBLT))
        {
            GdiFlush();
            Marshal.Copy(_bits, _pixels, 0, _pixels.Length);
            for (int i = 0; i < _pixels.Length; i++) _pixels[i] &= 0x00FFFFFF;
        }
        else
        {
            Array.Clear(_pixels);
        }
        return _pixels;
    }

    /// <summary>Colour of the single pixel at (x, y) as 0x00RRGGBB.</summary>
    public int CaptureCentre(int x, int y) => Capture(x, y)[(Size / 2) * Size + Size / 2];

    public void Dispose()
    {
        if (_memDc != IntPtr.Zero)
        {
            if (_oldObject != IntPtr.Zero) SelectObject(_memDc, _oldObject);
            DeleteDC(_memDc);
            _memDc = IntPtr.Zero;
            _oldObject = IntPtr.Zero;
        }
        if (_dib != IntPtr.Zero)
        {
            DeleteObject(_dib);
            _dib = IntPtr.Zero;
        }
        if (_screenDc != IntPtr.Zero)
        {
            ReleaseDC(IntPtr.Zero, _screenDc);
            _screenDc = IntPtr.Zero;
        }
    }

    private const uint SRCCOPY = 0x00CC0020;
    private const uint CAPTUREBLT = 0x40000000;

    [StructLayout(LayoutKind.Sequential)]
    private struct BITMAPINFOHEADER
    {
        public uint biSize;
        public int biWidth;
        public int biHeight;
        public ushort biPlanes;
        public ushort biBitCount;
        public uint biCompression;
        public uint biSizeImage;
        public int biXPelsPerMeter;
        public int biYPelsPerMeter;
        public uint biClrUsed;
        public uint biClrImportant;
    }

    [DllImport("user32.dll")] private static extern IntPtr GetDC(IntPtr hWnd);
    [DllImport("user32.dll")] private static extern int ReleaseDC(IntPtr hWnd, IntPtr hdc);
    [DllImport("gdi32.dll")] private static extern IntPtr CreateCompatibleDC(IntPtr hdc);
    [DllImport("gdi32.dll")] private static extern bool DeleteDC(IntPtr hdc);
    [DllImport("gdi32.dll")] private static extern IntPtr SelectObject(IntPtr hdc, IntPtr obj);
    [DllImport("gdi32.dll")] private static extern bool DeleteObject(IntPtr obj);
    [DllImport("gdi32.dll")] private static extern bool GdiFlush();

    [DllImport("gdi32.dll")]
    private static extern IntPtr CreateDIBSection(IntPtr hdc, ref BITMAPINFOHEADER info, uint usage,
        out IntPtr bits, IntPtr section, uint offset);

    [DllImport("gdi32.dll")]
    private static extern bool BitBlt(IntPtr dest, int xDest, int yDest, int width, int height,
        IntPtr src, int xSrc, int ySrc, uint rop);
}
