using System.Runtime.InteropServices;
using Avalonia;
using Avalonia.Media.Imaging;
using Avalonia.Platform;

namespace RbwrThemeCreator.Services;

public static class ScreenCapture
{
    public static bool IsSupported => OperatingSystem.IsWindows();

    public static Bitmap? CaptureVirtualScreen()
    {
        if (!OperatingSystem.IsWindows()) return null;
        int x = GetSystemMetrics(76), y = GetSystemMetrics(77), w = GetSystemMetrics(78), h = GetSystemMetrics(79);
        if (w <= 0 || h <= 0) return null;

        IntPtr screen = GetDC(IntPtr.Zero);
        IntPtr mem = CreateCompatibleDC(screen);
        var info = new BITMAPINFOHEADER { biSize = (uint)Marshal.SizeOf<BITMAPINFOHEADER>(), biWidth = w, biHeight = -h, biPlanes = 1, biBitCount = 32 };
        IntPtr dib = CreateDIBSection(screen, ref info, 0, out IntPtr bits, IntPtr.Zero, 0);
        IntPtr old = SelectObject(mem, dib);
        try
        {
            if (dib == IntPtr.Zero || !BitBlt(mem, 0, 0, w, h, screen, x, y, 0x00CC0020 | 0x40000000)) return null;
            GdiFlush();
            var wb = new WriteableBitmap(new PixelSize(w, h), new Vector(96, 96), PixelFormat.Bgra8888, AlphaFormat.Opaque);
            using (var fb = wb.Lock())
            {
                int rowBytes = w * 4;
                var row = new byte[rowBytes];
                for (int r = 0; r < h; r++)
                {
                    Marshal.Copy(bits + r * rowBytes, row, 0, rowBytes);
                    for (int i = 3; i < rowBytes; i += 4) row[i] = 0xFF;
                    Marshal.Copy(row, 0, fb.Address + r * fb.RowBytes, rowBytes);
                }
            }
            return wb;
        }
        finally
        {
            SelectObject(mem, old);
            if (dib != IntPtr.Zero) DeleteObject(dib);
            DeleteDC(mem);
            ReleaseDC(IntPtr.Zero, screen);
        }
    }

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

    [DllImport("user32.dll")] private static extern int GetSystemMetrics(int index);
    [DllImport("user32.dll")] private static extern IntPtr GetDC(IntPtr hWnd);
    [DllImport("user32.dll")] private static extern int ReleaseDC(IntPtr hWnd, IntPtr hdc);
    [DllImport("gdi32.dll")] private static extern IntPtr CreateCompatibleDC(IntPtr hdc);
    [DllImport("gdi32.dll")] private static extern bool DeleteDC(IntPtr hdc);
    [DllImport("gdi32.dll")] private static extern IntPtr SelectObject(IntPtr hdc, IntPtr obj);
    [DllImport("gdi32.dll")] private static extern bool DeleteObject(IntPtr obj);
    [DllImport("gdi32.dll")] private static extern bool GdiFlush();
    [DllImport("gdi32.dll")] private static extern IntPtr CreateDIBSection(IntPtr hdc, ref BITMAPINFOHEADER info, uint usage, out IntPtr bits, IntPtr section, uint offset);
    [DllImport("gdi32.dll")] private static extern bool BitBlt(IntPtr dest, int xDest, int yDest, int width, int height, IntPtr src, int xSrc, int ySrc, uint rop);
}
