using Avalonia.Controls;
using Avalonia.Interactivity;

namespace RbwrOverlay.UI.Tablet.Views;

public partial class TabletHudView : UserControl
{
    public TabletHudView()
    {
        InitializeComponent();
    }

    private void OnMinimize(object? sender, RoutedEventArgs e)
    {
        if (TopLevel.GetTopLevel(this) is Window w) w.WindowState = WindowState.Minimized;
    }

    private void OnClose(object? sender, RoutedEventArgs e)
    {
        if (TopLevel.GetTopLevel(this) is Window w) w.Close();
    }
}
