using System;
using Avalonia.Controls;
using Avalonia.Input;
using RbwrOverlay.UI.ViewModels;

namespace RbwrOverlay.UI.Views;

public partial class UpdateWindow : Window
{
    public UpdateWindow()
    {
        InitializeComponent();
        SetupDrag();
        KeyDown += OnWindowKeyDown;
    }

    protected override void OnDataContextChanged(EventArgs e)
    {
        base.OnDataContextChanged(e);
        if (DataContext is UpdateViewModel vm)
        {
            vm.RequestClose += (s, ev) => Close();
        }
    }

    private void SetupDrag()
    {
        HeaderBorder.PointerPressed += (s, e) =>
        {
            if (e.GetCurrentPoint(this).Properties.IsLeftButtonPressed)
            {
                BeginMoveDrag(e);
            }
        };

        RootBorder.PointerPressed += (s, e) =>
        {
            if (e.GetCurrentPoint(this).Properties.IsLeftButtonPressed && e.Source is not Button)
            {
                BeginMoveDrag(e);
            }
        };
    }

    private void OnWindowKeyDown(object? sender, KeyEventArgs e)
    {
        if (e.Key is Key.Escape)
        {
            Close();
            e.Handled = true;
        }
    }
}