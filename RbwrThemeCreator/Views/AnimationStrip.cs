using Avalonia;
using Avalonia.Animation;
using Avalonia.Controls;
using Avalonia.Media;
using Avalonia.Styling;
using RbwrThemeCreator.Models;

namespace RbwrThemeCreator.Views;

/// <summary>
/// Plays a colour's animation live on a Border, the same way the overlay will (all at once, or the
/// colours flowing along in the chosen direction):
/// <c>views:AnimationStrip.Animation="{Binding …}"</c> animates the fill,
/// <c>views:AnimationStrip.BorderAnimation="{Binding …}"</c> the outline.
/// Used by the ANIMATE panel strip, the THEME tab card and the preview's CONFIG theme list.
/// </summary>
public static class AnimationStrip
{
    public static readonly AttachedProperty<TokenAnimation?> AnimationProperty =
        AvaloniaProperty.RegisterAttached<Border, TokenAnimation?>("Animation", typeof(AnimationStrip));

    public static readonly AttachedProperty<TokenAnimation?> BorderAnimationProperty =
        AvaloniaProperty.RegisterAttached<Border, TokenAnimation?>("BorderAnimation", typeof(AnimationStrip));

    private static readonly AttachedProperty<CancellationTokenSource?> RunningProperty =
        AvaloniaProperty.RegisterAttached<Border, CancellationTokenSource?>("Running", typeof(AnimationStrip));

    private static readonly AttachedProperty<CancellationTokenSource?> RunningBorderProperty =
        AvaloniaProperty.RegisterAttached<Border, CancellationTokenSource?>("RunningBorder", typeof(AnimationStrip));

    static AnimationStrip()
    {
        AnimationProperty.Changed.AddClassHandler<Border>((border, e) =>
            Restart(border, Border.BackgroundProperty, e.NewValue as TokenAnimation, RunningProperty));
        BorderAnimationProperty.Changed.AddClassHandler<Border>((border, e) =>
            Restart(border, Border.BorderBrushProperty, e.NewValue as TokenAnimation, RunningBorderProperty));
    }

    public static TokenAnimation? GetAnimation(Border border) => border.GetValue(AnimationProperty);
    public static void SetAnimation(Border border, TokenAnimation? value) => border.SetValue(AnimationProperty, value);
    public static TokenAnimation? GetBorderAnimation(Border border) => border.GetValue(BorderAnimationProperty);
    public static void SetBorderAnimation(Border border, TokenAnimation? value) => border.SetValue(BorderAnimationProperty, value);

    private static void Restart(Border border, AvaloniaProperty property, TokenAnimation? anim, AttachedProperty<CancellationTokenSource?> running)
    {
        border.GetValue(running)?.Cancel();
        border.SetValue(running, null);
        if (anim is not { Colors.Count: >= 2 })
            return;

        var brushes = Brushes(anim);
        var animation = new Animation
        {
            Duration = TimeSpan.FromSeconds(Math.Clamp(anim.Seconds, 1, 60)),
            IterationCount = IterationCount.Infinite,
        };
        for (int i = 0; i < brushes.Count; i++)
        {
            animation.Children.Add(new KeyFrame
            {
                Cue = new Cue((double)i / (brushes.Count - 1)),
                Setters = { new Setter(property, brushes[i]) },
            });
        }

        var cts = new CancellationTokenSource();
        border.SetValue(running, cts);
        border.DetachedFromVisualTree += (_, _) => cts.Cancel();
        _ = animation.RunAsync(border, cts.Token);
    }

    /// <summary>Key frame brushes (same idea as ThemeXamlGenerator.TokenFrames, as brushes).</summary>
    public static IReadOnlyList<IBrush> Brushes(TokenAnimation anim)
    {
        var colours = anim.Colors.Take(TokenAnimation.MaxColors).ToList();
        var result = new List<IBrush>();
        if (!anim.Flow)
        {
            foreach (var c in colours.Append(colours[0]))
                result.Add(new SolidColorBrush(c));
            return result;
        }

        var (sx, sy, ex, ey) = new GradientSpec([colours[0]], anim.Angle).Points();
        int n = colours.Count;
        for (int shift = 0; shift <= n; shift++)
        {
            var brush = new LinearGradientBrush
            {
                StartPoint = new RelativePoint(sx / 100, sy / 100, RelativeUnit.Relative),
                EndPoint = new RelativePoint(ex / 100, ey / 100, RelativeUnit.Relative),
            };
            for (int k = 0; k <= n; k++)
                brush.GradientStops.Add(new GradientStop(colours[(k + shift) % n], (double)k / n));
            result.Add(brush);
        }
        return result;
    }
}
