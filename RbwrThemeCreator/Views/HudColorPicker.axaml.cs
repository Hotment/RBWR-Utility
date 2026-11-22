using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Data;
using Avalonia.Input;
using Avalonia.Media;
using RbwrThemeCreator.Services;

namespace RbwrThemeCreator.Views;

/// <summary>
/// Compact colour picker styled like the overlay HUD. Keeps the colour as HSV internally so the hue
/// is not lost when saturation or brightness reaches zero.
/// </summary>
public partial class HudColorPicker : UserControl
{
    public static readonly StyledProperty<Color> ColorProperty =
        AvaloniaProperty.Register<HudColorPicker, Color>(nameof(Color), Colors.White, defaultBindingMode: BindingMode.TwoWay);

    public static readonly StyledProperty<bool> IsAlphaEnabledProperty =
        AvaloniaProperty.Register<HudColorPicker, bool>(nameof(IsAlphaEnabled), true);

    /// <summary>Quick picks: the overlay's built-in theme colours.</summary>
    private static readonly string[] PaletteHex =
    [
        "#00f0ff", "#39ff14", "#ff003c", "#ffaa00", "#b026ff", "#ffffff", "#73839c",
        "#ffb000", "#7dff5a", "#60a5fa", "#4ade80", "#f87171", "#facc15", "#a78bfa",
        "#070a12", "#0f1422", "#111726", "#1b253b", "#192338", "#120c05", "#0b111a",
    ];

    private static IBrush? _checker;
    private HsvColor _hsv;
    private bool _updating;

    public Color Color
    {
        get => GetValue(ColorProperty);
        set => SetValue(ColorProperty, value);
    }

    public bool IsAlphaEnabled
    {
        get => GetValue(IsAlphaEnabledProperty);
        set => SetValue(IsAlphaEnabledProperty, value);
    }

    public HudColorPicker()
    {
        InitializeComponent();

        SwatchChecker.Background = Checker;
        PreviewChecker.Background = Checker;

        foreach (string hex in PaletteHex)
        {
            var c = Avalonia.Media.Color.Parse(hex);
            var b = new Button
            {
                Classes = { "palette" },
                Background = new SolidColorBrush(c),
                Tag = c,
            };
            ToolTip.SetTip(b, hex);
            b.Click += (_, _) =>
            {
                var picked = (Color)b.Tag!;
                Color = IsAlphaEnabled ? Avalonia.Media.Color.FromArgb(Color.A, picked.R, picked.G, picked.B) : picked;
            };
            Swatches.Children.Add(b);
        }

        Spectrum.PropertyChanged += (_, e) =>
        {
            if (e.Property == ColorSpectrum.HsvColorProperty) FromControl(Spectrum.HsvColor);
        };
        HueSlider.PropertyChanged += (_, e) =>
        {
            if (e.Property == ColorSlider.HsvColorProperty)
            {
                var h = HueSlider.HsvColor;
                FromControl(new HsvColor(_hsv.A, h.H, _hsv.S, _hsv.V));
            }
        };
        AlphaSlider.PropertyChanged += (_, e) =>
        {
            if (e.Property == ColorSlider.HsvColorProperty)
                FromControl(new HsvColor(AlphaSlider.HsvColor.A, _hsv.H, _hsv.S, _hsv.V));
        };

        HexBox.KeyDown += (_, e) =>
        {
            if (e.Key == Key.Enter) ApplyHex();
        };
        HexBox.LostFocus += (_, _) => ApplyHex();

        EyedropperButton.IsVisible = OperatingSystem.IsWindows();
        EyedropperButton.Click += async (_, _) => await PickFromScreenAsync(fromFlyout: true);
        InlineEyedropperButton.IsVisible = OperatingSystem.IsWindows();
        InlineEyedropperButton.Click += async (_, _) => await PickFromScreenAsync(fromFlyout: false);

        SetFromColor(Color);
        AlphaPanel.IsVisible = IsAlphaEnabled;
    }

    private static IBrush Checker => _checker ??= CreateChecker();

