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
    private CreatorUpdateWindow? _updateWindow;
    private bool _closeConfirmed;
    private bool _closingPromptOpen;

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
        Closed += (_, _) =>
        {
            foreach (var b in _activeBitmaps)
            {
                try { b.Dispose(); } catch { }
            }
            _activeBitmaps.Clear();
        };
        Viewport.SizeChanged += (_, _) => UpdateZoom();
        PreviewHost.SizeChanged += (_, _) => UpdateZoom();
        Viewport.PointerWheelChanged += OnViewportWheel;
        Viewport.AddHandler(PointerPressedEvent, OnViewportPointerPressed, Avalonia.Interactivity.RoutingStrategies.Tunnel);
        Viewport.PointerMoved += OnViewportPointerMoved;
        Viewport.PointerReleased += OnViewportPointerReleased;
        Viewport.PointerExited += (_, _) => ClearInspectHover();
        AddHandler(KeyDownEvent, OnShortcutKeyDown);
        AddHandler(KeyDownEvent, OnShortcutRecordingKeyDown, Avalonia.Interactivity.RoutingStrategies.Tunnel);
        AddHandler(DragDrop.DragOverEvent, OnWindowDragOver);
        AddHandler(DragDrop.DropEvent, OnWindowDrop);
        Opened += (_, _) =>
        {
            ApplyCornerPreference();
            var settings = CreatorSettings.Current;
            if (settings.CheckUpdatesAtStart)
                _ = _vm?.RunUpdateCheckAsync(isManual: false);
            if (settings.OpenLastThemeAtStart)
                _vm?.OpenLastTheme();
            // Older installed themes without preview.png get one (shown by the overlay's Theme Manager).
            if (settings.AutoCreateThumbnails)
                Dispatcher.UIThread.Post(() => _ = CreateMissingInstalledThumbnailsAsync(), DispatcherPriority.ApplicationIdle);
        };
        // Enter in a number box commits the value (the bindings update on focus loss).
        AddHandler(KeyDownEvent, (_, e) =>
        {
            if (e.Key is Key.Enter && (e.Source as Visual)?.FindAncestorOfType<TextBox>(includeSelf: true) is { } tb
                && (tb.Classes.Contains("num-input") || tb.Classes.Contains("hex")))
            {
                var expr = Avalonia.Data.BindingOperations.GetBindingExpressionBase(tb, TextBox.TextProperty);
                expr?.UpdateSource();
                // Show the value that was actually applied (rejected or clamped input snaps back).
                Dispatcher.UIThread.Post(() => { expr?.UpdateTarget(); tb.SelectAll(); }, DispatcherPriority.Background);
                e.Handled = true;
            }
        }, Avalonia.Interactivity.RoutingStrategies.Tunnel);
        AddHandler(LostFocusEvent, (_, e) =>
        {
            if (e.Source is TextBox tb && (tb.Classes.Contains("num-input") || tb.Classes.Contains("hex")))
            {
                var expr = Avalonia.Data.BindingOperations.GetBindingExpressionBase(tb, TextBox.TextProperty);
                Dispatcher.UIThread.Post(() => expr?.UpdateTarget(), DispatcherPriority.Background);
            }
        }, Avalonia.Interactivity.RoutingStrategies.Bubble, handledEventsToo: true);
    }

    private void AttachViewModel(MainViewModel? vm)
    {
        if (_vm != null)
        {
            _vm.PreviewReady -= OnPreviewReady;
            _vm.PropertyChanged -= OnViewModelPropertyChanged;
            _vm.RequestShowUpdate -= OnShowUpdate;
            _vm.Dialogs = null;
        }
        _vm = vm;
        if (vm == null) return;

        vm.Dialogs = this;
        vm.PreviewReady += OnPreviewReady;
        vm.PropertyChanged += OnViewModelPropertyChanged;
        vm.RequestShowUpdate += OnShowUpdate;
        vm.Shortcuts.Changed += (_, _) => UpdateShortcutHints();
        UpdateShortcutHints();
        ApplyBackdrop(vm.PreviewBackdrop);
        Preview.SetMode(vm.PreviewMode);
        vm.Refresh();
        UpdateZoom();
    }

    private void OnShowUpdate(RbwrOverlay.Core.Models.UpdateInfo info)
    {
        Dispatcher.UIThread.Post(() =>
        {
            if (_updateWindow != null)
            {
                _updateWindow.Activate();
                return;
            }
            if (_vm == null) return;

            var updateVm = new CreatorUpdateViewModel(
                _vm.UpdateService,
                info,
                MainViewModel.AppVersion,
                _vm.SkipVersion);

            _updateWindow = new CreatorUpdateWindow { DataContext = updateVm };
            _updateWindow.Closed += (_, _) => _updateWindow = null;
            if (IsVisible)
                _updateWindow.Show(this);
            else
                _updateWindow.Show();
        });
    }

    private void OnViewModelPropertyChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (_vm == null) return;
        if (e.PropertyName == nameof(MainViewModel.PreviewBackdrop))
            ApplyBackdrop(_vm.PreviewBackdrop);
        else if (e.PropertyName == nameof(MainViewModel.CurrentFolder))
            OnThemeFolderOpened();
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
        QueueThemeCardThumbnail();

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

        // FIND COLOUR: Ctrl+click (or a click while the toggle is on) jumps to the element's colours.
        if (props.IsLeftButtonPressed && IsInspecting(e.KeyModifiers))
        {
            if (FindTokenElement(e.Source) is { } hit)
            {
                e.Handled = true;
                _ = ShowTokensForElementAsync(hit.Element, hit.Keys);
                return;
            }
            if (InspectToggle.IsChecked == true)
            {
                _vm?.SetStatus("No editable colour is mapped to that spot. Try a card, title, button, slider or the window background.");
                e.Handled = true;
                return;
            }
        }

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
        if (!_panning)
        {
            UpdateInspectHover(e);
            return;
        }
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
        WindowFrame.BorderThickness = new Thickness(_maximized ? 0 : 1);
        ApplyCornerPreference();
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

    private void OnWindowDragOver(object? sender, DragEventArgs e)
    {
        var files = e.DataTransfer.TryGetFiles();
        e.DragEffects = files != null && files.Any() ? DragDropEffects.Copy : DragDropEffects.None;
        e.Handled = true;
    }

    private async void OnWindowDrop(object? sender, DragEventArgs e)
    {
        if (_vm == null) return;
        var files = e.DataTransfer.TryGetFiles();
        if (files == null) return;
        var paths = files
            .Select(f => f.TryGetLocalPath())
            .Where(p => !string.IsNullOrWhiteSpace(p))
            .Select(p => p!)
            .ToList();
        if (paths.Count > 0)
        {
            await _vm.HandleDroppedPathsAsync(paths);
            e.Handled = true;
        }
    }

    /// <summary>Renders the preview as it is shown now (current view), at <paramref name="scale"/>x.</summary>
    private RenderTargetBitmap RenderPreview(double scale)
    {
        var size = PreviewHost.Bounds.Size;
        if (size.Width < 1 || size.Height < 1)
            size = PreviewHost.DesiredSize;
        int pxW = Math.Max(1, (int)Math.Ceiling(size.Width * scale));
        int pxH = Math.Max(1, (int)Math.Ceiling(size.Height * scale));

        var rtb = new RenderTargetBitmap(new PixelSize(pxW, pxH), new Vector(96 * scale, 96 * scale));
        rtb.Render(PreviewHost);
        return rtb;
    }

    private async void OnExportPreviewPngClick(object? sender, RoutedEventArgs e)
    {
        if (_vm == null) return;
        string suggested = string.IsNullOrWhiteSpace(_vm.ThemeId) ? "theme-preview.png" : $"{_vm.ThemeId}-preview.png";
        string? outPath = await PickSaveFileAsync("Export preview screenshot", suggested, "PNG image (*.png)", "*.png");
        if (string.IsNullOrWhiteSpace(outPath)) return;

        try
        {
            ClearInspectHover();
            using var rtb = RenderPreview(2.0);
            using (var fs = File.Create(outPath))
            {
                rtb.Save(fs, new PngBitmapEncoderOptions());
            }
            _vm.SetStatus($"Saved preview screenshot to {Path.GetFileName(outPath)} ({rtb.PixelSize.Width}x{rtb.PixelSize.Height}).");
        }
        catch (Exception ex)
        {
            _vm.SetStatus($"Could not export preview PNG: {ex.Message}", isError: true);
        }
    }

    /// <summary>Copies the preview as an image so it can be pasted straight into Discord.</summary>
    private async void OnCopyPreviewImageClick(object? sender, RoutedEventArgs e) => await CopyPreviewImageAsync();

    private async Task CopyPreviewImageAsync()
    {
        if (_vm == null || Clipboard == null) return;
        try
        {
            ClearInspectHover();
            using var rtb = RenderPreview(2.0);
            await Clipboard.SetBitmapAsync(rtb);
            _vm.SetStatus("Preview image copied. Paste it on Discord (or anywhere) with Ctrl+V.");
        }
        catch (Exception ex)
        {
            _vm.SetStatus($"Could not copy the preview image: {ex.Message}", isError: true);
        }
    }

    /// <summary>
    /// preview.png for saved and exported themes: the MONITOR view of the edited theme, rendered off
    /// screen (see MainWindow.Thumbnails.cs), so the live preview is never switched or redrawn.
    /// </summary>
    public byte[]? RenderThumbnailPng() => _vm == null ? null : RenderThemeThumbnail(_vm.BuildState());

    // ===================== FIND COLOUR (click an element in the preview) =====================

    private bool IsInspecting(KeyModifiers modifiers) =>
        InspectToggle.IsChecked == true || modifiers.HasFlag(KeyModifiers.Control);

    private void OnInspectToggled(object? sender, RoutedEventArgs e)
    {
        bool on = InspectToggle.IsChecked == true;
        if (!on) ClearInspectHover();
        _vm?.SetStatus(on
            ? "FIND COLOUR: click an element in the preview to jump to its colours. Esc to stop."
            : "Ready.");
    }

    /// <summary>The innermost preview element under the pointer that a colour token is mapped to.</summary>
    private (Control Element, string[] Keys)? FindTokenElement(object? source)
    {
        for (var v = source as Visual; v != null && v != Viewport; v = v.GetVisualParent())
        {
            if (v is not Control c) continue;
            if (TokenLocations.TryGetTokensForElement(c.Name, out var keys))
                return (c, keys);
            if (c is Slider)
                return (c, TokenLocations.SliderTokens);
        }
        return null;
    }

    private void UpdateInspectHover(PointerEventArgs e)
    {
        if (!IsInspecting(e.KeyModifiers))
        {
            ClearInspectHover();
            return;
        }
        var hit = FindTokenElement(e.Source);
        Preview.SetHoverTarget(hit?.Element);
        Viewport.Cursor = hit != null ? new Cursor(StandardCursorType.Hand) : Cursor.Default;
    }

    private void ClearInspectHover()
    {
        Preview.SetHoverTarget(null);
        if (!_panning) Viewport.Cursor = Cursor.Default;
    }

    private async Task ShowTokensForElementAsync(Control element, string[] keys)
    {
        if (_vm == null) return;
        var tokens = _vm.GetTokens(keys);
        if (tokens.Count == 0) return;

        Preview.Highlight([element]);
        NavTabs.SelectedItem = ColoursTab;
        string name = string.IsNullOrEmpty(element.Name) ? element.GetType().Name : element.Name;
        _vm.SetStatus($"{name} uses: {string.Join(", ", tokens.Select(t => t.Label))}");

        // Starts the flash (and clears a search that would hide these rows) before the scroll.
        var flash = _vm.FlashTokensAsync(tokens);
        await Dispatcher.UIThread.InvokeAsync(() => { }, DispatcherPriority.Loaded);

        string firstKey = tokens[0].Key;
        var row = NavTabs.GetVisualDescendants().OfType<Border>()
            .FirstOrDefault(b => b.Classes.Contains("token-row") && Equals(b.Tag, firstKey));
        // A little extra room above and below so the neighbouring rows are visible too.
        row?.BringIntoView(new Rect(0, -60, row.Bounds.Width, row.Bounds.Height + 120));

        await flash;
    }

    private async void OnClosing(object? sender, WindowClosingEventArgs e)
    {
        if (_closeConfirmed || _vm == null || !_vm.IsDirty)
            return;

        e.Cancel = true;
        if (_closingPromptOpen)
            return;
        _closingPromptOpen = true;
        try
        {
            if (await ConfirmAsync("Unsaved changes", "The theme has unsaved changes. Close anyway?", "Close without saving"))
            {
                _closeConfirmed = true;
                Close();
            }
        }
        finally
        {
            _closingPromptOpen = false;
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
        // Let DWM draw the rounded outer border on Windows 11 so WindowFrame's square border does not clip at the corners.
        WindowFrame.BorderThickness = new Thickness(0);
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
