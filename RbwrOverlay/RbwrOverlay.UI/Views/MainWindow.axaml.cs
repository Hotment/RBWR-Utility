using System.ComponentModel;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Threading;
using Avalonia.VisualTree;
using RbwrOverlay.Core.Models;
using RbwrOverlay.UI.Behaviors;
using RbwrOverlay.UI.ViewModels;

namespace RbwrOverlay.UI.Views;

public partial class MainWindow : Window
{
    private CustomMessageWindow? _messageWindow;
    private UpdateWindow? _updateWindow;
    private Tablet.Views.TabletWindow? _tabletWindow;

    public MainWindow()
    {
        InitializeComponent();
        TooltipBehaviors.AttachWindow(this, RootHostPanel);
        AddHandler(PointerPressedEvent, OnPointerPressed, handledEventsToo: false);
    }

    protected override void OnDataContextChanged(EventArgs e)
    {
        base.OnDataContextChanged(e);
        if (DataContext is MainOverlayViewModel vm)
        {
            vm.PropertyChanged += OnViewModelPropertyChanged;
            vm.RequestShowMessage += OnShowMessage;
            vm.RequestShowUpdate += OnShowUpdate;
            vm.RequestQuit += OnQuit;
            vm.RequestOpenTablet += OnOpenTablet;

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
            e.PropertyName == nameof(MainOverlayViewModel.SelectedUnit) ||
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

    private void OnShowUpdate(UpdateInfo info)
    {
        Dispatcher.UIThread.Post(() =>
        {
            if (_updateWindow != null)
            {
                _updateWindow.Activate();
                return;
            }

            if (DataContext is not MainOverlayViewModel vm) return;

            var updateVm = new UpdateViewModel(
                vm.ApiClient,
                info,
                MainOverlayViewModel.AppVersion,
                skippedVersion => vm.SkipVersion(skippedVersion));

            _updateWindow = new UpdateWindow
            {
                DataContext = updateVm
            };

            _updateWindow.Closed += (s, ev) => _updateWindow = null;

            if (IsVisible)
            {
                _updateWindow.Show(this);
            }
            else
            {
                _updateWindow.Show();
            }
        });
    }

    private void OnOpenTablet()
    {
        Dispatcher.UIThread.Post(() =>
        {
            if (_tabletWindow != null)
            {
                if (_tabletWindow.WindowState == WindowState.Minimized)
                    _tabletWindow.WindowState = WindowState.Normal;
                _tabletWindow.Activate();
                return;
            }

            if (DataContext is not MainOverlayViewModel vm) return;

            _tabletWindow = new Tablet.Views.TabletWindow { DataContext = vm.CreateTabletViewModel() };
            _tabletWindow.Closed += (s, ev) =>
            {
                _tabletWindow = null;
                if (DataContext is MainOverlayViewModel closedVm) closedVm.IsTabletOpen = false;
            };
            vm.IsTabletOpen = true;
            _tabletWindow.Show();
        });
    }

    private void OnQuit()
    {
        _tabletWindow?.Close();
        Close();
        Environment.Exit(0);
    }
}