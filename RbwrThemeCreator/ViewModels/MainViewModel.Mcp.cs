using System.Text.Json.Nodes;
using Avalonia.Media;
using Avalonia.Threading;
using RbwrThemeCreator.Models;
using RbwrThemeCreator.Services;
using RbwrThemeCreator.Services.Mcp;
using static RbwrThemeCreator.Services.Mcp.McpSchema;

namespace RbwrThemeCreator.ViewModels;

public partial class MainViewModel
{
    // =====================================================================
    // Built-in MCP server tools & resources
    // =====================================================================

    private McpServerViewModel? _mcp;
    public McpServerViewModel Mcp => _mcp ??= new McpServerViewModel(this);

    private IReadOnlyList<McpTool>? _mcpTools;
    public IReadOnlyList<McpTool> McpTools => _mcpTools ??= CreateMcpTools();

    private IReadOnlyList<McpResource>? _mcpResources;
    public IReadOnlyList<McpResource> McpResources => _mcpResources ??= CreateMcpResources();

    private IReadOnlyList<McpResource> CreateMcpResources() =>
    [
        new("rbwr://theme/state", "Current Theme State",
            "Complete JSON state of the theme currently open in RBWR Theme Creator.",
            "application/json",
            () => OnUiResourceAsync("rbwr://theme/state", "application/json", GetThemeStateJson)),
        new("rbwr://theme/xaml", "Generated theme.axaml",
            "The live generated Avalonia XAML stylesheet for the current theme.",
            "application/xml",
            () => OnUiResourceAsync("rbwr://theme/xaml", "application/xml", () => { Refresh(); return GeneratedXaml; })),
        new("rbwr://theme/tokens", "Token Catalog Reference",
            "All editable theme colour tokens, groups, hints, and capabilities.",
            "text/plain",
            () => OnUiResourceAsync("rbwr://theme/tokens", "text/plain", () => DescribeTokensText(null, null))),
        new("rbwr://theme/selectors", "Overlay XAML Selector Reference",
            "Overlay style classes, named elements, pseudo-classes, snippets, and safety rules for custom XAML.",
            "application/json",
            () => OnUiResourceAsync("rbwr://theme/selectors", "application/json", GetSelectorReferenceJson)),
        new("rbwr://preview/monitor.png", "Live MONITOR Preview PNG",
            "Rendered PNG screenshot of the MONITOR overlay view using the current theme.",
            "image/png",
            () => OnUiImageResourceAsync("rbwr://preview/monitor.png", 0, 1.5, 0)),
        new("rbwr://preview/all.png", "Live ALL-Views Contact Sheet PNG",
            "Rendered 2x2 PNG contact sheet of MONITOR, CONFIG, COMPACT, and TABLET views.",
            "image/png",
            () => OnUiImageResourceAsync("rbwr://preview/all.png", 4, 1.25, 0)),
    ];

