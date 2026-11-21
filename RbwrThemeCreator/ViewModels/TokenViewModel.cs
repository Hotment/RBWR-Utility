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

    /// <summary>Where this colour sits along the gradient, 0..100 %.</summary>
    [ObservableProperty]
    private double _position;

    public string PositionText => $"{Math.Round(Position)}%";

    /// <summary>Typed position in %, e.g. "30" or "30%". Bad input is ignored and the box shows the real value again.</summary>
    public string PositionInput
    {
        get => ColorUtil.FormatNumber(Position);
        set
        {
            if (ColorUtil.TryParseUserNumber(value, out var v))
                Position = Math.Clamp(v, 0, 100);
            // Re-notify after the binding finished writing, so rejected text is replaced by the real value.
            Avalonia.Threading.Dispatcher.UIThread.Post(() => OnPropertyChanged(nameof(PositionInput)));
        }
    }

    internal bool Silent;

    public GradientStopViewModel(TokenViewModel owner, Color color, double position)
    {
        _owner = owner;
        _color = color;
        _position = position;
    }

    partial void OnColorChanged(Color value) => _owner.OnStopColorChanged(this);

    partial void OnPositionChanged(double value)
    {
        OnPropertyChanged(nameof(PositionText));
        OnPropertyChanged(nameof(PositionInput));
        if (!Silent)
            _owner.OnStopPositionChanged(this);
    }

    /// <summary>Sets the position without notifying the owner (used while the owner rearranges stops).</summary>
    internal void SetPositionSilently(double value)
    {
        Silent = true;
        try { Position = value; }
        finally { Silent = false; }
    }

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

    /// <summary>ANIMATE is offered only where the overlay's styles use this colour (else it would do nothing).</summary>
    public bool SupportsAnimation => SupportsGradient && TokenUsages.For(Key).Count > 0;
    public string GroupName => Definition.Group;

    /// <summary>False when the row is hidden by the COLOURS search box.</summary>
    [ObservableProperty]
    private bool _isMatch = true;

    /// <summary>Briefly true after the token is picked by clicking its element in the preview.</summary>
    [ObservableProperty]
    private bool _isFlashing;

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

    // ---------- Animation (ANIMATE on the row) ----------
    [ObservableProperty]
    private bool _isAnimated;

    /// <summary>0 = all at once, 1 = flow (one after another).</summary>
    [ObservableProperty]
    private int _animMode;

    [ObservableProperty]
    private double _animSeconds = 6;

    /// <summary>Flow direction in degrees (same meaning as the gradient angle).</summary>
    [ObservableProperty]
    private double _animAngle;

    public ObservableCollection<AnimationColourViewModel> AnimColours { get; } = new();
    public bool CanAddAnimColour => AnimColours.Count < TokenAnimation.MaxColors;
    public string AnimSecondsText => $"{Math.Round(AnimSeconds)} s";
    public string AnimStopCountText => $"{AnimColours.Count}/{TokenAnimation.MaxColors}";
    public bool IsFlow => AnimMode == 1;

    /// <summary>The animation as it is now (drives the live strip in the ANIMATE panel).</summary>
    public TokenAnimation? AnimPreview => IsAnimated && AnimColours.Count >= 2
        ? new TokenAnimation(AnimColours.Select(a => a.Color).ToList(), AnimMode == 1, Math.Round(AnimSeconds), AnimAngle)
        : null;

    // ---------- Fold the GRADIENT / ANIMATED editor of the row ----------
    /// <summary>Whether the gradient / animation editor is unfolded. Folded rows show a small live strip instead.</summary>
    [ObservableProperty]
    private bool _isEditorOpen;

    public bool HasEditor => IsGradient || IsAnimated;
    public bool ShowGradientEditor => IsGradient && IsEditorOpen;
    public bool ShowAnimEditor => IsAnimated && IsEditorOpen;
    public bool ShowGradientMini => IsGradient && !IsEditorOpen;
    public bool ShowAnimMini => IsAnimated && !IsEditorOpen;
    public string EditorGlyph => IsEditorOpen ? "▾" : "▸";
    public string EditorToggleTip => IsEditorOpen ? "Fold the settings" : "Show the settings";

    [CommunityToolkit.Mvvm.Input.RelayCommand]
    private void ToggleEditor() => IsEditorOpen = !IsEditorOpen;

    partial void OnIsEditorOpenChanged(bool value) => NotifyEditor();

    private void NotifyEditor()
    {
        foreach (string name in new[] { nameof(HasEditor), nameof(ShowGradientEditor), nameof(ShowAnimEditor),
                     nameof(ShowGradientMini), nameof(ShowAnimMini), nameof(EditorGlyph), nameof(EditorToggleTip) })
            OnPropertyChanged(name);
    }

    /// <summary>SOLID / GRADIENT / ANIMATED switch on the row (0 / 1 / 2).</summary>
    public int FillMode
    {
        get => IsAnimated ? 2 : IsGradient ? 1 : 0;
        set
        {
            if (value == FillMode) return;
            IsGradient = value == 1;
            IsAnimated = value == 2;
            OnPropertyChanged();
        }
    }

    /// <summary>Typed loop time in seconds (1..20).</summary>
    public string AnimSecondsInput
    {
        get => ColorUtil.FormatNumber(Math.Round(AnimSeconds));
        set
        {
            if (ColorUtil.TryParseUserNumber(value, out var v))
                AnimSeconds = Math.Clamp(Math.Round(v), 1, 20);
            Avalonia.Threading.Dispatcher.UIThread.Post(() => OnPropertyChanged(nameof(AnimSecondsInput)));
        }
    }

    /// <summary>Typed flow direction in degrees.</summary>
    public string AnimAngleInput
    {
        get => ColorUtil.FormatNumber(Math.Round(AnimAngle));
        set
        {
            if (ColorUtil.TryParseUserNumber(value, out var v) && double.IsFinite(v))
                AnimAngle = ((Math.Round(v) % 360) + 360) % 360;
            Avalonia.Threading.Dispatcher.UIThread.Post(() => OnPropertyChanged(nameof(AnimAngleInput)));
        }
    }

    partial void OnAnimAngleChanged(double value)
    {
        OnPropertyChanged(nameof(AnimAngleInput));
        Changed();
    }

    [CommunityToolkit.Mvvm.Input.RelayCommand]
    private void SetAnimDirection(string? degrees)
    {
        if (double.TryParse(degrees, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var d))
            AnimAngle = d;
    }

    /// <summary>REVERSE: the colours in the opposite order.</summary>
    [CommunityToolkit.Mvvm.Input.RelayCommand]
    private void ReverseAnimColours() => SetAnimColours(AnimColours.Select(a => a.Color).Reverse().ToList());

    /// <summary>SHIFT: every colour moves one place (the last one becomes the first).</summary>
    [CommunityToolkit.Mvvm.Input.RelayCommand]
    private void ShiftAnimColours()
    {
        var list = AnimColours.Select(a => a.Color).ToList();
        if (list.Count < 2) return;
        SetAnimColours([list[^1], .. list.Take(list.Count - 1)]);
    }

    /// <summary>RANDOM: fresh colours that go well together (evenly spaced hues around a random start).</summary>
    [CommunityToolkit.Mvvm.Input.RelayCommand]
    private void RandomAnimColours()
    {
        int n = Math.Max(2, AnimColours.Count);
        double start = Random.Shared.NextDouble() * 360;
        SetAnimColours(Enumerable.Range(0, n).Select(i => ColorUtil.FromHsl(start + i * 360.0 / n, 0.85, 0.55, 255)).ToList());
    }

    private void SetAnimColours(IReadOnlyList<Color> colours)
    {
        ResetAnimColours(colours);
        Changed();
    }

    partial void OnIsAnimatedChanged(bool value)
    {
        if (value && !SupportsAnimation)
        {
            IsAnimated = false;
            return;
        }
        if (value && AnimColours.Count < 2 && !_loading)
            ResetAnimColours([Color, AnimPartner(Color)]);
        // An animation already has its own colours: GRADIENT and ANIMATE are one or the other.
        if (value && IsGradient)
            IsGradient = false;
        if (value && !_loading)
            IsEditorOpen = true;
        OnPropertyChanged(nameof(FillMode));
        NotifyEditor();
        Changed();
    }

    partial void OnAnimModeChanged(int value)
    {
        OnPropertyChanged(nameof(IsFlow));
        Changed();
    }

    partial void OnAnimSecondsChanged(double value)
    {
        OnPropertyChanged(nameof(AnimSecondsText));
        OnPropertyChanged(nameof(AnimSecondsInput));
        Changed();
    }

    [CommunityToolkit.Mvvm.Input.RelayCommand]
    private void AddAnimColour()
    {
        if (AnimColours.Count >= TokenAnimation.MaxColors) return;
        AnimColours.Add(NewAnimColour(AnimPartner(AnimColours.Count > 0 ? AnimColours[^1].Color : Color)));
        UpdateAnimColourState();
        Changed();
    }

    private AnimationColourViewModel NewAnimColour(Color c) => new(Changed, RemoveAnimColour, c);

    private void RemoveAnimColour(AnimationColourViewModel colour)
    {
        if (AnimColours.Count <= 2) return;
        AnimColours.Remove(colour);
        UpdateAnimColourState();
        Changed();
    }

    private void ResetAnimColours(IEnumerable<Color> colours)
    {
        AnimColours.Clear();
        foreach (var c in colours.Take(TokenAnimation.MaxColors))
            AnimColours.Add(NewAnimColour(c));
        UpdateAnimColourState();
    }

    private void UpdateAnimColourState()
    {
        int number = 1;
        foreach (var c in AnimColours)
        {
            c.CanRemove = AnimColours.Count > 2;
            c.Number = number++;
        }
        OnPropertyChanged(nameof(CanAddAnimColour));
        OnPropertyChanged(nameof(AnimStopCountText));
    }

    /// <summary>A second animation colour that clearly differs: the hue turned by 120°.</summary>
    private static Color AnimPartner(Color c)
    {
        var (h, s, l) = ColorUtil.ToHsl(c);
        return ColorUtil.FromHsl(h + 120, Math.Max(s, 0.6), Math.Clamp(l, 0.35, 0.65), c.A);
    }

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

    /// <summary>Typed opacity in % (0..100).</summary>
    public string OpacityInput
    {
        get => ColorUtil.FormatNumber(Opacity * 100);
        set
        {
            if (ColorUtil.TryParseUserNumber(value, out var v))
                Opacity = Math.Clamp(v, 0, 100) / 100;
            // Re-notify after the binding finished writing, so rejected text is replaced by the real value.
            Avalonia.Threading.Dispatcher.UIThread.Post(() => OnPropertyChanged(nameof(OpacityInput)));
        }
    }

    /// <summary>Typed gradient angle in degrees; any number is wrapped into 0..359.</summary>
    public string AngleInput
    {
        get => ColorUtil.FormatNumber(Angle);
        set
        {
            if (ColorUtil.TryParseUserNumber(value, out var v))
                Angle = v;
            // Re-notify after the binding finished writing, so rejected text is replaced by the real value.
            Avalonia.Threading.Dispatcher.UIThread.Post(() => OnPropertyChanged(nameof(AngleInput)));
        }
    }

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

    private GradientSpec CurrentGradient()
    {
        var offsets = Stops.Select(st => st.Position / 100).ToList();
        return new(Stops.Skip(1).Select(st => st.Color).ToList(), Angle, GradientSpec.IsEven(offsets) ? null : offsets);
    }

    public TokenValue ToValue() => new(
        Color,
        SupportsOpacity ? Opacity : 1.0,
        IsGradient && !IsAnimated && SupportsGradient && Stops.Count >= 2 ? CurrentGradient() : null,
        IsAnimated && SupportsAnimation && AnimColours.Count >= 2
            ? new TokenAnimation(AnimColours.Select(a => a.Color).ToList(), AnimMode == 1, Math.Round(AnimSeconds), AnimAngle)
            : null);

    public void SetValue(TokenValue value)
    {
        _loading = true;
        try
        {
            Color = value.Color;
            Opacity = double.IsFinite(value.Opacity) ? Math.Clamp(value.Opacity, 0, 1) : 1;
            if (value.Gradient is { } g && SupportsGradient)
            {
                var stops = g.Stops(value.Color);
                ReplaceStops(stops.Select(st => st.Color), stops.Select(st => st.Offset * 100).ToList());
                Angle = Math.Round(g.SafeAngle);
                IsGradient = true;
            }
            else
            {
                ReplaceStops([value.Color, DefaultEnd(value.Color)]);
                Angle = 90;
                IsGradient = false;
            }

            if (value.Animation is { Colors.Count: >= 2 } anim && SupportsAnimation)
            {
                ResetAnimColours(anim.Colors);
                AnimMode = anim.Flow ? 1 : 0;
                AnimSeconds = Math.Clamp(anim.Seconds, 1, 20);
                AnimAngle = anim.Angle;
                IsAnimated = true;
            }
            else
            {
                ResetAnimColours([value.Color, AnimPartner(value.Color)]);
                AnimMode = 0;
                AnimSeconds = 6;
                AnimAngle = 0;
                IsAnimated = false;
            }
        }
        finally
        {
            _loading = false;
        }
        Changed();
    }

    // ---------- Stop management ----------

    private void ReplaceStops(IEnumerable<Color> colors, IReadOnlyList<double>? positions = null)
    {
        _syncingStops = true;
        try
        {
            Stops.Clear();
            foreach (var c in colors.Take(GradientSpec.MaxStops))
                Stops.Add(new GradientStopViewModel(this, c, 0));
            while (Stops.Count < 2)
                Stops.Add(new GradientStopViewModel(this, DefaultEnd(Stops.Count > 0 ? Stops[^1].Color : Color), 0));

            if (positions != null && positions.Count == Stops.Count)
                for (int i = 0; i < Stops.Count; i++)
                    Stops[i].SetPositionSilently(Math.Clamp(double.IsFinite(positions[i]) ? positions[i] : 0, 0, 100));
            else
                SpreadEvenlySilently();
        }
        finally
        {
            _syncingStops = false;
        }
        RefreshStopInfo();
    }

    private void SpreadEvenlySilently()
    {
        var even = GradientSpec.EvenOffsets(Stops.Count);
        for (int i = 0; i < Stops.Count; i++)
            Stops[i].SetPositionSilently(Math.Round(even[i] * 100, 1));
    }

    private bool PositionsAreEven() => GradientSpec.IsEven(Stops.Select(st => st.Position / 100).ToList());

    /// <summary>Keeps a moved stop between its neighbours so the colours can never cross over.</summary>
    internal void OnStopPositionChanged(GradientStopViewModel stop)
    {
        int i = Stops.IndexOf(stop);
        if (i < 0) return;
        double min = i > 0 ? Stops[i - 1].Position : 0;
        double max = i < Stops.Count - 1 ? Stops[i + 1].Position : 100;
        double v = double.IsFinite(stop.Position) ? Math.Clamp(stop.Position, min, max) : min;
        if (Math.Abs(v - stop.Position) > 1e-9)
            stop.SetPositionSilently(v);
        Changed();
    }

    /// <summary>Spreads all colours evenly again (0%, ..., 100%).</summary>
    [RelayCommand]
    private void SpreadEvenly()
    {
        SpreadEvenlySilently();
        Changed();
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
        bool wasEven = PositionsAreEven();
        Stops.Remove(stop);
        if (wasEven) SpreadEvenlySilently();
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
        bool wasEven = PositionsAreEven();
        _syncingStops = true;
        try
        {
            var stop = new GradientStopViewModel(this, ColorUtil.FromHsl(h + 40, Math.Max(s, 0.35), Math.Clamp(l, 0.2, 0.7), last.A), 100);
            if (!wasEven && Stops.Count >= 2 && Stops[^1].Position >= 100)
            {
                // Custom positions: make room at the end instead of resetting the user's layout.
                Stops[^1].SetPositionSilently(Math.Round((Stops[^2].Position + 100) / 2, 1));
            }
            Stops.Add(stop);
            if (wasEven) SpreadEvenlySilently();
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
        var mirrored = Stops.Select(st => 100 - st.Position).Reverse().ToList();
        _loading = true;
        try
        {
            ReplaceStops(reversed, mirrored);
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
        OnPropertyChanged(nameof(AnimPreview));
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
        OnPropertyChanged(nameof(OpacityInput));
        Changed();
    }

    partial void OnIsGradientChanged(bool value)
    {
        if (value && !SupportsGradient)
        {
            IsGradient = false;
            return;
        }
        if (value && IsAnimated)
            IsAnimated = false; // one or the other, see OnIsAnimatedChanged
        if (value && !_loading)
            IsEditorOpen = true;
        OnPropertyChanged(nameof(FillMode));
        NotifyEditor();
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
        OnPropertyChanged(nameof(AngleInput));
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

public sealed partial class TokenGroupViewModel : ObservableObject
{
    /// <summary>Unfolded group card (the header arrow folds it).</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(Glyph))]
    private bool _isExpanded = true;

    public string Glyph => IsExpanded ? "▾" : "▸";

    [CommunityToolkit.Mvvm.Input.RelayCommand]
    private void Toggle() => IsExpanded = !IsExpanded;

    public string Name { get; }
    public string Description { get; }
    public IReadOnlyList<TokenViewModel> Tokens { get; }

    /// <summary>False when the search box hides every token of this group.</summary>
    [ObservableProperty]
    private bool _hasMatches = true;

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

/// <summary>A theme folder in THEME → Recent themes.</summary>
public sealed record RecentThemeEntry(string Folder, string Name, string Details, Avalonia.Media.Imaging.Bitmap? Thumbnail)
{
    public bool HasThumbnail => Thumbnail != null;

    /// <summary>Reads the name and version from theme.json and the thumbnail from preview.png.</summary>
    public static RecentThemeEntry Read(string folder)
    {
        string name = Path.GetFileName(folder);
        string version = string.Empty;
        try
        {
            string json = Path.Combine(folder, "theme.json");
            if (File.Exists(json))
            {
                var m = System.Text.Json.JsonSerializer.Deserialize<RbwrOverlay.Core.Models.ThemeManifest>(File.ReadAllText(json),
                    new System.Text.Json.JsonSerializerOptions { PropertyNameCaseInsensitive = true });
                if (!string.IsNullOrWhiteSpace(m?.Name)) name = m!.Name;
                if (!string.IsNullOrWhiteSpace(m?.Version)) version = "v" + m!.Version.Trim().TrimStart('v', 'V');
            }
        }
        catch
        {
            // unreadable manifest: show the folder name
        }
        var thumb = PreviewImage.TryLoad(Path.Combine(folder, ThemeExporter.PreviewFileName), 96);
        string details = string.IsNullOrEmpty(version) ? folder : $"{version}  ·  {folder}";
        return new RecentThemeEntry(folder, name, details, thumb);
    }
}

public sealed record InstalledThemeEntry(string Id, string Name, string Directory)
{
    public override string ToString() => $"{Name}  ({Id})";
}