    protected override void OnPropertyChanged(AvaloniaPropertyChangedEventArgs change)
    {
        base.OnPropertyChanged(change);
        if (change.Property == ColorProperty && !_updating)
            SetFromColor(Color);
        else if (change.Property == IsAlphaEnabledProperty && AlphaPanel != null)
            AlphaPanel.IsVisible = IsAlphaEnabled;
    }

    /// <summary>External colour change: convert to HSV, keeping the previous hue for greys.</summary>
    private void SetFromColor(Color color)
    {
        var hsv = color.ToHsv();
        if (hsv.S < 0.0001 || hsv.V < 0.0001)
            hsv = new HsvColor(hsv.A, _hsv.H, hsv.V < 0.0001 ? _hsv.S : hsv.S, hsv.V);
        Sync(hsv);
    }

    /// <summary>Change coming from the spectrum/sliders.</summary>
    private void FromControl(HsvColor hsv)
    {
        if (_updating) return;
        if (!IsAlphaEnabled) hsv = new HsvColor(1, hsv.H, hsv.S, hsv.V);
        Sync(hsv);
        _updating = true;
        try
        {
            Color = hsv.ToRgb();
        }
        finally
        {
            _updating = false;
        }
    }

    private void Sync(HsvColor hsv)
    {
        _hsv = hsv;
        bool wasUpdating = _updating;
        _updating = true;
        try
        {
            Spectrum.HsvColor = hsv;
            HueSlider.HsvColor = new HsvColor(1, hsv.H, 1, 1);
            AlphaSlider.HsvColor = hsv;
            var rgb = hsv.ToRgb();
            var brush = new SolidColorBrush(rgb);
            SwatchFill.Background = brush;
            PreviewFill.Background = brush;
            HexBox.Text = ColorUtil.ToHex(rgb);
        }
        finally
        {
            _updating = wasUpdating;
        }
    }

    /// <summary>
    /// Lets the user pick a pixel anywhere on screen. When started from the flyout, the flyout is
    /// hidden so it does not cover the screen and reopened with the result afterwards. The current
    /// opacity is kept, like the palette swatches.
    /// </summary>
    private async Task PickFromScreenAsync(bool fromFlyout)
    {
        if (!OperatingSystem.IsWindows()) return;

        var flyout = fromFlyout ? SwatchButton.Flyout : null;
        flyout?.Hide();

        var picked = await EyedropperSession.PickAsync();
        if (picked is { } c)
            Color = IsAlphaEnabled ? Avalonia.Media.Color.FromArgb(Color.A, c.R, c.G, c.B) : c;

        flyout?.ShowAt(SwatchButton);
    }

    private void ApplyHex()
    {
        if (ColorUtil.TryParse(HexBox.Text, out var c))
        {
            if (!IsAlphaEnabled) c = Avalonia.Media.Color.FromArgb(255, c.R, c.G, c.B);
            if (c != Color) Color = c;
        }
        else
        {
            HexBox.Text = ColorUtil.ToHex(Color);
        }
    }

    private static IBrush CreateChecker()
    {
        var group = new DrawingGroup();
        group.Children.Add(new GeometryDrawing { Brush = new SolidColorBrush(Avalonia.Media.Color.Parse("#2a3142")), Geometry = new RectangleGeometry(new Rect(0, 0, 10, 10)) });
        group.Children.Add(new GeometryDrawing { Brush = new SolidColorBrush(Avalonia.Media.Color.Parse("#151a26")), Geometry = new RectangleGeometry(new Rect(0, 0, 5, 5)) });
        group.Children.Add(new GeometryDrawing { Brush = new SolidColorBrush(Avalonia.Media.Color.Parse("#151a26")), Geometry = new RectangleGeometry(new Rect(5, 5, 5, 5)) });
        return new DrawingBrush(group)
        {
            TileMode = TileMode.Tile,
            Stretch = Stretch.None,
            DestinationRect = new RelativeRect(0, 0, 10, 10, RelativeUnit.Absolute),
        };
    }
}