    private IReadOnlyList<McpTool> CreateMcpTools() =>
    [
        // ---------- Inspection & Preview ----------
        new("get_theme",
            "Returns the complete JSON state of the open theme: manifest, fonts, shape, APRM box overrides, background image, assets, custom thumbnail, contrast summary, validation status, preview state, and every colour token (solid, gradient, opacity, animation). Call this first.",
            Obj(),
            _ => OnUi(() => McpToolResult.Ok(GetThemeStateJson()))),

        new("describe_tokens",
            "Lists editable colour tokens with group, label, hint, opacity/gradient support, and preview locations. Filter by group or search text to keep output compact.",
            Obj(
                ("group", Str("Optional group filter: SURFACES, ACCENTS, TEXT, CONTROL STATES, TOOLTIPS, SLIDERS"), false),
                ("search", Str("Optional substring filter across key, label, hint, or group"), false)),
            a => OnUi(() => McpToolResult.Ok(DescribeTokensText(GetStr(a, "group"), GetStr(a, "search"))))),

        new("render_preview",
            "Renders the current theme preview off-screen as a PNG image and returns it directly as an MCP image block so you can visually inspect your edits. Supports all 5 views (monitor, config, compact, tablet, all), scale (0.5-2.5), backdrop (dark, game, light, checker, transparent), and optional output_path to save the PNG to disk.",
            Obj(
                ("mode", Enum("Overlay view to render (default: monitor)", "monitor", "config", "compact", "tablet", "all"), false),
                ("scale", Num("Render scale factor 0.5..2.5 (default: 1.5 for single views, 1.25 for all)"), false),
                ("backdrop", Enum("Backdrop behind the overlay (default: dark)", "dark", "game", "light", "checker", "transparent"), false),
                ("output_path", Str("Optional local .png file path to also save the rendered image"), false)),
            a => OnUi(() => RenderPreviewTool(a))),

        new("set_preview_view",
            "Updates the live preview viewport inside the Theme Creator window (mode, backdrop, fit/zoom) and optionally flashes specific token elements.",
            Obj(
                ("mode", Enum("Preview view mode", "monitor", "config", "compact", "tablet", "all"), false),
                ("backdrop", Enum("Preview backdrop", "dark", "game", "light", "checker"), false),
                ("fit", Bool("Fit preview to viewport"), false),
                ("zoom", Num("Manual zoom 0.25..4.0 (disables fit)"), false),
                ("highlight_tokens", Arr(Str("Token key"), "Optional list of token keys to highlight in the live preview"), false)),
            a => OnUi(() => SetPreviewViewTool(a))),

        new("validate_theme",
            "Validates manifest fields, generated XAML, resource resolution, and WCAG contrast ratios; returns structured JSON report.",
            Obj(),
            _ => OnUi(() => McpToolResult.Ok(ValidateThemeJson()))),

        new("get_xaml",
            "Returns the generated theme.axaml, and optionally the raw custom_styles and custom_resources strings.",
            Obj(("include_custom_sections", Bool("Return JSON with generated_xaml, custom_styles, and custom_resources"), false)),
            a => OnUi(() => GetXamlTool(GetBool(a, "include_custom_sections") == true))),

        new("get_selector_reference",
            "Returns the overlay's Avalonia XAML selector reference: style classes, button/input classes, pseudo-classes, named elements (#PowerBanner, #OverlayTitle, etc.), built-in snippets, and disallowed XAML rules.",
            Obj(),
            _ => OnUi(() => McpToolResult.Ok(GetSelectorReferenceJson()))),

        // ---------- Colours, Palettes, Gradients, Animations & APRM Box ----------
        new("set_tokens",
            "Batch-edits one or more colour tokens. Each item accepts key, color (#RRGGBB or #AARRGGBB), optional opacity (0..1), optional gradient ({colors, angle, offsets} or extra colors array), clear_gradient, optional animation ({colors, flow, seconds, angle}), and clear_animation.",
            Obj(("tokens", Arr(Obj(
                ("key", Str("Token key from get_theme or describe_tokens"), true),
                ("color", Str("Main hex colour (#RRGGBB or #AARRGGBB)"), false),
                ("opacity", Num("0..1 opacity for tokens that support it"), false),
                ("gradient", Arr(Str("Hex colour"), "Extra gradient stop colours after main color (up to 5); empty array clears gradient"), false),
                ("angle", Num("Linear gradient angle in degrees (0=left->right, 90=top->bottom)"), false),
                ("offsets", Arr(Num("0..1 stop offset"), "Optional ascending offsets matching 1 + gradient.length stops"), false),
                ("clear_gradient", Bool("Explicitly clear gradient back to solid"), false),
                ("animation", Obj(
                    ("colors", Arr(Str("Hex colour"), "2 to 4 animation colours"), true),
                    ("flow", Bool("false = pulse/cycle solid colour, true = flowing animated gradient"), false),
                    ("seconds", Num("Cycle duration in seconds (0.5..60)"), false),
                    ("angle", Num("Flow gradient angle in degrees"), false)), false),
                ("clear_animation", Bool("Explicitly remove colour animation"), false)), "Tokens to modify"), true)),
            a => OnUi(() => SetTokensTool(a["tokens"] as JsonArray))),

        new("generate_palette",
            "Rebuilds the full colour palette from a single accent hex colour. mood: 0=dark, 1=tinted, 2=neutral.",
            Obj(
                ("accent", Str("Primary accent hex colour (#RRGGBB)"), true),
                ("mood", Int("0 = dark (tinted black), 1 = tinted (more colour), 2 = neutral (grey)"), false),
                ("status_colours", Bool("Also recolour green/red/gold status colours (default: false)"), false)),
            a => OnUi(() => GeneratePaletteTool(a))),

        new("set_aprm_box",
            "Configures the independent APRM power box (#PowerBanner) border, readout text, and bar colours.",
            Obj(
                ("enabled", Bool("Enable independent APRM box colours"), false),
                ("border_color", Str("Hex colour for APRM box border"), false),
                ("text_color", Str("Hex colour for APRM main readout text"), false),
                ("bar_color", Str("Hex colour for APRM progress bar"), false)),
            a => OnUi(() => SetAprmBoxTool(a))),

        new("reset_colours",
            "Resets all colour tokens and APRM box overrides back to the base Cyberpunk palette.",
            Obj(),
            _ => OnUi(() => { ResetColoursToBase(); return StatusResult("Colours reset to base Cyberpunk palette."); })),

        // ---------- Presets, Manifest, Shape & Custom XAML ----------
        new("list_presets",
            "Lists all built-in starter theme presets available in Theme Creator.",
            Obj(),
            _ => OnUi(() => McpToolResult.Ok(ListPresetsJson()))),

        new("load_preset",
            "Loads a built-in starter theme preset by name or index into the editor.",
            Obj(
                ("name", Str("Preset name from list_presets (case-insensitive)"), false),
                ("index", Int("0-based preset index from list_presets"), false)),
            a => OnUi(() => LoadPresetTool(a))),

        new("set_theme_info",
            "Updates theme manifest metadata and/or font family stacks. Only provided fields change.",
            Obj(
                ("id", Str("Manifest folder/theme ID (lowercase slug)"), false),
                ("name", Str("Theme display name"), false),
                ("author", Str("Theme author name"), false),
                ("version", Str("Semantic version string, e.g. 1.0.0"), false),
                ("description", Str("Theme description"), false),
                ("min_app_version", Str("Minimum RBWR Overlay version, e.g. 2.3.0 (auto-raised to 2.3.1 if animated colours are used)"), false),
                ("font_family", Str("Main UI font family list"), false),
                ("mono_font_family", Str("Numeric/monospace font family list"), false)),
            a => OnUi(() => SetThemeInfoTool(a))),

        new("set_shape",
            "Configures overlay window/card/button corner radii, border thickness, and window glow, or resets shape to defaults.",
            Obj(
                ("reset", Bool("Reset all shape settings to defaults before applying any other fields"), false),
                ("enabled", Bool("Enable custom shape overrides"), false),
                ("shell_corner_radius", Num("0..30"), false),
                ("shell_border_thickness", Num("0..6"), false),
                ("card_corner_radius", Num("0..20"), false),
                ("button_corner_radius", Num("0..20"), false),
                ("compact_corner_radius", Num("0..30"), false),
                ("shell_glow", Bool("Enable outer glow around window"), false),
                ("shell_glow_blur", Num("0..40"), false)),
            a => OnUi(() => SetShapeTool(a))),

        new("set_custom_xaml",
            "Sets/replaces custom Avalonia <Styles> and/or <Styles.Resources> XAML, or appends a built-in style snippet. Immediately validates and returns any preview error.",
            Obj(
                ("styles", Str("Raw XAML placed inside <Styles> (pass empty string to clear)"), false),
                ("resources", Str("Raw XAML placed inside <Styles.Resources> (pass empty string to clear)"), false),
                ("append_snippet", Enum("Optional built-in snippet to append to custom_styles", "title", "nav", "readout", "image"), false)),
            a => OnUi(() => SetCustomXamlTool(a))),

        // ---------- Fonts, Image Assets, Background & Thumbnail ----------
        new("list_fonts",
            "Lists bundled theme fonts, current main/mono font stacks, and installed system fonts (filtered by optional substring, max 80).",
            Obj(("filter", Str("Optional case-insensitive substring filter, e.g. 'mono' or 'jetbrains'"), false)),
            a => OnUi(() => McpToolResult.Ok(ListFontsJson(GetStr(a, "filter"))))),

        new("add_font_file",
            "Bundles a local .ttf/.otf/.ttc font file into the theme (fonts/) and optionally applies it as main or mono font.",
            Obj(
                ("path", Str("Full local path to .ttf, .otf, or .ttc file"), true),
                ("use_as", Enum("Optional slot to apply the font to immediately", "main", "mono"), false)),
            a => OnUi(() => AddFontFileTool(GetStr(a, "path"), GetStr(a, "use_as")))),

        new("remove_font",
            "Removes a bundled font from the theme by file name.",
            Obj(("file_name", Str("Bundled font file name from list_fonts"), true)),
            a => OnUi(() => RemoveFontTool(GetStr(a, "file_name")))),

        new("use_font",
            "Applies a bundled theme font or installed system font to the main or mono font slot, or resets both font stacks.",
            Obj(
                ("font", Str("Bundled file name/family name or installed system font name"), false),
                ("slot", Enum("Target slot: main or mono", "main", "mono"), false),
                ("reset", Bool("Reset both main and mono fonts to defaults"), false)),
            a => OnUi(() => UseFontTool(a))),

        new("list_assets",
            "Lists bundled image assets in assets/, background image settings, and custom thumbnail status.",
            Obj(),
            _ => OnUi(() => McpToolResult.Ok(ListAssetsJson()))),

        new("add_image_asset",
            "Bundles a local image file (.png/.jpg/.jpeg/.webp/.bmp/.gif) into assets/ and optionally sets it as the theme background image.",
            Obj(
                ("path", Str("Full local path to the image file"), true),
                ("set_as_background", Bool("Also assign this image as the overlay background image"), false)),
            a => OnUi(() => AddImageAssetTool(GetStr(a, "path"), GetBool(a, "set_as_background") == true))),

        new("remove_image_asset",
            "Removes a bundled image asset from assets/ by file name.",
            Obj(("file_name", Str("Asset file name from list_assets"), true)),
            a => OnUi(() => RemoveImageAssetTool(GetStr(a, "file_name")))),

        new("set_background_image",
            "Configures or clears the overlay background image (from bundled assets/), its opacity (0..1), and stretch mode.",
            Obj(
                ("file_name", Str("Asset file name in assets/ (pass empty string or clear=true to remove)"), false),
                ("clear", Bool("Clear the background image"), false),
                ("opacity", Num("0..1 background opacity"), false),
                ("stretch", Enum("Image stretch mode", "UniformToFill", "Uniform", "Fill", "None"), false)),
            a => OnUi(() => SetBackgroundImageTool(a))),

        new("set_custom_thumbnail",
            "Sets a local image file as the theme's custom preview.png thumbnail, or clears it back to automatic MONITOR rendering.",
            Obj(
                ("path", Str("Full local path to an image file"), false),
                ("clear", Bool("Remove custom thumbnail and revert to automatic MONITOR render"), false)),
            a => OnUi(() => SetCustomThumbnailTool(GetStr(a, "path"), GetBool(a, "clear") == true))),

        // ---------- Undo / Redo, Files & Overlay Integration ----------
        new("undo",
            "Undoes the last theme change in the editor history.",
            Obj(),
            _ => OnUi(() =>
            {
                if (!CanUndo) return McpToolResult.Ok("Nothing to undo.");
                Undo();
                return StatusResult($"Undid last change. can_undo={CanUndo}, can_redo={CanRedo}");
            })),

        new("redo",
            "Redoes the previously undone theme change.",
            Obj(),
            _ => OnUi(() =>
            {
                if (!CanRedo) return McpToolResult.Ok("Nothing to redo.");
                Redo();
                return StatusResult($"Redid change. can_undo={CanUndo}, can_redo={CanRedo}");
            })),

        new("list_installed_themes",
            "Lists themes installed in the overlay's themes folder, recent theme folders, and the configured overlay themes directory.",
            Obj(("refresh", Bool("Rescan the overlay themes folder first (default: true)"), false)),
            a => OnUi(() =>
            {
                if (GetBool(a, "refresh") != false) RefreshInstalledThemes();
                return McpToolResult.Ok(ListInstalledThemesJson());
            })),

        new("open_theme",
            "Opens an existing theme into the editor by local path (theme folder, theme.json, .zip, or .axaml) or by installed overlay theme ID.",
            Obj(
                ("path", Str("Local folder or file path to open"), false),
                ("installed_id", Str("Installed overlay theme ID from list_installed_themes"), false)),
            a => OnUi(() => OpenThemeTool(GetStr(a, "path"), GetStr(a, "installed_id")))),

        new("save_theme",
            "Validates and saves the open theme to its current folder (or to a specified destination folder), including preview.png thumbnail.",
            Obj(("folder", Str("Optional target folder path; defaults to the currently open theme folder"), false)),
            a => OnUi(() => SaveThemeTool(GetStr(a, "folder")))),

        new("export_zip",
            "Validates and exports the open theme as a shareable .zip pack (including theme.json, theme.axaml, fonts, assets, and preview.png).",
            Obj(("path", Str("Full destination .zip file path"), true)),
            a => OnUi(() => ExportZipTool(GetStr(a, "path")))),

        new("install_to_overlay",
            "Validates and installs the open theme directly into the configured RBWR Overlay themes directory.",
            Obj(("overlay_themes_dir", Str("Optional override path to the overlay themes directory"), false)),
            a => OnUi(() => InstallToOverlayTool(GetStr(a, "overlay_themes_dir")))),

        new("detect_overlay",
            "Detects a running or nearby RBWR Overlay themes directory (or sets an explicit path) and refreshes the installed themes list.",
            Obj(("overlay_themes_dir", Str("Optional explicit path to the overlay folder or its themes/ directory"), false)),
            a => OnUi(() => DetectOverlayTool(GetStr(a, "overlay_themes_dir")))),

        new("delete_installed_theme",
            "Deletes an installed custom theme folder from the RBWR Overlay themes directory by ID.",
            Obj(("installed_id", Str("Installed overlay theme ID from list_installed_themes"), true)),
            a => OnUi(() => DeleteInstalledThemeTool(GetStr(a, "installed_id")))),
    ];

