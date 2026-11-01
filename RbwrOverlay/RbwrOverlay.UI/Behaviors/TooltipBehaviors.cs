using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Controls.Primitives.PopupPositioning;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Media;
using Avalonia.Threading;
using Avalonia.VisualTree;
using RbwrOverlay.UI.ViewModels;

namespace RbwrOverlay.UI.Behaviors;

public static class TooltipBehaviors
{
    public static readonly AttachedProperty<string?> KeyProperty =
        AvaloniaProperty.RegisterAttached<Control, string?>(
            "Key",
            typeof(TooltipBehaviors),
            defaultValue: null);

    public static readonly AttachedProperty<TooltipItem?> ItemProperty =
        AvaloniaProperty.RegisterAttached<Control, TooltipItem?>(
            "Item",
            typeof(TooltipBehaviors),
            defaultValue: null);

    private static readonly List<WindowTooltipSession> ActiveSessions = new();

    public static string? GetKey(Control element) => element.GetValue(KeyProperty);
    public static void SetKey(Control element, string? value) => element.SetValue(KeyProperty, value);

    public static TooltipItem? GetItem(Control element) => element.GetValue(ItemProperty);
    public static void SetItem(Control element, TooltipItem? value) => element.SetValue(ItemProperty, value);

    static TooltipBehaviors()
    {
        KeyProperty.Changed.AddClassHandler<Control>((control, _) => NotifyControlChanged(control));
        ItemProperty.Changed.AddClassHandler<Control>((control, _) => NotifyControlChanged(control));
        TooltipCatalog.EnabledChanged += OnCatalogEnabledChanged;
    }

    public static void AttachWindow(Window window, Panel rootHostPanel)
    {
        for (int i = ActiveSessions.Count - 1; i >= 0; i--)
        {
            if (ReferenceEquals(ActiveSessions[i].Window, window))
            {
                return;
            }
        }

        var session = new WindowTooltipSession(window, rootHostPanel);
        ActiveSessions.Add(session);
    }

    private static void RemoveSession(WindowTooltipSession session)
    {
        ActiveSessions.Remove(session);
    }

    private static void NotifyControlChanged(Control control)
    {
        for (int i = ActiveSessions.Count - 1; i >= 0; i--)
        {
            ActiveSessions[i].RefreshIfTracking(control);
        }
    }

    private static void OnCatalogEnabledChanged()
    {
        if (!TooltipCatalog.IsEnabled)
        {
            for (int i = ActiveSessions.Count - 1; i >= 0; i--)
            {
                ActiveSessions[i].Hide();
            }
        }
    }

    private static (Control? Target, TooltipItem? Item) ResolveTooltip(Visual? source, Window window)
    {
        if (!TooltipCatalog.IsEnabled)
        {
            return (null, null);
        }

        for (var current = source; current != null && !ReferenceEquals(current, window); current = current.GetVisualParent())
        {
            if (current is Control control)
            {
                var directItem = GetItem(control);
                if (directItem != null)
                {
                    return (control, directItem);
                }

                var key = GetKey(control);
                if (!string.IsNullOrWhiteSpace(key))
                {
                    var catalogItem = TooltipCatalog.Get(key);
                    if (catalogItem != null)
                    {
                        return (control, catalogItem);
                    }
                }
            }
        }

        return (null, null);
    }

    private sealed class WindowTooltipSession
    {
        private static readonly TimeSpan InitialShowDelay = TimeSpan.FromMilliseconds(180);
        private static readonly FontFamily TooltipFont = new("Consolas, 'Segoe UI', Inter, monospace");

        public Window Window { get; }

        private readonly Popup _popup;
        private readonly ScaleTransform _scaleTransform;
        private readonly TextBlock _titleBlock;
        private readonly TextBlock _descBlock;
        private readonly DispatcherTimer _showTimer;

        private Control? _activeControl;
        private TooltipItem? _activeItem;
        private Point _lastCursorPoint;

