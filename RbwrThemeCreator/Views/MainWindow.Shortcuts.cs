using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Threading;
using RbwrThemeCreator.Services;

namespace RbwrThemeCreator.Views;

/// <summary>
/// Keyboard shortcuts. Every action is looked up in the user's shortcut map (SETTINGS → Keyboard
/// shortcuts), so changed shortcuts work everywhere and the menus and tooltips show the current ones.
/// Esc (clear search / stop FIND COLOUR) and Ctrl+click in the preview are fixed.
/// </summary>
public partial class MainWindow
{
    private void OnShortcutKeyDown(object? sender, KeyEventArgs e)
    {
        if (_vm == null || e.Handled) return;

        if (e.Key == Key.Escape)
        {
            if (InspectToggle.IsChecked == true)
                InspectToggle.IsChecked = false;
            else if (!string.IsNullOrEmpty(_vm.TokenSearch))
                _vm.TokenSearch = string.Empty;
            else
                return;
            e.Handled = true;
            return;
        }

        var gesture = ShortcutGesture.FromKeyPress(e.Key, e.KeyModifiers);
        if (_vm.Shortcuts.FindAction(gesture) is { } action && RunShortcut(action))
            e.Handled = true;
    }

    /// <summary>While a shortcut row waits for keys, the key press is captured here (before anything else).</summary>
    private void OnShortcutRecordingKeyDown(object? sender, KeyEventArgs e)
    {
        if (_vm?.RecordingShortcut == null) return;
        e.Handled = true;

        if (ShortcutGesture.IsModifierKey(e.Key))
            return; // wait for the real key

        switch (e.Key)
        {
            case Key.Escape when e.KeyModifiers == KeyModifiers.None:
                _vm.CancelShortcutRecording();
                _vm.SetStatus("Shortcut not changed.");
                return;
            case Key.Back or Key.Delete when e.KeyModifiers == KeyModifiers.None:
                _vm.FinishShortcutRecording(null);
                return;
        }

        var gesture = ShortcutGesture.FromKeyPress(e.Key, e.KeyModifiers);
        if (!gesture.IsAllowed)
        {
            _vm.SetStatus($"{gesture} can't be a shortcut: hold Ctrl, Alt or Win, or use an F-key. Esc cancels.", isError: true);
            return;
        }
        _vm.FinishShortcutRecording(gesture);
    }

    /// <summary>Runs a shortcut action. Returns false when it did nothing (e.g. nothing to undo).</summary>
    private bool RunShortcut(string id)
    {
        if (_vm == null) return false;
        var vm = _vm;

        static bool Run(System.Windows.Input.ICommand command)
        {
            if (!command.CanExecute(null)) return false;
            command.Execute(null);
            return true;
        }

        switch (id)
        {
            case "save": return Run(vm.SaveCommand);
            case "save-as": return Run(vm.SaveAsCommand);
            case "open-file": return Run(vm.OpenFileCommand);
            case "open-folder": return Run(vm.OpenFolderCommand);
            case "export-zip": return Run(vm.ExportZipCommand);
            case "install": return Run(vm.InstallToOverlayCommand);
            case "undo": return Run(vm.UndoCommand);
            case "redo" or "redo-alt": return Run(vm.RedoCommand);
            case "new":
                NewButton.Flyout?.ShowAt(NewButton);
                return true;
            case "search":
                NavTabs.SelectedItem = ColoursTab;
                Dispatcher.UIThread.Post(() =>
                {
                    TokenSearchBox.Focus();
                    TokenSearchBox.SelectAll();
                }, DispatcherPriority.Loaded);
                return true;
            case "find-colour":
                InspectToggle.IsChecked = InspectToggle.IsChecked != true;
                return true;
            case "view-monitor": vm.PreviewMode = OverlayPreview.ModeMonitor; return true;
            case "view-config": vm.PreviewMode = OverlayPreview.ModeConfig; return true;
            case "view-compact": vm.PreviewMode = OverlayPreview.ModeCompact; return true;
            case "view-tablet": vm.PreviewMode = OverlayPreview.ModeTablet; return true;
            case "view-all": vm.PreviewMode = OverlayPreview.ModeAll; return true;
            case "fit":
                _pan = default;
                vm.PreviewFit = true;
                UpdateZoom();
                return true;
            case "save-preview":
                OnExportPreviewPngClick(this, new RoutedEventArgs());
                return true;
            case "copy-preview":
                _ = CopyPreviewImageAsync();
                return true;
            case "guide":
                NavTabs.SelectedItem = GuideTab;
                Dispatcher.UIThread.Post(() => GuidePage.ShowSection("14-keyboard-shortcuts"), DispatcherPriority.Loaded);
                return true;
            default:
                return false;
        }
    }

    /// <summary>Menus, tooltips and the search box show the shortcuts that are set now.</summary>
    private void UpdateShortcutHints()
    {
        if (_vm == null) return;
        var map = _vm.Shortcuts;
        string Hint(string id) => map.Get(id)?.ToString() ?? string.Empty;
        string WithHint(string text, string id) => Hint(id) is { Length: > 0 } h ? $"{text} ({h})" : text;
        Avalonia.Input.KeyGesture? Gesture(string id) => map.Get(id)?.ToKeyGesture();

        MenuOpenFile.InputGesture = Gesture("open-file");
        MenuOpenFolder.InputGesture = Gesture("open-folder");
        MenuSaveAs.InputGesture = Gesture("save-as");
        MenuExportZip.InputGesture = Gesture("export-zip");
        MenuSavePreview.InputGesture = Gesture("save-preview");
        MenuCopyPreview.InputGesture = Gesture("copy-preview");

        ToolTip.SetTip(UndoButton, WithHint("Undo last change", "undo"));
        string redo = string.Join(" or ", new[] { Hint("redo"), Hint("redo-alt") }.Where(h => h.Length > 0));
        ToolTip.SetTip(RedoButton, redo.Length > 0 ? $"Redo change ({redo})" : "Redo change");
        ToolTip.SetTip(NewButton, WithHint("Start a new theme from a preset", "new"));
        ToolTip.SetTip(SaveButton, WithHint("Save to the current theme folder", "save"));
        ToolTip.SetTip(InstallButton, WithHint("Copy the theme into the overlay's themes folder", "install")
                                      + ". Then click Reload in the overlay's CONFIG tab.");
        ToolTip.SetTip(PngButton, WithHint("Save a high-DPI PNG screenshot of the current preview", "save-preview"));
        ToolTip.SetTip(CopyButton, WithHint("Copy the preview as an image, then paste with Ctrl+V", "copy-preview"));
        ToolTip.SetTip(InspectToggle, WithHint("Click an element in the preview to jump to the colours that paint it (or Ctrl+click any time). Esc to stop", "find-colour"));
        TokenSearchBox.PlaceholderText = WithHint("Search colours…", "search") + "  e.g. slider, tooltip, border, #00f0ff";
    }
}