    // =====================================================================
    // UI thread marshaling helpers
    // =====================================================================

    private static Task<McpToolResult> OnUi(Func<McpToolResult> action) =>
        Dispatcher.UIThread.InvokeAsync(() =>
        {
            try { return action(); }
            catch (Exception ex) { return McpToolResult.Error($"Error: {ex.Message}"); }
        }).GetTask();

    private static Task<McpResourceContent> OnUiResourceAsync(string uri, string mimeType, Func<string> read) =>
        Dispatcher.UIThread.InvokeAsync(() => new McpResourceContent
        {
            Uri = uri,
            MimeType = mimeType,
            Text = read(),
        }).GetTask();

    private Task<McpResourceContent> OnUiImageResourceAsync(string uri, int mode, double scale, int backdrop) =>
        Dispatcher.UIThread.InvokeAsync(() =>
        {
            Refresh();
            var rendered = Dialogs?.RenderPreviewPng(BuildState(), mode, scale, backdrop)
                ?? throw new InvalidOperationException("Preview renderer is unavailable (window not attached).");
            return new McpResourceContent
            {
                Uri = uri,
                MimeType = "image/png",
                Blob = rendered.PngBytes,
            };
        }).GetTask();

    private McpToolResult StatusResult(string message)
    {
        Refresh();
        if (HasPreviewError)
            return McpToolResult.Ok($"{message}\nPreview error: {PreviewError}");
        return McpToolResult.Ok(message);
    }

    // =====================================================================
    // JSON parameter helpers
    // =====================================================================

    private static string? GetStr(JsonObject a, string key) =>
        a[key] is JsonValue v && v.TryGetValue<string>(out var s) ? s : null;

    private static double? GetNum(JsonObject a, string key)
    {
        if (a[key] is not JsonValue v) return null;
        if (v.TryGetValue<double>(out double d)) return d;
        if (v.TryGetValue<int>(out int i)) return i;
        return null;
    }

    private static int? GetInt(JsonObject a, string key)
    {
        if (a[key] is not JsonValue v) return null;
        if (v.TryGetValue<int>(out int i)) return i;
        if (v.TryGetValue<double>(out double d)) return (int)Math.Round(d);
        return null;
    }

    private static bool? GetBool(JsonObject a, string key) =>
        a[key] is JsonValue v && v.TryGetValue<bool>(out bool b) ? b : null;

    private static int ParsePreviewMode(string? raw, int fallback) => (raw ?? string.Empty).Trim().ToLowerInvariant() switch
    {
        "monitor" or "0" => 0,
        "config" or "1" => 1,
        "compact" or "2" => 2,
        "tablet" or "3" => 3,
        "all" or "4" => 4,
        _ => fallback,
    };

    private static string PreviewModeName(int mode) => mode switch
    {
        0 => "monitor",
        1 => "config",
        2 => "compact",
        3 => "tablet",
        4 => "all",
        _ => "monitor",
    };

    private static int? ParseBackdrop(string? raw, int? fallback) => (raw ?? string.Empty).Trim().ToLowerInvariant() switch
    {
        "transparent" or "none" or "-1" => null,
        "dark" or "0" => 0,
        "game" or "1" => 1,
        "light" or "2" => 2,
        "checker" or "checkerboard" or "3" => 3,
        "" => fallback,
        _ => fallback,
    };

    private static string BackdropName(int? backdrop) => backdrop switch
    {
        0 => "dark",
        1 => "game",
        2 => "light",
        3 => "checker",
        _ => "transparent",
    };

    // =====================================================================
    // Tool implementations
    // =====================================================================

