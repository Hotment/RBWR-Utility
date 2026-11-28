using System.Text.Json.Nodes;
using Avalonia.Media;
using Avalonia.Threading;
using RbwrThemeCreator.Models;
using RbwrThemeCreator.Services;
using RbwrThemeCreator.Services.Ai;
using static RbwrThemeCreator.Services.Ai.Schema;

namespace RbwrThemeCreator.ViewModels;

public partial class MainViewModel
{
    // =====================================================================
    // AI / MCP theme tools
    // =====================================================================

    private AiChatViewModel? _ai;
    public AiChatViewModel Ai => _ai ??= new AiChatViewModel(this);

    private IReadOnlyList<AiTool>? _themeTools;
    public IReadOnlyList<AiTool> ThemeTools => _themeTools ??= CreateThemeTools();

    private IReadOnlyList<AiTool> CreateThemeTools() =>
    [
        new("get_theme",
            "Returns the current theme: info, fonts, shape and every colour token as Key: value. Value is #RRGGBB or #AARRGGBB; gradients are 'grad(angle, c1, c2, ...)'; opacity shown as '@0.8'. Call this first.",
            Obj(), _ => OnUi(GetThemeJson)),
        new("describe_tokens",
            "Lists colour tokens with group, label and where the overlay uses them. Use a group filter to save tokens.",
            Obj(("group", Str("Optional group: SURFACES, ACCENTS, TEXT, CONTROL STATES, TOOLTIPS, SLIDERS"), false)),
            a => OnUi(() => DescribeTokens(a["group"]?.GetValue<string>()))),
        new("set_tokens",
            "Sets colour tokens. Each item: key, color (#RRGGBB/#AARRGGBB), optional opacity 0-1, optional gradient (extra colours after 'color') and angle.",
            Obj(("tokens", Arr(Obj(
                ("key", Str("Token key from get_theme"), true),
                ("color", Str("Main colour"), true),
                ("opacity", Num("0..1, only for tokens that support it"), false),
                ("gradient", Arr(Str("colour"), "Extra gradient colours; empty or missing = solid"), false),
                ("angle", Num("Gradient angle in degrees"), false)), "Tokens to change"), true)),
            a => OnUi(() => SetTokens(a["tokens"] as JsonArray))),
        new("generate_palette",
            "Rebuilds the whole palette from one accent colour. mood: 0 dark, 1 tinted, 2 neutral.",
            Obj(("accent", Str("#RRGGBB"), true), ("mood", Num("0, 1 or 2"), false), ("status_colours", Bool("Also recolour green/red/gold status colours"), false)),
            a => OnUi(() => RunPalette(a))),
        new("set_theme_info",
            "Changes theme name, author, version, description, font_family or mono_font_family. Only given fields change.",
            Obj(("name", Str("Theme name"), false), ("author", Str("Author"), false), ("version", Str("e.g. 1.0.1"), false),
                ("description", Str("Description"), false), ("font_family", Str("UI font family list"), false), ("mono_font_family", Str("Number font family list"), false)),
            a => OnUi(() => SetInfo(a))),
        new("set_shape",
            "Changes the overlay shape. Only given fields change; enabled must be true for radii to apply.",
            Obj(("enabled", Bool("Turn SHAPE on/off"), false), ("shell_corner_radius", Num("0-30"), false), ("shell_border_thickness", Num("0-6"), false),
                ("card_corner_radius", Num("0-20"), false), ("button_corner_radius", Num("0-20"), false), ("compact_corner_radius", Num("0-30"), false),
                ("shell_glow", Bool("Glow around the window"), false), ("shell_glow_blur", Num("0-40"), false)),
            a => OnUi(() => SetShape(a))),
        new("set_custom_styles",
            "Replaces the ADVANCED custom Avalonia styles and/or extra resources XAML. Returns preview errors if any.",
            Obj(("styles", Str("Content placed inside <Styles>"), false), ("resources", Str("Content placed inside <Styles.Resources>"), false)),
            a => OnUi(() => SetCustom(a))),
        new("list_fonts",
            "Lists fonts: the ones added to this theme (file + family) and installed system fonts matching the filter (max 60).",
            Obj(("filter", Str("Optional part of a font name, e.g. 'mono', 'orbitron'"), false)),
            a => OnUi(() => ListFonts(a["filter"]?.GetValue<string>()))),
        new("add_font_file",
            "Adds a .ttf/.otf/.ttc file from a local path to the theme (bundled with it) and optionally applies it.",
            Obj(("path", Str("Full local path to the font file"), true), ("use_as", Str("'main', 'mono' or empty"), false)),
            a => OnUi(() => AddFontTool(a["path"]?.GetValue<string>(), a["use_as"]?.GetValue<string>()))),
        new("use_font",
            "Applies a font as the main UI font or the number (mono) font. Accepts a theme font file/family or an installed system font name.",
            Obj(("font", Str("Family name or theme font file name"), true), ("slot", Str("'main' or 'mono'"), true)),
            a => OnUi(() => UseFontTool(a["font"]?.GetValue<string>(), a["slot"]?.GetValue<string>()))),
        new("undo", "Undoes the last change.", Obj(), _ => OnUi(() => { if (CanUndo) Undo(); return Result("undone"); })),
        new("get_xaml", "Returns the generated theme.axaml. Large; use only when needed.", Obj(), _ => OnUi(() => GeneratedXaml)),
    ];

