using System.Linq;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.VisualTree;
using RbwrOverlay.UI.Behaviors;
using RbwrOverlay.UI.ViewModels;

namespace RbwrOverlay.UI.Views;

public partial class DetailedOverlayView : UserControl
{
    public DetailedOverlayView()
    {
        InitializeComponent();

        var uiScaleSlider = this.FindControl<Slider>("UiScaleSlider");
        if (uiScaleSlider != null)
        {
            uiScaleSlider.AddHandler(InputElement.PointerReleasedEvent, OnUiScaleSliderReleased, RoutingStrategies.Bubble | RoutingStrategies.Tunnel, handledEventsToo: true);
            uiScaleSlider.AddHandler(InputElement.PointerCaptureLostEvent, OnUiScaleSliderReleased, RoutingStrategies.Bubble | RoutingStrategies.Tunnel, handledEventsToo: true);
            uiScaleSlider.AddHandler(InputElement.KeyUpEvent, OnUiScaleSliderKeyUp, RoutingStrategies.Bubble | RoutingStrategies.Tunnel, handledEventsToo: true);
        }

        var compactUiScaleSlider = this.FindControl<Slider>("CompactUiScaleSlider");
        if (compactUiScaleSlider != null)
        {
            compactUiScaleSlider.AddHandler(InputElement.PointerReleasedEvent, OnCompactScaleSliderReleased, RoutingStrategies.Bubble | RoutingStrategies.Tunnel, handledEventsToo: true);
            compactUiScaleSlider.AddHandler(InputElement.PointerCaptureLostEvent, OnCompactScaleSliderReleased, RoutingStrategies.Bubble | RoutingStrategies.Tunnel, handledEventsToo: true);
            compactUiScaleSlider.AddHandler(InputElement.KeyUpEvent, OnCompactScaleSliderKeyUp, RoutingStrategies.Bubble | RoutingStrategies.Tunnel, handledEventsToo: true);
        }
    }

    protected override void OnAttachedToVisualTree(VisualTreeAttachmentEventArgs e)
    {
        base.OnAttachedToVisualTree(e);
        foreach (var tb in this.GetVisualDescendants().OfType<TextBox>())
        {
            TextBoxBehaviors.Attach(tb);
        }
        foreach (var acb in this.GetVisualDescendants().OfType<AutoCompleteBox>())
        {
            AutoCompleteBehaviors.ApplyJobIdFilter(acb);
        }
    }

    private void OnUiScaleSliderReleased(object? sender, RoutedEventArgs e)
    {
        if (DataContext is MainOverlayViewModel vm)
        {
            vm.CommitUiScale();
        }
    }

    private void OnUiScaleSliderKeyUp(object? sender, KeyEventArgs e)
    {
        if (DataContext is MainOverlayViewModel vm)
        {
            vm.CommitUiScale();
        }
    }

    private void OnCompactScaleSliderReleased(object? sender, RoutedEventArgs e)
    {
        if (DataContext is MainOverlayViewModel vm)
        {
            vm.CommitCompactUiScale();
        }
    }

    private void OnCompactScaleSliderKeyUp(object? sender, KeyEventArgs e)
    {
        if (DataContext is MainOverlayViewModel vm)
        {
            vm.CommitCompactUiScale();
        }
    }
}