using Avalonia.Controls;
using Avalonia.Input;

namespace RbwrOverlay.UI.Views;

public partial class CrashReportWindow : Window
{
    public CrashReportWindow()
    {
        InitializeComponent();
        AddHandler(PointerPressedEvent, (s, e) =>
        {
            if (e.GetCurrentPoint(this).Properties.IsLeftButtonPressed &&
                e.Source is not TextBox && e.Source is not Button)
            {
                BeginMoveDrag(e);
            }
        });
    }
}