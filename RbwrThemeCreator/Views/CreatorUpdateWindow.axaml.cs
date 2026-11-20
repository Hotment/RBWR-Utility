using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.VisualTree;
using RbwrThemeCreator.ViewModels;

namespace RbwrThemeCreator.Views;

public partial class CreatorUpdateWindow : Window
{
    public CreatorUpdateWindow()
    {
        InitializeComponent();

        DataContextChanged += (_, _) =>
        {
            if (DataContext is CreatorUpdateViewModel vm)
            {
                vm.RequestClose -= OnRequestClose;
                vm.RequestClose += OnRequestClose;
            }
        };

        KeyDown += (_, e) =>
        {
            if (e.Key == Key.Escape && DataContext is CreatorUpdateViewModel vm && !vm.IsDownloading)
                Close();
        };
    }

    private void OnRequestClose(object? sender, EventArgs e) => Close();

    private void OnHeaderPointerPressed(object? sender, PointerPressedEventArgs e)
    {
        if ((e.Source as Avalonia.Visual)?.FindAncestorOfType<Button>(includeSelf: true) != null)
            return;

        if (e.GetCurrentPoint(this).Properties.IsLeftButtonPressed)
            BeginMoveDrag(e);
    }
}