    private string GetThemeStateJson()
    {
        var tokensObj = new JsonObject();
        foreach (var (key, vm) in _tokens)
        {
            var v = vm.ToValue();
            var tObj = new JsonObject
            {
                ["color"] = ColorUtil.ToHex(v.Color),
                ["opacity"] = Math.Round(v.Opacity, 3),
            };
            if (v.Gradient is { } g)
            {
                var gColors = new JsonArray(g.Colors.Select(c => (JsonNode)JsonValue.Create(ColorUtil.ToHex(c))!).ToArray());
                var gObj = new JsonObject
                {
                    ["colors"] = gColors,
                    ["angle"] = Math.Round(g.SafeAngle, 1),
                };
                if (g.Offsets is { Count: > 0 })
                    gObj["offsets"] = new JsonArray(g.Offsets.Select(o => (JsonNode)JsonValue.Create(Math.Round(o, 3))!).ToArray());
                tObj["gradient"] = gObj;
            }
            if (v.Animation is { } anim)
            {
                tObj["animation"] = new JsonObject
                {
                    ["colors"] = new JsonArray(anim.Colors.Select(c => (JsonNode)JsonValue.Create(ColorUtil.ToHex(c))!).ToArray()),
                    ["flow"] = anim.Flow,
                    ["seconds"] = Math.Round(anim.Seconds, 2),
                    ["angle"] = Math.Round(anim.Angle, 1),
                };
            }
            tokensObj[key] = tObj;
        }

        return new JsonObject
        {
            ["manifest"] = new JsonObject
            {
                ["id"] = ThemeId,
                ["name"] = ThemeName,
                ["author"] = Author,
                ["version"] = Version,
                ["description"] = Description,
                ["min_app_version"] = MinAppVersion,
            },
            ["fonts"] = new JsonObject
            {
                ["font_family"] = FontFamily,
                ["mono_font_family"] = MonoFontFamily,
                ["bundled"] = new JsonArray(Fonts.Select(f => (JsonNode)new JsonObject
                {
                    ["file_name"] = f.FileName,
                    ["family_name"] = f.FamilyName,
                    ["source_path"] = f.SourcePath,
                }).ToArray()),
            },
            ["shape"] = new JsonObject
            {
                ["enabled"] = ShapeEnabled,
                ["shell_corner_radius"] = ShellCornerRadius,
                ["shell_border_thickness"] = ShellBorderThickness,
                ["card_corner_radius"] = CardCornerRadius,
                ["button_corner_radius"] = ButtonCornerRadius,
                ["compact_corner_radius"] = CompactCornerRadius,
                ["shell_glow"] = ShellGlow,
                ["shell_glow_blur"] = ShellGlowBlur,
            },
            ["aprm_box"] = new JsonObject
            {
                ["enabled"] = AprmBoxEnabled,
                ["border_color"] = ColorUtil.ToHex(AprmBoxBorderColor),
                ["text_color"] = ColorUtil.ToHex(AprmBoxTextColor),
                ["bar_color"] = ColorUtil.ToHex(AprmBoxBarColor),
            },
            ["background_image"] = HasBackgroundImage ? new JsonObject
            {
                ["file_name"] = BackgroundImageFile,
                ["opacity"] = Math.Round(BackgroundImageOpacity, 3),
                ["stretch"] = BackgroundStretch,
            } : null,
            ["assets"] = new JsonArray(Assets.Select(a => (JsonNode)new JsonObject
            {
                ["file_name"] = a.FileName,
                ["source_path"] = a.SourcePath,
            }).ToArray()),
            ["custom_thumbnail"] = CustomThumbnailPath,
            ["has_custom_styles"] = !string.IsNullOrWhiteSpace(CustomStyles),
            ["has_custom_resources"] = !string.IsNullOrWhiteSpace(CustomResources),
            ["has_animated_colours"] = HasAnimatedColours,
            ["contrast_summary"] = ContrastSummary,
            ["contrast_warning"] = ContrastWarning,
            ["manifest_problems"] = ManifestProblems,
            ["preview_error"] = PreviewError,
            ["current_folder"] = CurrentFolder,
            ["is_dirty"] = IsDirty,
            ["can_undo"] = CanUndo,
            ["can_redo"] = CanRedo,
            ["preview_mode"] = PreviewModeName(PreviewMode),
            ["preview_backdrop"] = BackdropName(PreviewBackdrop),
            ["tokens"] = tokensObj,
        }.ToJsonString();
    }

    private string DescribeTokensText(string? group, string? search)
    {
        string gFilter = (group ?? string.Empty).Trim();
        string sFilter = (search ?? string.Empty).Trim();
        var lines = TokenCatalog.Tokens
            .Where(t => string.IsNullOrEmpty(gFilter) || t.Group.Equals(gFilter, StringComparison.OrdinalIgnoreCase))
            .Where(t => string.IsNullOrEmpty(sFilter)
                || t.Key.Contains(sFilter, StringComparison.OrdinalIgnoreCase)
                || t.Label.Contains(sFilter, StringComparison.OrdinalIgnoreCase)
                || t.Hint.Contains(sFilter, StringComparison.OrdinalIgnoreCase)
                || t.Group.Contains(sFilter, StringComparison.OrdinalIgnoreCase))
            .Select(t =>
            {
                var flags = new List<string>();
                if (t.SupportsOpacity) flags.Add("opacity");
                if (t.SupportsGradient) flags.Add("gradient");
                string flagText = flags.Count > 0 ? $" ({string.Join(", ", flags)})" : string.Empty;
                return $"{t.Key} [{t.Group}] {t.Label}: {t.Hint}{flagText}";
            })
            .ToList();

        return lines.Count == 0
            ? "No tokens matched the given filter."
            : string.Join("\n", lines);
    }

    private McpToolResult RenderPreviewTool(JsonObject a)
    {
        if (Dialogs == null)
            return McpToolResult.Error("Preview renderer is unavailable because the main window is not attached.");

        Refresh();
        int mode = ParsePreviewMode(GetStr(a, "mode"), 0);
        double defaultScale = mode == 4 ? 1.25 : 1.5;
        double scale = Math.Clamp(GetNum(a, "scale") ?? defaultScale, 0.5, 2.5);
        int? backdrop = ParseBackdrop(GetStr(a, "backdrop"), 0);
        string? outputPath = GetStr(a, "output_path");

        var rendered = Dialogs.RenderPreviewPng(BuildState(), mode, scale, backdrop);
        if (rendered == null || rendered.PngBytes.Length == 0)
            return McpToolResult.Error(HasPreviewError
                ? $"Could not render preview because of XAML error: {PreviewError}"
                : "Could not render preview image.");

        string savedNote = string.Empty;
        if (!string.IsNullOrWhiteSpace(outputPath))
        {
            string full = Path.GetFullPath(outputPath.Trim());
            if (!full.EndsWith(".png", StringComparison.OrdinalIgnoreCase))
                full += ".png";
            Directory.CreateDirectory(Path.GetDirectoryName(full)!);
            File.WriteAllBytes(full, rendered.PngBytes);
            savedNote = $" Saved copy to {full}.";
        }

        string meta = $"Rendered {PreviewModeName(mode)} preview ({rendered.Width}x{rendered.Height} px, scale {scale:0.##}x, backdrop {BackdropName(backdrop)}).{savedNote}";
        if (HasPreviewError) meta += $" Warning: preview error: {PreviewError}";

        return McpToolResult.Ok(
            McpContentBlock.FromImage(rendered.PngBytes, "image/png"),
            McpContentBlock.FromText(meta));
    }

    private McpToolResult SetPreviewViewTool(JsonObject a)
    {
        if (GetStr(a, "mode") is { } m) PreviewMode = ParsePreviewMode(m, PreviewMode);
        if (GetStr(a, "backdrop") is { } b && ParseBackdrop(b, PreviewBackdrop) is { } bi) PreviewBackdrop = bi;
        if (GetBool(a, "fit") is { } fit) PreviewFit = fit;
        if (GetNum(a, "zoom") is { } zoom)
        {
            PreviewFit = false;
            PreviewZoom = Math.Clamp(zoom, 0.25, 4.0);
        }
        if (a["highlight_tokens"] is JsonArray hiArr)
        {
            var keys = hiArr.Select(x => x?.GetValue<string>()).Where(s => !string.IsNullOrWhiteSpace(s)).Select(s => s!).ToList();
            if (keys.Count > 0) Dialogs?.HighlightPreviewTokens(keys);
        }
        return McpToolResult.Ok($"Preview updated: mode={PreviewModeName(PreviewMode)}, backdrop={BackdropName(PreviewBackdrop)}, fit={PreviewFit}, zoom={PreviewZoom:0.##}.");
    }