    private static Task<string> OnUi(Func<string> action) => Dispatcher.UIThread.InvokeAsync(() =>
    {
        try { return action(); }
        catch (Exception ex) { return $"error: {ex.Message}"; }
    }).GetTask();

    private string Result(string message)
    {
        Refresh();
        return HasPreviewError ? $"{message}; preview error: {PreviewError}" : message;
    }

    private static string FormatToken(TokenValue v)
    {
        string s = v.Gradient is { } g
            ? $"grad({Math.Round(g.Angle)}, {ColorUtil.ToHex(v.Color)}, {string.Join(", ", g.Colors.Select(ColorUtil.ToHex))})"
            : ColorUtil.ToHex(v.Color);
        if (v.Opacity < 0.999) s += $"@{Math.Round(v.Opacity, 2)}";
        if (v.Animation != null) s += " (animated)";
        return s;
    }

    private string GetThemeJson()
    {
        var tokens = new JsonObject();
        foreach (var (key, vm) in _tokens) tokens[key] = FormatToken(vm.ToValue());
        return new JsonObject
        {
            ["name"] = ThemeName, ["author"] = Author, ["version"] = Version, ["description"] = Description,
            ["font_family"] = FontFamily, ["mono_font_family"] = MonoFontFamily,
            ["theme_fonts"] = new JsonArray(Fonts.Select(f => (JsonNode)JsonValue.Create($"{f.FileName} ({f.FamilyName})")!).ToArray()),
            ["shape"] = new JsonObject
            {
                ["enabled"] = ShapeEnabled, ["shell_corner_radius"] = ShellCornerRadius, ["shell_border_thickness"] = ShellBorderThickness,
                ["card_corner_radius"] = CardCornerRadius, ["button_corner_radius"] = ButtonCornerRadius,
                ["compact_corner_radius"] = CompactCornerRadius, ["shell_glow"] = ShellGlow, ["shell_glow_blur"] = ShellGlowBlur,
            },
            ["has_custom_styles"] = !string.IsNullOrWhiteSpace(CustomStyles),
            ["preview_error"] = PreviewError,
            ["tokens"] = tokens,
        }.ToJsonString();
    }

    private string DescribeTokens(string? group)
    {
        var lines = TokenCatalog.Tokens
            .Where(t => string.IsNullOrWhiteSpace(group) || t.Group.Equals(group.Trim(), StringComparison.OrdinalIgnoreCase))
            .Select(t => $"{t.Key} [{t.Group}] {t.Label}: {t.Hint}{(t.SupportsOpacity ? " (opacity)" : "")}{(t.SupportsGradient ? " (gradient)" : "")}");
        return string.Join("\n", lines);
    }

    private string SetTokens(JsonArray? items)
    {
        if (items == null) return "error: tokens missing";
        var done = new List<string>();
        var problems = new List<string>();
        foreach (var node in items.OfType<JsonObject>())
        {
            string key = node["key"]?.GetValue<string>() ?? string.Empty;
            if (!_tokens.TryGetValue(key, out var vm)) { problems.Add($"unknown key {key}"); continue; }
            if (!ColorUtil.TryParse(node["color"]?.GetValue<string>(), out var color)) { problems.Add($"bad colour for {key}"); continue; }

            var current = vm.ToValue();
            double opacity = node["opacity"] is JsonNode o ? Math.Clamp(o.GetValue<double>(), 0, 1) : current.Opacity;
            GradientSpec? gradient = null;
            if (node["gradient"] is JsonArray g && g.Count > 0 && vm.SupportsGradient)
            {
                var extra = new List<Color>();
                foreach (var c in g)
                    if (ColorUtil.TryParse(c?.GetValue<string>(), out var parsed)) extra.Add(parsed);
                if (extra.Count > 0)
                    gradient = new GradientSpec(extra.Take(GradientSpec.MaxExtraStops).ToList(), node["angle"]?.GetValue<double>() ?? 90);
            }
            vm.SetValue(new TokenValue(color, opacity, gradient));
            done.Add(key);
        }
        string msg = $"set {done.Count} token(s)";
        if (problems.Count > 0) msg += "; " + string.Join(", ", problems);
        SetStatus($"AI changed {done.Count} colour(s).");
        return Result(msg);
    }

    private string RunPalette(JsonObject a)
    {
        if (!ColorUtil.TryParse(a["accent"]?.GetValue<string>(), out var accent)) return "error: bad accent";
        GeneratorAccent = accent;
        GeneratorMood = (int)Math.Clamp(a["mood"]?.GetValue<double>() ?? 0, 0, 2);
        GeneratorStatusColours = a["status_colours"]?.GetValue<bool>() ?? false;
        GeneratePalette();
        return Result("palette generated");
    }

