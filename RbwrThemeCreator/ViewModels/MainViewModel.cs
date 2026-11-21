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
    public const string AppVersion = "1.1.0-dev";
    public string GlobalAppVersion => AppVersion;
    public string AppVersionBadge => $"v{AppVersion}";
    public string AppVersionText => $"RBWR Theme Creator v{AppVersion}";

    private static readonly string[] FontPatterns = ["*.ttf", "*.otf", "*.ttc"];
    private static readonly string[] ImagePatterns = ["*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp", "*.gif"];

    private readonly DispatcherTimer _refreshTimer;
    private readonly Dictionary<string, TokenViewModel> _tokens = new(StringComparer.Ordinal);
    private readonly List<ThemeState> _undoStack = new();
    private readonly List<ThemeState> _redoStack = new();
    private const int MaxUndoSteps = 50;
    private ThemeState? _lastRecordedState;
    private string _lastRecordedFingerprint = string.Empty;
    private bool _isRestoringHistory;
    private bool _suppressChanges;
    private string _lastSavedFingerprint = string.Empty;

    public ICreatorUpdateService UpdateService { get; }
    public IDialogHost? Dialogs { get; set; }

    /// <summary>Raised on the UI thread with freshly parsed preview styles (or null on error).</summary>
    public event EventHandler<PreviewReadyEventArgs>? PreviewReady;

    /// <summary>Raised when a newer <c>theme-creator-v*</c> release is available on GitHub.</summary>
    public event Action<UpdateInfo>? RequestShowUpdate;

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

    // ---------- THEME tab: custom thumbnail ----------
    /// <summary>PNG used as preview.png instead of the rendered MONITOR view (null = automatic).</summary>
    [ObservableProperty] private string? _customThumbnailPath;
    public bool HasCustomThumbnail => CustomThumbnailPath != null;
    public string ThumbnailModeText => HasCustomThumbnail ? "Custom image" : "Automatic (MONITOR view)";

    partial void OnCustomThumbnailPathChanged(string? value)
    {
        OnPropertyChanged(nameof(HasCustomThumbnail));
        OnPropertyChanged(nameof(ThumbnailModeText));
        OnEdited();
    }

    // ---------- THEME tab: Theme Manager card preview + recent themes ----------
    /// <summary>How the theme's card looks in the overlay's Theme Manager (same texts as the overlay).</summary>
    public string CardName => string.IsNullOrWhiteSpace(ThemeName) ? "Untitled" : ThemeName.Trim();
    public string CardVersionText => string.IsNullOrWhiteSpace(Version) ? "v1.0.0" : (Version.Trim().StartsWith('v') ? Version.Trim() : $"v{Version.Trim()}");
    public string CardAuthorText => string.IsNullOrWhiteSpace(Author) ? "Unknown Author" : $"by {Author.Trim()}";

    // Brushes of the edited theme, so the card is drawn in the theme's own colours.
    public IBrush CardWindowBrush => TokenBrush("CyberMainBg");
    public IBrush CardBackgroundBrush => TokenBrush("CyberCardBg");
    public IBrush CardBorderBrush => TokenBrush("CyberBorder");
    public IBrush CardGlowBrush => TokenBrush("CyberBorderGlow"); // the card outline in the Theme Manager
    public IBrush CardPanelBrush => TokenBrush("DarkPanelBg");
    public IBrush CardTextBrush => TokenBrush("TextLight");
    public IBrush CardMutedBrush => TokenBrush("TextMuted");
    public IBrush CardGoldBrush => TokenBrush("NeonGold");
    public IBrush CardAccentBrush => TokenBrush("NeonCyan");

    private static readonly string[] CardBrushProperties =
    [
        nameof(CardWindowBrush), nameof(CardBackgroundBrush), nameof(CardBorderBrush), nameof(CardGlowBrush), nameof(CardPanelBrush),
        nameof(CardTextBrush), nameof(CardMutedBrush), nameof(CardGoldBrush), nameof(CardAccentBrush),
    ];

    private const int MaxRecentThemes = 6;
    public ObservableCollection<RecentThemeEntry> RecentThemes { get; } = new();
    public bool HasRecentThemes => RecentThemes.Count > 0;

    // ---------- SETTINGS tab ----------
    /// <summary>The keyboard shortcuts in use (defaults + the user's changes).</summary>
    public ShortcutMap Shortcuts { get; }
    public IReadOnlyList<ShortcutEntryViewModel> ShortcutEntries { get; }

    /// <summary>The shortcut row waiting for a key press, if any.</summary>
    public ShortcutEntryViewModel? RecordingShortcut { get; private set; }

    public bool OpenLastThemeAtStart
    {
        get => CreatorSettings.Current.OpenLastThemeAtStart;
        set => SetSetting(value, CreatorSettings.Current.OpenLastThemeAtStart, v => CreatorSettings.Current.OpenLastThemeAtStart = v);
    }

    public bool AutoCreateThumbnails
    {
        get => CreatorSettings.Current.AutoCreateThumbnails;
        set => SetSetting(value, CreatorSettings.Current.AutoCreateThumbnails, v => CreatorSettings.Current.AutoCreateThumbnails = v);
    }

    public bool AutosaveEnabled
    {
        get => CreatorSettings.Current.AutosaveEnabled;
        set
        {
            SetSetting(value, CreatorSettings.Current.AutosaveEnabled, v => CreatorSettings.Current.AutosaveEnabled = v);
            if (!value) Recovery?.Clear();
        }
    }

    // ---------- Autosave / crash recovery ----------
    /// <summary>Where the recovery copy lives. Null (tests) = no autosave at all.</summary>
    public RecoveryStore? Recovery { get; set; }
    private DispatcherTimer? _autosaveTimer;
    private string _loadedFingerprint = string.Empty;

    public bool CheckUpdatesAtStart
    {
        get => CreatorSettings.Current.CheckUpdatesAtStart;
        set => SetSetting(value, CreatorSettings.Current.CheckUpdatesAtStart, v => CreatorSettings.Current.CheckUpdatesAtStart = v);
    }

    /// <summary>SETTINGS → Default author (empty = the last author a theme was saved with).</summary>
    public string DefaultAuthor
    {
        get => CreatorSettings.Current.DefaultAuthor;
        set
        {
            string v = (value ?? string.Empty).Trim();
            if (v == CreatorSettings.Current.DefaultAuthor) return;
            CreatorSettings.Current.DefaultAuthor = v;
            CreatorSettings.Current.Save();
            OnPropertyChanged();
            OnPropertyChanged(nameof(DefaultAuthorHint));
            DefaultAuthorInput = v;
            SetDefaultAuthorCommand.NotifyCanExecuteChanged();
        }
    }

    /// <summary>What is typed in the Default author box; saved only by SET.</summary>
    public string DefaultAuthorInput
    {
        get => _defaultAuthorInput ??= CreatorSettings.Current.DefaultAuthor;
        set
        {
            if (value == _defaultAuthorInput) return;
            _defaultAuthorInput = value;
            OnPropertyChanged();
            SetDefaultAuthorCommand.NotifyCanExecuteChanged();
        }
    }
    private string? _defaultAuthorInput;

    public string DefaultAuthorHint => string.IsNullOrWhiteSpace(CreatorSettings.Current.DefaultAuthor)
        ? (string.IsNullOrWhiteSpace(CreatorSettings.Current.LastAuthor)
            ? "Empty: new themes start without an author until you save one with a name."
            : $"Empty: new themes use the last author you saved with ({CreatorSettings.Current.LastAuthor}).")
        : "New themes start with this author.";

    /// <summary>COLOURS tab boxes; hidden with their × button, shown again in SETTINGS.</summary>
    public bool ShowGradientTip
    {
        get => CreatorSettings.Current.ShowGradientTip;
        set => SetSetting(value, CreatorSettings.Current.ShowGradientTip, v => CreatorSettings.Current.ShowGradientTip = v);
    }

    public bool ShowContrastCheck
    {
        get => CreatorSettings.Current.ShowContrastCheck;
        set
        {
            SetSetting(value, CreatorSettings.Current.ShowContrastCheck, v => CreatorSettings.Current.ShowContrastCheck = v);
            OnPropertyChanged(nameof(ShowContrastOk));
            OnPropertyChanged(nameof(ShowContrastWarning));
        }
    }

    public bool ShowContrastOk => ShowContrastCheck && !ContrastWarning;
    public bool ShowContrastWarning => ShowContrastCheck && ContrastWarning;

    [RelayCommand]
    private void HideGradientTip()
    {
        ShowGradientTip = false;
        SetStatus("Gradient tip hidden. Show it again in SETTINGS.");
    }

    [RelayCommand]
    private void HideContrastCheck()
    {
        ShowContrastCheck = false;
        SetStatus("Contrast check hidden. Show it again in SETTINGS.");
    }

    public bool HasSkippedVersion => !string.IsNullOrWhiteSpace(CreatorSettings.Current.SkippedVersion);
    public string SkippedVersionText => HasSkippedVersion ? $"Skipped update: v{CreatorSettings.Current.SkippedVersion}" : "No update is skipped.";

    // ---------- Colour search ----------
    [ObservableProperty] private string _tokenSearch = string.Empty;
    [ObservableProperty] private bool _hasNoSearchResults;

    // ---------- Updates ----------
    [ObservableProperty] private bool _isCheckingUpdates;
    [ObservableProperty] private string _updateStatusText = $"Installed version: v{AppVersion}";

    public bool HasPreviewError => !string.IsNullOrEmpty(PreviewError);
    public bool HasManifestProblems => !string.IsNullOrEmpty(ManifestProblems);
    public bool HasBackgroundImage => !string.IsNullOrEmpty(BackgroundImageFile);
    public bool CanUndo => _undoStack.Count > 0;
    public bool CanRedo => _redoStack.Count > 0;
    public string WindowTitle => $"RBWR Theme Creator — {(string.IsNullOrWhiteSpace(ThemeName) ? "Untitled" : ThemeName)}{(IsDirty ? " •" : string.Empty)}";
    public string CurrentFolderDisplay => CurrentFolder ?? "Not saved yet";
    public string PreviewZoomText => $"{Math.Round(PreviewZoom * 100)}%";
    public string ThemeSubtitle => $"{(string.IsNullOrWhiteSpace(ThemeId) ? "no-id" : ThemeId)}  ·  v{Version}{(string.IsNullOrWhiteSpace(Author) ? "" : "  ·  " + Author)}";

    public MainViewModel(ICreatorUpdateService? updateService = null)
    {
        UpdateService = updateService ?? new CreatorUpdateService();

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
        _previewMode = Math.Clamp(settings.PreviewMode, 0, 4);

        OverlayThemesDirectory = OverlayLocator.Detect() ?? string.Empty;
        LoadRecentThemes();

        Shortcuts = new ShortcutMap(CreatorSettings.Current.Shortcuts, CreatorSettings.Current.Save);
        ShortcutEntries = ShortcutCatalog.All.Select(d => new ShortcutEntryViewModel(d, this)).ToList();
        Shortcuts.Changed += (_, _) => RefreshShortcutEntries();
        RefreshShortcutEntries();
        LoadState(BuiltInThemes.Presets[0].Create(), folder: null);
        SetStatus("New theme from the Cyberpunk preset. Edit colours on the left — the preview updates live.");
    }

    // =====================================================================
    // Autosave / crash recovery
    // =====================================================================

    /// <summary>Starts the 30-second autosave (MainWindow calls this once the window is open).</summary>
    public void StartAutosave()
    {
        _autosaveTimer ??= new DispatcherTimer(TimeSpan.FromSeconds(30), DispatcherPriority.Background, (_, _) => AutosaveNow());
        _autosaveTimer.Start();
    }

    /// <summary>
    /// Writes the recovery copy when there are unsaved changes (a theme that was just opened or
    /// created and not touched is not copied). Returns true when a copy was written.
    /// </summary>
    public bool AutosaveNow()
    {
        if (Recovery == null || !AutosaveEnabled) return false;
        var state = BuildState();
        string fingerprint = ComputeSaveFingerprint(state, GeneratedXaml);
        if (!IsDirty || fingerprint == _loadedFingerprint)
            return false;
        try
        {
            byte[]? custom = CustomThumbnailPath != null && File.Exists(CustomThumbnailPath) ? File.ReadAllBytes(CustomThumbnailPath) : null;
            Recovery.Save(state, GeneratedXaml, CurrentFolder, custom);
            return true;
        }
        catch
        {
            return false; // never interrupt the user over an autosave
        }
    }

    /// <summary>
    /// Loads the recovery copy: the theme comes back with all its changes, unsaved, and attached to
    /// its original folder (when that still exists) so SAVE writes it there.
    /// </summary>
    public bool RestoreRecovery()
    {
        if (Recovery?.Peek() is not { } info) return false;
        try
        {
            var state = Recovery.Load();
            if (state == null) return false;
            string? folder = info.OriginalFolder != null && Directory.Exists(info.OriginalFolder) ? info.OriginalFolder : null;
            LoadState(state, folder);
            _lastSavedFingerprint = string.Empty; // the restored changes are not saved yet
            IsDirty = true;
            SetStatus(folder != null
                ? $"Restored unsaved changes to '{info.ThemeName}'. SAVE to keep them in {folder}."
                : $"Restored unsaved theme '{info.ThemeName}'. Save it to a folder to keep it.");
            return true;
        }
        catch (Exception ex)
        {
            SetStatus($"Could not restore the unsaved theme: {ex.Message}", isError: true);
            return false;
        }
    }

    // =====================================================================
    // SETTINGS tab
    // =====================================================================

    private void SetSetting(bool value, bool current, Action<bool> store, [System.Runtime.CompilerServices.CallerMemberName] string? name = null)
    {
        if (value == current) return;
        store(value);
        CreatorSettings.Current.Save();
        OnPropertyChanged(name);
    }

    private void RefreshShortcutEntries()
    {
        foreach (var entry in ShortcutEntries)
            entry.Refresh(Shortcuts);
    }

    /// <summary>Clicked a shortcut: the next key press (see MainWindow) becomes its new shortcut.</summary>
    public void StartRecordingShortcut(ShortcutEntryViewModel entry)
    {
        CancelShortcutRecording();
        RecordingShortcut = entry;
        entry.IsRecording = true;
        SetStatus($"Press the new keys for '{entry.Label}'. Esc cancels, Backspace removes the shortcut.");
    }

    public void CancelShortcutRecording()
    {
        if (RecordingShortcut == null) return;
        RecordingShortcut.IsRecording = false;
        RecordingShortcut = null;
    }

    /// <summary>Ends recording with <paramref name="gesture"/> (null = remove the shortcut).</summary>
    public void FinishShortcutRecording(ShortcutGesture? gesture)
    {
        var entry = RecordingShortcut;
        if (entry == null) return;
        CancelShortcutRecording();

        string? taken = Shortcuts.Set(entry.Id, gesture);
        if (gesture == null)
            SetStatus($"'{entry.Label}' has no shortcut now.");
        else if (taken != null)
            SetStatus($"'{entry.Label}' is now {gesture}. It was used by '{ShortcutCatalog.Find(taken)?.Label}', which has no shortcut now.");
        else
            SetStatus($"'{entry.Label}' is now {gesture}.");
    }

    public void ResetShortcut(ShortcutEntryViewModel entry)
    {
        CancelShortcutRecording();
        Shortcuts.ResetToDefault(entry.Id);
        SetStatus($"'{entry.Label}' is back to its default shortcut ({entry.DefaultText}).");
    }

    [RelayCommand]
    private async Task ResetShortcutsAsync()
    {
        CancelShortcutRecording();
        if (Dialogs != null && !await Dialogs.ConfirmAsync("Reset shortcuts", "Set every keyboard shortcut back to its default?", "Reset shortcuts"))
            return;
        Shortcuts.ResetAll();
        SetStatus("Keyboard shortcuts are back to their defaults.");
    }

    private bool CanSetDefaultAuthor() => (DefaultAuthorInput ?? string.Empty).Trim() != CreatorSettings.Current.DefaultAuthor;

    /// <summary>SETTINGS → SET: saves the typed default author.</summary>
    [RelayCommand(CanExecute = nameof(CanSetDefaultAuthor))]
    private void SetDefaultAuthor()
    {
        DefaultAuthor = DefaultAuthorInput;
        SetStatus(string.IsNullOrWhiteSpace(DefaultAuthor)
            ? "Default author cleared: new themes use the last author you saved with."
            : $"Default author set to '{DefaultAuthor}'. New themes start with it.");
    }

    [RelayCommand]
    private void UnskipVersion()
    {
        CreatorSettings.Current.SkippedVersion = string.Empty;
        CreatorSettings.Current.Save();
        OnPropertyChanged(nameof(HasSkippedVersion));
        OnPropertyChanged(nameof(SkippedVersionText));
        SetStatus("The skipped update will be offered again.");
    }

    /// <summary>
    /// Resets the app settings (start-up options, skipped update, recent themes, preview view, last
    /// author). Keyboard shortcuts, the overlay folder and the themes themselves are not touched.
    /// </summary>
    [RelayCommand]
    private async Task ResetSettingsAsync()
    {
        if (Dialogs != null && !await Dialogs.ConfirmAsync("Reset settings",
                "Reset the start-up options, the default author, the COLOURS tab boxes, the skipped update, the recent themes list and the preview view? Keyboard shortcuts, the overlay folder and your themes are kept.",
                "Reset settings"))
            return;

        var s = CreatorSettings.Current;
        s.OpenLastThemeAtStart = false;
        s.AutoCreateThumbnails = true;
        s.CheckUpdatesAtStart = true;
        s.AutosaveEnabled = true;
        s.SkippedVersion = string.Empty;
        s.LastAuthor = string.Empty;
        s.DefaultAuthor = string.Empty;
        s.ShowGradientTip = true;
        s.ShowContrastCheck = true;
        s.RecentThemes.Clear();
        s.Save();

        PreviewBackdrop = 0;
        PreviewZoom = 1.0;
        PreviewFit = true;
        PreviewMode = 0;

        foreach (string name in new[] { nameof(OpenLastThemeAtStart), nameof(AutoCreateThumbnails), nameof(CheckUpdatesAtStart), nameof(AutosaveEnabled),
                     nameof(DefaultAuthor), nameof(DefaultAuthorHint),
                     nameof(ShowGradientTip), nameof(ShowContrastCheck), nameof(ShowContrastOk), nameof(ShowContrastWarning),
                     nameof(HasSkippedVersion), nameof(SkippedVersionText) })
            OnPropertyChanged(name);
        DefaultAuthorInput = string.Empty;
        SetDefaultAuthorCommand.NotifyCanExecuteChanged();
        LoadRecentThemes();
        SetStatus("Settings reset. Keyboard shortcuts were kept.");
    }

    [RelayCommand]
    private void OpenSettingsFolder() => OpenInExplorer(CreatorSettings.FolderPath, create: true);

    /// <summary>SETTINGS → Open the last theme at start: opens the newest folder of the recent list.</summary>
    public void OpenLastTheme()
    {
        string? folder = CreatorSettings.Current.RecentThemes.FirstOrDefault(Directory.Exists);
        if (folder != null)
            OpenPath(folder);
    }

    // =====================================================================
    // THEME tab: Theme Manager card + recent themes
    // =====================================================================

    [RelayCommand]
    private async Task ChooseCustomThumbnailAsync()
    {
        if (Dialogs == null) return;
        var files = await Dialogs.PickFilesAsync("Choose a thumbnail image", "Images", PreviewImage.PickPatterns, allowMultiple: false);
        if (files.Count == 0) return;
        string? png = PreviewImage.MakeThumbnail(files[0], out string error);
        if (png == null)
        {
            SetStatus($"Thumbnail not changed: {error}", isError: true);
            return;
        }
        CustomThumbnailPath = png;
        SetStatus("Custom thumbnail set. It is saved as preview.png on Save, Export and Install.");
    }

    [RelayCommand]
    private void UseAutoThumbnail()
    {
        CustomThumbnailPath = null;
        SetStatus("Custom thumbnail removed. The thumbnail is generated automatically again; Save to update preview.png.");
    }

    /// <summary>The token's brush as the theme draws it (gradient and opacity included).</summary>
    private IBrush TokenBrush(string key)
    {
        if (!_tokens.TryGetValue(key, out var token))
            return Brushes.Transparent;
        var brush = token.PreviewBrush;
        if (token.SupportsOpacity && brush is Brush b)
            b.Opacity = token.Opacity;
        return brush;
    }

    /// <summary>Puts <paramref name="folder"/> at the top of the recent list (temp folders are skipped).</summary>
    private void RememberRecentTheme(string folder)
    {
        string full;
        try
        {
            full = Path.GetFullPath(folder).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            // Extracted .zip packs and test folders live in %TEMP%: not useful to reopen later.
            if (full.StartsWith(Path.GetFullPath(Path.GetTempPath()), StringComparison.OrdinalIgnoreCase))
            {
                LoadRecentThemes();
                return;
            }
        }
        catch
        {
            return;
        }

        var list = CreatorSettings.Current.RecentThemes;
        list.RemoveAll(p => string.Equals(p, full, StringComparison.OrdinalIgnoreCase));
        list.Insert(0, full);
        if (list.Count > MaxRecentThemes * 2)
            list.RemoveRange(MaxRecentThemes * 2, list.Count - MaxRecentThemes * 2);
        CreatorSettings.Current.Save();
        LoadRecentThemes();
    }

    /// <summary>Rebuilds the recent list: existing folders only, without the theme that is open now.</summary>
    public void LoadRecentThemes()
    {
        RecentThemes.Clear();
        foreach (string folder in CreatorSettings.Current.RecentThemes)
        {
            if (RecentThemes.Count >= MaxRecentThemes) break;
            if (!Directory.Exists(folder)) continue;
            if (CurrentFolder != null && string.Equals(Path.GetFullPath(CurrentFolder).TrimEnd(Path.DirectorySeparatorChar), folder, StringComparison.OrdinalIgnoreCase))
                continue;
            RecentThemes.Add(RecentThemeEntry.Read(folder));
        }
        OnPropertyChanged(nameof(HasRecentThemes));
    }

    [RelayCommand]
    private async Task OpenRecentAsync(RecentThemeEntry? entry)
    {
        if (entry == null) return;
        if (!Directory.Exists(entry.Folder))
        {
            SetStatus($"'{entry.Folder}' no longer exists.", isError: true);
            LoadRecentThemes();
            return;
        }
        if (!await ConfirmDiscardAsync()) return;
        OpenPath(entry.Folder);
    }

    [RelayCommand]
    private void ClearRecentThemes()
    {
        CreatorSettings.Current.RecentThemes.Clear();
        CreatorSettings.Current.Save();
        LoadRecentThemes();
    }

    // =====================================================================
    // Colour search + "which colour is this?" from the preview
    // =====================================================================

    partial void OnTokenSearchChanged(string value) => ApplyTokenSearch();

    /// <summary>
    /// Filters the COLOURS list. Every word must appear in the label, key, hint, group or hex value,
    /// so "slider hover" or "#00f0ff" both work.
    /// </summary>
    private void ApplyTokenSearch()
    {
        string[] words = (TokenSearch ?? string.Empty)
            .Split(' ', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        int visible = 0;
        foreach (var group in Groups)
        {
            bool any = false;
            foreach (var token in group.Tokens)
            {
                bool match = words.Length == 0 || words.All(w =>
                    token.Label.Contains(w, StringComparison.OrdinalIgnoreCase)
                    || token.Key.Contains(w, StringComparison.OrdinalIgnoreCase)
                    || token.Hint.Contains(w, StringComparison.OrdinalIgnoreCase)
                    || group.Name.Contains(w, StringComparison.OrdinalIgnoreCase)
                    || token.HexText.Contains(w.TrimStart('#'), StringComparison.OrdinalIgnoreCase));
                token.IsMatch = match;
                any |= match;
                if (match) visible++;
            }
            group.HasMatches = any;
        }
        HasNoSearchResults = visible == 0;
    }

    [RelayCommand]
    private void ClearTokenSearch() => TokenSearch = string.Empty;

    /// <summary>Token view models for the given keys, in catalogue order.</summary>
    public IReadOnlyList<TokenViewModel> GetTokens(IEnumerable<string> keys)
    {
        var wanted = new HashSet<string>(keys, StringComparer.Ordinal);
        return TokenCatalog.Tokens.Where(t => wanted.Contains(t.Key)).Select(t => _tokens[t.Key]).ToList();
    }

    /// <summary>Makes sure the tokens are visible in the list and makes their rows flash briefly.</summary>
    public async Task FlashTokensAsync(IReadOnlyList<TokenViewModel> tokens)
    {
        if (tokens.Any(t => !t.IsMatch))
            TokenSearch = string.Empty;
        foreach (var t in tokens) t.IsFlashing = false;
        await Task.Delay(30);
        foreach (var t in tokens) t.IsFlashing = true;
        await Task.Delay(1800);
        foreach (var t in tokens) t.IsFlashing = false;
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
            CustomPreviewPath = CustomThumbnailPath,
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
            CustomThumbnailPath = state.CustomPreviewPath;

            GeneratorAccent = _tokens["NeonCyan"].Color;
            CurrentFolder = folder;
        }
        finally
        {
            _suppressChanges = false;
        }

        _undoStack.Clear();
        _redoStack.Clear();
        _lastRecordedState = null;
        _lastRecordedFingerprint = string.Empty;
        NotifyHistoryChanged();

        Refresh();
        _lastSavedFingerprint = folder != null ? ComputeSaveFingerprint(BuildState(), GeneratedXaml) : string.Empty;
        _loadedFingerprint = ComputeSaveFingerprint(BuildState(), GeneratedXaml);
        IsDirty = folder == null;
        if (state.ImportWarnings.Count > 0)
            SetStatus(string.Join(" ", state.ImportWarnings), isError: true);
    }

    private void NotifyHistoryChanged()
    {
        OnPropertyChanged(nameof(CanUndo));
        OnPropertyChanged(nameof(CanRedo));
        UndoCommand.NotifyCanExecuteChanged();
        RedoCommand.NotifyCanExecuteChanged();
    }

    private void RecordHistorySnapshot(ThemeState currentState, string currentFingerprint)
    {
        if (_isRestoringHistory) return;
        if (_lastRecordedState == null)
        {
            _lastRecordedState = currentState.Clone();
            _lastRecordedFingerprint = currentFingerprint;
            return;
        }
        if (string.Equals(currentFingerprint, _lastRecordedFingerprint, StringComparison.Ordinal))
            return;

        _undoStack.Add(_lastRecordedState);
        if (_undoStack.Count > MaxUndoSteps)
            _undoStack.RemoveAt(0);
        _redoStack.Clear();
        _lastRecordedState = currentState.Clone();
        _lastRecordedFingerprint = currentFingerprint;
        NotifyHistoryChanged();
    }

    private void ApplyHistorySnapshot(ThemeState snapshot)
    {
        _isRestoringHistory = true;
        _suppressChanges = true;
        try
        {
            var m = snapshot.Manifest;
            ThemeName = m.Name;
            ThemeId = m.Id;
            Author = m.Author;
            Version = string.IsNullOrWhiteSpace(m.Version) ? "1.0.0" : m.Version;
            Description = m.Description;
            MinAppVersion = m.MinAppVersion;

            FontFamily = snapshot.FontFamily;
            MonoFontFamily = snapshot.MonoFontFamily;

            foreach (var (key, vm) in _tokens)
            {
                if (snapshot.Tokens.TryGetValue(key, out var v))
                    vm.SetValue(v);
            }

            var s = snapshot.Shape;
            ShapeEnabled = s.Enabled;
            ShellCornerRadius = s.ShellCornerRadius;
            ShellBorderThickness = s.ShellBorderThickness;
            CardCornerRadius = s.CardCornerRadius;
            ButtonCornerRadius = s.ButtonCornerRadius;
            CompactCornerRadius = s.CompactCornerRadius;
            ShellGlow = s.ShellGlow;
            ShellGlowBlur = s.ShellGlowBlur;

            Fonts.Clear();
            foreach (var f in snapshot.Fonts)
                Fonts.Add(new FontEntry(f.FileName, f.SourcePath, FontTools.ReadFamilyName(f.SourcePath)));

            Assets.Clear();
            AssetNames.Clear();
            foreach (var a in snapshot.Assets)
            {
                Assets.Add(a);
                AssetNames.Add(a.FileName);
            }

            BackgroundImageFile = snapshot.BackgroundImage?.FileName;
            BackgroundImageOpacity = snapshot.BackgroundImage?.Opacity ?? 0.35;
            BackgroundStretch = snapshot.BackgroundImage?.Stretch ?? "UniformToFill";

            CustomResources = snapshot.CustomResources;
            CustomStyles = snapshot.CustomStyles;
            CustomThumbnailPath = snapshot.CustomPreviewPath;
            GeneratorAccent = _tokens["NeonCyan"].Color;
        }
        finally
        {
            _suppressChanges = false;
        }

        try
        {
            Refresh();
            var current = BuildState();
            _lastRecordedState = current.Clone();
            _lastRecordedFingerprint = ComputeSaveFingerprint(current, GeneratedXaml);
        }
        finally
        {
            _isRestoringHistory = false;
            NotifyHistoryChanged();
        }
    }

    [RelayCommand(CanExecute = nameof(CanUndo))]
    public void Undo()
    {
        if (_undoStack.Count == 0) return;
        var current = BuildState();
        _redoStack.Add(current.Clone());
        var previous = _undoStack[^1];
        _undoStack.RemoveAt(_undoStack.Count - 1);
        ApplyHistorySnapshot(previous);
        SetStatus("Undid last change.");
    }

    [RelayCommand(CanExecute = nameof(CanRedo))]
    public void Redo()
    {
        if (_redoStack.Count == 0) return;
        var current = BuildState();
        _undoStack.Add(current.Clone());
        var next = _redoStack[^1];
        _redoStack.RemoveAt(_redoStack.Count - 1);
        ApplyHistorySnapshot(next);
        SetStatus("Redid change.");
    }

    private static string ComputeSaveFingerprint(ThemeState state, string xaml)
    {
        var m = state.Manifest;
        string fonts = string.Join("|", state.Fonts.Select(f => $"{f.FileName}:{f.SourcePath}"));
        string assets = string.Join("|", state.Assets.Select(a => $"{a.FileName}:{a.SourcePath}"));
        return $"{m.Id}\n{m.Name}\n{m.Author}\n{m.Version}\n{m.Description}\n{m.MinAppVersion}\n{fonts}\n{assets}\n{state.CustomPreviewPath}\n---\n{xaml}";
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
                if (e.PropertyName == nameof(ThemeName)) OnPropertyChanged(nameof(CardName));
                break;
            case nameof(ThemeId):
            case nameof(Version):
            case nameof(Author):
                OnPropertyChanged(nameof(ThemeSubtitle));
                if (e.PropertyName == nameof(Version)) OnPropertyChanged(nameof(CardVersionText));
                if (e.PropertyName == nameof(Author)) OnPropertyChanged(nameof(CardAuthorText));
                break;
            case nameof(CurrentFolder):
                OnPropertyChanged(nameof(CurrentFolderDisplay));
                if (CurrentFolder != null) RememberRecentTheme(CurrentFolder);
                else LoadRecentThemes();
                break;
            case nameof(PreviewError):
                OnPropertyChanged(nameof(HasPreviewError));
                break;
            case nameof(ManifestProblems):
                OnPropertyChanged(nameof(HasManifestProblems));
                break;
            case nameof(ContrastWarning):
                OnPropertyChanged(nameof(ShowContrastOk));
                OnPropertyChanged(nameof(ShowContrastWarning));
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
        string fp = ComputeSaveFingerprint(state, xaml);
        IsDirty = !string.Equals(fp, _lastSavedFingerprint, StringComparison.Ordinal);
        RecordHistorySnapshot(state, fp);

        ManifestProblems = string.Join(Environment.NewLine, ThemeValidator.ValidateManifest(state));
        UpdateContrast();
        foreach (string name in CardBrushProperties)
            OnPropertyChanged(name);

        try
        {
            var (styles, bitmaps) = ThemeValidator.Load(xaml, rel => ResolvePreviewFile(rel));
            PreviewError = null;
            if (PreviewReady != null)
            {
                PreviewReady.Invoke(this, new PreviewReadyEventArgs(styles, bitmaps));
            }
            else
            {
                foreach (var b in bitmaps) b.Dispose();
            }
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
                          + (ContrastWarning ? "   [LOW CONTRAST: aim for >=4.5 text, >=3 muted/accent]" : "   [PASS]");
    }

    /// <summary>Shows an unexpected error in the status bar instead of crashing the app.</summary>
    public void ReportUnexpectedError(Exception ex) =>
        SetStatus($"Something went wrong (the app kept running): {ex.GetBaseException().Message}", isError: true);

    public void SetStatus(string message, bool isError = false)
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
        bool discard = await Dialogs.ConfirmAsync("Unsaved changes", "The current theme has unsaved changes. Discard them?", "Discard");
        if (discard) Recovery?.Clear(); // the changes are thrown away on purpose
        return discard;
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
                _lastSavedFingerprint = string.Empty;
                IsDirty = true;
            }
            RefreshInstalledThemes();
            SetStatus($"Deleted '{theme.Name}'. In the overlay click CONFIG -> Reload.");
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
            string? folder = null;
            if (Directory.Exists(path))
            {
                folder = path;
            }
            else if (Path.GetFileName(path).Equals("theme.json", StringComparison.OrdinalIgnoreCase))
            {
                folder = Path.GetDirectoryName(path);
            }
            else if (Path.GetExtension(path) is var ext
                     && (ext.Equals(".axaml", StringComparison.OrdinalIgnoreCase) || ext.Equals(".xaml", StringComparison.OrdinalIgnoreCase)))
            {
                string? dir = Path.GetDirectoryName(path);
                if (!string.IsNullOrEmpty(dir) && File.Exists(Path.Combine(dir, "theme.json")))
                    folder = dir;
            }
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
            OnPropertyChanged(nameof(DefaultAuthorHint));
        }
    }

    private void MarkSaved(string folder)
    {
        Recovery?.Clear(); // saved: nothing left to recover
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
        _lastSavedFingerprint = ComputeSaveFingerprint(BuildState(), GeneratedXaml);
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
            var warnings = ThemeExporter.WriteFolder(state, GeneratedXaml, folder, RenderThumbnail());
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
            var warnings = ThemeExporter.WriteZip(state, GeneratedXaml, path, RenderThumbnail());
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
            var warnings = ThemeExporter.WriteFolder(state, GeneratedXaml, target, RenderThumbnail());
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

    /// <summary>preview.png for saved/exported themes; a failed render never blocks saving.</summary>
    private byte[]? RenderThumbnail()
    {
        try
        {
            if (CustomThumbnailPath != null && File.Exists(CustomThumbnailPath))
                return File.ReadAllBytes(CustomThumbnailPath);
            return Dialogs?.RenderThumbnailPng();
        }
        catch
        {
            return null;
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
        AddFontFiles(files);
    }

    public int AddFontFiles(IEnumerable<string> files)
    {
        FontEntry? last = null;
        int count = 0;
        foreach (var file in files)
        {
            if (string.IsNullOrWhiteSpace(file) || !File.Exists(file)) continue;
            string name = SafeFileName(file);
            var existing = Fonts.FirstOrDefault(f => f.FileName.Equals(name, StringComparison.OrdinalIgnoreCase));
            if (existing != null) Fonts.Remove(existing);
            last = new FontEntry(name, file, FontTools.ReadFamilyName(file));
            Fonts.Add(last);
            count++;
        }
        if (last != null)
        {
            SetStatus(count == 1
                ? $"Added font {last.FileName}. Click 'Use as main' to apply it."
                : $"Added {count} fonts.");
            OnEdited();
        }
        return count;
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
        AddImageFiles(files, setAsBackground);
    }

    public int AddImageFiles(IEnumerable<string> files, bool setAsBackground = false)
    {
        string? lastName = null;
        int count = 0;
        foreach (var file in files)
        {
            if (string.IsNullOrWhiteSpace(file) || !File.Exists(file)) continue;
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
            count++;
        }
        if (lastName == null) return 0;

        if (setAsBackground)
        {
            // Re-select so the preview reloads even if the name did not change.
            BackgroundImageFile = null;
            BackgroundImageFile = lastName;
            SetStatus($"Background image set to assets/{lastName}.");
        }
        else
        {
            SetStatus($"Added {count} image(s). Reference them in custom styles as Source=\"assets/{lastName}\".");
        }
        OnEdited();
        return count;
    }

    /// <summary>Handles files or folders dropped onto the window.</summary>
    public async Task HandleDroppedPathsAsync(IReadOnlyList<string> paths)
    {
        if (paths.Count == 0) return;

        var fontExts = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { ".ttf", ".otf", ".ttc" };
        var imgExts = new HashSet<string>(ThemeImporter.ImageExtensions, StringComparer.OrdinalIgnoreCase);

        // 1. Theme pack / folder / theme.json / .axaml -> open theme
        string? themePath = paths.FirstOrDefault(p =>
            Directory.Exists(p)
            || Path.GetFileName(p).Equals("theme.json", StringComparison.OrdinalIgnoreCase)
            || Path.GetExtension(p).Equals(".zip", StringComparison.OrdinalIgnoreCase)
            || Path.GetExtension(p).Equals(".axaml", StringComparison.OrdinalIgnoreCase)
            || Path.GetExtension(p).Equals(".xaml", StringComparison.OrdinalIgnoreCase));
        if (themePath != null)
        {
            if (!await ConfirmDiscardAsync()) return;
            OpenPath(themePath);
            return;
        }

        // 2. Fonts & images -> attach to current theme
        var fonts = paths.Where(p => File.Exists(p) && fontExts.Contains(Path.GetExtension(p))).ToList();
        var images = paths.Where(p => File.Exists(p) && imgExts.Contains(Path.GetExtension(p))).ToList();

        int addedFonts = fonts.Count > 0 ? AddFontFiles(fonts) : 0;
        int addedImages = images.Count > 0 ? AddImageFiles(images, setAsBackground: false) : 0;

        if (addedFonts == 0 && addedImages == 0)
        {
            SetStatus("Dropped file type is not supported. Drop a theme (.zip, .axaml, folder), font (.ttf/.otf/.ttc), or image.", isError: true);
        }
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

    [RelayCommand]
    public async Task CheckUpdatesAsync() => await RunUpdateCheckAsync(isManual: true);

    public async Task RunUpdateCheckAsync(bool isManual = false, CancellationToken ct = default)
    {
        if (IsCheckingUpdates)
            return;

        IsCheckingUpdates = true;
        try
        {
            if (!isManual)
                await Task.Delay(1500, ct);

            UpdateStatusText = "Checking for latest release...";
            string skipped = isManual ? string.Empty : CreatorSettings.Current.SkippedVersion;
            var info = await UpdateService.CheckForUpdatesAsync(AppVersion, skipped, ct);

            if (info.IsAvailable)
            {
                UpdateStatusText = $"Update available: v{info.Version}";
                SetStatus($"Update v{info.Version} is available.");
                RequestShowUpdate?.Invoke(info);
            }
            else
            {
                UpdateStatusText = $"Up to date (v{AppVersion})";
                if (isManual)
                    SetStatus($"RBWR Theme Creator is up to date (v{AppVersion}).");
            }
        }
        catch (OperationCanceledException)
        {
            // Cancelled
        }
        finally
        {
            IsCheckingUpdates = false;
        }
    }

    public void SkipVersion(string version)
    {
        CreatorSettings.Current.SkippedVersion = version;
        CreatorSettings.Current.Save();
        OnPropertyChanged(nameof(HasSkippedVersion));
        OnPropertyChanged(nameof(SkippedVersionText));
        UpdateStatusText = $"Version v{version} skipped.";
        SetStatus($"Skipped update v{version}.");
    }
}
