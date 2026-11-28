using RbwrThemeCreator.Models;

namespace RbwrThemeCreator.Services;

public sealed record PreviewRenderResult(byte[] PngBytes, int Width, int Height);

/// <summary>UI services the view model needs from the window (pickers, dialogs, clipboard, preview rendering).</summary>
public interface IDialogHost
{
    Task<string?> PickFolderAsync(string title);
    Task<IReadOnlyList<string>> PickFilesAsync(string title, string filterName, string[] patterns, bool allowMultiple);
    Task<string?> PickSaveFileAsync(string title, string suggestedName, string filterName, string pattern);
    Task<bool> ConfirmAsync(string title, string message, string okText = "OK");
    Task CopyTextAsync(string text);

    /// <summary>Renders the MONITOR view of the live preview as a PNG thumbnail, or null on failure.</summary>
    byte[]? RenderThumbnailPng();

    /// <summary>
    /// Renders any preview mode (0=MONITOR, 1=CONFIG, 2=COMPACT, 3=TABLET, 4=ALL) off-screen as PNG bytes
    /// with optional backdrop (-1/null=transparent, 0=dark, 1=game, 2=light, 3=checkerboard).
    /// </summary>
    PreviewRenderResult? RenderPreviewPng(ThemeState state, int mode, double scale = 1.5, int? backdrop = null);

    /// <summary>Highlights the preview elements associated with the specified token keys.</summary>
    void HighlightPreviewTokens(IReadOnlyList<string> tokenKeys);
}
