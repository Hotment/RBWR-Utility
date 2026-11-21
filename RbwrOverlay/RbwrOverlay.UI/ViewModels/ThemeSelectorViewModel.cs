using System.Collections.ObjectModel;
using System.Diagnostics;
using Avalonia;
using Avalonia.Media;
using Avalonia.Media.Imaging;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using RbwrOverlay.Core.Models;
using RbwrOverlay.UI.Services;

namespace RbwrOverlay.UI.ViewModels;

public partial class ThemeEntryViewModel : ObservableObject
{
    private readonly ThemeSelectorViewModel _owner;

    public InstalledThemeInfo Info { get; }
    public string Id => Info.Id;
    public string Name => Info.Name;
    public string VersionText => string.IsNullOrWhiteSpace(Info.Version) ? "v1.0.0" : (Info.Version.StartsWith('v') ? Info.Version : $"v{Info.Version}");
    public string AuthorText => string.IsNullOrWhiteSpace(Info.Author) ? "Unknown Author" : $"by {Info.Author}";
    public string DescriptionText => string.IsNullOrWhiteSpace(Info.Description) ? "No description provided." : Info.Description;
    public string MinAppVersionText => string.IsNullOrWhiteSpace(Info.Manifest?.MinAppVersion) ? "Any" : Info.Manifest!.MinAppVersion;
    public bool IsVersionWarning => !ThemeService.IsCompatibleWithAppVersion(Info.Manifest?.MinAppVersion, MainOverlayViewModel.AppVersion);
    public string VersionWarningText => IsVersionWarning ? $"REQUIRES v{Info.Manifest!.MinAppVersion.Trim().TrimStart('v', 'V')}+" : string.Empty;
    public string LocationText => Info.IsBuiltIn ? "Built-in application resource" : Info.DirectoryPath;
    public bool IsBuiltIn => Info.IsBuiltIn;
    public bool CanManageFiles => !Info.IsBuiltIn;

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(ApplyButtonText))]
    [NotifyPropertyChangedFor(nameof(BadgeText))]
    private bool _isActive;

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(ExpandButtonText))]
    private bool _isExpanded;

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(DeleteButtonText))]
    private bool _isConfirmingDelete;

    public string ApplyButtonText => IsActive ? "Active" : "Apply";
    public string BadgeText => IsActive ? "ACTIVE" : (IsBuiltIn ? "BUILT-IN" : "CUSTOM");
    public string ExpandButtonText => IsExpanded ? "Hide" : "Details";
    public string DeleteButtonText => IsConfirmingDelete ? "Confirm?" : "Delete";

    // ---------- Thumbnail: preview.png of the theme (null = no thumbnail) ----------
    public Bitmap? Thumbnail { get; }
    public bool HasThumbnail => Thumbnail != null;

    public ThemeEntryViewModel(InstalledThemeInfo info, bool isActive, bool isExpanded, ThemeSelectorViewModel owner)
    {
        Info = info;
        _isActive = isActive;
        _isExpanded = isExpanded;
        _owner = owner;

        Thumbnail = ThemeThumbnailService.Get(info);
    }

    partial void OnIsExpandedChanged(bool value)
    {
        if (!value)
            IsConfirmingDelete = false;
    }

    [RelayCommand]
    public void ToggleExpand() => IsExpanded = !IsExpanded;

    [RelayCommand]
    public void Apply() => _owner.ApplyEntry(this);

    [RelayCommand]
    public void ReloadEntry() => _owner.ReloadEntry(this);

    [RelayCommand]
    public void OpenEntryFolder() => _owner.OpenEntryFolder(this);

    [RelayCommand]
    public void EditAxaml() => _owner.EditEntryAxaml(this);

    [RelayCommand]
    public void Delete() => _owner.DeleteEntry(this);
}

public partial class ThemeSelectorViewModel : ViewModelBase, IDisposable
{
    private readonly IThemeService _themeService;
    private readonly Func<string, ThemeApplyResult> _applyThemeCallback;
    private readonly Func<string, (bool Success, string? ErrorMessage)> _installPathCallback;
    private readonly Action _reloadCallback;
    private readonly Action _refreshListCallback;
    private readonly Func<(bool Success, string? ErrorMessage)> _createTemplateCallback;
    private readonly Action _openFolderCallback;
    private readonly HashSet<string> _expandedIds = new(StringComparer.OrdinalIgnoreCase);
    private bool _suppressExternalThemeRefresh;
    private bool _disposed;

