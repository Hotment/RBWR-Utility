using Avalonia.Controls;
using Avalonia.Input;

namespace RbwrOverlay.UI.Views;

public partial class FeedbackWindow : Window
{
    public FeedbackWindow()
    {
        InitializeComponent();
        AddHandler(PointerPressedEvent, (s, e) =>
        {
            if (e.GetCurrentPoint(this).Properties.IsLeftButtonPressed &&
                e.Source is not TextBox && e.Source is not Button && e.Source is not CheckBox)
            {
                BeginMoveDrag(e);
            }
        });
    }
}