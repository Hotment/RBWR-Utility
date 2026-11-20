using Avalonia;
using Avalonia.Media;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
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
    private Color _endColor;

    [ObservableProperty]
    private bool _hasMid;

    [ObservableProperty]
    private Color _midColor;

    [ObservableProperty]
    private double _angle = 90;

    private bool _loading;

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
            if (!IsGradient)
                return new SolidColorBrush(Color);
            var g = new GradientSpec(EndColor, HasMid ? MidColor : null, Angle);
            var (sx, sy, ex, ey) = g.Points();
            var brush = new LinearGradientBrush
            {
                StartPoint = new RelativePoint(sx / 100, sy / 100, RelativeUnit.Relative),
                EndPoint = new RelativePoint(ex / 100, ey / 100, RelativeUnit.Relative),
            };
            brush.GradientStops.Add(new GradientStop(Color, 0));
            if (HasMid) brush.GradientStops.Add(new GradientStop(MidColor, 0.5));
            brush.GradientStops.Add(new GradientStop(EndColor, 1));
            return brush;
        }
    }

    public TokenValue ToValue() => new(
        Color,
        SupportsOpacity ? Opacity : 1.0,
        IsGradient && SupportsGradient ? new GradientSpec(EndColor, HasMid ? MidColor : null, Angle) : null);

    public void SetValue(TokenValue value)
    {
        _loading = true;
        try
        {
            Color = value.Color;
            Opacity = double.IsFinite(value.Opacity) ? Math.Clamp(value.Opacity, 0, 1) : 1;
            if (value.Gradient is { } g && SupportsGradient)
            {
                EndColor = g.End;
                HasMid = g.Mid != null;
                MidColor = g.Mid ?? Blend(value.Color, g.End);
                Angle = Math.Round(g.SafeAngle);
                IsGradient = true;
            }
            else
            {
                IsGradient = false;
                EndColor = DefaultEnd(value.Color);
                MidColor = Blend(value.Color, EndColor);
                HasMid = false;
                Angle = 90;
            }
        }
        finally
        {
            _loading = false;
        }
        Changed();
    }

    // ---------- Commands ----------

    [RelayCommand]
    private void SetDirection(string? degrees)
    {
        if (double.TryParse(degrees, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var d))
            Angle = d;
    }

    [RelayCommand]
    private void Swap()
    {
        _loading = true;
        try
        {
            (Color, EndColor) = (EndColor, Color);
        }
        finally
        {
            _loading = false;
        }
        Changed();
    }

    /// <summary>Quick look: a subtle fade from the colour to a darker/lighter shade of itself.</summary>
    [RelayCommand]
    private void SoftFade()
    {
        EndColor = DefaultEnd(Color);
        HasMid = false;
    }

    private static Color DefaultEnd(Color c)
    {
        var (h, s, l) = ColorUtil.ToHsl(c);
        // Dark colours fade lighter, bright colours fade darker; hue shifts slightly for a livelier look.
        double target = l < 0.5 ? Math.Min(l + 0.12, 1) : Math.Max(l - 0.22, 0);
        return ColorUtil.FromHsl(h + 18, s, target, c.A);
    }

    private static Color Blend(Color a, Color b) => Color.FromArgb(
        (byte)((a.A + b.A) / 2), (byte)((a.R + b.R) / 2), (byte)((a.G + b.G) / 2), (byte)((a.B + b.B) / 2));

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

    partial void OnEndColorChanged(Color value) => Changed();
    partial void OnMidColorChanged(Color value) => Changed();
    partial void OnHasMidChanged(bool value) => Changed();

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
