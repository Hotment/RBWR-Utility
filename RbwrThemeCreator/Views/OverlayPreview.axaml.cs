using Avalonia;
using Avalonia.Animation;
using Avalonia.Animation.Easings;
using Avalonia.Controls;
using Avalonia.Media;
using Avalonia.Styling;

namespace RbwrThemeCreator.Views;

public partial class OverlayPreview : UserControl
{
    public const int ModeMonitor = 0;
    public const int ModeConfig = 1;
    public const int ModeCompact = 2;
    public const int ModeTablet = 3;
    public const int ModeAll = 4;

    private const double Gap = 28;

    public OverlayPreview()
    {
        InitializeComponent();
        SetMode(ModeMonitor);
    }

    /// <summary>Shows one overlay view, or all of them in a fixed 2x2 layout.</summary>
    public void SetMode(int mode)
    {
        DetailedShell.IsVisible = mode is ModeMonitor or ModeAll;
        ConfigShell.IsVisible = mode is ModeConfig or ModeAll;
        CompactGroup.IsVisible = mode is ModeCompact or ModeAll;
        TabletShell.IsVisible = mode is ModeTablet or ModeAll;

        Place(DetailedShell, 0, 0, new Thickness(0));
        if (mode == ModeAll)
        {
            Place(ConfigShell, 0, 1, new Thickness(Gap, 0, 0, 0));
            Place(TabletShell, 1, 0, new Thickness(0, Gap, 0, 0));
            Place(CompactGroup, 1, 1, new Thickness(Gap, Gap, 0, 0));
            Grid.SetColumnSpan(CompactGroup, 1);
            CompactGroup.Orientation = Avalonia.Layout.Orientation.Vertical;
        }
        else
        {
            Place(ConfigShell, 0, 0, new Thickness(0));
            Place(TabletShell, 0, 0, new Thickness(0));
            Place(CompactGroup, 0, 0, new Thickness(0));
            Grid.SetColumnSpan(CompactGroup, 1);
            CompactGroup.Orientation = mode == ModeCompact ? Avalonia.Layout.Orientation.Vertical : Avalonia.Layout.Orientation.Horizontal;
        }
    }

    /// <summary>
    /// Briefly outlines the named elements with a soft glow that fades out, so the user can see
    /// where a colour token is used.
    /// </summary>
    public void Highlight(IEnumerable<string> elementNames)
    {
        HighlightLayer.Children.Clear();
        foreach (string name in elementNames)
        {
            if (this.FindControl<Control>(name) is not { IsEffectivelyVisible: true } target)
                continue;
            var topLeft = target.TranslatePoint(new Point(0, 0), HighlightLayer);
            if (topLeft == null || target.Bounds.Width < 1)
                continue;

            const double pad = 4;
            var radius = target is Border tb
                ? new CornerRadius(
                    tb.CornerRadius.TopLeft + 2,
                    tb.CornerRadius.TopRight + 2,
                    tb.CornerRadius.BottomRight + 2,
                    tb.CornerRadius.BottomLeft + 2)
                : new CornerRadius(8);
            var marker = new Border
            {
                Width = target.Bounds.Width + pad * 2,
                Height = target.Bounds.Height + pad * 2,
                CornerRadius = radius,
                BorderThickness = new Thickness(2),
                BorderBrush = new SolidColorBrush(Color.Parse("#ffffff")),
                Background = new SolidColorBrush(Color.Parse("#22ffffff")),
                BoxShadow = BoxShadows.Parse("0 0 18 4 #aaffffff"),
                Opacity = 0,
            };
            Canvas.SetLeft(marker, topLeft.Value.X - pad);
            Canvas.SetTop(marker, topLeft.Value.Y - pad);
            HighlightLayer.Children.Add(marker);
            _ = AnimateAndRemove(marker);
        }
    }

    private async Task AnimateAndRemove(Border marker)
    {
        // Quick fade-in, a gentle second pulse, then a long soft fade-out.
        var animation = new Animation
        {
            Duration = TimeSpan.FromMilliseconds(1900),
            Easing = new SineEaseInOut(),
            FillMode = FillMode.Forward,
            Children =
            {
                new KeyFrame { Cue = new Cue(0.0), Setters = { new Setter(OpacityProperty, 0d) } },
                new KeyFrame { Cue = new Cue(0.10), Setters = { new Setter(OpacityProperty, 1d) } },
                new KeyFrame { Cue = new Cue(0.28), Setters = { new Setter(OpacityProperty, 0.45d) } },
                new KeyFrame { Cue = new Cue(0.42), Setters = { new Setter(OpacityProperty, 1d) } },
                new KeyFrame { Cue = new Cue(1.0), Setters = { new Setter(OpacityProperty, 0d) } },
            },
        };
        await animation.RunAsync(marker);
        HighlightLayer.Children.Remove(marker);
    }

    private static void Place(Control c, int row, int column, Thickness margin)
    {
        Grid.SetRow(c, row);
        Grid.SetColumn(c, column);
        c.Margin = margin;
    }
}