    public ObservableCollection<ThemeEntryViewModel> FilteredThemes { get; } = new();

    [ObservableProperty]
    private string _searchQuery = string.Empty;

    [ObservableProperty]
    private string _themeCountText = "1 theme";

    [ObservableProperty]
    private string _statusMessage = string.Empty;

    [ObservableProperty]
    private bool _hasStatusMessage;

    [ObservableProperty]
    private IBrush _statusBrush = ThemeService.ResolveBrush("NeonCyan", "#00f0ff");

    public event EventHandler? RequestClose;
    public event Action? RequestInstallPicker;

    public ThemeSelectorViewModel(
        IThemeService themeService,
        Func<string, ThemeApplyResult> applyThemeCallback,
        Func<string, (bool Success, string? ErrorMessage)> installPathCallback,
        Action reloadCallback,
        Action refreshListCallback,
        Func<(bool Success, string? ErrorMessage)> createTemplateCallback,
        Action openFolderCallback)
    {
        _themeService = themeService;
        _applyThemeCallback = applyThemeCallback;
        _installPathCallback = installPathCallback;
        _reloadCallback = reloadCallback;
        _refreshListCallback = refreshListCallback;
        _createTemplateCallback = createTemplateCallback;
        _openFolderCallback = openFolderCallback;

        _themeService.ThemeChanged += OnExternalThemeChanged;
        Refresh();
    }

    private void OnExternalThemeChanged(object? sender, string themeId)
    {
        if (_suppressExternalThemeRefresh || _disposed) return;

        if (Application.Current != null && !Dispatcher.UIThread.CheckAccess())
        {
            Dispatcher.UIThread.Post(() =>
            {
                if (!_disposed) Refresh();
            });
        }
        else
        {
            Refresh();
        }
    }

    partial void OnSearchQueryChanged(string value) => Refresh();

    public void Refresh()
    {
        foreach (var existing in FilteredThemes)
        {
            if (existing.IsExpanded) _expandedIds.Add(existing.Id);
            else _expandedIds.Remove(existing.Id);
        }

        var all = _themeService.DiscoverThemes();
        string q = SearchQuery.Trim();
        var matches = string.IsNullOrEmpty(q)
            ? all
            : all.Where(t =>
                t.Name.Contains(q, StringComparison.OrdinalIgnoreCase)
                || t.Id.Contains(q, StringComparison.OrdinalIgnoreCase)
                || t.Author.Contains(q, StringComparison.OrdinalIgnoreCase)
                || t.Description.Contains(q, StringComparison.OrdinalIgnoreCase)).ToList();

        FilteredThemes.Clear();
        foreach (var t in matches)
        {
            bool isActive = string.Equals(t.Id, _themeService.ActiveThemeId, StringComparison.OrdinalIgnoreCase);
            bool isExpanded = _expandedIds.Contains(t.Id);
            FilteredThemes.Add(new ThemeEntryViewModel(t, isActive, isExpanded, this));
        }

        ThemeCountText = $"{matches.Count} / {all.Count} theme{(all.Count == 1 ? "" : "s")}";
    }

    internal void ApplyEntry(ThemeEntryViewModel entry)
    {
        _suppressExternalThemeRefresh = true;
        ThemeApplyResult res;
        try
        {
            res = _applyThemeCallback(entry.Id);
        }
        finally
        {
            _suppressExternalThemeRefresh = false;
        }
        Refresh();
        if (res.Success)
        {
            if (entry.IsVersionWarning)
                SetStatus($"Applied '{entry.Name}' (targets v{entry.MinAppVersionText}+; current is v{MainOverlayViewModel.AppVersion}).", isError: false, isWarning: true);
            else
                SetStatus($"Applied theme '{entry.Name}'.", isError: false);
        }
        else
        {
            SetStatus($"Failed to apply '{entry.Name}': {res.ErrorMessage}", isError: true);
        }
    }

    internal void ReloadEntry(ThemeEntryViewModel entry)
    {
        if (entry.IsActive)
        {
            _suppressExternalThemeRefresh = true;
            try
            {
                _reloadCallback();
            }
            finally
            {
                _suppressExternalThemeRefresh = false;
            }
            Refresh();
            SetStatus($"Reloaded '{entry.Name}' from disk.", isError: false);
        }
        else
        {
            ApplyEntry(entry);
        }
    }