    private string SetInfo(JsonObject a)
    {
        if (a["name"]?.GetValue<string>() is { } name) ThemeName = name;
        if (a["author"]?.GetValue<string>() is { } author) Author = author;
        if (a["version"]?.GetValue<string>() is { } version) Version = version;
        if (a["description"]?.GetValue<string>() is { } description) Description = description;
        if (a["font_family"]?.GetValue<string>() is { } font) FontFamily = font;
        if (a["mono_font_family"]?.GetValue<string>() is { } mono) MonoFontFamily = mono;
        return Result("info updated");
    }

    private string SetShape(JsonObject a)
    {
        double? N(string k) => a[k]?.GetValue<double>();
        if (a["enabled"]?.GetValue<bool>() is { } en) ShapeEnabled = en;
        if (N("shell_corner_radius") is { } scr) ShellCornerRadius = Math.Clamp(scr, 0, 30);
        if (N("shell_border_thickness") is { } sbt) ShellBorderThickness = Math.Clamp(sbt, 0, 6);
        if (N("card_corner_radius") is { } ccr) CardCornerRadius = Math.Clamp(ccr, 0, 20);
        if (N("button_corner_radius") is { } bcr) ButtonCornerRadius = Math.Clamp(bcr, 0, 20);
        if (N("compact_corner_radius") is { } cpr) CompactCornerRadius = Math.Clamp(cpr, 0, 30);
        if (a["shell_glow"]?.GetValue<bool>() is { } glow) ShellGlow = glow;
        if (N("shell_glow_blur") is { } blur) ShellGlowBlur = Math.Clamp(blur, 0, 40);
        return Result("shape updated");
    }

    private string ListFonts(string? filter)
    {
        bool Match(string s) => string.IsNullOrWhiteSpace(filter) || s.Contains(filter.Trim(), StringComparison.OrdinalIgnoreCase);
        var theme = Fonts.Where(f => Match(f.FileName) || Match(f.FamilyName)).Select(f => $"{f.FileName} (family: {f.FamilyName})").ToList();
        var system = FontManager.Current.SystemFonts.Select(f => f.Name).Where(Match).Distinct().OrderBy(n => n).Take(60).ToList();
        return $"theme fonts: {(theme.Count == 0 ? "none" : string.Join("; ", theme))}\nsystem fonts: {string.Join(", ", system)}\n" +
               $"current main: {FontFamily}\ncurrent mono: {MonoFontFamily}";
    }

    public FontEntry? AddFontForAi(string path)
    {
        string name = SafeFileName(path);
        return AddFontFiles([path]) > 0 ? Fonts.LastOrDefault(f => f.FileName.Equals(name, StringComparison.OrdinalIgnoreCase)) : null;
    }

    private string AddFontTool(string? path, string? useAs)
    {
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path)) return "error: file not found";
        if (!FontTools.IsFontFile(path)) return "error: not a .ttf/.otf/.ttc file";
        var font = AddFontForAi(path);
        if (font == null) return "error: could not add the font";
        if (useAs is "main" or "mono") return UseFontTool(font.FileName, useAs);
        return Result($"added {font.FileName} (family: {font.FamilyName})");
    }

    private string UseFontTool(string? name, string? slot)
    {
        if (string.IsNullOrWhiteSpace(name)) return "error: font missing";
        bool mono = string.Equals(slot, "mono", StringComparison.OrdinalIgnoreCase);
        string n = name.Trim();
        var entry = Fonts.FirstOrDefault(f => f.FileName.Equals(n, StringComparison.OrdinalIgnoreCase) || f.FamilyName.Equals(n, StringComparison.OrdinalIgnoreCase));
        string current = mono ? MonoFontFamily : FontFamily;
        string fallback = mono ? BuiltInThemes.Cyberpunk.MonoFontFamily : BuiltInThemes.Cyberpunk.FontFamily;
        string list;
        if (entry != null) list = PrependFontReference(entry, current, fallback);
        else
        {
            if (!FontManager.Current.SystemFonts.Any(f => f.Name.Equals(n, StringComparison.OrdinalIgnoreCase)))
                return $"error: '{n}' is not a theme font or installed system font. Call list_fonts.";
            var rest = current.Split(',').Select(s => s.Trim()).Where(s => s.Length > 0 && !s.Trim('\'', '"').Equals(n, StringComparison.OrdinalIgnoreCase));
            list = string.Join(", ", new[] { n }.Concat(rest));
        }
        if (mono) MonoFontFamily = list;
        else FontFamily = list;
        return Result($"{(mono ? "mono" : "main")} font: {list}");
    }

    private string SetCustom(JsonObject a)
    {
        if (a["styles"]?.GetValue<string>() is { } styles) CustomStyles = styles;
        if (a["resources"]?.GetValue<string>() is { } res) CustomResources = res;
        return Result("custom XAML updated");
    }
}
