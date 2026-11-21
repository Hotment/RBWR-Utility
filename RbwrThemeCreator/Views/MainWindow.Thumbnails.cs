using Avalonia;
using Avalonia.Controls;
using Avalonia.Media.Imaging;
using Avalonia.Styling;
using Avalonia.Threading;
using RbwrThemeCreator.Models;
using RbwrThemeCreator.Services;

namespace RbwrThemeCreator.Views;

/// <summary>
/// Theme thumbnails (preview.png): the overlay's Theme Manager shows them next to each theme name.
///  - Save / Export / Install write one for the edited theme.
///  - When a theme without one is opened, it is created right away.
///  - On start-up, installed overlay themes without one get one (older themes made before thumbnails).
/// Each thumbnail is rendered off screen with the theme's own styles, so the live preview never flickers.
/// A toast in the bottom-right corner says when thumbnails were created.
/// </summary>
public partial class MainWindow
{
    private const double ThumbnailScale = 1.5;
    private int _toastVersion;

    /// <summary>preview.png bytes for <paramref name="state"/> (MONITOR view, overlay window only), or null.</summary>
    private byte[]? RenderThemeThumbnail(ThemeState state)
    {
        List<Bitmap>? bitmaps = null;
        var host = new Border();
        try
        {
            string xaml = ThemeXamlGenerator.Generate(state);
            (Styles styles, bitmaps) = ThemeValidator.Load(xaml, rel => ResolveStateFile(state, rel));

            var preview = new OverlayPreview();
            preview.SetMode(OverlayPreview.ModeMonitor);
            host.Child = preview;
            // Same stack as the live preview: overlay base styles, then the theme on top.
            if (_baseStyles != null)
                host.Styles.Add(BuiltInThemes.LoadPreviewBaseStyles());
            host.Styles.Add(styles);

            ThumbRenderHost.Children.Add(host);
            UpdateLayout();

            Control target = preview.FindControl<Control>("DetailedShell") is { Bounds.Width: >= 1 } shell ? shell : host;
            var size = target.Bounds.Size;
            if (size.Width < 1 || size.Height < 1)
                return null;

            using var rtb = new RenderTargetBitmap(
                new PixelSize((int)Math.Ceiling(size.Width * ThumbnailScale), (int)Math.Ceiling(size.Height * ThumbnailScale)),
                new Vector(96 * ThumbnailScale, 96 * ThumbnailScale));
            rtb.Render(target);
            using var ms = new MemoryStream();
            rtb.Save(ms, new PngBitmapEncoderOptions());
            return ms.ToArray();
        }
        catch
        {
            return null; // e.g. a theme the creator cannot preview: it simply gets no thumbnail
        }
        finally
        {
            ThumbRenderHost.Children.Remove(host);
            host.Child = null;
            if (bitmaps != null)
            {
                foreach (var b in bitmaps)
                {
                    try { b.Dispose(); } catch { /* already drawn */ }
                }
            }
        }
    }

    /// <summary>"fonts/x.ttf#Family" / "assets/x.png" -> a preview copy of that file of the theme.</summary>
    private static string? ResolveStateFile(ThemeState state, string relative)
    {
        string rel = relative.Replace('\\', '/');
        IEnumerable<ThemeFile> files;
        string name;
        if (rel.StartsWith("fonts/", StringComparison.OrdinalIgnoreCase))
        {
            files = state.Fonts;
            name = rel[6..];
        }
        else if (rel.StartsWith("assets/", StringComparison.OrdinalIgnoreCase))
        {
            files = state.Assets;
            name = rel[7..];
        }
        else
        {
            return null;
        }
        var file = files.FirstOrDefault(f => f.FileName.Equals(name, StringComparison.OrdinalIgnoreCase));
        return file != null && File.Exists(file.SourcePath) ? FontTools.GetPreviewCopy(file.SourcePath) : null;
    }

    /// <summary>Writes preview.png into <paramref name="folder"/> when it has none. True when one was created.</summary>
    private bool CreateMissingThumbnail(string folder, Func<ThemeState> loadState)
    {
        string target = Path.Combine(folder, ThemeExporter.PreviewFileName);
        if (File.Exists(target) || !Directory.Exists(folder))
            return false;
        try
        {
            var png = RenderThemeThumbnail(loadState());
            if (png == null) return false;
            File.WriteAllBytes(target, png);
            return true;
        }
        catch
        {
            return false; // read-only folder, theme that cannot be loaded, ...
        }
    }

    /// <summary>A theme was opened from a folder: give it a thumbnail if it has none yet.</summary>
    private void OnThemeFolderOpened()
    {
        if (_vm?.CurrentFolder is not { } folder) return;
        if (File.Exists(Path.Combine(folder, ThemeExporter.PreviewFileName))) return;

        // After the preview refresh that follows loading, so the state is complete.
        Dispatcher.UIThread.Post(() =>
        {
            if (_vm == null || _vm.CurrentFolder != folder) return;
            if (CreateMissingThumbnail(folder, () => _vm.BuildState()))
            {
                string name = string.IsNullOrWhiteSpace(_vm.ThemeName) ? Path.GetFileName(folder) : _vm.ThemeName;
                ShowToast("THUMBNAIL CREATED", $"{name}: preview.png saved in the theme folder.");
            }
        }, DispatcherPriority.Background);
    }

    /// <summary>
    /// Start-up pass over the overlay's installed themes: every theme without preview.png gets one.
    /// One theme per dispatcher turn at background priority, so the window stays responsive.
    /// </summary>
    private async Task CreateMissingInstalledThumbnailsAsync()
    {
        if (_vm == null) return;
        var themes = _vm.InstalledThemes.ToList();
        var created = new List<string>();

        foreach (var theme in themes)
        {
            await Dispatcher.UIThread.InvokeAsync(() => { }, DispatcherPriority.Background);
            if (CreateMissingThumbnail(theme.Directory, () => ThemeImporter.Load(theme.Directory, BuiltInThemes.Cyberpunk)))
                created.Add(theme.Name);
        }

        if (created.Count == 1)
            ShowToast("THUMBNAIL CREATED", $"{created[0]}: preview.png added for the overlay's Theme Manager.");
        else if (created.Count > 1)
            ShowToast("THUMBNAILS CREATED", $"{created.Count} installed themes got a preview.png for the overlay's Theme Manager.");
    }

    /// <summary>Shows the bottom-right toast for a few seconds.</summary>
    public void ShowToast(string title, string message)
    {
        int version = ++_toastVersion;
        ToastTitle.Text = title;
        ToastText.Text = message;
        Toast.IsVisible = true;
        Dispatcher.UIThread.Post(() => Toast.Opacity = 1, DispatcherPriority.Background);

        DispatcherTimer.RunOnce(() =>
        {
            if (version != _toastVersion) return;
            Toast.Opacity = 0;
            DispatcherTimer.RunOnce(() =>
            {
                if (version == _toastVersion) Toast.IsVisible = false;
            }, TimeSpan.FromMilliseconds(300));
        }, TimeSpan.FromSeconds(4.5));
    }
}
