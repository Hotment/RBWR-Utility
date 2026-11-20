using System.ComponentModel;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Input.Platform;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.VisualTree;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Media.Imaging;
using Avalonia.Platform.Storage;
using Avalonia.Styling;
using Avalonia.Threading;
using RbwrThemeCreator.Services;
using RbwrThemeCreator.ViewModels;

namespace RbwrThemeCreator.Views;

public partial class MainWindow : Window, IDialogHost
{
    private Styles? _baseStyles;
    private List<Bitmap> _activeBitmaps = new();
    private MainViewModel? _vm;
    private bool _closeConfirmed;

    public MainWindow()
    {
        InitializeComponent();

        try
        {
            _baseStyles = BuiltInThemes.LoadPreviewBaseStyles();
            PreviewHost.Styles.Add(_baseStyles);
        }
        catch (Exception ex)
        {
            // Preview still works, it just will not match the overlay's base look exactly.
            Console.Error.WriteLine($"Could not load overlay base styles: {ex}");
        }

        DataContextChanged += (_, _) => AttachViewModel(DataContext as MainViewModel);
        Closing += OnClosing;
        Viewport.SizeChanged += (_, _) => UpdateZoom();
        PreviewHost.SizeChanged += (_, _) => UpdateZoom();
        Viewport.PointerWheelChanged += OnViewportWheel;
        Viewport.AddHandler(PointerPressedEvent, OnViewportPointerPressed, Avalonia.Interactivity.RoutingStrategies.Tunnel);
        Viewport.PointerMoved += OnViewportPointerMoved;
        Viewport.PointerReleased += OnViewportPointerReleased;
        Opened += (_, _) => ApplyCornerPreference();
    }

    private void AttachViewModel(MainViewModel? vm)
    {
        if (_vm != null)
        {
            _vm.PreviewReady -= OnPreviewReady;
            _vm.PropertyChanged -= OnViewModelPropertyChanged;
            _vm.Dialogs = null;
        }
        _vm = vm;
        if (vm == null) return;

        vm.Dialogs = this;
        vm.PreviewReady += OnPreviewReady;
        vm.PropertyChanged += OnViewModelPropertyChanged;
        ApplyBackdrop(vm.PreviewBackdrop);
        Preview.SetMode(vm.PreviewMode);
        vm.Refresh();
        UpdateZoom();
    }

