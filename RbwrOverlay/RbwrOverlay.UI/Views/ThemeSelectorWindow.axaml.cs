using System.Linq;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Input;
using Avalonia.Platform.Storage;
using Avalonia.VisualTree;
using RbwrOverlay.UI.Behaviors;
using RbwrOverlay.UI.ViewModels;

namespace RbwrOverlay.UI.Views;

public partial class ThemeSelectorWindow : Window
{
    private ThemeSelectorViewModel? _subscribedVm;

    public ThemeSelectorWindow()
    {
        InitializeComponent();
        TooltipBehaviors.AttachWindow(this, RootHostPanel);
        SetupDrag();
        KeyDown += OnWindowKeyDown;
        Closed += OnWindowClosed;
    }

    protected override void OnDataContextChanged(EventArgs e)
    {
        base.OnDataContextChanged(e);
        if (_subscribedVm != null)
        {
            _subscribedVm.RequestClose -= OnRequestClose;
            _subscribedVm.RequestInstallPicker -= OnRequestInstallPicker;
            _subscribedVm = null;
        }

        if (DataContext is ThemeSelectorViewModel vm)
        {
            _subscribedVm = vm;
            _subscribedVm.RequestClose += OnRequestClose;
            _subscribedVm.RequestInstallPicker += OnRequestInstallPicker;
        }
    }

    private void OnRequestClose(object? sender, EventArgs e) => Close();

    private void OnWindowClosed(object? sender, EventArgs e)
    {
        if (_subscribedVm != null)
        {
            _subscribedVm.RequestClose -= OnRequestClose;
            _subscribedVm.RequestInstallPicker -= OnRequestInstallPicker;
            _subscribedVm.Dispose();
            _subscribedVm = null;
        }
    }

    private async void OnRequestInstallPicker()
    {
        if (DataContext is not ThemeSelectorViewModel vm) return;

        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
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

    private void OnThemeCardPointerPressed(object? sender, PointerPressedEventArgs e)
    {
        if (!e.GetCurrentPoint(this).Properties.IsLeftButtonPressed)
            return;

        for (var current = e.Source as Visual; current != null && !ReferenceEquals(current, sender); current = current.GetVisualParent())
        {
            if (current is Button)
                return;
        }

        if (sender is Control { DataContext: ThemeEntryViewModel entry })
        {
            entry.ToggleExpand();
            e.Handled = true;
        }
    }

    private static bool IsInsideInteractiveControl(Visual? visual)
    {
        for (var current = visual; current != null && current is not Window; current = current.GetVisualParent())
        {
            if (current is Button or TextBox or ScrollBar or Thumb or ComboBox or Slider or CheckBox or MenuItem)
            {
                return true;
            }
        }
        return false;
    }

    private void SetupDrag()
    {
        HeaderBorder.PointerPressed += (_, e) =>
        {
            if (e.GetCurrentPoint(this).Properties.IsLeftButtonPressed
                && !IsInsideInteractiveControl(e.Source as Visual))
            {
                BeginMoveDrag(e);
            }
        };

        RootBorder.PointerPressed += (_, e) =>
        {
            if (e.GetCurrentPoint(this).Properties.IsLeftButtonPressed
                && !IsInsideInteractiveControl(e.Source as Visual))
            {
                BeginMoveDrag(e);
            }
        };
    }

    private void OnWindowKeyDown(object? sender, KeyEventArgs e)
    {
        if (e.Key == Key.Escape)
        {
            Close();
            e.Handled = true;
        }
    }
}