namespace RbwrThemeCreator.Services;

/// <summary>UI services the view model needs from the window (pickers, dialogs, clipboard).</summary>
public interface IDialogHost
{
    Task<string?> PickFolderAsync(string title);
    Task<IReadOnlyList<string>> PickFilesAsync(string title, string filterName, string[] patterns, bool allowMultiple);
    Task<string?> PickSaveFileAsync(string title, string suggestedName, string filterName, string pattern);
    Task<bool> ConfirmAsync(string title, string message, string okText = "OK");
    Task CopyTextAsync(string text);

    /// <summary>Renders the MONITOR view of the live preview as a PNG thumbnail, or null on failure.</summary>
    byte[]? RenderThumbnailPng();
}
