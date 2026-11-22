using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Threading;
using RbwrThemeCreator.Services;

namespace RbwrThemeCreator.Views;

/// <summary>
/// Screen-wide colour picker. While active, a magnifier follows the cursor and the next click
/// anywhere on screen (game, browser, the overlay itself) picks that pixel instead of reaching
/// the window underneath.
///
/// Controls: left click / Enter = pick, right click / Esc = cancel,
/// arrow keys = move 1 px (Shift: 10 px) for pixel-exact picks.
/// </summary>
[SupportedOSPlatform("windows")]
internal sealed class EyedropperSession
{
    private static EyedropperSession? _active;

    private readonly TaskCompletionSource<Color?> _result = new();
    private readonly ScreenSampler _sampler;
    private readonly LoupeWindow _loupe = new();
    private readonly DispatcherTimer _timer;
    private readonly HookProc _mouseProc;
    private readonly HookProc _keyProc;
    private IntPtr _mouseHook;
    private IntPtr _keyHook;
    private Color? _pendingPick;
    private bool _pendingCancel;
    private bool _finished;

    /// <summary>Starts a pick. Returns the chosen colour (opaque), or null when cancelled.</summary>
    public static Task<Color?> PickAsync()
    {
        if (_active != null) return Task.FromResult<Color?>(null);
        EyedropperSession? session = null;
        try
        {
            session = new EyedropperSession();
            _active = session;
            session.Start();
            return session._result.Task;
        }
        catch
        {
            session?.Finish(null);
            _active = null;
            return Task.FromResult<Color?>(null);
        }
    }

    private EyedropperSession()
    {
        _sampler = new ScreenSampler();
        // Keep the delegates in fields: the hooks call them from native code.
        _mouseProc = MouseHook;
        _keyProc = KeyboardHook;
        _loupe.Closed += (_, _) => Finish(null);
        _timer = new DispatcherTimer(TimeSpan.FromMilliseconds(16), DispatcherPriority.Render, (_, _) => Tick());
    }

    private void Start()
    {
        IntPtr module = GetModuleHandle(null);
        _mouseHook = SetWindowsHookEx(WH_MOUSE_LL, _mouseProc, module, 0);
        _keyHook = SetWindowsHookEx(WH_KEYBOARD_LL, _keyProc, module, 0);
        if (_mouseHook == IntPtr.Zero)
        {
            Finish(null);
            return;
        }

        _loupe.Show();
        Tick();
        _timer.Start();
    }

    private void Tick()
    {
        if (_finished) return;

        // Fallback in case Windows silently dropped the keyboard hook.
        if (_keyHook == IntPtr.Zero && (GetAsyncKeyState(VK_ESCAPE) & 0x8000) != 0)
        {
            Finish(null);
            return;
        }

        if (!GetCursorPos(out var pt)) return;
        var pixels = _sampler.Capture(pt.X, pt.Y);
        _loupe.Update(pixels, new PixelPoint(pt.X, pt.Y));
    }

    private IntPtr MouseHook(int code, IntPtr wParam, IntPtr lParam)
    {
        if (code >= 0 && !_finished)
        {
            int msg = (int)wParam;
            switch (msg)
            {
                case WM_LBUTTONDOWN:
                {
                    // MSLLHOOKSTRUCT starts with the POINT in physical screen coordinates.
                    int x = Marshal.ReadInt32(lParam);
                    int y = Marshal.ReadInt32(lParam, 4);
                    _pendingPick = ToColor(_sampler.CaptureCentre(x, y));
                    return 1;
                }
                case WM_LBUTTONUP when _pendingPick != null:
                    Dispatcher.UIThread.Post(() => Finish(_pendingPick));
                    return 1;
                case WM_RBUTTONDOWN:
                    _pendingCancel = true;
                    return 1;
                case WM_RBUTTONUP when _pendingCancel:
                    Dispatcher.UIThread.Post(() => Finish(null));
                    return 1;
                case WM_MBUTTONDOWN:
                case WM_MBUTTONUP:
                    return 1;
            }
        }
        return CallNextHookEx(IntPtr.Zero, code, wParam, lParam);
    }

