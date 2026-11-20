using System.Collections.ObjectModel;
using Avalonia;
using Avalonia.Media;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using RbwrThemeCreator.Models;
using RbwrThemeCreator.Services;

namespace RbwrThemeCreator.ViewModels;

/// <summary>One colour of a gradient (the first one is the token's own colour).</summary>
public partial class GradientStopViewModel : ObservableObject
{
    private readonly TokenViewModel _owner;

    [ObservableProperty]
    private Color _color;

    [ObservableProperty]
    private int _number;

    [ObservableProperty]
    private bool _canRemove;

    public GradientStopViewModel(TokenViewModel owner, Color color)
    {
        _owner = owner;
        _color = color;
    }

    partial void OnColorChanged(Color value) => _owner.OnStopColorChanged(this);

    [RelayCommand]
    private void Remove() => _owner.RemoveStop(this);
}

public partial class TokenViewModel : ObservableObject
{
    public TokenDefinition Definition { get; }
    public string Key => Definition.Key;
    public string Label => Definition.Label;
    public string Hint => Definition.Hint;
    public bool SupportsOpacity => Definition.SupportsOpacity;
    public bool SupportsGradient => Definition.SupportsGradient;

    [ObservableProperty]
    private Color _color;

    [ObservableProperty]
    private double _opacity = 1.0;

    [ObservableProperty]
    private string _hexText = string.Empty;

    [ObservableProperty]
    private bool _hexInvalid;

    // ---------- Gradient ----------
    [ObservableProperty]
    private bool _isGradient;

    [ObservableProperty]
    private double _angle = 90;

    /// <summary>All gradient colours in order; Stops[0] is always the token colour.</summary>
    public ObservableCollection<GradientStopViewModel> Stops { get; } = new();

    public bool CanAddStop => Stops.Count < GradientSpec.MaxStops;
    public string StopCountText => $"{Stops.Count}/{GradientSpec.MaxStops}";

    private bool _loading;
    private bool _syncingStops;

    /// <summary>Raised whenever the colour, opacity or gradient changes (used to refresh the preview).</summary>
    public event EventHandler? ValueChanged;

    public TokenViewModel(TokenDefinition definition, TokenValue value)
    {
        Definition = definition;
        SetValue(value);
    }

    public string OpacityText => $"{Math.Round(Opacity * 100)}%";
    public string AngleText => $"{Math.Round(Angle)}°";

    /// <summary>The brush exactly as the theme will draw it (solid or gradient), for the editor preview strip.</summary>
    public IBrush PreviewBrush
    {
        get
        {
            if (!IsGradient || Stops.Count < 2)
                return new SolidColorBrush(Color);
            var g = CurrentGradient();
            var (sx, sy, ex, ey) = g.Points();
            var brush = new LinearGradientBrush
            {
                StartPoint = new RelativePoint(sx / 100, sy / 100, RelativeUnit.Relative),
                EndPoint = new RelativePoint(ex / 100, ey / 100, RelativeUnit.Relative),
            };
            foreach (var (offset, color) in g.Stops(Color))
                brush.GradientStops.Add(new GradientStop(color, offset));
            return brush;
        }
    }

    private GradientSpec CurrentGradient() => new(Stops.Skip(1).Select(st => st.Color).ToList(), Angle);

    public TokenValue ToValue() => new(
        Color,
        SupportsOpacity ? Opacity : 1.0,
        IsGradient && SupportsGradient && Stops.Count >= 2 ? CurrentGradient() : null);

    public void SetValue(TokenValue value)
    {
        _loading = true;
        try
        {
            Color = value.Color;
            Opacity = double.IsFinite(value.Opacity) ? Math.Clamp(value.Opacity, 0, 1) : 1;
            if (value.Gradient is { } g && SupportsGradient)
            {
                ReplaceStops([value.Color, .. g.SafeColors(value.Color)]);
                Angle = Math.Round(g.SafeAngle);
                IsGradient = true;
            }
            else
            {
                ReplaceStops([value.Color, DefaultEnd(value.Color)]);
                Angle = 90;
                IsGradient = false;
            }
        }
        finally
        {
            _loading = false;
        }
        Changed();
    }

    // ---------- Stop management ----------

    private void ReplaceStops(IEnumerable<Color> colors)
    {
        _syncingStops = true;
        try
        {
            Stops.Clear();
            foreach (var c in colors.Take(GradientSpec.MaxStops))
                Stops.Add(new GradientStopViewModel(this, c));
            while (Stops.Count < 2)
                Stops.Add(new GradientStopViewModel(this, DefaultEnd(Stops.Count > 0 ? Stops[^1].Color : Color)));
        }
        finally
        {
            _syncingStops = false;
        }
        RefreshStopInfo();
    }

