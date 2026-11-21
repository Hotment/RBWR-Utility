using Avalonia;
using Avalonia.Animation;
using Avalonia.Controls;
using Avalonia.Markup.Xaml.MarkupExtensions;
using Avalonia.Styling;
using RbwrOverlay.UI.Services;

namespace RbwrOverlay.UI.Behaviors;

/// <summary>
/// Gives an element its own copy of a theme's resources. Every {DynamicResource ...} inside it
/// (texts, badges, buttons, the card background) then resolves to that theme instead of the active
/// one. Used by the Theme Manager to draw each theme's card in its own colours. A Border is also
/// filled with the theme's main background (gradients included) and outlined in its window glow colour.
/// </summary>
public static class ThemeCardBehaviors
{
    public static readonly AttachedProperty<IReadOnlyDictionary<object, object?>?> ResourcesProperty =
        AvaloniaProperty.RegisterAttached<StyledElement, IReadOnlyDictionary<object, object?>?>(
            "Resources",
            typeof(ThemeCardBehaviors));

    /// <summary>The theme's animated main background: the card's fill plays it.</summary>
    public static readonly AttachedProperty<CardAnimation?> BackgroundAnimationProperty =
        AvaloniaProperty.RegisterAttached<Border, CardAnimation?>("BackgroundAnimation", typeof(ThemeCardBehaviors));

    /// <summary>The theme's animated window outline (Shell border glow): the card's outline plays it.</summary>
    public static readonly AttachedProperty<CardAnimation?> BorderAnimationProperty =
        AvaloniaProperty.RegisterAttached<Border, CardAnimation?>("BorderAnimation", typeof(ThemeCardBehaviors));

    private static readonly AttachedProperty<CancellationTokenSource?> RunningBackgroundProperty =
        AvaloniaProperty.RegisterAttached<Border, CancellationTokenSource?>("RunningBackground", typeof(ThemeCardBehaviors));

    private static readonly AttachedProperty<CancellationTokenSource?> RunningBorderProperty =
        AvaloniaProperty.RegisterAttached<Border, CancellationTokenSource?>("RunningBorder", typeof(ThemeCardBehaviors));

    /// <summary>
    /// A theme's animation styles (XAML &lt;Styles&gt;) applied to this element and everything inside it, so the
    /// inside of a theme card animates like the overlay with that theme.
    /// </summary>
    public static readonly AttachedProperty<string?> AnimationStylesProperty =
        AvaloniaProperty.RegisterAttached<StyledElement, string?>("AnimationStyles", typeof(ThemeCardBehaviors));

    private static readonly AttachedProperty<IStyle?> AddedStylesProperty =
        AvaloniaProperty.RegisterAttached<StyledElement, IStyle?>("AddedStyles", typeof(ThemeCardBehaviors));

    public static string? GetAnimationStyles(StyledElement e) => e.GetValue(AnimationStylesProperty);
    public static void SetAnimationStyles(StyledElement e, string? value) => e.SetValue(AnimationStylesProperty, value);

    private static void ApplyAnimationStyles(StyledElement element, string? xaml)
    {
        if (element.GetValue(AddedStylesProperty) is { } old)
        {
            element.Styles.Remove(old);
            element.SetValue(AddedStylesProperty, null);
        }
        if (string.IsNullOrWhiteSpace(xaml)) return;
        try
        {
            // A fresh copy per card: a style collection can only belong to one element.
            var styles = Avalonia.Markup.Xaml.AvaloniaRuntimeXamlLoader.Parse<Styles>(xaml);
            element.Styles.Add(styles);
            element.SetValue(AddedStylesProperty, styles);
        }
        catch
        {
            // the card just does not animate inside
        }
    }

    private static readonly ResourceDictionary MarkerKey = new();

    static ThemeCardBehaviors()
    {
        AnimationStylesProperty.Changed.AddClassHandler<StyledElement>((e, args) => ApplyAnimationStyles(e, args.NewValue as string));
        ResourcesProperty.Changed.AddClassHandler<StyledElement>((element, e) => Apply(element, e.NewValue as IReadOnlyDictionary<object, object?>));
        BackgroundAnimationProperty.Changed.AddClassHandler<Border>((b, e) =>
            Run(b, Border.BackgroundProperty, e.NewValue as CardAnimation, RunningBackgroundProperty));
        BorderAnimationProperty.Changed.AddClassHandler<Border>((b, e) =>
            Run(b, Border.BorderBrushProperty, e.NewValue as CardAnimation, RunningBorderProperty));
    }

    public static CardAnimation? GetBackgroundAnimation(Border b) => b.GetValue(BackgroundAnimationProperty);
    public static void SetBackgroundAnimation(Border b, CardAnimation? value) => b.SetValue(BackgroundAnimationProperty, value);
    public static CardAnimation? GetBorderAnimation(Border b) => b.GetValue(BorderAnimationProperty);
    public static void SetBorderAnimation(Border b, CardAnimation? value) => b.SetValue(BorderAnimationProperty, value);

    /// <summary>
    /// Plays the animation on the card while it is on screen; stops it when the card is removed (the list
    /// is rebuilt on every search keystroke) so nothing keeps running in the background.
    /// </summary>
    private static void Run(Border border, AvaloniaProperty property, CardAnimation? anim, AttachedProperty<CancellationTokenSource?> running)
    {
        border.GetValue(running)?.Cancel();
        border.SetValue(running, null);
        if (anim is not { Colors.Count: >= 2 }) return;

        try
        {
            var frames = anim.Frames();
            var animation = new Animation
            {
                Duration = TimeSpan.FromSeconds(anim.Seconds),
                IterationCount = IterationCount.Infinite,
            };
            for (int i = 0; i < frames.Count; i++)
                animation.Children.Add(new KeyFrame { Cue = new Cue((double)i / (frames.Count - 1)), Setters = { new Setter(property, frames[i]) } });

            var cts = new CancellationTokenSource();
            border.SetValue(running, cts);
            border.DetachedFromVisualTree += (_, _) => cts.Cancel();
            _ = animation.RunAsync(border, cts.Token);
        }
        catch
        {
            // the card just stays still
        }
    }

    public static IReadOnlyDictionary<object, object?>? GetResources(StyledElement element) => element.GetValue(ResourcesProperty);

    public static void SetResources(StyledElement element, IReadOnlyDictionary<object, object?>? value) => element.SetValue(ResourcesProperty, value);

    private static void Apply(StyledElement element, IReadOnlyDictionary<object, object?>? resources)
    {
        var merged = element.Resources.MergedDictionaries;
        // Remove the dictionary this behaviour added before (if any); keep anything else.
        foreach (var old in merged.OfType<ResourceDictionary>().Where(d => d.ContainsKey(MarkerKey)).ToList())
            merged.Remove(old);

        if (resources == null || resources.Count == 0)
            return;

        // A fresh dictionary per element: a resource dictionary can only belong to one owner.
        var dict = new ResourceDictionary { [MarkerKey] = true };
        foreach (var (key, value) in resources)
            dict[key] = value;
        merged.Add(dict);

        if (element is Border border)
        {
            border[!Border.BackgroundProperty] = new DynamicResourceExtension(RbwrOverlay.UI.Services.ThemeCardResources.CardBackgroundKey);
            border[!Border.BorderBrushProperty] = new DynamicResourceExtension("CyberBorderGlow");
        }
    }
}
