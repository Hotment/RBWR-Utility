using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Diagnostics;
using Avalonia.Media;
using Avalonia.Media.Imaging;
using Avalonia.Styling;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using RbwrOverlay.Core.Models;
using RbwrThemeCreator.Models;
using RbwrThemeCreator.Services;

namespace RbwrThemeCreator.ViewModels;

public sealed class PreviewReadyEventArgs(Styles? styles, List<Bitmap> bitmaps) : EventArgs
{
    public Styles? Styles { get; } = styles;
    public List<Bitmap> Bitmaps { get; } = bitmaps;
}

public partial class MainViewModel : ObservableObject
{
    public const string AppVersion = "1.0.0";

    private static readonly string[] FontPatterns = ["*.ttf", "*.otf", "*.ttc"];
    private static readonly string[] ImagePatterns = ["*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp", "*.gif"];

    private readonly DispatcherTimer _refreshTimer;
    private readonly Dictionary<string, TokenViewModel> _tokens = new(StringComparer.Ordinal);
    private bool _suppressChanges;
    private string _lastSavedXaml = string.Empty;
    private ThemeManifest _savedManifestSnapshot = new();

    public IDialogHost? Dialogs { get; set; }

    /// <summary>Raised on the UI thread with freshly parsed preview styles (or null on error).</summary>
    public event EventHandler<PreviewReadyEventArgs>? PreviewReady;

    public IReadOnlyList<TokenGroupViewModel> Groups { get; }
    public IReadOnlyList<ThemePreset> Presets => BuiltInThemes.Presets;
    public ObservableCollection<FontEntry> Fonts { get; } = new();
    public ObservableCollection<ThemeFile> Assets { get; } = new();
    public ObservableCollection<string> AssetNames { get; } = new();
    public ObservableCollection<InstalledThemeEntry> InstalledThemes { get; } = new();

    public IReadOnlyList<string> StretchModes { get; } = ["UniformToFill", "Uniform", "Fill", "None"];
    public IReadOnlyList<string> MoodNames { get; } = ["Dark (tinted black)", "Tinted (more colour)", "Neutral (grey)"];
    public IReadOnlyList<string> BackdropNames { get; } = ["Dark desktop", "Game scene", "Light desktop", "Checkerboard"];

    // ---------- Manifest ----------
    [ObservableProperty] private string _themeId = string.Empty;
    [ObservableProperty] private string _themeName = string.Empty;
    [ObservableProperty] private string _author = string.Empty;
    [ObservableProperty] private string _version = "1.0.0";
    [ObservableProperty] private string _description = string.Empty;
    [ObservableProperty] private string _minAppVersion = "2.3.0";

    // ---------- Fonts ----------
    [ObservableProperty] private string _fontFamily = string.Empty;
    [ObservableProperty] private string _monoFontFamily = string.Empty;

    // ---------- Shape ----------
    [ObservableProperty] private bool _shapeEnabled;
    [ObservableProperty] private double _shellCornerRadius = 8;
    [ObservableProperty] private double _shellBorderThickness = 1;
    [ObservableProperty] private double _cardCornerRadius = 4;
    [ObservableProperty] private double _buttonCornerRadius = 4;
    [ObservableProperty] private double _compactCornerRadius = 18;
    [ObservableProperty] private bool _shellGlow;
    [ObservableProperty] private double _shellGlowBlur = 14;

    // ---------- Background image ----------
    [ObservableProperty] private string? _backgroundImageFile;
    [ObservableProperty] private double _backgroundImageOpacity = 0.35;
    [ObservableProperty] private string _backgroundStretch = "UniformToFill";

    // ---------- Advanced ----------
    [ObservableProperty] private string _customResources = string.Empty;
    [ObservableProperty] private string _customStyles = string.Empty;

    // ---------- Palette generator ----------
    [ObservableProperty] private Color _generatorAccent = Color.Parse("#00f0ff");
    [ObservableProperty] private int _generatorMood;
    [ObservableProperty] private bool _generatorStatusColours;

    // ---------- Output / status ----------
    [ObservableProperty] private string _generatedXaml = string.Empty;
    [ObservableProperty] private string _statusMessage = "Ready.";
    [ObservableProperty] private bool _statusIsError;
    [ObservableProperty] private string? _previewError;
    [ObservableProperty] private string _manifestProblems = string.Empty;
    [ObservableProperty] private string _contrastSummary = string.Empty;
    [ObservableProperty] private bool _contrastWarning;
    [ObservableProperty] private string? _currentFolder;
    [ObservableProperty] private bool _isDirty;

    // ---------- Overlay integration ----------
    [ObservableProperty] private string _overlayThemesDirectory = string.Empty;
    [ObservableProperty] private InstalledThemeEntry? _selectedInstalledTheme;

    // ---------- Preview ----------
    [ObservableProperty] private int _previewBackdrop;
    [ObservableProperty] private double _previewZoom = 1.0;
    [ObservableProperty] private bool _previewFit = true;
    [ObservableProperty] private int _previewMode;

