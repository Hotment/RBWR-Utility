using System.Linq;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Platform.Storage;
using Avalonia.VisualTree;
using RbwrOverlay.UI.Behaviors;
using RbwrOverlay.UI.ViewModels;

namespace RbwrOverlay.UI.Views;

public partial class DetailedOverlayView : UserControl
{
    private MainOverlayViewModel? _subscribedVm;

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

        if (DataContext is MainOverlayViewModel vm && !ReferenceEquals(_subscribedVm, vm))
        {
            if (_subscribedVm != null)
            {
                _subscribedVm.RequestInstallThemePicker -= OnRequestInstallThemePicker;
            }
            _subscribedVm = vm;
            _subscribedVm.RequestInstallThemePicker += OnRequestInstallThemePicker;
        }
    }

    protected override void OnDetachedFromVisualTree(VisualTreeAttachmentEventArgs e)
    {
        base.OnDetachedFromVisualTree(e);
        if (_subscribedVm != null)
        {
            _subscribedVm.RequestInstallThemePicker -= OnRequestInstallThemePicker;
            _subscribedVm = null;
        }
    }

    private async void OnRequestInstallThemePicker()
    {
        if (DataContext is not MainOverlayViewModel vm) return;
        var topLevel = TopLevel.GetTopLevel(this);
        if (topLevel?.StorageProvider == null) return;

        var files = await topLevel.StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = "Install RBWR Overlay Theme",
            AllowMultiple = false,
            FileTypeFilter = new[]
            {
                new FilePickerFileType("Theme Files (*.zip, *.axaml, theme.json)")
                {
                    Patterns = new[] { "*.zip", "*.axaml", "*.xaml", "theme.json" }
                }
            }
        });

        var file = files.FirstOrDefault();
        string? localPath = file?.TryGetLocalPath();
        if (!string.IsNullOrWhiteSpace(localPath))
        {
            vm.InstallThemeFromPath(localPath);
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