    private void OnViewModelPropertyChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (_vm == null) return;
        if (e.PropertyName == nameof(MainViewModel.PreviewBackdrop))
            ApplyBackdrop(_vm.PreviewBackdrop);
        else if (e.PropertyName == nameof(MainViewModel.PreviewMode))
        {
            _pan = default;
            Preview.SetMode(_vm.PreviewMode);
            Dispatcher.UIThread.Post(UpdateZoom, DispatcherPriority.Loaded);
        }
        else if (e.PropertyName is nameof(MainViewModel.PreviewZoom) or nameof(MainViewModel.PreviewFit))
        {
            if (!_wheelZooming && !_panning) UpdateZoom();
        }
    }

    private void OnPreviewReady(object? sender, PreviewReadyEventArgs e)
    {
        // Keep the overlay base stylesheet at index 0 and swap the theme on top of it,
        // exactly like the overlay adds a custom theme after CyberpunkTheme.axaml.
        while (PreviewHost.Styles.Count > (_baseStyles != null ? 1 : 0))
            PreviewHost.Styles.RemoveAt(PreviewHost.Styles.Count - 1);
        if (e.Styles != null)
            PreviewHost.Styles.Add(e.Styles);

        var old = _activeBitmaps;
        _activeBitmaps = e.Bitmaps;
        if (old.Count > 0)
        {
            Dispatcher.UIThread.Post(() =>
            {
                foreach (var b in old) b.Dispose();
            }, DispatcherPriority.Background);
        }
    }

    private double _appliedZoom = -1;
    private double _zoom = 1;
    private Vector _pan;
    private bool _panning;
    private Point _panStart;
    private Vector _panAtStart;
    private bool _wheelZooming;

    private const double MinZoom = 0.25;
    private const double MaxZoom = 4;

    /// <summary>Applies the manual zoom, or in Fit mode scales and centres the preview in the panel.</summary>
    private void UpdateZoom()
    {
        if (_vm == null) return;
        Size content = PreviewHost.DesiredSize;
        Size view = Viewport.Bounds.Size;

        double zoom = _vm.PreviewZoom;
        if (_vm.PreviewFit)
        {
            if (content.Width < 1 || content.Height < 1 || view.Width < 1 || view.Height < 1)
                return;
            zoom = Math.Min((view.Width - 16) / content.Width, (view.Height - 16) / content.Height);
            zoom = Math.Clamp(Math.Floor(zoom * 100) / 100, 0.3, 1.6);
            _pan = default;
        }

        _zoom = zoom;
        ZoomText.Text = $"{Math.Round(zoom * 100)}%";
        if (Math.Abs(zoom - _appliedZoom) >= 0.001)
        {
            _appliedZoom = zoom;
            ZoomHost.LayoutTransform = new ScaleTransform(zoom, zoom);
        }
        PositionPreview();
    }

    /// <summary>Centres the (scaled) preview in the viewport and applies the pan offset.</summary>
    private void PositionPreview()
    {
        Size content = PreviewHost.DesiredSize;
        Size view = Viewport.Bounds.Size;
        Canvas.SetLeft(ZoomHost, (view.Width - content.Width * _zoom) / 2 + _pan.X);
        Canvas.SetTop(ZoomHost, (view.Height - content.Height * _zoom) / 2 + _pan.Y);
    }

    private void OnViewportWheel(object? sender, PointerWheelEventArgs e)
    {
        if (_vm == null) return;
        e.Handled = true;

        Size content = PreviewHost.DesiredSize;
        Size view = Viewport.Bounds.Size;
        double oldZoom = _zoom;
        double newZoom = Math.Clamp(oldZoom * Math.Pow(1.15, e.Delta.Y), MinZoom, MaxZoom);
        if (Math.Abs(newZoom - oldZoom) < 0.0001) return;

        // Keep the point under the cursor fixed while zooming.
        Point p = e.GetPosition(Viewport);
        double left = (view.Width - content.Width * oldZoom) / 2 + _pan.X;
        double top = (view.Height - content.Height * oldZoom) / 2 + _pan.Y;
        double qx = (p.X - left) / oldZoom, qy = (p.Y - top) / oldZoom;
        double newLeft = p.X - qx * newZoom, newTop = p.Y - qy * newZoom;
        _pan = new Vector(newLeft - (view.Width - content.Width * newZoom) / 2,
                          newTop - (view.Height - content.Height * newZoom) / 2);

        _wheelZooming = true;
        try
        {
            _vm.PreviewFit = false;
            _vm.PreviewZoom = Math.Round(newZoom, 3);
        }
        finally
        {
            _wheelZooming = false;
        }
        UpdateZoom();
    }

    private static bool IsInteractive(object? source, Visual stopAt)
    {
        for (var v = source as Visual; v != null && v != stopAt; v = v.GetVisualParent())
        {
            if (v is Button or TextBox or Slider or ComboBox or ToggleButton or Thumb or ScrollBar)
                return true;
        }
        return false;
    }

    private void OnViewportPointerPressed(object? sender, PointerPressedEventArgs e)
    {
        var props = e.GetCurrentPoint(Viewport).Properties;
        // Middle/right button always pans; left button pans unless it is on a control in the mock overlay.
        bool pan = props.IsMiddleButtonPressed || props.IsRightButtonPressed
                   || (props.IsLeftButtonPressed && !IsInteractive(e.Source, Viewport));
        if (!pan) return;

        if (props.IsLeftButtonPressed && e.ClickCount == 2)
        {
            // Double-click: back to Fit.
            if (_vm != null) _vm.PreviewFit = true;
            _pan = default;
            UpdateZoom();
            e.Handled = true;
            return;
        }

        _panning = true;
        _panStart = e.GetPosition(Viewport);
        _panAtStart = _pan;
        e.Pointer.Capture(Viewport);
        Viewport.Cursor = new Cursor(StandardCursorType.SizeAll);
        e.Handled = true;
    }

    private void OnViewportPointerMoved(object? sender, PointerEventArgs e)
    {
        if (!_panning) return;
        var p = e.GetPosition(Viewport);
        _pan = _panAtStart + (p - _panStart);
        if (_vm is { PreviewFit: true } && Math.Abs(p.X - _panStart.X) + Math.Abs(p.Y - _panStart.Y) > 3)
        {
            // Moving the preview leaves Fit mode but keeps the current scale.
            _vm.PreviewZoom = Math.Round(_zoom, 3);
            _vm.PreviewFit = false;
        }
        PositionPreview();
    }

    private void OnViewportPointerReleased(object? sender, PointerReleasedEventArgs e)
    {
        if (!_panning) return;
        _panning = false;
        e.Pointer.Capture(null);
        Viewport.Cursor = Cursor.Default;
    }

    private void ApplyBackdrop(int index)
    {
        Backdrop.Background = index switch
        {
            1 => new LinearGradientBrush
            {
                StartPoint = new RelativePoint(0, 0, RelativeUnit.Relative),
                EndPoint = new RelativePoint(1, 1, RelativeUnit.Relative),
                GradientStops =
                {
                    new GradientStop(Color.Parse("#5d7f9e"), 0),
                    new GradientStop(Color.Parse("#a9b8a0"), 0.45),
                    new GradientStop(Color.Parse("#6b6b5a"), 0.7),
                    new GradientStop(Color.Parse("#2d3330"), 1),
                },
            },
            2 => new SolidColorBrush(Color.Parse("#e9ecf1")),
            3 => CreateCheckerBrush(),
            _ => new SolidColorBrush(Color.Parse("#0b0e14")),
        };
    }

    private static IBrush CreateCheckerBrush()
    {
        var group = new DrawingGroup();
        group.Children.Add(new GeometryDrawing { Brush = new SolidColorBrush(Color.Parse("#9a9a9a")), Geometry = new RectangleGeometry(new Rect(0, 0, 24, 24)) });
        group.Children.Add(new GeometryDrawing { Brush = new SolidColorBrush(Color.Parse("#6a6a6a")), Geometry = new RectangleGeometry(new Rect(0, 0, 12, 12)) });
        group.Children.Add(new GeometryDrawing { Brush = new SolidColorBrush(Color.Parse("#6a6a6a")), Geometry = new RectangleGeometry(new Rect(12, 12, 12, 12)) });
        return new DrawingBrush(group)
        {
            TileMode = TileMode.Tile,
            Stretch = Stretch.None,
            DestinationRect = new RelativeRect(0, 0, 24, 24, RelativeUnit.Absolute),
        };
    }

    // ===================== Custom title bar =====================

    private static bool IsFromButton(object? source) =>
        source is Visual v && (v is Button || v.FindAncestorOfType<Button>() != null || v.FindAncestorOfType<TextBox>() != null);

    private void OnTitleBarPointerPressed(object? sender, PointerPressedEventArgs e)
    {
        if (e.ClickCount != 1 || !e.GetCurrentPoint(this).Properties.IsLeftButtonPressed || IsFromButton(e.Source))
            return;
        if (_maximized)
        {
            // Dragging a maximized window restores it under the cursor, like a native title bar.
            var cursor = this.PointToScreen(e.GetPosition(this));
            double ratio = Bounds.Width > 0 ? e.GetPosition(this).X / Bounds.Width : 0.5;
            ToggleMaximize();
            double scale = RenderScaling;
            Position = new PixelPoint((int)(cursor.X - _restoreSize.Width * scale * ratio), (int)(cursor.Y - 20 * scale));
        }
        BeginMoveDrag(e);
    }

    private void OnTitleBarDoubleTapped(object? sender, TappedEventArgs e)
    {
        if (!IsFromButton(e.Source))
            ToggleMaximize();
    }

    private void OnResizeGripPressed(object? sender, PointerPressedEventArgs e)
    {
        if (_maximized || sender is not Control { Tag: string edge } || !e.GetCurrentPoint(this).Properties.IsLeftButtonPressed)
            return;
        if (Enum.TryParse<WindowEdge>(edge, out var windowEdge))
            BeginResizeDrag(windowEdge, e);
    }

    private void OnMinimizeClick(object? sender, RoutedEventArgs e) => WindowState = WindowState.Minimized;

    private void OnMaximizeClick(object? sender, RoutedEventArgs e) => ToggleMaximize();

    private void OnCloseClick(object? sender, RoutedEventArgs e) => Close();

    private bool _maximized;
    private PixelPoint _restorePosition;
    private Size _restoreSize;

    /// <summary>
    /// Maximizes to the screen's working area so the taskbar stays visible
    /// (an OS-maximized frameless window would cover it).
    /// </summary>
    private void ToggleMaximize()
    {
        var screen = Screens.ScreenFromVisual(this) ?? Screens.Primary;
        if (screen == null) return;

        if (!_maximized)
        {
            _restorePosition = Position;
            _restoreSize = new Size(Width, Height);
            var area = screen.WorkingArea;
            double scale = screen.Scaling;
            Position = area.Position;
            Width = area.Width / scale;
            Height = area.Height / scale;
            _maximized = true;
        }
        else
        {
            Width = _restoreSize.Width;
            Height = _restoreSize.Height;
            Position = _restorePosition;
            _maximized = false;
        }

        ResizeGrips.IsVisible = !_maximized;
        ApplyCornerPreference();
        WindowFrame.BorderThickness = new Thickness(_maximized ? 0 : 1);
        MaximizeButton.Content = _maximized ? "❐" : "□";
        ToolTip.SetTip(MaximizeButton, _maximized ? "Restore" : "Maximize");
    }

    private void OnPresetClick(object? sender, RoutedEventArgs e)
    {
        if (sender is Button { Tag: ThemePreset preset } && _vm != null)
        {
            NewButton.Flyout?.Hide();
            _vm.NewFromPresetCommand.Execute(preset);
        }
    }

    private async void OnClosing(object? sender, WindowClosingEventArgs e)
    {
        if (_closeConfirmed || _vm == null || !_vm.IsDirty)
            return;

        e.Cancel = true;
        if (await ConfirmAsync("Unsaved changes", "The theme has unsaved changes. Close anyway?", "Close without saving"))
        {
            _closeConfirmed = true;
            Close();
        }
    }

    // ===================== "Show me where" for colour tokens =====================

    private void OnTokenRowDoubleTapped(object? sender, TappedEventArgs e)
    {
        if (_vm == null || sender is not Control { Tag: string key } || IsInteractive(e.Source, (Visual)sender))
            return;
        if (!TokenLocations.TryGet(key, out int mode, out var names))
            return;

        // Switch to the view that shows the token, fit it so everything is visible, then highlight.
        _pan = default;
        _vm.PreviewMode = mode;
        _vm.PreviewFit = true;
        Dispatcher.UIThread.Post(() =>
        {
            UpdateZoom();
            Dispatcher.UIThread.Post(() => Preview.Highlight(names), DispatcherPriority.Background);
        }, DispatcherPriority.Loaded);
        e.Handled = true;
    }

    // ===================== Rounded window corners (Windows 11) =====================

    [System.Runtime.InteropServices.DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);

    private const int DwmWindowCornerPreference = 33;
    private const int DwmBorderColor = 34;

    /// <summary>Asks Windows 11 to round the frameless window (square when maximized). No-op elsewhere.</summary>
    private void ApplyCornerPreference()
    {
        if (!OperatingSystem.IsWindowsVersionAtLeast(10, 0, 22000)) return;
        var handle = TryGetPlatformHandle()?.Handle ?? IntPtr.Zero;
        if (handle == IntPtr.Zero) return;
        int preference = _maximized ? 1 /* DWMWCP_DONOTROUND */ : 2 /* DWMWCP_ROUND */;
        DwmSetWindowAttribute(handle, DwmWindowCornerPreference, ref preference, sizeof(int));
        int border = 0x003b251b; // COLORREF (BGR) of #1b253b, matches the HUD border
        DwmSetWindowAttribute(handle, DwmBorderColor, ref border, sizeof(int));
    }

    // ===================== IDialogHost =====================

    public async Task<string?> PickFolderAsync(string title)
    {
        var result = await StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions { Title = title, AllowMultiple = false });
        return result.FirstOrDefault()?.TryGetLocalPath();
    }

    public async Task<IReadOnlyList<string>> PickFilesAsync(string title, string filterName, string[] patterns, bool allowMultiple)
    {
        var result = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = title,
            AllowMultiple = allowMultiple,
            FileTypeFilter = [new FilePickerFileType(filterName) { Patterns = patterns }],
        });
        return result.Select(f => f.TryGetLocalPath()).Where(p => p != null).Select(p => p!).ToList();
    }

    public async Task<string?> PickSaveFileAsync(string title, string suggestedName, string filterName, string pattern)
    {
        var file = await StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions
        {
            Title = title,
            SuggestedFileName = suggestedName,
            DefaultExtension = Path.GetExtension(pattern).TrimStart('.'),
            FileTypeChoices = [new FilePickerFileType(filterName) { Patterns = [pattern] }],
        });
        return file?.TryGetLocalPath();
    }

    public async Task CopyTextAsync(string text)
    {
        if (Clipboard != null)
            await Clipboard.SetTextAsync(text);
    }

    public async Task<bool> ConfirmAsync(string title, string message, string okText = "OK")
    {
        bool result = false;
        var dialog = new Window
        {
            Title = title,
            Width = 460,
            SizeToContent = SizeToContent.Height,
            CanResize = false,
            WindowDecorations = WindowDecorations.None,
            WindowStartupLocation = WindowStartupLocation.CenterOwner,
            ShowInTaskbar = false,
            Background = Brushes.Transparent,
            TransparencyLevelHint = [WindowTransparencyLevel.Transparent],
            Icon = Icon,
        };

        bool danger = !string.Equals(okText, "OK", StringComparison.OrdinalIgnoreCase);
        var ok = new Button { Content = okText.ToUpperInvariant(), Classes = { danger ? "hud-red" : "hud-blue" }, MinWidth = 100, Padding = new Thickness(14, 6) };
        var cancel = new Button { Content = "CANCEL", Classes = { "hud" }, MinWidth = 90, HorizontalContentAlignment = HorizontalAlignment.Center };
        var close = new Button { Content = "X", Classes = { "win-btn", "win-close" } };
        ok.Click += (_, _) => { result = true; dialog.Close(); };
        cancel.Click += (_, _) => dialog.Close();
        close.Click += (_, _) => dialog.Close();

        var titleRow = new Grid { ColumnDefinitions = new ColumnDefinitions("*,Auto"), Background = Brushes.Transparent };
        titleRow.Children.Add(new TextBlock { Text = title.ToUpperInvariant(), Classes = { "section-title" }, VerticalAlignment = VerticalAlignment.Center });
        Grid.SetColumn(close, 1);
        titleRow.Children.Add(close);
        titleRow.PointerPressed += (_, e) =>
        {
            if (!IsFromButton(e.Source) && e.GetCurrentPoint(dialog).Properties.IsLeftButtonPressed)
                dialog.BeginMoveDrag(e);
        };

        dialog.Content = new Border
        {
            Classes = { "dialog-frame" },
            Child = new StackPanel
            {
                Margin = new Thickness(18, 12, 12, 18),
                Spacing = 14,
                Children =
                {
                    titleRow,
                    new TextBlock { Text = message, TextWrapping = TextWrapping.Wrap, FontSize = 12, Margin = new Thickness(0, 0, 6, 0) },
                    new StackPanel
                    {
                        Orientation = Orientation.Horizontal,
                        HorizontalAlignment = HorizontalAlignment.Right,
                        Spacing = 8,
                        Margin = new Thickness(0, 0, 6, 0),
                        Children = { cancel, ok },
                    },
                },
            },
        };
        dialog.KeyDown += (_, e) =>
        {
            if (e.Key == Key.Escape) dialog.Close();
        };
        await dialog.ShowDialog(this);
        return result;
    }
}
