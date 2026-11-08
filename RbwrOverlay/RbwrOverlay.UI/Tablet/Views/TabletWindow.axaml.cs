using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.VisualTree;
using RbwrOverlay.UI.Tablet.ViewModels;

namespace RbwrOverlay.UI.Tablet.Views;

public partial class TabletWindow : Window
{
    private const double DesignWidth = 800;
    private const double BaseWidth = 620;
    private const double BaseHeight = 350;

    public TabletWindow()
    {
        InitializeComponent();
        TabletRoot.PointerPressed += OnHeaderPressed;
        WindowRoot.SizeChanged += (_, e) => ApplyScale(e.NewSize);

        var slider = this.FindControl<Slider>("UiScaleSlider");
        if (slider != null)
        {
            var routes = RoutingStrategies.Bubble | RoutingStrategies.Tunnel;
            slider.AddHandler(PointerReleasedEvent, OnScaleSliderCommit, routes, handledEventsToo: true);
            slider.AddHandler(PointerCaptureLostEvent, OnScaleSliderCommit, routes, handledEventsToo: true);
            slider.AddHandler(KeyUpEvent, OnScaleSliderCommit, routes, handledEventsToo: true);
        }
    }

    protected override void OnDataContextChanged(EventArgs e)
    {
        base.OnDataContextChanged(e);
        if (DataContext is TabletViewModel vm)
        {
            ApplyWindowSize(vm.UiScale);
            vm.PropertyChanged += (_, args) =>
            {
                if (args.PropertyName == nameof(TabletViewModel.UiScale)) ApplyWindowSize(vm.UiScale);
            };
        }
    }

    protected override void OnClosed(EventArgs e)
    {
        base.OnClosed(e);
        (DataContext as IDisposable)?.Dispose();
    }

    private void OnScaleSliderCommit(object? sender, RoutedEventArgs e)
    {
        if (DataContext is TabletViewModel vm) vm.CommitUiScale();
    }

    private void ApplyWindowSize(double scale)
    {
        Width = BaseWidth * scale;
        Height = BaseHeight * scale;
    }

    private void ApplyScale(Size size)
    {
        if (size.Width <= 0 || size.Height <= 0) return;
        double sc = size.Width / DesignWidth;
        ScaleHost.LayoutTransform = new Avalonia.Media.ScaleTransform(sc, sc);
        TabletRoot.Width = size.Width / sc;
        TabletRoot.Height = size.Height / sc;
    }

    private void OnHeaderPressed(object? sender, PointerPressedEventArgs e)
    {
        for (var v = e.Source as Visual; v != null && v != TabletRoot; v = v.GetVisualParent())
            if (v is Button or TextBox or Slider) return;
        if (e.GetCurrentPoint(this).Properties.IsLeftButtonPressed) BeginMoveDrag(e);
    }

    private void OnMinimize(object? sender, RoutedEventArgs e) => WindowState = WindowState.Minimized;

    private void OnClose(object? sender, RoutedEventArgs e) => Close();
}
