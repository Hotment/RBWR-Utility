using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using RbwrThemeCreator.Services;

namespace RbwrThemeCreator.ViewModels;

/// <summary>One row in SETTINGS → Keyboard shortcuts.</summary>
public sealed partial class ShortcutEntryViewModel : ObservableObject
{
    private readonly MainViewModel _owner;

    public ShortcutDefinition Definition { get; }
    public string Id => Definition.Id;
    public string Label => Definition.Label;
    public string Group => Definition.Group;
    public string DefaultText => string.IsNullOrEmpty(Definition.DefaultGesture) ? "none" : Definition.DefaultGesture;

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(ButtonText))]
    private bool _isRecording;

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(ButtonText))]
    private string _gestureText = string.Empty;

    [ObservableProperty]
    private bool _isCustom;

    public string ButtonText => IsRecording ? "Press keys…" : (string.IsNullOrEmpty(GestureText) ? "—" : GestureText);

    public ShortcutEntryViewModel(ShortcutDefinition definition, MainViewModel owner)
    {
        Definition = definition;
        _owner = owner;
    }

    /// <summary>Re-reads the current gesture from the shortcut map.</summary>
    public void Refresh(ShortcutMap map)
    {
        GestureText = map.Get(Id)?.ToString() ?? string.Empty;
        IsCustom = map.IsCustom(Id);
    }

    [RelayCommand]
    private void Record() => _owner.StartRecordingShortcut(this);

    [RelayCommand]
    private void ResetToDefault() => _owner.ResetShortcut(this);
}
