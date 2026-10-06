using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Threading;

namespace RbwrOverlay.UI.Behaviors;

public static class TextBoxBehaviors
{
    public static readonly AttachedProperty<bool> AutoEndCaretProperty =
        AvaloniaProperty.RegisterAttached<TextBox, bool>(
            "AutoEndCaret",
            typeof(TextBoxBehaviors),
            defaultValue: false);

    public static bool GetAutoEndCaret(TextBox element) => element.GetValue(AutoEndCaretProperty);
    public static void SetAutoEndCaret(TextBox element, bool value) => element.SetValue(AutoEndCaretProperty, value);

    static TextBoxBehaviors()
    {
        AutoEndCaretProperty.Changed.AddClassHandler<TextBox>((textBox, e) =>
        {
            if (e.NewValue is true)
            {
                Attach(textBox);
            }
        });
    }

    public static void Attach(TextBox textBox)
    {
        textBox.GotFocus += (s, e) => MoveCaretToEnd(textBox);
        textBox.AddHandler(InputElement.PointerReleasedEvent, (s, e) => MoveCaretToEnd(textBox), RoutingStrategies.Bubble | RoutingStrategies.Tunnel, handledEventsToo: true);
        textBox.PropertyChanged += (s, e) =>
        {
            if (e.Property == TextBox.TextProperty && textBox.IsFocused)
            {
                MoveCaretToEnd(textBox);
            }
        };
    }

    private static void MoveCaretToEnd(TextBox tb)
    {
        Dispatcher.UIThread.Post(() =>
        {
            if (tb.Text != null)
            {
                tb.CaretIndex = tb.Text.Length;
            }
        });
    }
}