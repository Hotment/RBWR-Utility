using Avalonia.Media;
using CommunityToolkit.Mvvm.ComponentModel;
using RbwrThemeCreator.Models;
using RbwrThemeCreator.Services;

namespace RbwrThemeCreator.ViewModels;

public partial class TokenViewModel : ObservableObject
{
    public TokenDefinition Definition { get; }
    public string Key => Definition.Key;
    public string Label => Definition.Label;
    public string Hint => Definition.Hint;
    public bool SupportsOpacity => Definition.SupportsOpacity;

    [ObservableProperty]
    private Color _color;

    [ObservableProperty]
    private double _opacity = 1.0;

    [ObservableProperty]
    private string _hexText = string.Empty;

    [ObservableProperty]
    private bool _hexInvalid;

    /// <summary>Raised whenever the colour or opacity changes (used to refresh the preview).</summary>
    public event EventHandler? ValueChanged;

    public TokenViewModel(TokenDefinition definition, TokenValue value)
    {
        Definition = definition;
        SetValue(value);
    }

    public string OpacityText => $"{Math.Round(Opacity * 100)}%";

    public TokenValue ToValue() => new(Color, SupportsOpacity ? Opacity : 1.0);

    public void SetValue(TokenValue value)
    {
        Color = value.Color;
        Opacity = value.Opacity;
    }

    partial void OnColorChanged(Color value)
    {
        string hex = ColorUtil.ToHex(value);
        if (!string.Equals(hex, HexText, StringComparison.OrdinalIgnoreCase))
            HexText = hex;
        ValueChanged?.Invoke(this, EventArgs.Empty);
    }

    partial void OnOpacityChanged(double value)
    {
        OnPropertyChanged(nameof(OpacityText));
        ValueChanged?.Invoke(this, EventArgs.Empty);
    }

    partial void OnHexTextChanged(string value)
    {
        if (ColorUtil.TryParse(value, out var parsed))
        {
            HexInvalid = false;
            if (parsed != Color)
                Color = parsed;
        }
        else
        {
            HexInvalid = true;
        }
    }
}

public sealed class TokenGroupViewModel
{
    public string Name { get; }
    public string Description { get; }
    public IReadOnlyList<TokenViewModel> Tokens { get; }

    public TokenGroupViewModel(string name, string description, IReadOnlyList<TokenViewModel> tokens)
    {
        Name = name;
        Description = description;
        Tokens = tokens;
    }
}

public sealed record FontEntry(string FileName, string SourcePath, string FamilyName)
{
    public string Display => string.IsNullOrEmpty(FamilyName) ? FileName : $"{FileName}  ·  {FamilyName}";
}

public sealed record InstalledThemeEntry(string Id, string Name, string Directory)
{
    public override string ToString() => $"{Name}  ({Id})";
}
