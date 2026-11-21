using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.VisualTree;

namespace RbwrThemeCreator.Views;

public partial class CreatorCrashReportWindow : Window
{
    public CreatorCrashReportWindow()
    {
        InitializeComponent();
    }

    private void OnHeaderPointerPressed(object? sender, PointerPressedEventArgs e)
    {
        if ((e.Source as Avalonia.Visual)?.FindAncestorOfType<Button>(includeSelf: true) != null)
            return;

        if (e.GetCurrentPoint(this).Properties.IsLeftButtonPressed)
            BeginMoveDrag(e);
    }
}
