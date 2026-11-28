using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Media.Imaging;
using Avalonia.Platform.Storage;
using RbwrThemeCreator.Services;
using RbwrThemeCreator.ViewModels;

namespace RbwrThemeCreator.Views;

public partial class MainWindow : IAiChatHost
{
    // =====================================================================
    // AI chat host
    // =====================================================================

    private bool IsChatOpen => NavTabs.SelectedItem == AiTab && _vm?.Ai.HasProvider == true;

    private void WireAiChat(MainViewModel vm)
    {
        vm.Ai.Host = this;
        vm.Ai.MessageAdded += () => Avalonia.Threading.Dispatcher.UIThread.Post(() => ChatScroll.ScrollToEnd(), Avalonia.Threading.DispatcherPriority.Background);
        vm.Ai.RequestOpenSettings += () =>
        {
            NavTabs.SelectedItem = SettingsTab;
            Avalonia.Threading.Dispatcher.UIThread.Post(() => AiAccountsCard.BringIntoView(), Avalonia.Threading.DispatcherPriority.Background);
        };
        ChatInput.PastingFromClipboard += OnChatPaste;
    }

    private async void OnChatPaste(object? sender, RoutedEventArgs e)
    {
        if (_vm == null || Clipboard == null) return;
        var files = await Avalonia.Input.Platform.ClipboardExtensions.TryGetFilesAsync(Clipboard);
        var paths = files?.Select(f => f.TryGetLocalPath()).Where(p => !string.IsNullOrEmpty(p)).Select(p => p!).ToList();
        if (paths is { Count: > 0 })
        {
            e.Handled = true;
            _vm.Ai.AttachFiles(paths);
            return;
        }
        using var bmp = await ClipboardImageAsync();
        if (bmp == null) return;
        e.Handled = true;
        _vm.Ai.AttachBitmap(bmp, $"pasted-{DateTime.Now:HHmmss}.jpg");
    }

    private bool TryAttachDroppedToChat(IReadOnlyList<string> paths)
    {
        if (!IsChatOpen || _vm == null) return false;
        _vm.Ai.AttachFiles(paths);
        return true;
    }

    public async Task<Bitmap?> CaptureScreenAsync()
    {
        var previous = WindowState;
        WindowState = WindowState.Minimized;
        await Task.Delay(400);
        try
        {
            return ScreenCapture.CaptureVirtualScreen();
        }
        finally
        {
            WindowState = previous == WindowState.Minimized ? WindowState.Normal : previous;
            Activate();
        }
    }

    public Bitmap? RenderPreviewBitmap() => RenderPreview(1.0);

    public async Task<IReadOnlyList<string>> PickFilesAsync()
    {
        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = "Attach files to the chat",
            AllowMultiple = true,
            FileTypeFilter =
            [
                new FilePickerFileType("Images, PDF, text and fonts") { Patterns = ["*.ttf", "*.otf", "*.ttc", "*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp", "*.gif", "*.pdf", "*.txt", "*.md", "*.json", "*.axaml", "*.xaml", "*.theme"] },
                new FilePickerFileType("All files") { Patterns = ["*"] },
            ],
        });
        return files.Select(f => f.TryGetLocalPath()).Where(p => !string.IsNullOrEmpty(p)).Select(p => p!).ToList();
    }

    public async Task<Bitmap?> ClipboardImageAsync()
    {
        if (Clipboard == null) return null;
        try { return await Avalonia.Input.Platform.ClipboardExtensions.TryGetBitmapAsync(Clipboard); }
        catch { return null; }
    }
}
