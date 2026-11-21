using Avalonia;
using Avalonia.Controls;
using Avalonia.Markup.Xaml.MarkupExtensions;

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

    private static readonly ResourceDictionary MarkerKey = new();

    static ThemeCardBehaviors()
    {
        ResourcesProperty.Changed.AddClassHandler<StyledElement>((element, e) => Apply(element, e.NewValue as IReadOnlyDictionary<object, object?>));
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