    private string ValidateThemeJson()
    {
        Refresh();
        var state = BuildState();
        var manifestIssues = ThemeValidator.ValidateManifest(state);
        string? prepareError = null;
        try { ThemeValidator.Prepare(GeneratedXaml, ResolveSourceFile, out _); }
        catch (Exception ex) { prepareError = ex.Message; }

        Color C(string key) => _tokens[key].ToValue().Representative;
        double main = Math.Round(ColorUtil.Contrast(C("TextLight"), C("CyberMainBg")), 2);
        double card = Math.Round(ColorUtil.Contrast(C("TextLight"), C("CyberCardBg")), 2);
        double muted = Math.Round(ColorUtil.Contrast(C("TextMuted"), C("CyberCardBg")), 2);
        double accent = Math.Round(ColorUtil.Contrast(C("NeonCyan"), C("CyberCardBg")), 2);

        bool exportReady = manifestIssues.Count == 0
            && prepareError == null
            && (!HasPreviewError || ThemeValidator.UsesOverlayOnlyNamespaces(GeneratedXaml));

        return new JsonObject
        {
            ["export_ready"] = exportReady,
            ["manifest_problems"] = new JsonArray(manifestIssues.Select(p => (JsonNode)JsonValue.Create(p)!).ToArray()),
            ["prepare_error"] = prepareError,
            ["preview_error"] = PreviewError,
            ["contrast"] = new JsonObject
            {
                ["pass"] = !ContrastWarning,
                ["text_on_background"] = main,
                ["text_on_card"] = card,
                ["muted_on_card"] = muted,
                ["accent_on_card"] = accent,
                ["summary"] = ContrastSummary,
            },
        }.ToJsonString();
    }

    private McpToolResult GetXamlTool(bool includeCustom)
    {
        Refresh();
        if (!includeCustom)
            return McpToolResult.Ok(GeneratedXaml);

        return McpToolResult.Ok(new JsonObject
        {
            ["generated_xaml"] = GeneratedXaml,
            ["custom_styles"] = CustomStyles,
            ["custom_resources"] = CustomResources,
            ["preview_error"] = PreviewError,
        }.ToJsonString());
    }

    private McpToolResult SetTokensTool(JsonArray? items)
    {
        if (items == null || items.Count == 0)
            return McpToolResult.Error("tokens array is required and must contain at least one item.");

        var done = new List<string>();
        var problems = new List<string>();

        _suppressChanges = true;
        try
        {
            foreach (var node in items.OfType<JsonObject>())
            {
                string key = GetStr(node, "key") ?? string.Empty;
                if (!_tokens.TryGetValue(key, out var vm))
                {
                    problems.Add($"unknown key '{key}'");
                    continue;
                }

                var current = vm.ToValue();
                Color color = current.Color;
                if (GetStr(node, "color") is { } colorStr)
                {
                    if (!ColorUtil.TryParse(colorStr, out var parsedColor))
                    {
                        problems.Add($"invalid color '{colorStr}' for {key}");
                        continue;
                    }
                    color = parsedColor;
                }

                double opacity = GetNum(node, "opacity") is { } op
                    ? (vm.SupportsOpacity ? Math.Clamp(op, 0, 1) : 1.0)
                    : current.Opacity;

                GradientSpec? gradient = current.Gradient;
                if (GetBool(node, "clear_gradient") == true || (node.ContainsKey("gradient") && node["gradient"] == null))
                {
                    gradient = null;
                }
                else if (node["gradient"] is JsonArray or JsonObject)
                {
                    if (!vm.SupportsGradient)
                    {
                        gradient = null;
                    }
                    else
                    {
                        JsonArray? gColorsArr = node["gradient"] as JsonArray
                            ?? (node["gradient"] as JsonObject)?["colors"] as JsonArray;
                        var gObj = node["gradient"] as JsonObject;
                        if (gColorsArr == null || gColorsArr.Count == 0)
                        {
                            gradient = null;
                        }
                        else
                        {
                            var extra = new List<Color>();
                            foreach (var c in gColorsArr)
                                if (ColorUtil.TryParse(c?.GetValue<string>(), out var parsed)) extra.Add(parsed);
                            if (extra.Count > 0)
                            {
                                double angle = (gObj != null ? GetNum(gObj, "angle") : null)
                                    ?? GetNum(node, "angle")
                                    ?? current.Gradient?.Angle
                                    ?? 90;
                                List<double>? offsets = null;
                                var offArr = (gObj?["offsets"] as JsonArray) ?? (node["offsets"] as JsonArray);
                                if (offArr is { Count: > 0 })
                                {
                                    offsets = new List<double>();
                                    foreach (var o in offArr)
                                        if (o is JsonValue ov && ov.TryGetValue<double>(out double d)) offsets.Add(d);
                                }
                                gradient = new GradientSpec(extra.Take(GradientSpec.MaxExtraStops).ToList(), angle, offsets);
                            }
                            else
                            {
                                gradient = null;
                            }
                        }
                    }
                }
                else if (gradient != null && (GetNum(node, "angle") is not null || node["offsets"] is JsonArray))
                {
                    double angle = GetNum(node, "angle") ?? gradient.Angle;
                    IReadOnlyList<double>? offsets = gradient.Offsets;
                    if (node["offsets"] is JsonArray offArr && offArr.Count > 0)
                    {
                        var parsedOffsets = new List<double>();
                        foreach (var o in offArr)
                            if (o is JsonValue ov && ov.TryGetValue<double>(out double d)) parsedOffsets.Add(d);
                        offsets = parsedOffsets;
                    }
                    gradient = new GradientSpec(gradient.Colors, angle, offsets);
                }

                TokenAnimation? animation = current.Animation;
                if (GetBool(node, "clear_animation") == true || (node.ContainsKey("animation") && node["animation"] == null))
                {
                    animation = null;
                }
                else if (node["animation"] is JsonObject animObj)
                {
                    var animColors = new List<Color>();
                    if (animObj["colors"] is JsonArray acArr)
                    {
                        foreach (var c in acArr)
                            if (ColorUtil.TryParse(c?.GetValue<string>(), out var parsed)) animColors.Add(parsed);
                    }
                    if (animColors.Count < 2)
                    {
                        problems.Add($"animation for {key} needs at least 2 valid hex colours");
                    }
                    else
                    {
                        bool flow = GetBool(animObj, "flow") ?? false;
                        double seconds = Math.Clamp(GetNum(animObj, "seconds") ?? 4.0, 0.5, 60.0);
                        double animAngle = GetNum(animObj, "angle") ?? 0.0;
                        animation = new TokenAnimation(animColors.Take(TokenAnimation.MaxColors).ToList(), flow, seconds, animAngle);
                    }
                }

                vm.SetValue(new TokenValue(color, opacity, gradient, animation));
                done.Add(key);
            }
        }
        finally
        {
            _suppressChanges = false;
        }

        Refresh();
        string summary = $"Updated {done.Count} token(s).";
        if (problems.Count > 0) summary += " Issues: " + string.Join("; ", problems);
        SetStatus($"MCP updated {done.Count} colour token(s).");
        string full = summary + $"\n{ContrastSummary}";
        return HasPreviewError
            ? McpToolResult.Ok($"{full}\nPreview error: {PreviewError}")
            : McpToolResult.Ok(full);
    }