    private void RefreshStopInfo()
    {
        for (int i = 0; i < Stops.Count; i++)
        {
            Stops[i].Number = i + 1;
            Stops[i].CanRemove = Stops.Count > 2;
        }
        OnPropertyChanged(nameof(CanAddStop));
        OnPropertyChanged(nameof(StopCountText));
    }

    internal void OnStopColorChanged(GradientStopViewModel stop)
    {
        if (_syncingStops) return;
        if (Stops.Count > 0 && ReferenceEquals(Stops[0], stop) && Color != stop.Color)
            Color = stop.Color; // the first stop is the token colour
        else
            Changed();
    }

    internal void RemoveStop(GradientStopViewModel stop)
    {
        if (Stops.Count <= 2 || !Stops.Contains(stop)) return;
        bool wasFirst = ReferenceEquals(Stops[0], stop);
        Stops.Remove(stop);
        RefreshStopInfo();
        if (wasFirst)
            Color = Stops[0].Color;
        else
            Changed();
    }

    /// <summary>Adds a colour at the end: a hue-shifted continuation of the last colour.</summary>
    [RelayCommand]
    private void AddStop()
    {
        if (!CanAddStop) return;
        var last = Stops.Count > 0 ? Stops[^1].Color : Color;
        var (h, s, l) = ColorUtil.ToHsl(last);
        _syncingStops = true;
        try
        {
            Stops.Add(new GradientStopViewModel(this, ColorUtil.FromHsl(h + 40, Math.Max(s, 0.35), Math.Clamp(l, 0.2, 0.7), last.A)));
        }
        finally
        {
            _syncingStops = false;
        }
        RefreshStopInfo();
        Changed();
    }

    [RelayCommand]
    private void SetDirection(string? degrees)
    {
        if (double.TryParse(degrees, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var d))
            Angle = d;
    }

    /// <summary>Reverses the order of all colours.</summary>
    [RelayCommand]
    private void Swap()
    {
        var reversed = Stops.Select(st => st.Color).Reverse().ToList();
        _loading = true;
        try
        {
            ReplaceStops(reversed);
            Color = reversed[0];
        }
        finally
        {
            _loading = false;
        }
        Changed();
    }

    /// <summary>Quick look: a subtle two-colour fade from the first colour to a darker/lighter shade of itself.</summary>
    [RelayCommand]
    private void SoftFade()
    {
        ReplaceStops([Color, DefaultEnd(Color)]);
        Changed();
    }

    private static Color DefaultEnd(Color c)
    {
        var (h, s, l) = ColorUtil.ToHsl(c);
        // Dark colours fade lighter, bright colours fade darker; hue shifts slightly for a livelier look.
        double target = l < 0.5 ? Math.Min(l + 0.12, 1) : Math.Max(l - 0.22, 0);
        return ColorUtil.FromHsl(h + 18, s, target, c.A);
    }

    private void Changed()
    {
        OnPropertyChanged(nameof(PreviewBrush));
        if (!_loading)
            ValueChanged?.Invoke(this, EventArgs.Empty);
    }

    // ---------- Property hooks ----------

    partial void OnColorChanged(Color value)
    {
        string hex = ColorUtil.ToHex(value);
        if (!string.Equals(hex, HexText, StringComparison.OrdinalIgnoreCase))
            HexText = hex;
        if (Stops.Count > 0 && Stops[0].Color != value)
        {
            _syncingStops = true;
            try { Stops[0].Color = value; }
            finally { _syncingStops = false; }
        }
        Changed();
    }

    partial void OnOpacityChanged(double value)
    {
        if (!double.IsFinite(value) || value < 0 || value > 1)
        {
            Opacity = double.IsFinite(value) ? Math.Clamp(value, 0, 1) : 1;
            return;
        }
        OnPropertyChanged(nameof(OpacityText));
        Changed();
    }

    partial void OnIsGradientChanged(bool value)
    {
        if (value && !SupportsGradient)
        {
            IsGradient = false;
            return;
        }
        Changed();
    }

    partial void OnAngleChanged(double value)
    {
        double safe = double.IsFinite(value) ? ((value % 360) + 360) % 360 : 90;
        if (Math.Abs(safe - value) > 1e-9)
        {
            Angle = safe;
            return;
        }
        OnPropertyChanged(nameof(AngleText));
        Changed();
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
