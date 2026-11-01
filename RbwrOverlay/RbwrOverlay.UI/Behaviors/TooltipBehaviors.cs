using Avalonia;
using Avalonia.Controls;

namespace RbwrOverlay.UI.Behaviors;

public static class TooltipBehaviors
{
    public static readonly AttachedProperty<string?> KeyProperty =
        AvaloniaProperty.RegisterAttached<Control, string?>(
            "Key",
            typeof(TooltipBehaviors),
            defaultValue: null);

    private static readonly List<WeakReference<Control>> TrackedControls = new();

    public static string? GetKey(Control element) => element.GetValue(KeyProperty);
    public static void SetKey(Control element, string? value) => element.SetValue(KeyProperty, value);

    static TooltipBehaviors()
    {
        KeyProperty.Changed.AddClassHandler<Control>((control, e) =>
        {
            TrackControl(control);
            ApplyTooltip(control, e.NewValue as string);
        });

        TooltipCatalog.EnabledChanged += OnEnabledChanged;
    }

    private static void TrackControl(Control control)
    {
        for (int i = TrackedControls.Count - 1; i >= 0; i--)
        {
            if (!TrackedControls[i].TryGetTarget(out var existing))
            {
                TrackedControls.RemoveAt(i);
            }
            else if (ReferenceEquals(existing, control))
            {
                return;
            }
        }

        TrackedControls.Add(new WeakReference<Control>(control));
    }

    private static void OnEnabledChanged()
    {
        for (int i = TrackedControls.Count - 1; i >= 0; i--)
        {
            if (!TrackedControls[i].TryGetTarget(out var control))
            {
                TrackedControls.RemoveAt(i);
                continue;
            }

            ApplyTooltip(control, GetKey(control));
        }
    }

    private static void ApplyTooltip(Control control, string? key)
    {
        var item = TooltipCatalog.Get(key);
        ToolTip.SetTip(control, item);
        if (item != null)
        {
            ToolTip.SetShowDelay(control, 350);
        }
    }
}