    private McpToolResult GeneratePaletteTool(JsonObject a)
    {
        if (!ColorUtil.TryParse(GetStr(a, "accent"), out var accent))
            return McpToolResult.Error("Valid hex 'accent' colour is required (e.g. #00f0ff).");

        GeneratorAccent = accent;
        GeneratorMood = Math.Clamp(GetInt(a, "mood") ?? 0, 0, 2);
        GeneratorStatusColours = GetBool(a, "status_colours") ?? false;
        GeneratePalette();
        return StatusResult($"Generated palette from {ColorUtil.ToHex(accent)} (mood={MoodNames[GeneratorMood]}, status_colours={GeneratorStatusColours}).\n{ContrastSummary}");
    }

    private McpToolResult SetAprmBoxTool(JsonObject a)
    {
        if (GetBool(a, "enabled") is { } en) AprmBoxEnabled = en;
        if (GetStr(a, "border_color") is { } bc)
        {
            if (!ColorUtil.TryParse(bc, out var c)) return McpToolResult.Error($"Invalid border_color '{bc}'.");
            AprmBoxBorderColor = c;
        }
        if (GetStr(a, "text_color") is { } tc)
        {
            if (!ColorUtil.TryParse(tc, out var c)) return McpToolResult.Error($"Invalid text_color '{tc}'.");
            AprmBoxTextColor = c;
        }
        if (GetStr(a, "bar_color") is { } barc)
        {
            if (!ColorUtil.TryParse(barc, out var c)) return McpToolResult.Error($"Invalid bar_color '{barc}'.");
            AprmBoxBarColor = c;
        }
        return StatusResult($"APRM box updated: enabled={AprmBoxEnabled}, border={ColorUtil.ToHex(AprmBoxBorderColor)}, text={ColorUtil.ToHex(AprmBoxTextColor)}, bar={ColorUtil.ToHex(AprmBoxBarColor)}.");
    }

    private string ListPresetsJson()
    {
        var arr = new JsonArray();
        for (int i = 0; i < Presets.Count; i++)
        {
            arr.Add(new JsonObject
            {
                ["index"] = i,
                ["name"] = Presets[i].Name,
                ["description"] = Presets[i].Description,
            });
        }
        return arr.ToJsonString();
    }

    private McpToolResult LoadPresetTool(JsonObject a)
    {
        ThemePreset? preset = null;
        if (GetStr(a, "name") is { } name && !string.IsNullOrWhiteSpace(name))
        {
            preset = Presets.FirstOrDefault(p => p.Name.Equals(name.Trim(), StringComparison.OrdinalIgnoreCase))
                  ?? Presets.FirstOrDefault(p => p.Name.Contains(name.Trim(), StringComparison.OrdinalIgnoreCase));
        }
        else if (GetInt(a, "index") is { } idx && idx >= 0 && idx < Presets.Count)
        {
            preset = Presets[idx];
        }

        if (preset == null)
            return McpToolResult.Error("Preset not found. Call list_presets to see available names and indices.");

        LoadState(preset.Create(), folder: null);
        SetStatus($"MCP loaded preset '{preset.Name}'.");
        return StatusResult($"Loaded preset '{preset.Name}'.");
    }

    private McpToolResult SetThemeInfoTool(JsonObject a)
    {
        if (GetStr(a, "name") is { } name) ThemeName = name;
        if (GetStr(a, "id") is { } id) ThemeId = ThemeValidator.SanitizeId(id);
        if (GetStr(a, "author") is { } author) Author = author;
        if (GetStr(a, "version") is { } version) Version = version;
        if (GetStr(a, "description") is { } desc) Description = desc;
        if (GetStr(a, "min_app_version") is { } minVer) MinAppVersion = minVer;
        if (GetStr(a, "font_family") is { } ff) FontFamily = ff;
        if (GetStr(a, "mono_font_family") is { } mff) MonoFontFamily = mff;
        return StatusResult($"Theme info updated: id='{ThemeId}', name='{ThemeName}', version='{Version}'.");
    }

    private McpToolResult SetShapeTool(JsonObject a)
    {
        if (GetBool(a, "reset") == true) ResetShape();
        if (GetBool(a, "enabled") is { } en) ShapeEnabled = en;
        if (GetNum(a, "shell_corner_radius") is { } scr) ShellCornerRadius = Math.Clamp(scr, 0, 30);
        if (GetNum(a, "shell_border_thickness") is { } sbt) ShellBorderThickness = Math.Clamp(sbt, 0, 6);
        if (GetNum(a, "card_corner_radius") is { } ccr) CardCornerRadius = Math.Clamp(ccr, 0, 20);
        if (GetNum(a, "button_corner_radius") is { } bcr) ButtonCornerRadius = Math.Clamp(bcr, 0, 20);
        if (GetNum(a, "compact_corner_radius") is { } cpr) CompactCornerRadius = Math.Clamp(cpr, 0, 30);
        if (GetBool(a, "shell_glow") is { } glow) ShellGlow = glow;
        if (GetNum(a, "shell_glow_blur") is { } blur) ShellGlowBlur = Math.Clamp(blur, 0, 40);
        return StatusResult($"Shape updated (enabled={ShapeEnabled}).");
    }

    private McpToolResult SetCustomXamlTool(JsonObject a)
    {
        if (GetStr(a, "styles") is { } styles) CustomStyles = styles;
        if (GetStr(a, "resources") is { } res) CustomResources = res;
        if (GetStr(a, "append_snippet") is { } snippet && !string.IsNullOrWhiteSpace(snippet))
            InsertStyleSnippet(snippet.Trim().ToLowerInvariant());
        return StatusResult("Custom XAML updated.");
    }

    private string ListFontsJson(string? filter)
    {
        bool Match(string s) => string.IsNullOrWhiteSpace(filter) || s.Contains(filter.Trim(), StringComparison.OrdinalIgnoreCase);
        var bundled = Fonts
            .Where(f => Match(f.FileName) || Match(f.FamilyName))
            .Select(f => (JsonNode)new JsonObject { ["file_name"] = f.FileName, ["family_name"] = f.FamilyName })
            .ToArray();
        var system = FontManager.Current.SystemFonts
            .Select(f => f.Name)
            .Where(Match)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .OrderBy(n => n)
            .Take(80)
            .Select(n => (JsonNode)JsonValue.Create(n)!)
            .ToArray();

        return new JsonObject
        {
            ["current_main"] = FontFamily,
            ["current_mono"] = MonoFontFamily,
            ["bundled_fonts"] = new JsonArray(bundled),
            ["system_fonts"] = new JsonArray(system),
        }.ToJsonString();
    }

    private McpToolResult AddFontFileTool(string? path, string? useAs)
    {
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
            return McpToolResult.Error("Font file not found at the given path.");
        if (!FontTools.IsFontFile(path))
            return McpToolResult.Error("Only .ttf, .otf, and .ttc font files are supported.");

        string safeName = SafeFileName(path);
        if (AddFontFiles([path]) <= 0)
            return McpToolResult.Error("Could not add font file.");

        var entry = Fonts.LastOrDefault(f => f.FileName.Equals(safeName, StringComparison.OrdinalIgnoreCase));
        if (entry == null)
            return McpToolResult.Error("Font was not found after adding.");

        if (string.Equals(useAs, "main", StringComparison.OrdinalIgnoreCase))
            UseFontAsMain(entry);
        else if (string.Equals(useAs, "mono", StringComparison.OrdinalIgnoreCase))
            UseFontAsMono(entry);

        return StatusResult($"Added font '{entry.FileName}' (family: '{entry.FamilyName}'). Main='{FontFamily}', Mono='{MonoFontFamily}'.");
    }