    public bool HasPreviewError => !string.IsNullOrEmpty(PreviewError);
    public bool HasManifestProblems => !string.IsNullOrEmpty(ManifestProblems);
    public bool HasBackgroundImage => !string.IsNullOrEmpty(BackgroundImageFile);
    public string WindowTitle => $"RBWR Theme Creator — {(string.IsNullOrWhiteSpace(ThemeName) ? "Untitled" : ThemeName)}{(IsDirty ? " •" : string.Empty)}";
    public string CurrentFolderDisplay => CurrentFolder ?? "Not saved yet";
    public string PreviewZoomText => $"{Math.Round(PreviewZoom * 100)}%";
    public string ThemeSubtitle => $"{(string.IsNullOrWhiteSpace(ThemeId) ? "no-id" : ThemeId)}  ·  v{Version}{(string.IsNullOrWhiteSpace(Author) ? "" : "  ·  " + Author)}";

    public MainViewModel()
    {
        foreach (var def in TokenCatalog.Tokens)
        {
            var vm = new TokenViewModel(def, BuiltInThemes.Cyberpunk.Tokens.GetValueOrDefault(def.Key) ?? new TokenValue(Colors.Gray));
            vm.ValueChanged += (_, _) => OnEdited();
            _tokens[def.Key] = vm;
        }

        Groups = TokenCatalog.Groups
            .Select(g => new TokenGroupViewModel(g, TokenCatalog.GroupDescriptions[g],
                TokenCatalog.Tokens.Where(t => t.Group == g).Select(t => _tokens[t.Key]).ToList()))
            .ToList();

        _refreshTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(220) };
        _refreshTimer.Tick += (_, _) =>
        {
            _refreshTimer.Stop();
            Refresh();
        };

        var settings = CreatorSettings.Current;
        _previewBackdrop = Math.Clamp(settings.PreviewBackdrop, 0, BackdropNames.Count - 1);
        _previewZoom = settings.PreviewZoom is >= 0.25 and <= 4 ? settings.PreviewZoom : 1.0;
        _previewFit = settings.PreviewFit;
        _previewMode = Math.Clamp(settings.PreviewMode, 0, 3);