    private IntPtr KeyboardHook(int code, IntPtr wParam, IntPtr lParam)
    {
        if (code >= 0 && !_finished)
        {
            int msg = (int)wParam;
            int vk = Marshal.ReadInt32(lParam); // KBDLLHOOKSTRUCT.vkCode
            bool down = msg is WM_KEYDOWN or WM_SYSKEYDOWN;
            bool up = msg is WM_KEYUP or WM_SYSKEYUP;

            switch (vk)
            {
                case VK_ESCAPE:
                    if (down) Dispatcher.UIThread.Post(() => Finish(null));
                    return 1;
                case VK_RETURN:
                    if (down && GetCursorPos(out var p))
                    {
                        var c = ToColor(_sampler.CaptureCentre(p.X, p.Y));
                        Dispatcher.UIThread.Post(() => Finish(c));
                    }
                    return 1;
                case VK_LEFT or VK_UP or VK_RIGHT or VK_DOWN:
                    if (down) Nudge(vk);
                    if (down || up) return 1;
                    break;
            }
        }
        return CallNextHookEx(IntPtr.Zero, code, wParam, lParam);
    }

    private void Nudge(int vk)
    {
        if (!GetCursorPos(out var p)) return;
        int step = (GetKeyState(VK_SHIFT) & 0x8000) != 0 ? 10 : 1;
        switch (vk)
        {
            case VK_LEFT: p.X -= step; break;
            case VK_RIGHT: p.X += step; break;
            case VK_UP: p.Y -= step; break;
            case VK_DOWN: p.Y += step; break;
        }
        SetCursorPos(p.X, p.Y);
    }

    private void Finish(Color? color)
    {
        if (_finished) return;
        _finished = true;

        _timer.Stop();
        if (_mouseHook != IntPtr.Zero) UnhookWindowsHookEx(_mouseHook);
        if (_keyHook != IntPtr.Zero) UnhookWindowsHookEx(_keyHook);
        _mouseHook = _keyHook = IntPtr.Zero;

        try { _loupe.Close(); } catch { /* window may not have opened */ }
        _sampler.Dispose();

        _active = null;
        _result.TrySetResult(color);
    }

    private static Color ToColor(int rgb) =>
        Color.FromRgb((byte)(rgb >> 16), (byte)(rgb >> 8), (byte)rgb);

    // ---- Win32 ----

    private delegate IntPtr HookProc(int code, IntPtr wParam, IntPtr lParam);

    [StructLayout(LayoutKind.Sequential)]
    private struct POINT
    {
        public int X;
        public int Y;
    }

    private const int WH_KEYBOARD_LL = 13;
    private const int WH_MOUSE_LL = 14;
    private const int WM_KEYDOWN = 0x0100;
    private const int WM_KEYUP = 0x0101;
    private const int WM_SYSKEYDOWN = 0x0104;
    private const int WM_SYSKEYUP = 0x0105;
    private const int WM_LBUTTONDOWN = 0x0201;
    private const int WM_LBUTTONUP = 0x0202;
    private const int WM_RBUTTONDOWN = 0x0204;
    private const int WM_RBUTTONUP = 0x0205;
    private const int WM_MBUTTONDOWN = 0x0207;
    private const int WM_MBUTTONUP = 0x0208;
    private const int VK_RETURN = 0x0D;
    private const int VK_SHIFT = 0x10;
    private const int VK_ESCAPE = 0x1B;
    private const int VK_LEFT = 0x25;
    private const int VK_UP = 0x26;
    private const int VK_RIGHT = 0x27;
    private const int VK_DOWN = 0x28;

    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr SetWindowsHookEx(int idHook, HookProc proc, IntPtr hMod, uint threadId);

    [DllImport("user32.dll")] private static extern bool UnhookWindowsHookEx(IntPtr hook);
    [DllImport("user32.dll")] private static extern IntPtr CallNextHookEx(IntPtr hook, int code, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")] private static extern bool GetCursorPos(out POINT point);
    [DllImport("user32.dll")] private static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] private static extern short GetAsyncKeyState(int vk);
    [DllImport("user32.dll")] private static extern short GetKeyState(int vk);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] private static extern IntPtr GetModuleHandle(string? name);
}

/// <summary>Small always-on-top magnifier that follows the cursor during an eyedropper pick.</summary>
[SupportedOSPlatform("windows")]
internal sealed class LoupeWindow : Window
{
    private const int CellSize = 12;
    private const int CursorGap = 24; // physical px between cursor and loupe

    private readonly SolidColorBrush[] _cells = new SolidColorBrush[ScreenSampler.Size * ScreenSampler.Size];
    private readonly SolidColorBrush _swatch = new(Colors.Black);
    private readonly TextBlock _hex;
    private readonly TextBlock _coords;

