using Avalonia.Media;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace RbwrThemeCreator.ViewModels;

/// <summary>One colour of an animated colour (ANIMATED on a colour row).</summary>
public sealed partial class AnimationColourViewModel : ObservableObject
{
    private readonly Action _changed;
    private readonly Action<AnimationColourViewModel> _remove;

    [ObservableProperty]
    private Color _color;

    [ObservableProperty]
    private bool _canRemove;

    /// <summary>1-based position shown on the chip.</summary>
    [ObservableProperty]
    private int _number;

    public AnimationColourViewModel(Action changed, Action<AnimationColourViewModel> remove, Color color)
    {
        _changed = changed;
        _remove = remove;
        _color = color;
    }

    partial void OnColorChanged(Color value) => _changed();

    [RelayCommand]
    private void Remove() => _remove(this);
}