    private McpToolResult RemoveFontTool(string? fileName)
    {
        if (string.IsNullOrWhiteSpace(fileName))
            return McpToolResult.Error("file_name is required.");
        var entry = Fonts.FirstOrDefault(f => f.FileName.Equals(fileName.Trim(), StringComparison.OrdinalIgnoreCase));
        if (entry == null)
            return McpToolResult.Error($"Bundled font '{fileName}' not found.");
        RemoveFont(entry);
        return StatusResult($"Removed font '{entry.FileName}'.");
    }

    private McpToolResult UseFontTool(JsonObject a)
    {
        if (GetBool(a, "reset") == true)
        {
            ResetFonts();
            return StatusResult($"Fonts reset. Main='{FontFamily}', Mono='{MonoFontFamily}'.");
        }

        string? name = GetStr(a, "font")?.Trim();
        string? slot = GetStr(a, "slot")?.Trim();
        if (string.IsNullOrWhiteSpace(name))
            return McpToolResult.Error("font is required unless reset=true.");

        bool mono = string.Equals(slot, "mono", StringComparison.OrdinalIgnoreCase);
        var entry = Fonts.FirstOrDefault(f =>
            f.FileName.Equals(name, StringComparison.OrdinalIgnoreCase)
            || f.FamilyName.Equals(name, StringComparison.OrdinalIgnoreCase));

        string current = mono ? MonoFontFamily : FontFamily;
        string fallback = mono ? BuiltInThemes.Cyberpunk.MonoFontFamily : BuiltInThemes.Cyberpunk.FontFamily;
        string list;

        if (entry != null)
        {
            list = PrependFontReference(entry, current, fallback);
        }
        else
        {
            if (!FontManager.Current.SystemFonts.Any(f => f.Name.Equals(name, StringComparison.OrdinalIgnoreCase)))
                return McpToolResult.Error($"'{name}' is not a bundled theme font or installed system font. Call list_fonts to inspect available fonts.");
            var rest = current.Split(',').Select(s => s.Trim())
                .Where(s => s.Length > 0 && !s.Trim('\'', '"').Equals(name, StringComparison.OrdinalIgnoreCase));
            list = string.Join(", ", new[] { name }.Concat(rest));
        }

        if (mono) MonoFontFamily = list;
        else FontFamily = list;
        return StatusResult($"{(mono ? "Mono" : "Main")} font updated to: {list}");
    }

    private string ListAssetsJson() => new JsonObject
    {
        ["assets"] = new JsonArray(Assets.Select(a => (JsonNode)new JsonObject
        {
            ["file_name"] = a.FileName,
            ["source_path"] = a.SourcePath,
            ["xaml_reference"] = $"assets/{a.FileName}",
        }).ToArray()),
        ["background_image"] = HasBackgroundImage ? new JsonObject
        {
            ["file_name"] = BackgroundImageFile,
            ["opacity"] = Math.Round(BackgroundImageOpacity, 3),
            ["stretch"] = BackgroundStretch,
        } : null,
        ["custom_thumbnail"] = CustomThumbnailPath,
    }.ToJsonString();

    private McpToolResult AddImageAssetTool(string? path, bool setAsBackground)
    {
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
            return McpToolResult.Error("Image file not found at the given path.");
        if (!FontTools.IsImageFile(path))
            return McpToolResult.Error("Unsupported image format. Use .png, .jpg, .jpeg, .webp, .bmp, or .gif.");

        string safeName = SafeFileName(path);
        if (AddImageFiles([path], setAsBackground) <= 0)
            return McpToolResult.Error("Could not add image asset.");

        return StatusResult($"Added image asset 'assets/{safeName}'{(setAsBackground ? " and set as background image" : string.Empty)}.");
    }

    private McpToolResult RemoveImageAssetTool(string? fileName)
    {
        if (string.IsNullOrWhiteSpace(fileName))
            return McpToolResult.Error("file_name is required.");
        var asset = Assets.FirstOrDefault(a => a.FileName.Equals(fileName.Trim(), StringComparison.OrdinalIgnoreCase));
        if (asset == null)
            return McpToolResult.Error($"Asset '{fileName}' not found.");
        RemoveAsset(asset);
        return StatusResult($"Removed asset '{asset.FileName}'.");
    }

    private McpToolResult SetBackgroundImageTool(JsonObject a)
    {
        if (GetBool(a, "clear") == true)
        {
            ClearBackgroundImage();
            return StatusResult("Background image cleared.");
        }

        if (GetStr(a, "file_name") is { } fn)
        {
            string clean = fn.Trim();
            if (clean.Length == 0)
            {
                ClearBackgroundImage();
            }
            else
            {
                if (clean.StartsWith("assets/", StringComparison.OrdinalIgnoreCase)) clean = clean[7..];
                var match = Assets.FirstOrDefault(x => x.FileName.Equals(clean, StringComparison.OrdinalIgnoreCase));
                if (match == null)
                    return McpToolResult.Error($"Asset '{clean}' is not in assets/. Add it first with add_image_asset.");
                BackgroundImageFile = null;
                BackgroundImageFile = match.FileName;
            }
        }
        if (GetNum(a, "opacity") is { } op) BackgroundImageOpacity = Math.Clamp(op, 0, 1);
        if (GetStr(a, "stretch") is { } st && StretchModes.Contains(st, StringComparer.OrdinalIgnoreCase))
            BackgroundStretch = StretchModes.First(m => m.Equals(st, StringComparison.OrdinalIgnoreCase));

        return StatusResult($"Background image updated: file='{BackgroundImageFile ?? "(none)"}', opacity={BackgroundImageOpacity:0.##}, stretch={BackgroundStretch}.");
    }

    private McpToolResult SetCustomThumbnailTool(string? path, bool clear)
    {
        if (clear)
        {
            UseAutoThumbnail();
            return StatusResult("Custom thumbnail cleared; automatic MONITOR preview will be used.");
        }
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
            return McpToolResult.Error("Thumbnail image file not found at the given path.");
        string? png = PreviewImage.MakeThumbnail(path, out string error);
        if (png == null)
            return McpToolResult.Error($"Thumbnail could not be created: {error}");
        CustomThumbnailPath = png;
        return StatusResult("Custom thumbnail set (used as preview.png on save/export/install).");
    }

    private string ListInstalledThemesJson() => new JsonObject
    {
        ["overlay_themes_directory"] = OverlayThemesDirectory,
        ["current_folder"] = CurrentFolder,
        ["installed"] = new JsonArray(InstalledThemes.Select(t => (JsonNode)new JsonObject
        {
            ["id"] = t.Id,
            ["name"] = t.Name,
            ["directory"] = t.Directory,
        }).ToArray()),
        ["recent"] = new JsonArray(RecentThemes.Select(r => (JsonNode)new JsonObject
        {
            ["name"] = r.Name,
            ["folder"] = r.Folder,
        }).ToArray()),
    }.ToJsonString();

    private McpToolResult OpenThemeTool(string? path, string? installedId)
    {
        string? resolved = path?.Trim();
        if (string.IsNullOrWhiteSpace(resolved) && !string.IsNullOrWhiteSpace(installedId))
        {
            RefreshInstalledThemes();
            var match = InstalledThemes.FirstOrDefault(t => t.Id.Equals(installedId.Trim(), StringComparison.OrdinalIgnoreCase));
            if (match == null)
                return McpToolResult.Error($"Installed theme '{installedId}' not found.");
            resolved = match.Directory;
        }
        if (string.IsNullOrWhiteSpace(resolved) || (!Directory.Exists(resolved) && !File.Exists(resolved)))
            return McpToolResult.Error("Provide an existing local 'path' or valid 'installed_id'.");

        OpenPath(resolved);
        return StatusResult($"Opened theme '{ThemeName}' (id='{ThemeId}', folder='{CurrentFolder ?? "(unsaved)"}').");
    }

