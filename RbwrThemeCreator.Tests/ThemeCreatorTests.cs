using System.IO.Compression;
using Avalonia.Media;
using RbwrOverlay.Core.Models;
using RbwrThemeCreator.Models;
using RbwrThemeCreator.Services;
using RbwrThemeCreator.ViewModels;

namespace RbwrThemeCreator.Tests;

public class ThemeCreatorTests : IDisposable
{
    private readonly string _tempDir;
    private static readonly byte[] TinyPng = Convert.FromBase64String(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=");

    public ThemeCreatorTests()
    {
        _tempDir = Path.Combine(Path.GetTempPath(), "rbwr_tc_tests_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(_tempDir);
    }

    public void Dispose()
    {
        try
        {
            if (Directory.Exists(_tempDir))
                Directory.Delete(_tempDir, recursive: true);
        }
        catch { }
    }

    // ==================== ColorUtil ====================

    [Theory]
    [InlineData("#00f0ff", 255, 0, 240, 255)]
    [InlineData("ff003c", 255, 255, 0, 60)]
    [InlineData("#f0a", 255, 255, 0, 170)]
    [InlineData("#8000f0ff", 128, 0, 240, 255)]
    public void ColorUtil_TryParse_ValidFormats(string input, byte a, byte r, byte g, byte b)
    {
        Assert.True(ColorUtil.TryParse(input, out var c));
        Assert.Equal(Color.FromArgb(a, r, g, b), c);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("#12345")]
    [InlineData("#zzzzzz")]
    public void ColorUtil_TryParse_InvalidFormatsReturnFalse(string? input)
    {
        Assert.False(ColorUtil.TryParse(input, out _));
    }

    [Fact]
    public void ColorUtil_ToHex_Hsl_Contrast_And_Helpers()
    {
        Assert.Equal("#00f0ff", ColorUtil.ToHex(Color.Parse("#00f0ff")));
        Assert.Equal("#8000f0ff", ColorUtil.ToHex(Color.Parse("#8000f0ff")));

        var orig = Color.Parse("#3b82f6");
        var (h, s, l) = ColorUtil.ToHsl(orig);
        var roundTrip = ColorUtil.FromHsl(h, s, l);
        Assert.InRange(Math.Abs(orig.R - roundTrip.R), 0, 2);
        Assert.InRange(Math.Abs(orig.G - roundTrip.G), 0, 2);
        Assert.InRange(Math.Abs(orig.B - roundTrip.B), 0, 2);

        Assert.Equal(21.0, Math.Round(ColorUtil.Contrast(Colors.White, Colors.Black), 1));
        Assert.Equal(1.0, Math.Round(ColorUtil.Contrast(Colors.Cyan, Colors.Cyan), 1));

        var alpha = ColorUtil.WithAlpha(Colors.Red, 0x44);
        Assert.Equal(0x44, alpha.A);
        Assert.Equal(Colors.Red.R, alpha.R);

        var lighter = ColorUtil.Lighten(Color.Parse("#203040"), 0.2);
        Assert.True(ColorUtil.ToHsl(lighter).L > ColorUtil.ToHsl(Color.Parse("#203040")).L);
    }

    // ==================== BuiltInThemes & PaletteGenerator ====================

    [Fact]
    public void BuiltInThemes_LoadsCyberpunkAmberAndPreviewBaseStylesWithHoverBridge()
    {
        var cp = BuiltInThemes.Cyberpunk;
        Assert.Equal("default", cp.Manifest.Id);
        foreach (var def in TokenCatalog.Tokens)
            Assert.True(cp.Tokens.ContainsKey(def.Key), $"Missing token {def.Key}");

        var hoverBridge = BuiltInThemes.LoadPreviewHoverBridgeStyles();
        Assert.True(hoverBridge.Count >= 15);
        Assert.Equal(5, BuiltInThemes.Presets.Count);
        foreach (var preset in BuiltInThemes.Presets)
        {
            var s = preset.Create();
            Assert.False(string.IsNullOrWhiteSpace(s.Manifest.Id));
            Assert.Equal(TokenCatalog.Tokens.Count, s.Tokens.Count);
        }
    }

    [Fact]
    public void GradientBrushes_SynthwavePresetRoundTripsThroughGeneratorAndImporter()
    {
        var synthwave = BuiltInThemes.Presets.First(p => p.Name.Contains("Synthwave", StringComparison.OrdinalIgnoreCase)).Create();
        Assert.NotNull(synthwave.Tokens["CyberMainBg"].Gradient);

        string xaml = ThemeXamlGenerator.Generate(synthwave);
        Assert.Contains("LinearGradientBrush", xaml);

        var imported = ThemeImporter.FromXaml(xaml, synthwave.Manifest, BuiltInThemes.Cyberpunk, includeStyles: true);
        Assert.NotNull(imported.Tokens["CyberMainBg"].Gradient);
        Assert.Equal(synthwave.Tokens["CyberMainBg"].Color, imported.Tokens["CyberMainBg"].Color);
        Assert.Equal(synthwave.Tokens["CyberMainBg"].Gradient!.Colors, imported.Tokens["CyberMainBg"].Gradient!.Colors);

        // Multi-stop gradient with custom offsets round-trip
        var customStops = new GradientSpec([Color.Parse("#ff00ff"), Color.Parse("#00f0ff")], 45, [0.0, 0.35, 1.0]);
        synthwave.Tokens["CyberCardBg"] = new TokenValue(Color.Parse("#101020"), 0.9, customStops);
        string xaml2 = ThemeXamlGenerator.Generate(synthwave);
        var imported2 = ThemeImporter.FromXaml(xaml2, synthwave.Manifest, BuiltInThemes.Cyberpunk, includeStyles: true);
        var g2 = imported2.Tokens["CyberCardBg"].Gradient;
        Assert.NotNull(g2);
        Assert.Equal(2, g2!.Colors.Count);
        Assert.NotNull(g2.Offsets);
        Assert.Equal(0.35, g2.Offsets![1], 2);
    }

    [Theory]
    [InlineData(PaletteGenerator.Mood.Dark, true)]
    [InlineData(PaletteGenerator.Mood.Tinted, true)]
    [InlineData(PaletteGenerator.Mood.Neutral, false)]
    public void PaletteGenerator_PopulatesAllTokens(PaletteGenerator.Mood mood, bool keepStatus)
    {
        var state = BuiltInThemes.Cyberpunk.Clone();
        var origGreen = state.Tokens["NeonGreen"].Color;
        var accent = Color.Parse("#ff5500");

        PaletteGenerator.Apply(state, accent, mood, keepStatusColours: keepStatus);

        Assert.Equal(accent, state.Tokens["NeonCyan"].Color);
        Assert.Equal(accent, state.Tokens["CyberBorderGlow"].Color);
        if (keepStatus)
            Assert.Equal(origGreen, state.Tokens["NeonGreen"].Color);
        foreach (var def in TokenCatalog.Tokens)
            Assert.True(state.Tokens.ContainsKey(def.Key));
    }

    // ==================== ThemeValidator ====================

    [Fact]
    public void ThemeValidator_SanitizeId_And_ValidateManifest()
    {
        Assert.Equal("my-cool_theme", ThemeValidator.SanitizeId("  My Cool_Theme!!  "));
        Assert.Equal(string.Empty, ThemeValidator.SanitizeId("   "));

        var bad = new ThemeState
        {
            Manifest = new ThemeManifest { Id = "default", Name = "", Version = "not-a-ver" }
        };
        var problems = ThemeValidator.ValidateManifest(bad);
        Assert.Contains(problems, p => p.Contains("name is empty", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(problems, p => p.Contains("reserved", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(problems, p => p.Contains("Version", StringComparison.OrdinalIgnoreCase));

        var amber = new ThemeState { Manifest = new ThemeManifest { Id = "reactor-amber", Name = "Amber", Version = "1.0.0" } };
        Assert.Contains(ThemeValidator.ValidateManifest(amber), p => p.Contains("reserved", StringComparison.OrdinalIgnoreCase));

        var uppercase = new ThemeState { Manifest = new ThemeManifest { Id = "MyTheme", Name = "My Theme", Version = "1.0.0" } };
        Assert.Contains(ThemeValidator.ValidateManifest(uppercase), p => p.Contains("suggested: 'mytheme'", StringComparison.OrdinalIgnoreCase));

        var ok = new ThemeState { Manifest = new ThemeManifest { Id = "my-theme", Name = "My Theme", Version = "1.2.3" } };
        Assert.Empty(ThemeValidator.ValidateManifest(ok));
    }

    [Fact]
    public void ThemeValidator_Prepare_SecurityAndResourceRewriting()
    {
        string fontPath = Path.Combine(_tempDir, "Orbitron.ttf");
        string imgPath = Path.Combine(_tempDir, "bg.png");
        File.WriteAllBytes(fontPath, [0x00, 0x01, 0x00, 0x00]);
        File.WriteAllBytes(imgPath, TinyPng);

        string? Resolver(string rel) => rel switch
        {
            "fonts/Orbitron.ttf" => fontPath,
            "assets/bg.png" => imgPath,
            _ => null
        };

        string valid = """
<Styles xmlns="https://github.com/avaloniaui" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
    <Styles.Resources>
        <FontFamily x:Key="AppFontFamily">fonts/Orbitron.ttf#Orbitron</FontFamily>
        <ImageBrush x:Key="CyberMainBg" Source="assets/bg.png" />
        <ImageBrush x:Key="ExtraBg" Source="assets/bg.png" />
    </Styles.Resources>
</Styles>
""";
        string prepared = ThemeValidator.Prepare(valid, Resolver, out var assets);
        Assert.Contains("file:///", prepared);
        Assert.Contains("#Orbitron", prepared);
        Assert.Single(assets); // deduplicated
        Assert.Contains("Source=\"{DynamicResource __theme_asset_0}\"", prepared);

        // Missing font / image
        Assert.Throws<FileNotFoundException>(() => ThemeValidator.Prepare(
            "<Styles xmlns=\"https://github.com/avaloniaui\"><Styles.Resources><FontFamily x:Key=\"A\">fonts/missing.ttf#X</FontFamily></Styles.Resources></Styles>",
            Resolver, out _));
        Assert.Throws<FileNotFoundException>(() => ThemeValidator.Prepare(
            "<Styles xmlns=\"https://github.com/avaloniaui\"><Styles.Resources><ImageBrush x:Key=\"A\" Source=\"assets/missing.png\" /></Styles.Resources></Styles>",
            Resolver, out _));

        // Security blocks
        Assert.Throws<InvalidOperationException>(() => ThemeValidator.Prepare(
            "<Styles xmlns=\"https://github.com/avaloniaui\" xmlns:s=\"clr-namespace:System\"></Styles>", Resolver, out _));
        Assert.Throws<InvalidOperationException>(() => ThemeValidator.Prepare(
            "<Styles xmlns=\"https://github.com/avaloniaui\" xmlns:e=\"using:AvaloniaEvil\"></Styles>", Resolver, out _));
        Assert.Throws<InvalidOperationException>(() => ThemeValidator.Prepare(
            "<Styles xmlns=\"https://github.com/avaloniaui\" xmlns:x=\"http://schemas.microsoft.com/winfx/2006/xaml\" x:Class=\"Evil\"></Styles>", Resolver, out _));
        Assert.Throws<InvalidOperationException>(() => ThemeValidator.Prepare(
            "<Styles xmlns=\"https://github.com/avaloniaui\"><StyleInclude Source=\"file:///evil.axaml\" /></Styles>", Resolver, out _));

        // Overlay-only namespaces detected
        Assert.True(ThemeValidator.UsesOverlayOnlyNamespaces(
            "<Styles xmlns=\"https://github.com/avaloniaui\" xmlns:b=\"using:RbwrOverlay.UI.Behaviors\"></Styles>"));
    }

    // ==================== Generator <-> Importer <-> Exporter Round-Trip ====================

    [Fact]
    public void GeneratorImporterExporter_FullRoundTrip_FolderAndZip()
    {
        string srcFont = Path.Combine(_tempDir, "TestFont.ttf");
        string srcImg = Path.Combine(_tempDir, "backdrop.png");
        File.WriteAllBytes(srcFont, [0x00, 0x01, 0x00, 0x00]);
        File.WriteAllBytes(srcImg, TinyPng);

        var original = BuiltInThemes.Presets[2].Create(); // Arctic Slate
        original.Manifest.Id = "roundtrip-theme";
        original.Manifest.Name = "RoundTrip -- Test & <Demo>";
        original.Manifest.Author = "QA";
        original.Manifest.Version = "2.1.0";
        original.Manifest.Description = "Full round-trip test theme.";
        original.Manifest.MinAppVersion = "2.3.0";
        original.FontFamily = "fonts/TestFont.ttf#TestFont, Consolas";
        original.Shape.Enabled = true;
        original.Shape.ShellCornerRadius = 12;
        original.Shape.ShellBorderThickness = 2;
        original.Shape.CardCornerRadius = 6;
        original.Shape.ButtonCornerRadius = 5;
        original.Shape.CompactCornerRadius = 16;
        original.Shape.ShellGlow = true;
        original.Shape.ShellGlowBlur = 18;
        original.BackgroundImage = new BackgroundImageSettings { FileName = "backdrop.png", Opacity = 0.42, Stretch = "Uniform" };
        original.Fonts.Add(new ThemeFile("TestFont.ttf", srcFont));
        original.Assets.Add(new ThemeFile("backdrop.png", srcImg));
        original.CustomResources = "<SolidColorBrush x:Key=\"CustomAccent\" Color=\"#123456\" />";
        original.CustomStyles = "<Style Selector=\"TextBlock#OverlayTitle\"><Setter Property=\"FontSize\" Value=\"14\" /></Style>";

        string xaml = ThemeXamlGenerator.Generate(original);
        Assert.DoesNotContain("RoundTrip --", xaml); // comment-safe

        // Folder export + stale file pruning
        string folder = Path.Combine(_tempDir, "out_folder", original.Manifest.Id);
        Directory.CreateDirectory(Path.Combine(folder, "assets"));
        string staleFile = Path.Combine(folder, "assets", "old_unused.png");
        File.WriteAllBytes(staleFile, TinyPng);

        var folderWarnings = ThemeExporter.WriteFolder(original, xaml, folder);
        Assert.Empty(folderWarnings);
        Assert.False(File.Exists(staleFile));
        Assert.True(File.Exists(Path.Combine(folder, "theme.json")));
        Assert.True(File.Exists(Path.Combine(folder, "theme.axaml")));
        Assert.True(File.Exists(Path.Combine(folder, "fonts", "TestFont.ttf")));
        Assert.True(File.Exists(Path.Combine(folder, "assets", "backdrop.png")));

        // Import from folder
        var fromFolder = ThemeImporter.Load(folder, BuiltInThemes.Cyberpunk);
        Assert.Equal("roundtrip-theme", fromFolder.Manifest.Id);
        Assert.Equal("RoundTrip -- Test & <Demo>", fromFolder.Manifest.Name);
        Assert.Equal("QA", fromFolder.Manifest.Author);
        Assert.True(fromFolder.Shape.Enabled);
        Assert.Equal(12, fromFolder.Shape.ShellCornerRadius);
        Assert.Equal(2, fromFolder.Shape.ShellBorderThickness);
        Assert.True(fromFolder.Shape.ShellGlow);
        Assert.Equal(18, fromFolder.Shape.ShellGlowBlur);
        Assert.NotNull(fromFolder.BackgroundImage);
        Assert.Equal("backdrop.png", fromFolder.BackgroundImage!.FileName);
        Assert.Equal("Uniform", fromFolder.BackgroundImage.Stretch);
        Assert.Equal(0.42, fromFolder.BackgroundImage.Opacity, 2);
        Assert.Contains("CustomAccent", fromFolder.CustomResources);
        Assert.Contains("OverlayTitle", fromFolder.CustomStyles);
        Assert.Single(fromFolder.Fonts);
        Assert.Single(fromFolder.Assets);

        // Zip export + re-import
        string zipPath = Path.Combine(_tempDir, "roundtrip.zip");
        var zipWarnings = ThemeExporter.WriteZip(original, xaml, zipPath);
        Assert.Empty(zipWarnings);
        Assert.True(File.Exists(zipPath));

        var fromZip = ThemeImporter.Load(zipPath, BuiltInThemes.Cyberpunk);
        Assert.Equal("roundtrip-theme", fromZip.Manifest.Id);
        Assert.Equal(original.Tokens["NeonCyan"].Color, fromZip.Tokens["NeonCyan"].Color);
        Assert.NotNull(fromZip.BackgroundImage);
        Assert.Empty(fromZip.ImportWarnings);
    }

    [Fact]
    public void ThemeImporter_HandlesDuplicateShapeSetters_And_SecurityChecks()
    {
        // Duplicate <Setter> in shape block should not throw
        string dupShapeXaml = $"""
<Styles xmlns="https://github.com/avaloniaui" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
    <Styles.Resources />
    {ThemeXamlGenerator.ShapeBegin}
    <Style Selector="Border.overlay-shell">
        <Setter Property="CornerRadius" Value="4" />
        <Setter Property="CornerRadius" Value="14" />
    </Style>
    {ThemeXamlGenerator.ShapeEnd}
</Styles>
""";
        var parsed = ThemeImporter.FromXaml(dupShapeXaml, new ThemeManifest { Id = "dup", Name = "Dup" }, BuiltInThemes.Cyberpunk, includeStyles: true);
        Assert.True(parsed.Shape.Enabled);
        Assert.Equal(14, parsed.Shape.ShellCornerRadius);

        // Entry path traversal blocked
        string evilDir = Path.Combine(_tempDir, "evil_entry");
        Directory.CreateDirectory(evilDir);
        File.WriteAllText(Path.Combine(evilDir, "theme.json"), """{"id":"evil","name":"Evil","entry":"../outside.axaml"}""");
        Assert.Throws<InvalidOperationException>(() => ThemeImporter.LoadFolder(evilDir, BuiltInThemes.Cyberpunk));

        // Zip with > 200 entries rejected
        string bigZip = Path.Combine(_tempDir, "too_many.zip");
        using (var archive = ZipFile.Open(bigZip, ZipArchiveMode.Create))
        {
            for (int i = 0; i < 205; i++)
            {
                var e = archive.CreateEntry($"f{i}.txt");
                using var sw = new StreamWriter(e.Open());
                sw.Write("x");
            }
        }
        Assert.Throws<InvalidOperationException>(() => ThemeImporter.Load(bigZip, BuiltInThemes.Cyberpunk));
    }

    [Fact]
    public void Exporter_WritesPreviewThumbnail_InFolderAndZip_AndImportStillWorks()
    {
        var state = BuiltInThemes.Presets[0].Create();
        state.Manifest.Id = "thumb-theme";
        state.Manifest.Name = "Thumb Theme";
        string xaml = ThemeXamlGenerator.Generate(state);

        string folder = Path.Combine(_tempDir, "thumb-theme");
        Assert.Empty(ThemeExporter.WriteFolder(state, xaml, folder, TinyPng));
        Assert.Equal(TinyPng, File.ReadAllBytes(Path.Combine(folder, ThemeExporter.PreviewFileName)));

        string zip = Path.Combine(_tempDir, "thumb-theme.zip");
        Assert.Empty(ThemeExporter.WriteZip(state, xaml, zip, TinyPng));
        using (var archive = ZipFile.OpenRead(zip))
            Assert.Contains(archive.Entries, e => e.FullName.Replace('\\', '/') == "thumb-theme/preview.png");

        // The thumbnail must not show up as a theme asset when the theme is opened again.
        var imported = ThemeImporter.Load(zip, BuiltInThemes.Cyberpunk);
        Assert.DoesNotContain(imported.Assets, a => a.FileName == ThemeExporter.PreviewFileName);

        // No thumbnail given: nothing is written.
        string plain = Path.Combine(_tempDir, "plain-theme");
        ThemeExporter.WriteFolder(state, xaml, plain);
        Assert.False(File.Exists(Path.Combine(plain, ThemeExporter.PreviewFileName)));
    }

    [Fact]
    public void Guide_EmbeddedGuideParses_AndEveryContentsLinkHasASection()
    {
        var blocks = GuideParser.Parse(GuideParser.LoadEmbedded());

        Assert.IsType<GuideTitle>(blocks[0]);
        var anchors = blocks.OfType<GuideSection>().Select(s => s.Anchor).ToHashSet();
        Assert.Contains("14-keyboard-shortcuts", anchors); // F1 jumps here

        // Contents list: every link must point at a real section.
        int contents = blocks.ToList().FindIndex(b => b is GuideSection { Title: "Contents" });
        var toc = Assert.IsType<GuideList>(blocks[contents + 1]);
        Assert.True(toc.Numbered);
        foreach (string item in toc.Items)
        {
            var link = Assert.Single(GuideParser.ParseInlines(item), i => i.Kind == GuideInlineKind.Link);
            Assert.Contains(link.Target!.TrimStart('#'), anchors);
        }
        Assert.Equal(toc.Items.Count, anchors.Count - 1); // every numbered section is listed (minus "Contents")

        // Tables keep their rows and drop the |---| separator.
        var shortcuts = blocks.OfType<GuideTable>().Single(t => t.Header[0] == "Shortcut");
        Assert.Contains(shortcuts.Rows, r => r[0] == "**Ctrl+S**" && r[1] == "Save");
        Assert.DoesNotContain(shortcuts.Rows, r => r[0].StartsWith("---", StringComparison.Ordinal));
    }

    [Fact]
    public void ShortcutGesture_ParsesFormatsAndChecksAllowedKeys()
    {
        Assert.True(ShortcutGesture.TryParse("Ctrl+Shift+S", out var save));
        Assert.Equal(new ShortcutGesture(Avalonia.Input.Key.S, Avalonia.Input.KeyModifiers.Control | Avalonia.Input.KeyModifiers.Shift), save);
        Assert.Equal("Ctrl+Shift+S", save.ToString());

        Assert.True(ShortcutGesture.TryParse("ctrl+1", out var one));
        Assert.Equal("Ctrl+1", one.ToString());
        // The number pad digit counts as the same shortcut.
        Assert.Equal(one, ShortcutGesture.FromKeyPress(Avalonia.Input.Key.NumPad1, Avalonia.Input.KeyModifiers.Control));

        Assert.True(ShortcutGesture.TryParse("F1", out var f1));
        Assert.True(f1.IsAllowed);
        Assert.True(save.IsAllowed);
        // Plain letters would fire while typing a name: not allowed.
        Assert.False(new ShortcutGesture(Avalonia.Input.Key.S, Avalonia.Input.KeyModifiers.Shift).IsAllowed);
        Assert.False(new ShortcutGesture(Avalonia.Input.Key.A, Avalonia.Input.KeyModifiers.None).IsAllowed);

        Assert.False(ShortcutGesture.TryParse("", out _));
        Assert.False(ShortcutGesture.TryParse("Ctrl+", out _));
        Assert.False(ShortcutGesture.TryParse("Ctrl+NotAKey", out _));
        Assert.False(ShortcutGesture.TryParse("Ctrl+A+B", out _));

        // Every default in the catalogue parses (or is empty = no shortcut) and is unique.
        var defaults = ShortcutCatalog.All.Where(d => d.DefaultGesture.Length > 0).Select(d =>
        {
            Assert.True(ShortcutGesture.TryParse(d.DefaultGesture, out var g), d.Id);
            return g;
        }).ToList();
        Assert.Equal(defaults.Count, defaults.Distinct().Count());
    }

    [Fact]
    public void ShortcutMap_ChangesResolveConflictsAndReset()
    {
        var stored = new Dictionary<string, string>();
        int saves = 0;
        var map = new ShortcutMap(stored, () => saves++);
        ShortcutGesture.TryParse("Ctrl+E", out var ctrlE);
        ShortcutGesture.TryParse("Ctrl+K", out var ctrlK);

        Assert.Equal("export-zip", map.FindAction(ctrlE));
        Assert.Null(map.FindAction(ctrlK));

        // Give Ctrl+E to "save": export loses it.
        string? taken = map.Set("save", ctrlE);
        Assert.Equal("export-zip", taken);
        Assert.Equal("save", map.FindAction(ctrlE));
        Assert.Null(map.Get("export-zip"));
        Assert.Equal("Ctrl+E", stored["save"]);
        Assert.Equal("", stored["export-zip"]);
        Assert.True(saves > 0);

        // Remove a shortcut, set a free one.
        map.Set("search", null);
        Assert.Null(map.Get("search"));
        map.Set("find-colour", ctrlK);
        Assert.Equal("find-colour", map.FindAction(ctrlK));

        // Setting the default again stores nothing for it.
        ShortcutGesture.TryParse("Ctrl+I", out var ctrlI);
        map.Set("install", ctrlI);
        Assert.False(map.IsCustom("install"));

        // One reset back to default: export takes Ctrl+E back from "save".
        map.ResetToDefault("export-zip");
        Assert.Equal("export-zip", map.FindAction(ctrlE));
        Assert.Null(map.Get("save"));

        // Reset everything.
        map.ResetAll();
        Assert.Empty(stored);
        ShortcutGesture.TryParse("Ctrl+S", out var ctrlS);
        Assert.Equal("save", map.FindAction(ctrlS));
        Assert.Equal("search", map.FindAction(ShortcutGesture.FromKeyPress(Avalonia.Input.Key.F, Avalonia.Input.KeyModifiers.Control)));
    }

    [Fact]
    public void Guide_InlinesAndSlugs()
    {
        var parts = GuideParser.ParseInlines("Press **Ctrl+S**, type `#00f0ff`, pick *Dark* or see [section 5](#5-x).");
        Assert.Equal(
            [GuideInlineKind.Text, GuideInlineKind.Bold, GuideInlineKind.Text, GuideInlineKind.Code, GuideInlineKind.Text,
             GuideInlineKind.Italic, GuideInlineKind.Text, GuideInlineKind.Link, GuideInlineKind.Text],
            parts.Select(p => p.Kind));
        Assert.Equal("#5-x", parts[7].Target);

        Assert.Equal("5-picking-colours-from-the-screen-eyedropper", GuideParser.Slug("5. Picking colours from the screen (eyedropper)"));
        Assert.Equal("8-shape-corners-borders-glow", GuideParser.Slug("8. Shape: corners, borders, glow"));
    }

    [Fact]
    public void CustomThumbnail_IsMarkedOnSave_FoundOnOpen_AndRemovedWhenAuto()
    {
        var state = BuiltInThemes.Presets[0].Create();
        state.Manifest.Id = "custom-thumb";
        state.Manifest.Name = "Custom Thumb";
        string xaml = ThemeXamlGenerator.Generate(state);
        string folder = Path.Combine(_tempDir, "custom-thumb");
        string marker = Path.Combine(folder, ThemeExporter.CustomPreviewMarker);
        string preview = Path.Combine(folder, ThemeExporter.PreviewFileName);

        // Saved with a custom thumbnail: preview.png + marker.
        string custom = Path.Combine(_tempDir, "my-thumb.png");
        File.WriteAllBytes(custom, TinyPng);
        state.CustomPreviewPath = custom;
        ThemeExporter.WriteFolder(state, xaml, folder, File.ReadAllBytes(custom));
        Assert.True(File.Exists(marker));
        Assert.Equal(TinyPng, File.ReadAllBytes(preview));

        // Opening the folder again knows the thumbnail is custom.
        var reopened = ThemeImporter.Load(folder, BuiltInThemes.Cyberpunk);
        Assert.Equal(Path.GetFullPath(preview), reopened.CustomPreviewPath);
        Assert.Equal(reopened.CustomPreviewPath, reopened.Clone().CustomPreviewPath);

        // Back to automatic: the marker goes away, so the thumbnail is rendered again next time.
        reopened.CustomPreviewPath = null;
        ThemeExporter.WriteFolder(reopened, xaml, folder, TinyPng);
        Assert.False(File.Exists(marker));
        Assert.Null(ThemeImporter.Load(folder, BuiltInThemes.Cyberpunk).CustomPreviewPath);
    }

    [Fact]
    public async Task Autosave_SurvivesACrash_RestoresIntoTheOriginalFolder_AndSaveClearsIt()
    {
        if (!CreatorSettings.Current.AutosaveEnabled) return; // turned off by the user on this PC

        var store = new RecoveryStore(Path.Combine(_tempDir, "recovery"));
        var seed = BuiltInThemes.Presets[0].Create();
        seed.Manifest.Id = "crash-theme";
        seed.Manifest.Name = "Crash Theme";
        string folder = Path.Combine(_tempDir, "crash-theme");
        ThemeExporter.WriteFolder(seed, ThemeXamlGenerator.Generate(seed), folder);

        var vm = new MainViewModel { Recovery = store };
        vm.OpenPath(folder);
        Assert.False(vm.AutosaveNow()); // just opened, nothing changed: no copy
        Assert.False(store.Exists);

        vm.Description = "Changed before the crash";
        vm.Refresh();
        Assert.True(vm.AutosaveNow());
        Assert.True(store.Exists);
        var info = store.Peek();
        Assert.NotNull(info);
        Assert.Equal("Crash Theme", info!.ThemeName);
        Assert.Equal(folder, info.OriginalFolder);

        // "Crash": a brand-new editor restores the copy.
        var after = new MainViewModel { Recovery = store };
        Assert.True(after.RestoreRecovery());
        Assert.Equal("Changed before the crash", after.Description);
        Assert.Equal(folder, after.CurrentFolder);
        Assert.True(after.IsDirty);

        // Saving writes the changes to the original folder and removes the copy.
        await after.SaveCommand.ExecuteAsync(null);
        Assert.False(store.Exists);
        Assert.Contains("Changed before the crash", File.ReadAllText(Path.Combine(folder, "theme.json")));
    }

    [Fact]
    public void AnimatedTokens_AllAtOnceAndFlow_AreWrittenForEveryOverlayUsage_AndComeBackOnOpen()
    {
        var state = BuiltInThemes.Presets[0].Create();
        state.Manifest.Id = "token-anim";
        state.Manifest.Name = "Token Anim";
        var red = Color.Parse("#ff0000");
        var green = Color.Parse("#00ff00");
        var blue = Color.Parse("#0000ff");
        state.Tokens["CyberCardBg"] = state.Tokens["CyberCardBg"] with { Animation = new TokenAnimation([red, green, blue], Flow: true, Seconds: 5) };
        state.Tokens["NeonCyan"] = state.Tokens["NeonCyan"] with { Animation = new TokenAnimation([red, blue], Flow: false, Seconds: 3) };

        string xaml = ThemeXamlGenerator.Generate(state);

        // Every style where the overlay uses the colour gets an animation.
        foreach (var usage in TokenUsages.For("CyberCardBg").Concat(TokenUsages.For("NeonCyan")))
            Assert.Contains($"<Style Selector=\"{System.Security.SecurityElement.Escape(usage.Selector)}\">", xaml);
        Assert.True(TokenUsages.For("CyberCardBg").Count >= 5);

        // Flow: a gradient whose colours shift one place per frame (n + 1 frames, last = first).
        var flow = ThemeXamlGenerator.TokenFrames(state.Tokens["CyberCardBg"], state.Tokens["CyberCardBg"].Animation!);
        Assert.Equal(4, flow.Count);
        Assert.All(flow, f => Assert.StartsWith("<LinearGradientBrush", f));
        Assert.Equal(flow[0], flow[^1]);
        Assert.NotEqual(flow[0], flow[1]);

        // All at once: solid colours and back to the first.
        var whole = ThemeXamlGenerator.TokenFrames(state.Tokens["NeonCyan"], state.Tokens["NeonCyan"].Animation!);
        Assert.Equal(["#ff0000", "#0000ff", "#ff0000"], whole);

        // Opening the theme again: same animations, nothing leaks into the custom styles, stable output.
        var reopened = ThemeImporter.FromXaml(xaml, state.Manifest, BuiltInThemes.Cyberpunk, includeStyles: true);
        var card = reopened.Tokens["CyberCardBg"].Animation;
        Assert.NotNull(card);
        Assert.True(card!.Flow);
        Assert.Equal([red, green, blue], card.Colors);
        Assert.Equal(5, card.Seconds);
        Assert.False(reopened.Tokens["NeonCyan"].Animation!.Flow);
        Assert.Null(reopened.Tokens["CyberBorder"].Animation);
        Assert.DoesNotContain("Style.Animations", reopened.CustomStyles);
        Assert.Equal(xaml, ThemeXamlGenerator.Generate(reopened));

        // Colours the overlay styles never use get no ANIMATE button (it would do nothing).
        var vm = new MainViewModel();
        var tokens = vm.Groups.SelectMany(g => g.Tokens).ToDictionary(t => t.Key);

        // GRADIENT and ANIMATE are one or the other.
        var cardRow = tokens["CyberCardBg"];
        cardRow.IsGradient = true;
        cardRow.IsAnimated = true;
        Assert.False(cardRow.IsGradient);
        Assert.Null(cardRow.ToValue().Gradient);
        Assert.NotNull(cardRow.ToValue().Animation);
        cardRow.IsGradient = true;
        Assert.False(cardRow.IsAnimated);
        Assert.Null(cardRow.ToValue().Animation);
        Assert.NotNull(cardRow.ToValue().Gradient);
        Assert.True(tokens["CyberCardBg"].SupportsAnimation);
        Assert.False(tokens["NeonPurple"].SupportsAnimation);
        Assert.False(tokens["TextLight"].SupportsAnimation); // no gradient, no animation
    }

    [Fact]
    public void OldAnimatedColoursSection_IsDroppedOnOpen_NotKeptAsCustomStyles()
    {
        var state = BuiltInThemes.Presets[0].Create();
        string xaml = ThemeXamlGenerator.Generate(state);
        // A theme saved by an earlier build that still had the "Animated colours" card.
        string old = xaml.Replace("</Styles>", $$"""
                {{ThemeXamlGenerator.AnimationBegin}}
                <Style Selector="TextBlock.overlay-title">
                    <Style.Animations>
                        <Animation Duration="0:0:6" IterationCount="Infinite">
                            <KeyFrame Cue="0%"><Setter Property="Foreground" Value="#ff0000" /></KeyFrame>
                            <KeyFrame Cue="100%"><Setter Property="Foreground" Value="#0000ff" /></KeyFrame>
                        </Animation>
                    </Style.Animations>
                </Style>
                {{ThemeXamlGenerator.AnimationEnd}}
            </Styles>
            """);

        var reopened = ThemeImporter.FromXaml(old, state.Manifest, BuiltInThemes.Cyberpunk, includeStyles: true);
        Assert.DoesNotContain("overlay-title", reopened.CustomStyles);
        Assert.DoesNotContain("Style.Animations", ThemeXamlGenerator.Generate(reopened));
    }

    [Fact]
    public void TokenSearch_FiltersByLabelKeyAndHex_AndClears()
    {
        var vm = new MainViewModel();
        var all = vm.Groups.SelectMany(g => g.Tokens).ToList();

        vm.TokenSearch = "slider thumb";
        Assert.All(all, t => Assert.Equal(t.Key.StartsWith("SliderThumb", StringComparison.Ordinal), t.IsMatch));
        Assert.Contains(vm.Groups, g => !g.HasMatches);
        Assert.False(vm.HasNoSearchResults);

        string hex = all.First(t => t.Key == "NeonCyan").HexText;
        vm.TokenSearch = hex;
        Assert.Contains(all, t => t.Key == "NeonCyan" && t.IsMatch);

        vm.TokenSearch = "no-such-colour-xyz";
        Assert.True(vm.HasNoSearchResults);

        vm.ClearTokenSearchCommand.Execute(null);
        Assert.All(all, t => Assert.True(t.IsMatch));
        Assert.All(vm.Groups, g => Assert.True(g.HasMatches));
    }

    // ==================== OverlayLocator & FontTools ====================

    [Fact]
    public void OverlayLocator_NormaliseSelection_HandlesExeOverlayAndThemesFolder()
    {
        string overlayDir = Path.Combine(_tempDir, "overlay_app");
        string themesDir = Path.Combine(overlayDir, "themes");
        Directory.CreateDirectory(themesDir);
        string exePath = Path.Combine(overlayDir, "RbwrOverlay.exe");
        File.WriteAllText(exePath, "");

        Assert.Equal(themesDir, OverlayLocator.NormaliseSelection(exePath));
        Assert.Equal(themesDir, OverlayLocator.NormaliseSelection(overlayDir));
        Assert.Equal(themesDir, OverlayLocator.NormaliseSelection(themesDir));
    }

    [Fact]
    public void FontTools_GetPreviewCopy_And_CleanupStaleTempFiles()
    {
        string src = Path.Combine(_tempDir, "sample.png");
        File.WriteAllBytes(src, TinyPng);
        string copy1 = FontTools.GetPreviewCopy(src);
        string copy2 = FontTools.GetPreviewCopy(src);
        Assert.Equal(copy1, copy2);
        Assert.True(File.Exists(copy1));

        // Stale cleanup test in isolated temp root
        string fakeRoot = Path.Combine(_tempDir, "fake_temp_root");
        string oldDir = Path.Combine(fakeRoot, "imports", "old_run");
        string freshDir = Path.Combine(fakeRoot, "imports", "fresh_run");
        Directory.CreateDirectory(oldDir);
        Directory.CreateDirectory(freshDir);
        Directory.SetLastWriteTimeUtc(oldDir, DateTime.UtcNow.AddHours(-48));

        int removed = FontTools.CleanupStaleTempFiles(TimeSpan.FromHours(24), rootOverride: fakeRoot);
        Assert.Equal(1, removed);
        Assert.False(Directory.Exists(oldDir));
        Assert.True(Directory.Exists(freshDir));
    }

    // ==================== MainViewModel: Dirty Tracking, Undo/Redo, Drag-Drop, Contrast ====================

    [Fact]
    public async Task MainViewModel_DirtyTracking_UndoRedo_And_DropSupport()
    {
        var vm = new MainViewModel();

        // Save to a folder first so IsDirty becomes false
        string saveFolder = Path.Combine(_tempDir, "vm_theme");
        var state = vm.BuildState();
        state.Manifest.Id = "vm-theme";
        state.Manifest.Name = "VM Theme";
        ThemeExporter.WriteFolder(state, ThemeXamlGenerator.Generate(state), saveFolder);

        // Opening .axaml inside a folder with theme.json sets CurrentFolder!
        vm.OpenPath(Path.Combine(saveFolder, "theme.axaml"));
        Assert.Equal(saveFolder, vm.CurrentFolder);
        Assert.False(vm.IsDirty);
        Assert.False(vm.CanUndo);
        Assert.False(vm.CanRedo);

        // Contrast summary must never contain warning/checkmark emojis
        Assert.DoesNotContain("\u26A0", vm.ContrastSummary);
        Assert.DoesNotContain("\u2713", vm.ContrastSummary);

        // Manifest-only edit marks IsDirty = true and records Undo step
        vm.Description = "Updated description";
        vm.Refresh();
        Assert.True(vm.IsDirty);
        Assert.True(vm.CanUndo);
        Assert.False(vm.CanRedo);

        // Undo restores previous description and IsDirty returns to false
        vm.Undo();
        Assert.Equal(string.Empty, vm.Description);
        Assert.False(vm.IsDirty);
        Assert.False(vm.CanUndo);
        Assert.True(vm.CanRedo);

        // Redo re-applies description
        vm.Redo();
        Assert.Equal("Updated description", vm.Description);
        Assert.True(vm.IsDirty);
        Assert.True(vm.CanUndo);
        Assert.False(vm.CanRedo);

        // Drag-and-drop image & font attaches them and marks dirty
        string dropImg = Path.Combine(_tempDir, "dropped bg.png");
        string dropFont = Path.Combine(_tempDir, "My Font.ttf");
        File.WriteAllBytes(dropImg, TinyPng);
        File.WriteAllBytes(dropFont, [0x00, 0x01, 0x00, 0x00]);

        await vm.HandleDroppedPathsAsync([dropImg, dropFont]);
        Assert.Contains(vm.Assets, a => a.FileName == "dropped_bg.png");
        Assert.Contains(vm.Fonts, f => f.FileName == "My_Font.ttf");
    }

    [Fact]
    public void MainViewModel_AppVersion_MatchesAssemblyMetadata()
    {
        var vm = new MainViewModel();
        Assert.Equal(MainViewModel.AppVersion, vm.GlobalAppVersion);
        Assert.Equal($"v{MainViewModel.AppVersion}", vm.AppVersionBadge);
        Assert.Equal($"RBWR Theme Creator v{MainViewModel.AppVersion}", vm.AppVersionText);

        var infoAttr = typeof(MainViewModel).Assembly
            .GetCustomAttributes(typeof(System.Reflection.AssemblyInformationalVersionAttribute), false)
            .OfType<System.Reflection.AssemblyInformationalVersionAttribute>()
            .FirstOrDefault();
        Assert.NotNull(infoAttr);
        Assert.Equal(MainViewModel.AppVersion, infoAttr.InformationalVersion);
    }

    [Fact]
    public void CreatorUpdateService_ParseLatestCreatorRelease_FiltersTagDraftPrereleaseAndSkipped()
    {
        const string sampleReleasesJson = """
        [
          {
            "tag_name": "v2.4.0",
            "draft": false,
            "prerelease": false,
            "body": "Overlay release",
            "assets": [
              { "name": "RBWR_APRM_Calculator_win-x64.exe", "browser_download_url": "https://example.com/overlay.exe" }
            ]
          },
          {
            "tag_name": "theme-creator-v1.3.0-beta.1",
            "draft": false,
            "prerelease": true,
            "body": "Prerelease",
            "assets": []
          },
          {
            "tag_name": "theme-creator-v1.2.5",
            "draft": true,
            "prerelease": false,
            "body": "Draft",
            "assets": []
          },
          {
            "tag_name": "theme-creator-v1.2.0",
            "draft": false,
            "prerelease": false,
            "body": "New gradient tools",
            "assets": [
              { "name": "RBWR_Theme_Creator_win-x64.exe", "browser_download_url": "https://example.com/creator-x64.exe" },
              { "name": "RBWR_Theme_Creator_win-arm64.exe", "browser_download_url": "https://example.com/creator-arm64.exe" },
              { "name": "RBWR_Theme_Creator_linux-x64.AppImage", "browser_download_url": "https://example.com/creator.AppImage" },
              { "name": "RBWR_Theme_Creator_macOS_osx-arm64.zip", "browser_download_url": "https://example.com/creator-mac.zip" }
            ]
          },
          {
            "tag_name": "theme-creator-v1.1.0",
            "draft": false,
            "prerelease": false,
            "body": "Older release",
            "assets": []
          }
        ]
        """;

        // Newer release found, ignoring v2.4.0 overlay release, prerelease, and draft
        var update = CreatorUpdateService.ParseLatestCreatorRelease(sampleReleasesJson, "1.0.0", string.Empty);
        Assert.True(update.IsAvailable);
        Assert.Equal("1.2.0", update.Version);
        Assert.Equal("New gradient tools", update.ReleaseNotes);
        Assert.StartsWith("RBWR_Theme_Creator_", update.FileName);
        Assert.NotEmpty(update.DownloadUrl);

        // Already up to date (1.2.0 == 1.2.0) or newer dev build (1.3.0 > 1.2.0)
        Assert.False(CreatorUpdateService.ParseLatestCreatorRelease(sampleReleasesJson, "1.2.0", string.Empty).IsAvailable);
        Assert.False(CreatorUpdateService.ParseLatestCreatorRelease(sampleReleasesJson, "1.3.0", string.Empty).IsAvailable);

        // Respects skippedVersion
        Assert.False(CreatorUpdateService.ParseLatestCreatorRelease(sampleReleasesJson, "1.0.0", "1.2.0").IsAvailable);
    }

    [Fact]
    public void CreatorUpdateService_IsNewerVersion_ComparesSemver()
    {
        Assert.True(CreatorUpdateService.IsNewerVersion("1.0.1", "1.0.0"));
        Assert.True(CreatorUpdateService.IsNewerVersion("1.2.0", "1.1.9"));
        Assert.True(CreatorUpdateService.IsNewerVersion("2.0.0", "1.9.9"));
        Assert.False(CreatorUpdateService.IsNewerVersion("1.0.0", "1.0.0"));
        Assert.False(CreatorUpdateService.IsNewerVersion("0.9.9", "1.0.0"));
        Assert.False(CreatorUpdateService.IsNewerVersion("1.0.0", "1.1.0"));
    }

    private sealed class FakeUpdateService(RbwrOverlay.Core.Models.UpdateInfo result) : ICreatorUpdateService
    {
        public string? LastSkippedVersion { get; private set; }
        public Task<RbwrOverlay.Core.Models.UpdateInfo> CheckForUpdatesAsync(string currentVersion, string skippedVersion, CancellationToken ct = default)
        {
            LastSkippedVersion = skippedVersion;
            return Task.FromResult(result);
        }
        public Task DownloadUpdateAsync(string downloadUrl, string destinationPath, IProgress<double>? progress = null, CancellationToken ct = default)
            => Task.CompletedTask;
    }

    [Fact]
    public async Task MainViewModel_ManualUpdateCheck_FiresRequestShowUpdate_AndIgnoresSkipped()
    {
        var fake = new FakeUpdateService(new RbwrOverlay.Core.Models.UpdateInfo
        {
            IsAvailable = true,
            Version = "1.5.0",
            ReleaseNotes = "Test update",
            FileName = "RBWR_Theme_Creator_win-x64.exe",
            DownloadUrl = "https://example.com/creator.exe",
        });

        var vm = new MainViewModel(fake);
        RbwrOverlay.Core.Models.UpdateInfo? shown = null;
        vm.RequestShowUpdate += info => shown = info;

        await vm.RunUpdateCheckAsync(isManual: true);

        Assert.NotNull(shown);
        Assert.Equal("1.5.0", shown.Version);
        Assert.Equal(string.Empty, fake.LastSkippedVersion);
        Assert.Contains("1.5.0", vm.UpdateStatusText);
    }
}