    internal void OpenEntryFolder(ThemeEntryViewModel entry)
    {
        if (entry.IsBuiltIn || string.IsNullOrWhiteSpace(entry.Info.DirectoryPath)) return;
        try
        {
            Process.Start(new ProcessStartInfo(entry.Info.DirectoryPath) { UseShellExecute = true });
        }
        catch (Exception ex)
        {
            SetStatus($"Could not open folder: {ex.Message}", isError: true);
        }
    }

    internal void EditEntryAxaml(ThemeEntryViewModel entry)
    {
        if (entry.IsBuiltIn || string.IsNullOrWhiteSpace(entry.Info.EntryFilePath)) return;
        try
        {
            Process.Start(new ProcessStartInfo(entry.Info.EntryFilePath) { UseShellExecute = true });
        }
        catch (Exception ex)
        {
            SetStatus($"Could not open AXAML file: {ex.Message}", isError: true);
        }
    }

    internal void DeleteEntry(ThemeEntryViewModel entry)
    {
        if (entry.IsBuiltIn) return;

        if (!entry.IsConfirmingDelete)
        {
            foreach (var other in FilteredThemes)
            {
                if (!ReferenceEquals(other, entry))
                    other.IsConfirmingDelete = false;
            }
            entry.IsConfirmingDelete = true;
            SetStatus($"Click 'Confirm?' again to permanently delete '{entry.Name}'.", isError: false, isWarning: true);
            return;
        }

        bool wasActive = entry.IsActive;
        _suppressExternalThemeRefresh = true;
        (bool ok, string? err) result;
        try
        {
            result = _themeService.DeleteTheme(entry.Id);
            if (!result.ok)
            {
                entry.IsConfirmingDelete = false;
                SetStatus($"Delete failed: {result.err}", isError: true);
                return;
            }

            if (wasActive)
            {
                _applyThemeCallback(ThemeService.DefaultThemeId);
            }
            else
            {
                _refreshListCallback();
            }
        }
        finally
        {
            _suppressExternalThemeRefresh = false;
        }

        _expandedIds.Remove(entry.Id);
        Refresh();
        SetStatus($"Deleted theme '{entry.Name}'.", isError: false);
    }

    [RelayCommand]
    public void InstallTheme() => RequestInstallPicker?.Invoke();

    public void InstallThemeFromPath(string sourcePath)
    {
        _suppressExternalThemeRefresh = true;
        (bool ok, string? err) res;
        try
        {
            res = _installPathCallback(sourcePath);
        }
        finally
        {
            _suppressExternalThemeRefresh = false;
        }
        Refresh();
        if (res.ok)
            SetStatus("Theme installed and applied.", isError: false);
        else
            SetStatus($"Install failed: {res.err}", isError: true);
    }

    [RelayCommand]
    public void ReloadAll()
    {
        _suppressExternalThemeRefresh = true;
        try
        {
            _reloadCallback();
        }
        finally
        {
            _suppressExternalThemeRefresh = false;
        }
        Refresh();
        SetStatus("Reloaded themes from disk.", isError: false);
    }

    [RelayCommand]
    public void CreateTemplate()
    {
        _suppressExternalThemeRefresh = true;
        (bool ok, string? err) res;
        try
        {
            res = _createTemplateCallback();
        }
        finally
        {
            _suppressExternalThemeRefresh = false;
        }
        Refresh();
        if (res.ok)
            SetStatus("Created and applied template theme.", isError: false);
        else
            SetStatus($"Template creation failed: {res.err}", isError: true);
    }

    [RelayCommand]
    public void OpenThemesFolder() => _openFolderCallback();

    [RelayCommand]
    public void Close() => RequestClose?.Invoke(this, EventArgs.Empty);

    private void SetStatus(string msg, bool isError, bool isWarning = false)
    {
        StatusMessage = msg;
        HasStatusMessage = !string.IsNullOrWhiteSpace(msg);
        StatusBrush = isError
            ? ThemeService.ResolveBrush("NeonRed", "#ff003c")
            : isWarning
                ? ThemeService.ResolveBrush("NeonGold", "#ffaa00")
                : ThemeService.ResolveBrush("NeonGreen", "#39ff14");
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        _themeService.ThemeChanged -= OnExternalThemeChanged;
    }
}