    private McpToolResult SaveThemeTool(string? folder)
    {
        if (!EnsureValidForExport(out var state))
            return McpToolResult.Error(StatusMessage);

        string? target = string.IsNullOrWhiteSpace(folder) ? CurrentFolder : Path.GetFullPath(folder.Trim());
        if (string.IsNullOrWhiteSpace(target))
            return McpToolResult.Error("Theme has no current folder yet. Pass 'folder' (target directory path) to save.");

        WriteFolderTo(state, target);
        return StatusIsError ? McpToolResult.Error(StatusMessage) : McpToolResult.Ok(StatusMessage);
    }

    private McpToolResult ExportZipTool(string? path)
    {
        if (string.IsNullOrWhiteSpace(path))
            return McpToolResult.Error("Destination 'path' (.zip) is required.");
        if (!EnsureValidForExport(out var state))
            return McpToolResult.Error(StatusMessage);

        string full = Path.GetFullPath(path.Trim());
        if (!full.EndsWith(".zip", StringComparison.OrdinalIgnoreCase))
            full += ".zip";
        Directory.CreateDirectory(Path.GetDirectoryName(full)!);

        var warnings = ThemeExporter.WriteZip(state, GeneratedXaml, full, RenderThumbnail());
        RememberAuthor();
        string msg = warnings.Count == 0
            ? $"Exported theme zip to {full}."
            : $"Exported to {full} with warnings: {string.Join(" ", warnings)}";
        SetStatus(msg, warnings.Count > 0);
        return McpToolResult.Ok(msg);
    }

    private McpToolResult InstallToOverlayTool(string? overlayDirOverride)
    {
        if (!EnsureValidForExport(out var state))
            return McpToolResult.Error(StatusMessage);

        string dir = !string.IsNullOrWhiteSpace(overlayDirOverride)
            ? OverlayLocator.NormaliseSelection(overlayDirOverride.Trim())
            : OverlayThemesDirectory;

        if (string.IsNullOrWhiteSpace(dir))
            return McpToolResult.Error("Overlay themes directory is not configured. Pass 'overlay_themes_dir' or detect the overlay first.");

        string target = Path.Combine(dir, state.Manifest.Id);
        var warnings = ThemeExporter.WriteFolder(state, GeneratedXaml, target, RenderThumbnail());
        RememberAuthor();
        if (CurrentFolder != null && string.Equals(Path.GetFullPath(CurrentFolder), Path.GetFullPath(target), StringComparison.OrdinalIgnoreCase))
            MarkSaved(target);
        RefreshInstalledThemes();
        string msg = warnings.Count == 0
            ? $"Installed '{state.Manifest.Name}' ({state.Manifest.Id}) to {target}."
            : $"Installed to {target} with warnings: {string.Join(" ", warnings)}";
        SetStatus(msg, warnings.Count > 0);
        return McpToolResult.Ok(msg);
    }

    private McpToolResult DetectOverlayTool(string? explicitDir)
    {
        if (!string.IsNullOrWhiteSpace(explicitDir))
        {
            OverlayThemesDirectory = OverlayLocator.NormaliseSelection(explicitDir.Trim());
            RefreshInstalledThemes();
            SetStatus($"Overlay themes directory set to {OverlayThemesDirectory}");
        }
        else
        {
            string? found = OverlayLocator.Detect();
            if (!string.IsNullOrWhiteSpace(found))
            {
                OverlayThemesDirectory = found;
                RefreshInstalledThemes();
                SetStatus($"Detected overlay themes directory: {found}");
            }
            else
            {
                RefreshInstalledThemes();
                return McpToolResult.Error("Could not automatically detect the RBWR Overlay themes directory. Pass 'overlay_themes_dir' explicitly.");
            }
        }
        return McpToolResult.Ok(ListInstalledThemesJson());
    }

    private McpToolResult DeleteInstalledThemeTool(string? installedId)
    {
        if (string.IsNullOrWhiteSpace(installedId))
            return McpToolResult.Error("installed_id is required.");

        RefreshInstalledThemes();
        var match = InstalledThemes.FirstOrDefault(t => t.Id.Equals(installedId.Trim(), StringComparison.OrdinalIgnoreCase));
        if (match == null)
            return McpToolResult.Error($"Installed theme '{installedId}' not found.");

        if (!Directory.Exists(match.Directory))
            return McpToolResult.Error($"Directory not found: {match.Directory}");

        Directory.Delete(match.Directory, recursive: true);
        if (CurrentFolder != null && string.Equals(Path.GetFullPath(CurrentFolder), Path.GetFullPath(match.Directory), StringComparison.OrdinalIgnoreCase))
            CurrentFolder = null;
        RefreshInstalledThemes();
        SetStatus($"Deleted installed theme '{match.Name}' ({match.Id}).");
        return McpToolResult.Ok($"Deleted installed theme '{match.Name}' ({match.Id}) from {match.Directory}.");
    }

    private static string GetSelectorReferenceJson() => new JsonObject
    {
        ["surface_classes"] = new JsonArray(
            "overlay-shell", "popup-shell", "compact-shell", "overlay-title",
            "status-pill", "sync-pill", "hud-card", "sub-panel", "hud-header",
            "nav-bar", "power-banner", "power-readout", "power-subtext",
            "preset-card", "metric-card", "hud-footer", "config-card",
            "sync-card", "feedback-card"),
        ["button_classes"] = new JsonArray(
            "cyber", "cyber-nav", "cyber-blue", "cyber-green", "cyber-gold",
            "cyber-red", "cyber-header-btn", "cyber-close", "cyber-close-btn",
            "cyber-preset", "cyber-tick"),
        ["pseudo_and_state_classes"] = new JsonArray(
            ":pointerover", ":pressed", ".active", ".error"),
        ["input_and_control_selectors"] = new JsonArray(
            "TextBox.cyber", "ComboBox.cyber", "ProgressBar.cyber-power", "Slider", "ToolTip"),
        ["named_elements"] = new JsonArray(
            "#DetailedShell", "#HeaderBar", "#OverlayTitle", "#SyncBadge", "#NavBar",
            "#PowerBanner", "#MainPowerReadout", "#MainPowerBar", "#MainPowerSubtext",
            "#DemandPresetCard", "#DemandPresetSlider", "#MonitorMetricsGrid",
            "#DemandInputCard", "#CorePowerCard", "#GenLoadCard", "#FlowCard",
            "#StatusFooterBar", "#ThemeConfigCard", "#UiScaleSlider",
            "#CompactShell", "#CompactDemandInput", "#CompactCounterButton"),
        ["built_in_snippets"] = new JsonObject
        {
            ["title"] = "TextBlock#OverlayTitle (FontSize=13, LetterSpacing=2)",
            ["nav"] = "Button.cyber-nav.active (BorderThickness=0,0,0,3)",
            ["readout"] = "TextBlock.power-readout (FontSize=28)",
            ["image"] = "Border#PowerBanner (ImageBrush background from assets/banner.png)",
        },
        ["asset_reference_syntax"] = "Use bundled assets in custom XAML via Source=\"assets/<file_name>\" (add them first with add_image_asset).",
        ["disallowed_in_overlay"] = new JsonArray(
            "x:Class", "StyleInclude", "ResourceInclude", "clr-namespace", "non-Avalonia using: namespaces"),
    }.ToJsonString();
}