    public LoupeWindow()
    {
        WindowDecorations = WindowDecorations.None;
        CanResize = false;
        ShowInTaskbar = false;
        ShowActivated = false;
        Topmost = true;
        SizeToContent = SizeToContent.WidthAndHeight;
        Background = Brushes.Transparent;
        TransparencyLevelHint = [WindowTransparencyLevel.Transparent];
        Title = "Eyedropper";

        const int n = ScreenSampler.Size;
        var grid = new UniformGrid { Rows = n, Columns = n, Width = n * CellSize, Height = n * CellSize };
        for (int i = 0; i < _cells.Length; i++)
        {
            _cells[i] = new SolidColorBrush(Colors.Black);
            grid.Children.Add(new Border { Background = _cells[i] });
        }

        // Centre pixel marker: black + white outline so it is visible on any colour.
        var marker = new Border
        {
            Width = CellSize + 2,
            Height = CellSize + 2,
            BorderBrush = Brushes.Black,
            BorderThickness = new Thickness(1),
            HorizontalAlignment = HorizontalAlignment.Center,
            VerticalAlignment = VerticalAlignment.Center,
            Child = new Border { BorderBrush = Brushes.White, BorderThickness = new Thickness(1) },
        };

        var zoom = new Border
        {
            CornerRadius = new CornerRadius(6),
            ClipToBounds = true,
            Child = new Grid { Children = { grid, marker } },
        };

        _hex = new TextBlock { FontSize = 13, FontWeight = FontWeight.Bold, VerticalAlignment = VerticalAlignment.Center };
        _coords = new TextBlock { FontSize = 10, Opacity = 0.6, VerticalAlignment = VerticalAlignment.Center };

        var info = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            Spacing = 8,
            Children =
            {
                new Border
                {
                    Width = 22, Height = 22, CornerRadius = new CornerRadius(5),
                    Background = _swatch, BorderBrush = Brushes.White, BorderThickness = new Thickness(1),
                },
                new StackPanel { Children = { _hex, _coords } },
            },
        };

        var help = new TextBlock
        {
            Text = "Click: pick · Esc: cancel\nArrows: 1 px · Shift: 10 px",
            FontSize = 9.5,
            Opacity = 0.6,
        };

        var frame = new Border
        {
            CornerRadius = new CornerRadius(10),
            BorderThickness = new Thickness(1),
            Padding = new Thickness(8),
            Child = new StackPanel { Spacing = 8, Children = { zoom, info, help } },
        };
        frame.Bind(Border.BackgroundProperty, frame.GetResourceObservable("EdCard"));
        frame.Bind(Border.BorderBrushProperty, frame.GetResourceObservable("EdCyan"));
        Content = frame;

        Opened += (_, _) =>
        {
            // Keep the loupe out of screen captures so it can never sample itself (Windows 10 2004+).
            if (TryGetPlatformHandle()?.Handle is { } hwnd && hwnd != IntPtr.Zero)
                SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE);
        };
    }

    public void Update(ReadOnlySpan<int> pixels, PixelPoint cursor)
    {
        for (int i = 0; i < _cells.Length && i < pixels.Length; i++)
        {
            int p = pixels[i];
            _cells[i].Color = Color.FromRgb((byte)(p >> 16), (byte)(p >> 8), (byte)p);
        }

        var centre = _cells[_cells.Length / 2].Color;
        _swatch.Color = centre;
        _hex.Text = ColorUtil.ToHex(centre);
        _coords.Text = $"{cursor.X}, {cursor.Y}";

        Reposition(cursor);
    }

    private void Reposition(PixelPoint cursor)
    {
        double scale = RenderScaling > 0 ? RenderScaling : 1;
        int w = (int)Math.Ceiling(Bounds.Width * scale);
        int h = (int)Math.Ceiling(Bounds.Height * scale);

        int x = cursor.X + CursorGap;
        int y = cursor.Y + CursorGap;

        var area = Screens.ScreenFromPoint(cursor)?.WorkingArea;
        if (area is { } a)
        {
            if (x + w > a.Right) x = cursor.X - CursorGap - w;
            if (y + h > a.Bottom) y = cursor.Y - CursorGap - h;
            x = Math.Max(a.X, x);
            y = Math.Max(a.Y, y);
        }

        var pos = new PixelPoint(x, y);
        if (Position != pos) Position = pos;
    }

    private const uint WDA_EXCLUDEFROMCAPTURE = 0x11;

    [DllImport("user32.dll")] private static extern bool SetWindowDisplayAffinity(IntPtr hwnd, uint affinity);
}