        OverlayThemesDirectory = OverlayLocator.Detect() ?? string.Empty;
        LoadState(BuiltInThemes.Presets[0].Create(), folder: null);
        SetStatus("New theme from the Cyberpunk preset. Edit colours on the left — the preview updates live.");
    }

    // =====================================================================
    // State <-> view model
    // =====================================================================

    public ThemeState BuildState()
    {
        var state = new ThemeState
        {
            Manifest = new ThemeManifest
            {
                Id = ThemeId.Trim(),
                Name = ThemeName.Trim(),
                Author = Author.Trim(),
                Version = string.IsNullOrWhiteSpace(Version) ? "1.0.0" : Version.Trim(),
                Description = Description.Trim(),
                Entry = "theme.axaml",
                MinAppVersion = MinAppVersion.Trim(),
            },
            FontFamily = string.IsNullOrWhiteSpace(FontFamily) ? BuiltInThemes.Cyberpunk.FontFamily : FontFamily.Trim(),
            MonoFontFamily = string.IsNullOrWhiteSpace(MonoFontFamily) ? BuiltInThemes.Cyberpunk.MonoFontFamily : MonoFontFamily.Trim(),
            Shape = new ShapeSettings
            {
                Enabled = ShapeEnabled,
                ShellCornerRadius = ShellCornerRadius,
                ShellBorderThickness = ShellBorderThickness,
                CardCornerRadius = CardCornerRadius,
                ButtonCornerRadius = ButtonCornerRadius,
                CompactCornerRadius = CompactCornerRadius,
                ShellGlow = ShellGlow,
                ShellGlowBlur = ShellGlowBlur,
            },
            BackgroundImage = HasBackgroundImage
                ? new BackgroundImageSettings { FileName = BackgroundImageFile!, Opacity = BackgroundImageOpacity, Stretch = BackgroundStretch }
                : null,
            Fonts = Fonts.Select(f => new ThemeFile(f.FileName, f.SourcePath)).ToList(),
            Assets = Assets.ToList(),
            CustomResources = CustomResources ?? string.Empty,
            CustomStyles = CustomStyles ?? string.Empty,
        };
        foreach (var (key, vm) in _tokens)
            state.Tokens[key] = vm.ToValue();
        return state;
    }

    private void LoadState(ThemeState state, string? folder)
    {
        _suppressChanges = true;
        try
        {
            var m = state.Manifest;
            ThemeName = m.Name;
            ThemeId = string.IsNullOrWhiteSpace(m.Id) ? ThemeValidator.SanitizeId(m.Name) : m.Id;
            Author = m.Author;
            Version = string.IsNullOrWhiteSpace(m.Version) ? "1.0.0" : m.Version;
            Description = m.Description;
            MinAppVersion = m.MinAppVersion;

            FontFamily = state.FontFamily;
            MonoFontFamily = state.MonoFontFamily;

            foreach (var (key, vm) in _tokens)
            {
                if (state.Tokens.TryGetValue(key, out var v))
                    vm.SetValue(v);
            }

            var s = state.Shape;
            ShapeEnabled = s.Enabled;
            ShellCornerRadius = s.ShellCornerRadius;
            ShellBorderThickness = s.ShellBorderThickness;
            CardCornerRadius = s.CardCornerRadius;
            ButtonCornerRadius = s.ButtonCornerRadius;
            CompactCornerRadius = s.CompactCornerRadius;
            ShellGlow = s.ShellGlow;
            ShellGlowBlur = s.ShellGlowBlur;

            Fonts.Clear();
            foreach (var f in state.Fonts)
                Fonts.Add(new FontEntry(f.FileName, f.SourcePath, FontTools.ReadFamilyName(f.SourcePath)));

            Assets.Clear();
            AssetNames.Clear();
            foreach (var a in state.Assets)
            {
                Assets.Add(a);
                AssetNames.Add(a.FileName);
            }

            BackgroundImageFile = state.BackgroundImage?.FileName;
            BackgroundImageOpacity = state.BackgroundImage?.Opacity ?? 0.35;
            BackgroundStretch = state.BackgroundImage?.Stretch ?? "UniformToFill";

            CustomResources = state.CustomResources;
            CustomStyles = state.CustomStyles;

            GeneratorAccent = _tokens["NeonCyan"].Color;
            CurrentFolder = folder;
        }
        finally
        {
            _suppressChanges = false;
        }

        Refresh();
        _lastSavedXaml = folder != null ? GeneratedXaml : string.Empty;
        IsDirty = folder == null;
        if (state.ImportWarnings.Count > 0)
            SetStatus(string.Join(" ", state.ImportWarnings), isError: true);
    }

    // =====================================================================
    // Change tracking + live preview
    // =====================================================================

    protected override void OnPropertyChanged(PropertyChangedEventArgs e)
    {
        base.OnPropertyChanged(e);
        switch (e.PropertyName)
        {
            case nameof(ThemeName):
            case nameof(IsDirty):
                OnPropertyChanged(nameof(WindowTitle));
                break;
            case nameof(ThemeId):
            case nameof(Version):
            case nameof(Author):
                OnPropertyChanged(nameof(ThemeSubtitle));
                break;
            case nameof(CurrentFolder):
                OnPropertyChanged(nameof(CurrentFolderDisplay));
                break;
            case nameof(PreviewError):
                OnPropertyChanged(nameof(HasPreviewError));
                break;
            case nameof(ManifestProblems):
                OnPropertyChanged(nameof(HasManifestProblems));
                break;
            case nameof(BackgroundImageFile):
                OnPropertyChanged(nameof(HasBackgroundImage));
                break;
            case nameof(PreviewZoom):
                OnPropertyChanged(nameof(PreviewZoomText));
                CreatorSettings.Current.PreviewZoom = PreviewZoom;
                CreatorSettings.Current.Save();
                break;
            case nameof(PreviewFit):
                CreatorSettings.Current.PreviewFit = PreviewFit;
                CreatorSettings.Current.Save();
                break;
            case nameof(PreviewMode):
                CreatorSettings.Current.PreviewMode = PreviewMode;
                CreatorSettings.Current.Save();
                break;
            case nameof(PreviewBackdrop):
                CreatorSettings.Current.PreviewBackdrop = PreviewBackdrop;
                CreatorSettings.Current.Save();
                break;
            case nameof(OverlayThemesDirectory):
                RefreshInstalledThemes();
                break;
        }

        if (e.PropertyName is nameof(ThemeId) or nameof(ThemeName) or nameof(Author) or nameof(Version) or nameof(Description)
            or nameof(MinAppVersion) or nameof(FontFamily) or nameof(MonoFontFamily) or nameof(ShapeEnabled)
            or nameof(ShellCornerRadius) or nameof(ShellBorderThickness) or nameof(CardCornerRadius) or nameof(ButtonCornerRadius)
            or nameof(CompactCornerRadius) or nameof(ShellGlow) or nameof(ShellGlowBlur) or nameof(BackgroundImageFile)
            or nameof(BackgroundImageOpacity) or nameof(BackgroundStretch) or nameof(CustomResources) or nameof(CustomStyles))
        {
            OnEdited();
        }
    }

    partial void OnThemeNameChanged(string? oldValue, string newValue)
    {
        if (_suppressChanges) return;
        // Keep the ID following the name until the user edits the ID by hand.
        if (string.IsNullOrWhiteSpace(ThemeId) || ThemeId == ThemeValidator.SanitizeId(oldValue))
            ThemeId = ThemeValidator.SanitizeId(newValue);
    }

    private void OnEdited()
    {
        if (_suppressChanges) return;
        _refreshTimer.Stop();
        _refreshTimer.Start();
    }

    /// <summary>Regenerates XAML, validates it and rebuilds the preview.</summary>
    public void Refresh()
    {
        var state = BuildState();
        string xaml = ThemeXamlGenerator.Generate(state);
        GeneratedXaml = xaml;
        IsDirty = !string.Equals(xaml, _lastSavedXaml, StringComparison.Ordinal);

        ManifestProblems = string.Join(Environment.NewLine, ThemeValidator.ValidateManifest(state));
        UpdateContrast();

        try
        {
            var (styles, bitmaps) = ThemeValidator.Load(xaml, rel => ResolvePreviewFile(rel));
            PreviewError = null;
            PreviewReady?.Invoke(this, new PreviewReadyEventArgs(styles, bitmaps));
        }
        catch (Exception ex)
        {
            PreviewError = ex.InnerException != null && ex.Message.Length < 40
                ? $"{ex.Message} {ex.InnerException.Message}"
                : ex.Message;
        }
    }

    /// <summary>Resolves "fonts/x" / "assets/x" to a temp copy of the file the theme references.</summary>
    private string? ResolvePreviewFile(string relative)
    {
        string? source = ResolveSourceFile(relative);
        return source == null ? null : FontTools.GetPreviewCopy(source);
    }

    private string? ResolveSourceFile(string relative)
    {
        string rel = relative.Replace('\\', '/');
        if (rel.StartsWith("fonts/", StringComparison.OrdinalIgnoreCase))
        {
            string name = rel[6..];
            var f = Fonts.FirstOrDefault(x => x.FileName.Equals(name, StringComparison.OrdinalIgnoreCase));
            return f != null && File.Exists(f.SourcePath) ? f.SourcePath : null;
        }
        if (rel.StartsWith("assets/", StringComparison.OrdinalIgnoreCase))
        {
            string name = rel[7..];
            var a = Assets.FirstOrDefault(x => x.FileName.Equals(name, StringComparison.OrdinalIgnoreCase));
            return a != null && File.Exists(a.SourcePath) ? a.SourcePath : null;
        }
        return null;
    }

    private void UpdateContrast()
    {
        // Gradients are judged by their average colour.
        Color C(string key) => _tokens[key].ToValue().Representative;
        double main = ColorUtil.Contrast(C("TextLight"), C("CyberMainBg"));
        double card = ColorUtil.Contrast(C("TextLight"), C("CyberCardBg"));
        double muted = ColorUtil.Contrast(C("TextMuted"), C("CyberCardBg"));
        double accent = ColorUtil.Contrast(C("NeonCyan"), C("CyberCardBg"));
        ContrastWarning = Math.Min(main, card) < 4.5 || muted < 3 || accent < 3;
        ContrastSummary = $"Contrast — text/background {main:0.0}:1, text/card {card:0.0}:1, muted/card {muted:0.0}:1, accent/card {accent:0.0}:1"
                          + (ContrastWarning ? "   ⚠ some text may be hard to read (aim for ≥4.5 text, ≥3 muted/accent)" : "   ✓ readable");
    }

    /// <summary>Shows an unexpected error in the status bar instead of crashing the app.</summary>
    public void ReportUnexpectedError(Exception ex) =>
        SetStatus($"Something went wrong (the app kept running): {ex.GetBaseException().Message}", isError: true);

    private void SetStatus(string message, bool isError = false)
    {
        StatusMessage = message;
        StatusIsError = isError;
    }

    // =====================================================================
    // Commands: new / open
    // =====================================================================

    private async Task<bool> ConfirmDiscardAsync()
    {
        if (!IsDirty || Dialogs == null) return true;
        return await Dialogs.ConfirmAsync("Unsaved changes", "The current theme has unsaved changes. Discard them?", "Discard");
    }

    [RelayCommand]
    private async Task NewFromPresetAsync(ThemePreset? preset)
    {
        if (preset == null || !await ConfirmDiscardAsync()) return;
        LoadState(preset.Create(), folder: null);
        SetStatus($"New theme from preset '{preset.Name}'.");
    }

    [RelayCommand]
    private async Task OpenFileAsync()
    {
        if (Dialogs == null || !await ConfirmDiscardAsync()) return;
        var files = await Dialogs.PickFilesAsync("Open theme", "Theme files (theme.json, .zip, .axaml)",
            ["theme.json", "*.zip", "*.axaml", "*.xaml"], allowMultiple: false);
        if (files.Count > 0)
            OpenPath(files[0]);
    }

    [RelayCommand]
    private async Task OpenFolderAsync()
    {
        if (Dialogs == null || !await ConfirmDiscardAsync()) return;
        var folder = await Dialogs.PickFolderAsync("Open theme folder");
        if (folder != null)
            OpenPath(folder);
    }

    [RelayCommand]
    private async Task OpenInstalledAsync()
    {
        if (SelectedInstalledTheme == null)
        {
            SetStatus("Select an installed theme first.", isError: true);
            return;
        }
        if (!await ConfirmDiscardAsync()) return;
        OpenPath(SelectedInstalledTheme.Directory);
    }

    [RelayCommand]
    private async Task DeleteInstalledAsync()
    {
        var theme = SelectedInstalledTheme;
        if (theme == null)
        {
            SetStatus("Select an installed theme first.", isError: true);
            return;
        }

        string root = Path.GetFullPath(OverlayThemesDirectory).TrimEnd('\\', '/') + Path.DirectorySeparatorChar;
        string target = Path.GetFullPath(theme.Directory);
        if (!target.StartsWith(root, StringComparison.OrdinalIgnoreCase) || !Directory.Exists(target))
        {
            SetStatus("That theme folder is not inside the overlay's themes folder.", isError: true);
            return;
        }

        if (Dialogs != null && !await Dialogs.ConfirmAsync("Delete theme",
                $"Delete '{theme.Name}' ({theme.Id}) from the overlay?\n\nThe folder {target} will be removed permanently. If the overlay is using this theme it falls back to the default theme.",
                "Delete"))
            return;

        try
        {
            Directory.Delete(target, recursive: true);
            if (CurrentFolder != null && string.Equals(Path.GetFullPath(CurrentFolder), target, StringComparison.OrdinalIgnoreCase))
            {
                // The open theme was the deleted one: keep it in the editor as unsaved.
                CurrentFolder = null;
                _lastSavedXaml = string.Empty;
                IsDirty = true;
            }
            RefreshInstalledThemes();
            SetStatus($"Deleted '{theme.Name}'. In the overlay click CONFIG → Reload.");
        }
        catch (Exception ex)
        {
            SetStatus($"Could not delete theme: {ex.Message}", isError: true);
        }
    }

    public void OpenPath(string path)
    {
        try
        {
            var state = ThemeImporter.Load(path, BuiltInThemes.Cyberpunk);
            bool isFolder = Directory.Exists(path) || Path.GetFileName(path).Equals("theme.json", StringComparison.OrdinalIgnoreCase);
            string? folder = isFolder ? (Directory.Exists(path) ? path : Path.GetDirectoryName(path)) : null;
            LoadState(state, folder);
            if (state.ImportWarnings.Count == 0)
                SetStatus($"Opened '{state.Manifest.Name}'{(folder != null ? " from " + folder : " (save it to a folder to keep changes)")}.");
        }
        catch (Exception ex)
        {
            SetStatus($"Could not open theme: {ex.Message}", isError: true);
        }
    }

    // =====================================================================
    // Commands: save / export / install
    // =====================================================================

    private bool EnsureValidForExport(out ThemeState state)
    {
        Refresh();
        state = BuildState();
        var problems = ThemeValidator.ValidateManifest(state);
        if (problems.Count > 0)
        {
            SetStatus("Fix the theme info first: " + string.Join(" ", problems), isError: true);
            return false;
        }

        try
        {
            ThemeValidator.Prepare(GeneratedXaml, ResolveSourceFile, out _);
        }
        catch (Exception ex)
        {
            SetStatus("Theme cannot be exported: " + ex.Message, isError: true);
            return false;
        }

        if (HasPreviewError && !ThemeValidator.UsesOverlayOnlyNamespaces(GeneratedXaml))
        {
            SetStatus("Theme XAML has errors (see preview): " + PreviewError, isError: true);
            return false;
        }
        return true;
    }

    private void RememberAuthor()
    {
        if (!string.IsNullOrWhiteSpace(Author) && CreatorSettings.Current.LastAuthor != Author.Trim())
        {
            CreatorSettings.Current.LastAuthor = Author.Trim();
            CreatorSettings.Current.Save();
        }
    }

    private void MarkSaved(string folder)
    {
        // After writing, fonts and assets live in the saved folder; point the editor at those copies.
        _suppressChanges = true;
        try
        {
            var fonts = Fonts.ToList();
            Fonts.Clear();
            foreach (var f in fonts)
                Fonts.Add(f with { SourcePath = Path.Combine(folder, "fonts", f.FileName) });
            var assets = Assets.ToList();
            Assets.Clear();
            foreach (var a in assets)
                Assets.Add(a with { SourcePath = Path.Combine(folder, "assets", a.FileName) });
        }
        finally
        {
            _suppressChanges = false;
        }
        CurrentFolder = folder;
        _lastSavedXaml = GeneratedXaml;
        IsDirty = false;
        RememberAuthor();
    }

    [RelayCommand]
    private async Task SaveAsync()
    {
        if (CurrentFolder == null)
        {
            await SaveAsAsync();
            return;
        }
        if (!EnsureValidForExport(out var state)) return;
        WriteFolderTo(state, CurrentFolder);
    }

    [RelayCommand]
    private async Task SaveAsAsync()
    {
        if (Dialogs == null || !EnsureValidForExport(out var state)) return;
        var parent = await Dialogs.PickFolderAsync("Choose where to create the theme folder");
        if (parent == null) return;
        string target = Path.Combine(parent, state.Manifest.Id);
        if (Directory.Exists(target) && Directory.EnumerateFileSystemEntries(target).Any()
            && !await Dialogs.ConfirmAsync("Folder exists", $"'{target}' already exists. Overwrite the theme files in it?", "Overwrite"))
            return;
        WriteFolderTo(state, target);
    }

    private void WriteFolderTo(ThemeState state, string folder)
    {
        try
        {
            var warnings = ThemeExporter.WriteFolder(state, GeneratedXaml, folder);
            MarkSaved(folder);
            SetStatus(warnings.Count == 0 ? $"Saved to {folder}" : $"Saved with warnings: {string.Join(" ", warnings)}", warnings.Count > 0);
            RefreshInstalledThemes();
        }
        catch (Exception ex)
        {
            SetStatus($"Save failed: {ex.Message}", isError: true);
        }
    }

    [RelayCommand]
    private async Task ExportZipAsync()
    {
        if (Dialogs == null || !EnsureValidForExport(out var state)) return;
        var path = await Dialogs.PickSaveFileAsync("Export theme pack", $"{state.Manifest.Id}.zip", "Theme pack (*.zip)", "*.zip");
        if (path == null) return;
        try
        {
            var warnings = ThemeExporter.WriteZip(state, GeneratedXaml, path);
            RememberAuthor();
            SetStatus(warnings.Count == 0
                ? $"Exported {Path.GetFileName(path)} — share it; users install it with CONFIG → Install in the overlay."
                : $"Exported with warnings: {string.Join(" ", warnings)}", warnings.Count > 0);
        }
        catch (Exception ex)
        {
            SetStatus($"Export failed: {ex.Message}", isError: true);
        }
    }

    [RelayCommand]
    private async Task InstallToOverlayAsync()
    {
        if (!EnsureValidForExport(out var state)) return;
        if (string.IsNullOrWhiteSpace(OverlayThemesDirectory))
        {
            SetStatus("Overlay themes folder is not set. Use 'Find overlay…' in the Overlay tab.", isError: true);
            return;
        }

        string target = Path.Combine(OverlayThemesDirectory, state.Manifest.Id);
        bool isCurrent = CurrentFolder != null && string.Equals(Path.GetFullPath(CurrentFolder), Path.GetFullPath(target), StringComparison.OrdinalIgnoreCase);
        if (!isCurrent && Directory.Exists(target) && Dialogs != null
            && !await Dialogs.ConfirmAsync("Theme already installed", $"A theme with ID '{state.Manifest.Id}' is already installed in the overlay. Replace it?", "Replace"))
            return;

        try
        {
            var warnings = ThemeExporter.WriteFolder(state, GeneratedXaml, target);
            RememberAuthor();
            if (isCurrent)
                MarkSaved(target);
            RefreshInstalledThemes();
            SetStatus(warnings.Count == 0
                ? $"Installed to overlay. In the overlay open CONFIG → Reload, then pick '{state.Manifest.Name}'."
                : $"Installed with warnings: {string.Join(" ", warnings)}", warnings.Count > 0);
        }
        catch (Exception ex)
        {
            SetStatus($"Install failed: {ex.Message}", isError: true);
        }
    }

    [RelayCommand]
    private async Task CopyXamlAsync()
    {
        if (Dialogs == null) return;
        await Dialogs.CopyTextAsync(GeneratedXaml);
        SetStatus("theme.axaml copied to clipboard.");
    }

    // =====================================================================
    // Commands: overlay integration
    // =====================================================================

    [RelayCommand]
    private void DetectOverlay()
    {
        CreatorSettings.Current.OverlayThemesDirectory = string.Empty;
        string? found = OverlayLocator.Detect();
        if (found != null)
        {
            OverlayThemesDirectory = found;
            SetStatus($"Overlay themes folder: {found}");
        }
        else
        {
            SetStatus("Overlay not found automatically. Start the overlay and try again, or browse to its folder.", isError: true);
        }
    }

    [RelayCommand]
    private async Task BrowseOverlayAsync()
    {
        if (Dialogs == null) return;
        var folder = await Dialogs.PickFolderAsync("Select the overlay folder (where RbwrOverlay.exe is) or its themes folder");
        if (folder == null) return;
        OverlayThemesDirectory = OverlayLocator.NormaliseSelection(folder);
        CreatorSettings.Current.OverlayThemesDirectory = OverlayThemesDirectory;
        CreatorSettings.Current.Save();
        SetStatus($"Overlay themes folder: {OverlayThemesDirectory}");
    }

    [RelayCommand]
    private void OpenOverlayThemesFolder() => OpenInExplorer(OverlayThemesDirectory, create: true);

    [RelayCommand]
    private void OpenCurrentFolder() => OpenInExplorer(CurrentFolder, create: false);

    private void OpenInExplorer(string? path, bool create)
    {
        if (string.IsNullOrWhiteSpace(path)) return;
        try
        {
            if (create) Directory.CreateDirectory(path);
            if (!Directory.Exists(path)) return;
            Process.Start(new ProcessStartInfo { FileName = path, UseShellExecute = true });
        }
        catch (Exception ex)
        {
            SetStatus($"Could not open folder: {ex.Message}", isError: true);
        }
    }

    [RelayCommand]
    private void RefreshInstalledThemes()
    {
        InstalledThemes.Clear();
        if (string.IsNullOrWhiteSpace(OverlayThemesDirectory) || !Directory.Exists(OverlayThemesDirectory))
            return;
        try
        {
            foreach (string dir in Directory.EnumerateDirectories(OverlayThemesDirectory).OrderBy(d => d, StringComparer.OrdinalIgnoreCase))
            {
                string json = Path.Combine(dir, "theme.json");
                string name = Path.GetFileName(dir);
                string id = name;
                if (File.Exists(json))
                {
                    try
                    {
                        var m = System.Text.Json.JsonSerializer.Deserialize<ThemeManifest>(File.ReadAllText(json),
                            new System.Text.Json.JsonSerializerOptions { PropertyNameCaseInsensitive = true });
                        if (!string.IsNullOrWhiteSpace(m?.Name)) name = m!.Name;
                        if (!string.IsNullOrWhiteSpace(m?.Id)) id = m!.Id;
                    }
                    catch
                    {
                        // show folder name for unreadable manifests
                    }
                }
                else if (!File.Exists(Path.Combine(dir, "theme.axaml")))
                {
                    continue;
                }
                InstalledThemes.Add(new InstalledThemeEntry(id, name, dir));
            }
        }
        catch (Exception ex)
        {
            SetStatus($"Could not list overlay themes: {ex.Message}", isError: true);
        }
    }

    // =====================================================================
    // Commands: fonts and images
    // =====================================================================

    [RelayCommand]
    private async Task AddFontAsync()
    {
        if (Dialogs == null) return;
        var files = await Dialogs.PickFilesAsync("Add font files", "Fonts (*.ttf, *.otf, *.ttc)", FontPatterns, allowMultiple: true);
        FontEntry? last = null;
        foreach (var file in files)
        {
            string name = SafeFileName(file);
            var existing = Fonts.FirstOrDefault(f => f.FileName.Equals(name, StringComparison.OrdinalIgnoreCase));
            if (existing != null) Fonts.Remove(existing);
            last = new FontEntry(name, file, FontTools.ReadFamilyName(file));
            Fonts.Add(last);
        }
        if (last != null)
        {
            SetStatus(files.Count == 1
                ? $"Added font {last.FileName}. Click 'Use as main' to apply it."
                : $"Added {files.Count} fonts.");
            OnEdited();
        }
    }

    [RelayCommand]
    private void RemoveFont(FontEntry? font)
    {
        if (font == null) return;
        Fonts.Remove(font);
        string reference = $"fonts/{font.FileName}";
        if (FontFamily.Contains(reference, StringComparison.OrdinalIgnoreCase))
            FontFamily = BuiltInThemes.Cyberpunk.FontFamily;
        if (MonoFontFamily.Contains(reference, StringComparison.OrdinalIgnoreCase))
            MonoFontFamily = BuiltInThemes.Cyberpunk.MonoFontFamily;
        OnEdited();
    }

    [RelayCommand]
    private void UseFontAsMain(FontEntry? font)
    {
        if (font != null) FontFamily = FontReference(font, "Consolas, 'Segoe UI', Inter, monospace");
    }

    [RelayCommand]
    private void UseFontAsMono(FontEntry? font)
    {
        if (font != null) MonoFontFamily = FontReference(font, "Consolas, monospace");
    }

    private static string FontReference(FontEntry font, string fallbacks)
    {
        string family = string.IsNullOrWhiteSpace(font.FamilyName) ? Path.GetFileNameWithoutExtension(font.FileName) : font.FamilyName;
        return $"fonts/{font.FileName}#{family}, {fallbacks}";
    }

    [RelayCommand]
    private void ResetFonts()
    {
        FontFamily = BuiltInThemes.Cyberpunk.FontFamily;
        MonoFontFamily = BuiltInThemes.Cyberpunk.MonoFontFamily;
    }

    [RelayCommand]
    private async Task AddImageAsync() => await AddImagesAsync(setAsBackground: false);

    [RelayCommand]
    private async Task ChooseBackgroundImageAsync() => await AddImagesAsync(setAsBackground: true);

    private async Task AddImagesAsync(bool setAsBackground)
    {
        if (Dialogs == null) return;
        var files = await Dialogs.PickFilesAsync(setAsBackground ? "Choose background image" : "Add images",
            "Images (*.png, *.jpg, *.webp, *.bmp, *.gif)", ImagePatterns, allowMultiple: !setAsBackground);
        string? lastName = null;
        foreach (var file in files)
        {
            string name = SafeFileName(file);
            var existing = Assets.FirstOrDefault(a => a.FileName.Equals(name, StringComparison.OrdinalIgnoreCase));
            if (existing != null)
            {
                Assets.Remove(existing);
                AssetNames.Remove(existing.FileName);
            }
            Assets.Add(new ThemeFile(name, file));
            AssetNames.Add(name);
            lastName = name;
        }
        if (lastName == null) return;

        if (setAsBackground)
        {
            // Re-select so the preview reloads even if the name did not change.
            BackgroundImageFile = null;
            BackgroundImageFile = lastName;
            SetStatus($"Background image set to assets/{lastName}.");
        }
        else
        {
            SetStatus($"Added {files.Count} image(s). Reference them in custom styles as Source=\"assets/{lastName}\".");
        }
        OnEdited();
    }

    [RelayCommand]
    private void RemoveAsset(ThemeFile? asset)
    {
        if (asset == null) return;
        Assets.Remove(asset);
        AssetNames.Remove(asset.FileName);
        if (string.Equals(BackgroundImageFile, asset.FileName, StringComparison.OrdinalIgnoreCase))
            BackgroundImageFile = null;
        OnEdited();
    }

    [RelayCommand]
    private void ClearBackgroundImage() => BackgroundImageFile = null;

    private static string SafeFileName(string path)
    {
        string name = Path.GetFileName(path);
        foreach (char c in new[] { ' ', '\'', '"', ',', ';', ')', '(', '#', '<', '>' })
            name = name.Replace(c, '_');
        return name;
    }

    // =====================================================================
    // Commands: palette
    // =====================================================================

    [RelayCommand]
    private void GeneratePalette()
    {
        var state = BuildState();
        PaletteGenerator.Apply(state, GeneratorAccent, (PaletteGenerator.Mood)Math.Clamp(GeneratorMood, 0, 2), keepStatusColours: !GeneratorStatusColours);
        _suppressChanges = true;
        try
        {
            foreach (var (key, vm) in _tokens)
                vm.SetValue(state.Tokens[key]);
        }
        finally
        {
            _suppressChanges = false;
        }
        Refresh();
        SetStatus($"Palette generated from {ColorUtil.ToHex(GeneratorAccent)}. Fine-tune individual colours below.");
    }

    [RelayCommand]
    private void ResetColoursToBase()
    {
        _suppressChanges = true;
        try
        {
            foreach (var (key, vm) in _tokens)
                if (BuiltInThemes.Cyberpunk.Tokens.TryGetValue(key, out var v))
                    vm.SetValue(v);
        }
        finally
        {
            _suppressChanges = false;
        }
        Refresh();
        SetStatus("Colours reset to the overlay's default Cyberpunk palette.");
    }

    [RelayCommand]
    private void ResetShape()
    {
        var d = new ShapeSettings();
        _suppressChanges = true;
        try
        {
            ShapeEnabled = d.Enabled;
            ShellCornerRadius = d.ShellCornerRadius;
            ShellBorderThickness = d.ShellBorderThickness;
            CardCornerRadius = d.CardCornerRadius;
            ButtonCornerRadius = d.ButtonCornerRadius;
            CompactCornerRadius = d.CompactCornerRadius;
            ShellGlow = d.ShellGlow;
            ShellGlowBlur = d.ShellGlowBlur;
        }
        finally
        {
            _suppressChanges = false;
        }
        Refresh();
        SetStatus("Shape reset to the overlay's defaults.");
    }

    [RelayCommand]
    private void InsertStyleSnippet(string? kind)
    {
        string snippet = kind switch
        {
            "title" => """
                <Style Selector="TextBlock#OverlayTitle">
                    <Setter Property="FontSize" Value="13" />
                    <Setter Property="LetterSpacing" Value="2" />
                </Style>
                """,
            "nav" => """
                <Style Selector="Button.cyber-nav.active">
                    <Setter Property="BorderThickness" Value="0,0,0,3" />
                </Style>
                """,
            "readout" => """
                <Style Selector="TextBlock.power-readout">
                    <Setter Property="FontSize" Value="28" />
                </Style>
                """,
            "image" => """
                <Style Selector="Border#PowerBanner">
                    <Setter Property="Background">
                        <ImageBrush Source="assets/banner.png" Stretch="UniformToFill" Opacity="0.4" />
                    </Setter>
                </Style>
                """,
            _ => string.Empty,
        };
        if (snippet.Length == 0) return;
        CustomStyles = string.IsNullOrWhiteSpace(CustomStyles) ? snippet : CustomStyles.TrimEnd() + Environment.NewLine + Environment.NewLine + snippet;
    }
}