        public WindowTooltipSession(Window window, Panel rootHostPanel)
        {
            Window = window;

            _titleBlock = new TextBlock
            {
                Foreground = new SolidColorBrush(Color.Parse("#00f0ff")),
                FontFamily = TooltipFont,
                FontWeight = FontWeight.Bold,
                FontSize = 10,
                LetterSpacing = 0.5,
                TextAlignment = TextAlignment.Left,
                TextWrapping = TextWrapping.Wrap
            };

            var divider = new Border
            {
                Height = 1,
                Background = new SolidColorBrush(Color.Parse("#1b253b"))
            };

            _descBlock = new TextBlock
            {
                Foreground = new SolidColorBrush(Color.Parse("#dce6f5")),
                FontFamily = TooltipFont,
                FontSize = 9.5,
                LineHeight = 13.5,
                TextAlignment = TextAlignment.Left,
                TextWrapping = TextWrapping.Wrap
            };

            var contentStack = new StackPanel
            {
                Spacing = 4,
                MaxWidth = 260,
                IsHitTestVisible = false,
                Children =
                {
                    _titleBlock,
                    divider,
                    _descBlock
                }
            };

            var cardBorder = new Border
            {
                Background = new SolidColorBrush(Color.Parse("#f7080d18")),
                BorderBrush = new SolidColorBrush(Color.Parse("#8c00f0ff")),
                BorderThickness = new Thickness(1),
                CornerRadius = new CornerRadius(6),
                Padding = new Thickness(10, 7),
                MaxWidth = 285,
                IsHitTestVisible = false,
                Child = contentStack
            };

            _scaleTransform = new ScaleTransform(1.0, 1.0);
            var scaleWrapper = new LayoutTransformControl
            {
                LayoutTransform = _scaleTransform,
                IsHitTestVisible = false,
                Child = cardBorder
            };

            _popup = new Popup
            {
                PlacementTarget = window,
                Placement = PlacementMode.AnchorAndGravity,
                PlacementAnchor = PopupAnchor.BottomRight,
                PlacementGravity = PopupGravity.BottomRight,
                PlacementConstraintAdjustment =
                    PopupPositionerConstraintAdjustment.FlipX |
                    PopupPositionerConstraintAdjustment.FlipY |
                    PopupPositionerConstraintAdjustment.SlideX |
                    PopupPositionerConstraintAdjustment.SlideY,
                HorizontalOffset = 0,
                VerticalOffset = 0,
                IsLightDismissEnabled = false,
                WindowManagerAddShadowHint = false,
                IsHitTestVisible = false,
                Focusable = false,
                Topmost = true,
                Child = scaleWrapper
            };

            rootHostPanel.Children.Add(_popup);

            _showTimer = new DispatcherTimer
            {
                Interval = InitialShowDelay
            };
            _showTimer.Tick += OnShowTimerTick;

            window.AddHandler(InputElement.PointerMovedEvent, OnPointerMoved, RoutingStrategies.Bubble, handledEventsToo: true);
            window.AddHandler(InputElement.PointerPressedEvent, OnPointerPressed, RoutingStrategies.Tunnel, handledEventsToo: true);
            window.AddHandler(InputElement.PointerWheelChangedEvent, OnPointerWheelChanged, RoutingStrategies.Tunnel, handledEventsToo: true);
            window.PointerExited += OnWindowPointerExited;
            window.Deactivated += OnWindowDeactivated;
            window.Closed += OnWindowClosed;
        }

        public void RefreshIfTracking(Control control)
        {
            if (!ReferenceEquals(_activeControl, control))
            {
                return;
            }

            var (_, updatedItem) = ResolveTooltip(control, Window);
            if (updatedItem == null)
            {
                Hide();
                return;
            }

            _activeItem = updatedItem;
            if (_popup.IsOpen)
            {
                ApplyItemContent(updatedItem);
                UpdatePopupPosition(_lastCursorPoint);
            }
        }

        public void Hide()
        {
            _showTimer.Stop();
            _activeControl = null;
            _activeItem = null;
            if (_popup.IsOpen)
            {
                _popup.IsOpen = false;
            }
        }

        private void OnPointerMoved(object? sender, PointerEventArgs e)
        {
            _lastCursorPoint = e.GetPosition(Window);

            var (target, item) = ResolveTooltip(e.Source as Visual, Window);
            if (target == null || item == null)
            {
                Hide();
                return;
            }

            _activeControl = target;
            _activeItem = item;

            if (_popup.IsOpen)
            {
                ApplyItemContent(item);
                UpdateScale();
                UpdatePopupPosition(_lastCursorPoint);
            }
            else if (!_showTimer.IsEnabled)
            {
                _showTimer.Start();
            }
        }

        private void OnShowTimerTick(object? sender, EventArgs e)
        {
            _showTimer.Stop();

            if (!TooltipCatalog.IsEnabled || _activeItem == null || !Window.IsVisible || !Window.IsPointerOver)
            {
                Hide();
                return;
            }

            ApplyItemContent(_activeItem);
            UpdateScale();
            UpdatePopupPosition(_lastCursorPoint);
            _popup.IsOpen = true;
        }

        private void ApplyItemContent(TooltipItem item)
        {
            if (_titleBlock.Text != item.Title)
            {
                _titleBlock.Text = item.Title;
            }

            if (_descBlock.Text != item.Description)
            {
                _descBlock.Text = item.Description;
            }
        }

        private void UpdateScale()
        {
            double scale = 1.0;
            if (Window.DataContext is MainOverlayViewModel vm)
            {
                scale = Math.Clamp(vm.ActiveUiScale, 0.9, 1.35);
            }

            if (Math.Abs(_scaleTransform.ScaleX - scale) > 0.001)
            {
                _scaleTransform.ScaleX = scale;
                _scaleTransform.ScaleY = scale;
            }
        }

        private void UpdatePopupPosition(Point cursorPoint)
        {
            _popup.PlacementRect = new Rect(cursorPoint.X - 12, cursorPoint.Y - 12, 26, 30);
        }

        private void OnPointerPressed(object? sender, PointerPressedEventArgs e) => Hide();

        private void OnPointerWheelChanged(object? sender, PointerWheelEventArgs e) => Hide();

        private void OnWindowPointerExited(object? sender, PointerEventArgs e)
        {
            if (!Window.IsPointerOver)
            {
                Hide();
            }
        }

        private void OnWindowDeactivated(object? sender, EventArgs e) => Hide();

        private void OnWindowClosed(object? sender, EventArgs e)
        {
            Hide();
            Window.RemoveHandler(InputElement.PointerMovedEvent, OnPointerMoved);
            Window.RemoveHandler(InputElement.PointerPressedEvent, OnPointerPressed);
            Window.RemoveHandler(InputElement.PointerWheelChangedEvent, OnPointerWheelChanged);
            Window.PointerExited -= OnWindowPointerExited;
            Window.Deactivated -= OnWindowDeactivated;
            Window.Closed -= OnWindowClosed;
            RemoveSession(this);
        }
    }
}