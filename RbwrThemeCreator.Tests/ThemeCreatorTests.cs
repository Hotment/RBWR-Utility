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
}
