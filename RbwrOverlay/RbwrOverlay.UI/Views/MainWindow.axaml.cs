using System.ComponentModel;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.VisualTree;
using RbwrOverlay.UI.ViewModels;

namespace RbwrOverlay.UI.Views;

public partial class MainWindow : Window
{
    private CustomMessageWindow? _messageWindow;

    public MainWindow()
    {
        InitializeComponent();
        AddHandler(PointerPressedEvent, OnPointerPressed, handledEventsToo: false);
    }

    protected override void OnDataContextChanged(EventArgs e)
    {
        base.OnDataContextChanged(e);
        if (DataContext is MainOverlayViewModel vm)
        {
            vm.PropertyChanged += OnViewModelPropertyChanged;
            vm.RequestShowMessage += OnShowMessage;
            vm.RequestQuit += OnQuit;

            UpdateWindowSize(vm.IsCompact);
        }
    }

    private void OnPointerPressed(object? sender, PointerPressedEventArgs e)
    {
        if (e.GetCurrentPoint(this).Properties.IsLeftButtonPressed)
        {
            if (e.Source is Visual visual && IsInteractiveControl(visual))
            {
                return;
            }

            if (e.ClickCount == 2)
            {
                if (DataContext is MainOverlayViewModel vm)
                {
                    vm.ToggleCompact();
                }
                return;
            }

            BeginMoveDrag(e);
        }
    }

    private static bool IsInteractiveControl(Visual? visual)
    {
        for (var current = visual; current != null && current is not Window; current = current.GetVisualParent())
        {
            if (current is Button or TextBox or Slider or AutoCompleteBox or CheckBox or MenuItem)
            {
                return true;
            }
        }
        return false;
    }

    private void OnViewModelPropertyChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(MainOverlayViewModel.IsCompact) ||
            e.PropertyName == nameof(MainOverlayViewModel.UiScale) ||
            e.PropertyName == nameof(MainOverlayViewModel.CompactUiScale) ||
            e.PropertyName == nameof(MainOverlayViewModel.ActiveUiScale) ||
            e.PropertyName == nameof(MainOverlayViewModel.CompactDisplayCounterText) ||
            e.PropertyName == nameof(MainOverlayViewModel.IsRecircOverrideActive))
        {
            if (DataContext is MainOverlayViewModel vm)
            {
                UpdateWindowSize(vm.IsCompact);
            }
        }
    }

    private void UpdateWindowSize(bool isCompact)
    {
        SizeToContent = SizeToContent.WidthAndHeight;
        Width = double.NaN;
        Height = double.NaN;
        InvalidateMeasure();
    }

    private void OnShowMessage(string title, string message, bool isError)
    {
        _messageWindow?.Close();
        _messageWindow = new CustomMessageWindow(title, message, isError);
        _messageWindow.Closed += (s, ev) => _messageWindow = null;
        _messageWindow.Show(this);
    }

    private void OnQuit()
    {
        Close();
        Environment.Exit(0);
    }
}