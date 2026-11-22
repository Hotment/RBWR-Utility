using System.IO.Compression;
using RbwrOverlay.Core.Models;
using RbwrOverlay.Core.Services;
using RbwrOverlay.Platform;
using RbwrOverlay.UI.Services;
using RbwrOverlay.UI.ViewModels;
using Xunit;

namespace RbwrOverlay.Tests;

public class ThemeTests : IDisposable
{
    private readonly string _tempDir;

    public ThemeTests()
    {
        _tempDir = Path.Combine(Path.GetTempPath(), "rbwr_theme_tests_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(_tempDir);
    }

    public void Dispose()
    {
        try
        {
            if (Directory.Exists(_tempDir))
                Directory.Delete(_tempDir, recursive: true);
        }
        catch
        {
        }
    }

    private static byte[] PngHeader(uint width, uint height)
    {
        var bytes = new byte[33];
        new byte[] { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 13, (byte)'I', (byte)'H', (byte)'D', (byte)'R' }.CopyTo(bytes, 0);
        System.Buffers.Binary.BinaryPrimitives.WriteUInt32BigEndian(bytes.AsSpan(16), width);
        System.Buffers.Binary.BinaryPrimitives.WriteUInt32BigEndian(bytes.AsSpan(20), height);
        return bytes;
    }

    [Fact]
    public void ThumbnailGuard_AcceptsNormalPng_RejectsHugeOrFakeImages()
    {
        Assert.True(ThemeThumbnailService.IsSafePng(new MemoryStream(PngHeader(705, 683))));
        Assert.True(ThemeThumbnailService.IsSafePng(new MemoryStream(PngHeader(4000, 4000))));

        // Small file declaring enormous dimensions: must not be decoded.
        Assert.False(ThemeThumbnailService.IsSafePng(new MemoryStream(PngHeader(30000, 30000))));
        Assert.False(ThemeThumbnailService.IsSafePng(new MemoryStream(PngHeader(8000, 8000))));
        Assert.False(ThemeThumbnailService.IsSafePng(new MemoryStream(PngHeader(0, 100))));
        Assert.False(ThemeThumbnailService.IsSafePng(new MemoryStream(PngHeader(uint.MaxValue, 1))));

        // Not a PNG (e.g. a JPEG renamed to preview.png), or a truncated file.
        Assert.False(ThemeThumbnailService.IsSafePng(new MemoryStream([0xFF, 0xD8, 0xFF, 0xE0, 0, 0x10, 0x4A, 0x46, 0x49, 0x46, 0, 1, 1, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0])));
        Assert.False(ThemeThumbnailService.IsSafePng(new MemoryStream([0x89, 0x50, 0x4E])));
        Assert.False(ThemeThumbnailService.IsSafePng(new MemoryStream()));
    }

    [Fact]
    public void Thumbnail_HugeOrBrokenPreviewPng_GivesNoThumbnailInsteadOfCrashing()
    {
        string dir = Path.Combine(_tempDir, "huge-preview");
        Directory.CreateDirectory(dir);
        File.WriteAllText(Path.Combine(dir, "theme.axaml"), "<Styles />");
        var info = new InstalledThemeInfo { Id = "huge-preview", DirectoryPath = dir, EntryFilePath = Path.Combine(dir, "theme.axaml") };

        File.WriteAllBytes(Path.Combine(dir, ThemeThumbnailService.PreviewFileName), PngHeader(50000, 50000));
        Assert.Null(ThemeThumbnailService.Get(info));

        File.WriteAllText(Path.Combine(dir, ThemeThumbnailService.PreviewFileName), "this is not an image");
        File.SetLastWriteTimeUtc(Path.Combine(dir, ThemeThumbnailService.PreviewFileName), DateTime.UtcNow.AddMinutes(1));
        Assert.Null(ThemeThumbnailService.Get(info));

        // No preview.png at all: still fine, just no thumbnail.
        File.Delete(Path.Combine(dir, ThemeThumbnailService.PreviewFileName));
        Assert.Null(ThemeThumbnailService.Get(info));
    }

    [Fact]
    public void TestDiscoverThemesIncludesBothBuiltInThemesFirst()
    {
        var svc = new ThemeService(themesDirectory: _tempDir);
        var themes = svc.DiscoverThemes();

        Assert.Equal(3, themes.Count);
        Assert.Equal(ThemeService.DefaultThemeId, themes[0].Id);
        Assert.Equal(ThemeService.ReactorAmberThemeId, themes[1].Id);
        Assert.Equal(ThemeService.AuroraDriftThemeId, themes[2].Id);
        Assert.All(themes, t => Assert.True(t.IsBuiltIn));
        Assert.Equal("Uranium-q2", themes[2].Author);

        var auroraRes = svc.ApplyTheme(ThemeService.AuroraDriftThemeId);
        Assert.True(auroraRes.Success, auroraRes.ErrorMessage);
        Assert.Equal(ThemeService.AuroraDriftThemeId, svc.ActiveThemeId);

        var amberRes = svc.ApplyTheme(ThemeService.ReactorAmberThemeId);
        Assert.True(amberRes.Success, amberRes.ErrorMessage);
        Assert.Equal(ThemeService.ReactorAmberThemeId, svc.ActiveThemeId);
    }

    [Fact]
    public void TestCreateTemplateThemeAndApplyParsesRuntimeAxaml()
    {
        var svc = new ThemeService(themesDirectory: _tempDir);
        var created = svc.CreateTemplateTheme("arctic-hud");

        Assert.Equal("arctic-hud", created.Id);
        Assert.Equal("Arctic Slate (Template)", created.Name);
        Assert.True(File.Exists(created.EntryFilePath));
        Assert.True(Directory.Exists(Path.Combine(created.DirectoryPath, "fonts")));
        Assert.True(Directory.Exists(Path.Combine(created.DirectoryPath, "assets")));

        var res = svc.ApplyTheme("arctic-hud");
        Assert.True(res.Success, res.ErrorMessage);
        Assert.Equal("arctic-hud", svc.ActiveThemeId);

        var reset = svc.ApplyTheme(ThemeService.DefaultThemeId);
        Assert.True(reset.Success);
        Assert.Equal(ThemeService.DefaultThemeId, svc.ActiveThemeId);
    }

    [Fact]
    public void TestPrepareThemeXamlRewritesRelativeFontsAndBlocksExternalAssemblies()
    {
        string themeDir = Path.Combine(_tempDir, "font-theme");
        string raw = """
<Styles xmlns="https://github.com/avaloniaui" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
    <Styles.Resources>
        <FontFamily x:Key="AppFontFamily">fonts/Orbitron.ttf#Orbitron</FontFamily>
    </Styles.Resources>
</Styles>
""";

        string prepared = ThemeService.PrepareThemeXaml(raw, themeDir);
        Assert.Contains("file:///", prepared);
        Assert.Contains("fonts/Orbitron.ttf#Orbitron", prepared);

        string unsafeXaml = """
<Styles xmlns="https://github.com/avaloniaui" xmlns:bad="clr-namespace:System.Diagnostics;assembly=System.Diagnostics.Process">
</Styles>
""";
        Assert.Throws<InvalidOperationException>(() => ThemeService.PrepareThemeXaml(unsafeXaml, themeDir));
    }

    [Fact]
    public void TestPrepareThemeXamlResolvesAssetsImagesAndAppliesRuntimeAxaml()
    {
        var svc = new ThemeService(themesDirectory: _tempDir);
        string themeDir = Path.Combine(_tempDir, "bg-image-theme");
        string assetsDir = Path.Combine(themeDir, "assets");
        Directory.CreateDirectory(assetsDir);

        // Minimal 1x1 PNG
        byte[] tinyPng = Convert.FromBase64String("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=");
        File.WriteAllBytes(Path.Combine(assetsDir, "bg.png"), tinyPng);
        File.WriteAllText(Path.Combine(themeDir, "theme.json"), """{"id":"bg-image-theme","name":"BG Image Theme","entry":"theme.axaml"}""");
        File.WriteAllText(Path.Combine(themeDir, "theme.axaml"), """
<Styles xmlns="https://github.com/avaloniaui" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
    <Styles.Resources>
        <ImageBrush x:Key="CyberMainBg" Source="assets/bg.png" Stretch="UniformToFill" Opacity="0.5" />
    </Styles.Resources>
</Styles>
""");

        string prepared = ThemeService.PrepareThemeXaml(File.ReadAllText(Path.Combine(themeDir, "theme.axaml")), themeDir, out var assetFiles);
        Assert.Single(assetFiles);
        Assert.Equal("__theme_asset_0", assetFiles[0].Key);
        Assert.Contains("Source=\"{DynamicResource __theme_asset_0}\"", prepared);

        var applyRes = svc.ApplyTheme("bg-image-theme");
        Assert.True(applyRes.Success, applyRes.ErrorMessage);

        // Missing asset throws FileNotFoundException
        string missingAssetXaml = """<Styles xmlns="https://github.com/avaloniaui"><Styles.Resources><ImageBrush x:Key="CyberMainBg" Source="assets/missing.png" /></Styles.Resources></Styles>""";
        Assert.Throws<FileNotFoundException>(() => ThemeService.PrepareThemeXaml(missingAssetXaml, themeDir, out _));
    }

    [Fact]
    public void TestInstallThemeFromZipAndStandaloneAxaml()
    {
        var svc = new ThemeService(themesDirectory: _tempDir);

        string axamlSrc = Path.Combine(_tempDir, "neon-green.axaml");
        File.WriteAllText(axamlSrc, """
<Styles xmlns="https://github.com/avaloniaui" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
    <Styles.Resources>
        <SolidColorBrush x:Key="NeonCyan" Color="#39ff14" />
    </Styles.Resources>
</Styles>
""");

        var (okAxaml, installedAxaml, errAxaml) = svc.InstallTheme(axamlSrc);
        Assert.True(okAxaml, errAxaml);
        Assert.NotNull(installedAxaml);
        Assert.Equal("neon-green", installedAxaml!.Id);

        string packStaging = Path.Combine(_tempDir, "pack_staging");
        Directory.CreateDirectory(packStaging);
        File.WriteAllText(Path.Combine(packStaging, "theme.json"), """
{
  "id": "ice-pack",
  "name": "Ice Pack",
  "author": "Tester",
  "version": "1.2.0",
  "entry": "theme.axaml"
}
""");
        File.WriteAllText(Path.Combine(packStaging, "theme.axaml"), """
<Styles xmlns="https://github.com/avaloniaui" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
    <Style Selector="Border.hud-card">
        <Setter Property="CornerRadius" Value="10" />
    </Style>
</Styles>
""");

        string zipPath = Path.Combine(_tempDir, "ice-pack.zip");
        ZipFile.CreateFromDirectory(packStaging, zipPath);

        var (okZip, installedZip, errZip) = svc.InstallTheme(zipPath);
        Assert.True(okZip, errZip);
        Assert.NotNull(installedZip);
        Assert.Equal("ice-pack", installedZip!.Id);
        Assert.Equal("Ice Pack", installedZip.Name);
        Assert.Contains(svc.DiscoverThemes(), t => t.Id == "ice-pack");
    }

    [Fact]
    public void TestViewModelThemeSwitchingAndFallbackOnInvalidTheme()
    {
        var settingsPath = Path.Combine(_tempDir, "settings.json");
        var settingsSvc = new SettingsService(customPath: settingsPath);
        settingsSvc.SaveSettings(new AppSettings { SelectedThemeId = "missing-theme" });

        var themeSvc = new ThemeService(themesDirectory: Path.Combine(_tempDir, "themes"));
        using var vm = new MainOverlayViewModel(
            settingsService: settingsSvc,
            apiClient: new MockThemeApiClient(),
            processMonitor: new MockThemeProcessMonitor(),
            themeService: themeSvc);

        // Missing theme falls back to default cleanly
        Assert.Equal(ThemeService.DefaultThemeId, vm.SelectedThemeItem?.Id);
        Assert.Contains(vm.AvailableThemes, t => t.Id == ThemeService.DefaultThemeId);
        Assert.True(vm.HasThemeStatusMessage);

        // Clearing SelectedThemeItem restores the active theme rather than leaving it blank
        vm.SelectedThemeItem = null;
        Assert.NotNull(vm.SelectedThemeItem);
        Assert.Equal(ThemeService.DefaultThemeId, vm.SelectedThemeItem!.Id);

        // Creating template selects & persists it
        vm.CreateTemplateTheme();
        Assert.Contains(vm.AvailableThemes, t => t.Id == ThemeService.DefaultThemeId);
        Assert.Equal("custom-template", vm.SelectedThemeItem?.Id);
        Assert.Equal("custom-template", settingsSvc.LoadSettings().SelectedThemeId);
    }

    [Fact]
    public void TestThemeSelectorViewModelListExpandFilterApplyAndDelete()
    {
        var settingsPath = Path.Combine(_tempDir, "settings_selector.json");
        var settingsSvc = new SettingsService(customPath: settingsPath);
        var themeSvc = new ThemeService(themesDirectory: Path.Combine(_tempDir, "themes_selector"));
        using var mainVm = new MainOverlayViewModel(
            settingsService: settingsSvc,
            apiClient: new MockThemeApiClient(),
            processMonitor: new MockThemeProcessMonitor(),
            themeService: themeSvc);

        themeSvc.CreateTemplateTheme("arctic-pack");
        using var selectorVm = mainVm.CreateThemeSelectorViewModel();

        Assert.Equal(4, selectorVm.FilteredThemes.Count);
        var builtIn = selectorVm.FilteredThemes.First(t => t.Id == ThemeService.DefaultThemeId);
        var amber = selectorVm.FilteredThemes.First(t => t.Id == ThemeService.ReactorAmberThemeId);
        var custom = selectorVm.FilteredThemes.First(t => t.Id == "arctic-pack");

        Assert.True(builtIn.IsActive);
        Assert.False(builtIn.CanManageFiles);
        Assert.False(amber.CanManageFiles);
        Assert.Equal("v1.0.0", custom.VersionText);
        Assert.Equal("by Custom", custom.AuthorText);
        Assert.False(string.IsNullOrWhiteSpace(custom.DescriptionText));
        Assert.True(custom.CanManageFiles);

        // Toggle expand
        Assert.False(custom.IsExpanded);
        custom.ToggleExpand();
        Assert.True(custom.IsExpanded);

        // Apply custom theme
        selectorVm.ApplyEntry(custom);
        Assert.Equal("arctic-pack", themeSvc.ActiveThemeId);
        var activeCustom = selectorVm.FilteredThemes.First(t => t.Id == "arctic-pack");
        Assert.True(activeCustom.IsActive);
        Assert.True(activeCustom.IsExpanded);

        // External theme switch (e.g. from Config dropdown) updates selector automatically
        mainVm.ApplyThemeAndSave(ThemeService.ReactorAmberThemeId);
        Assert.True(selectorVm.FilteredThemes.First(t => t.Id == ThemeService.ReactorAmberThemeId).IsActive);
        Assert.False(selectorVm.FilteredThemes.First(t => t.Id == "arctic-pack").IsActive);

        // Switch back to custom before testing delete
        activeCustom = selectorVm.FilteredThemes.First(t => t.Id == "arctic-pack");
        selectorVm.ApplyEntry(activeCustom);
        activeCustom = selectorVm.FilteredThemes.First(t => t.Id == "arctic-pack");

        // Search filter
        selectorVm.SearchQuery = "Arctic Slate";
        Assert.Single(selectorVm.FilteredThemes);
        selectorVm.SearchQuery = string.Empty;
        Assert.Equal(4, selectorVm.FilteredThemes.Count);

        // Built-in themes cannot be deleted
        var (delBuiltIn, _) = themeSvc.DeleteTheme(ThemeService.DefaultThemeId);
        Assert.False(delBuiltIn);
        var (delAmber, _) = themeSvc.DeleteTheme(ThemeService.ReactorAmberThemeId);
        Assert.False(delAmber);
        var (delAurora, _) = themeSvc.DeleteTheme(ThemeService.AuroraDriftThemeId);
        Assert.False(delAurora);

        // Deleting active custom theme requires two-click confirmation
        activeCustom = selectorVm.FilteredThemes.First(t => t.Id == "arctic-pack");
        Assert.False(activeCustom.IsConfirmingDelete);
        selectorVm.DeleteEntry(activeCustom);
        Assert.True(activeCustom.IsConfirmingDelete);
        Assert.Equal("Confirm?", activeCustom.DeleteButtonText);
        Assert.Equal(4, selectorVm.FilteredThemes.Count);

        // Second click confirms and deletes, reverting to default
        selectorVm.DeleteEntry(activeCustom);
        Assert.Equal(ThemeService.DefaultThemeId, themeSvc.ActiveThemeId);
        Assert.Equal(3, selectorVm.FilteredThemes.Count);
        Assert.All(selectorVm.FilteredThemes, t => Assert.True(t.IsBuiltIn));
    }

    [Fact]
    public void TestInvalidStandaloneAxamlDoesNotLeavePartialThemeOnDisk()
    {
        var svc = new ThemeService(themesDirectory: _tempDir);
        string badAxaml = Path.Combine(_tempDir, "broken-theme.axaml");
        File.WriteAllText(badAxaml, "<Styles xmlns=\"https://github.com/avaloniaui\"><NotClosed>");

        var (ok, theme, err) = svc.InstallTheme(badAxaml);
        Assert.False(ok);
        Assert.Null(theme);
        Assert.False(string.IsNullOrWhiteSpace(err));
        Assert.False(Directory.Exists(Path.Combine(_tempDir, "broken-theme")));
    }

    [Fact]
    public void TestCreateTemplateThemeDoesNotOverwriteExistingTemplate()
    {
        var svc = new ThemeService(themesDirectory: _tempDir);
        var first = svc.CreateTemplateTheme("custom-template");
        File.WriteAllText(first.EntryFilePath, "<!-- user edit -->");

        var second = svc.CreateTemplateTheme("custom-template");
        Assert.Equal("custom-template", first.Id);
        Assert.Equal("custom-template-2", second.Id);
        Assert.Equal("<!-- user edit -->", File.ReadAllText(first.EntryFilePath));
        Assert.True(File.Exists(second.EntryFilePath));
    }

    [Fact]
    public void TestPrepareThemeXamlSecurityHardening()
    {
        string themeDir = Path.Combine(_tempDir, "sec-theme");

        // clr-namespace without assembly=
        Assert.Throws<InvalidOperationException>(() => ThemeService.PrepareThemeXaml(
            "<Styles xmlns=\"https://github.com/avaloniaui\" xmlns:s=\"clr-namespace:System\"></Styles>", themeDir));

        // using:AvaloniaEvil bypass attempt
        Assert.Throws<InvalidOperationException>(() => ThemeService.PrepareThemeXaml(
            "<Styles xmlns=\"https://github.com/avaloniaui\" xmlns:e=\"using:AvaloniaEvil\"></Styles>", themeDir));

        // using:RbwrOverlay.UI.Services blocked
        Assert.Throws<InvalidOperationException>(() => ThemeService.PrepareThemeXaml(
            "<Styles xmlns=\"https://github.com/avaloniaui\" xmlns:svc=\"using:RbwrOverlay.UI.Services\"></Styles>", themeDir));

        // x:Class blocked
        Assert.Throws<InvalidOperationException>(() => ThemeService.PrepareThemeXaml(
            "<Styles xmlns=\"https://github.com/avaloniaui\" xmlns:x=\"http://schemas.microsoft.com/winfx/2006/xaml\" x:Class=\"Evil.Class\"></Styles>", themeDir));

        // StyleInclude blocked
        Assert.Throws<InvalidOperationException>(() => ThemeService.PrepareThemeXaml(
            "<Styles xmlns=\"https://github.com/avaloniaui\"><StyleInclude Source=\"file:///C:/evil.axaml\" /></Styles>", themeDir));

        // Allowed Avalonia & RbwrOverlay.UI.Behaviors namespaces pass
        string okXaml = ThemeService.PrepareThemeXaml(
            "<Styles xmlns=\"https://github.com/avaloniaui\" xmlns:b=\"using:RbwrOverlay.UI.Behaviors\" xmlns:a=\"using:Avalonia.Controls\"></Styles>", themeDir);
        Assert.Contains("using:RbwrOverlay.UI.Behaviors", okXaml);
    }

    private static void WriteTheme(string dir, string id, string minAppVersion)
    {
        Directory.CreateDirectory(dir);
        File.WriteAllText(Path.Combine(dir, "theme.json"),
            $$"""{"id":"{{id}}","name":"{{id}} name","version":"1.0.0","entry":"theme.axaml","min_app_version":"{{minAppVersion}}"}""");
        File.WriteAllText(Path.Combine(dir, "theme.axaml"), "<Styles xmlns=\"https://github.com/avaloniaui\" />");
    }

    [Fact]
    public void ThemesForANewerOverlay_AreHidden_NotInstalled_AndNotApplied()
    {
        string old = ThemeService.CurrentAppVersion;
        ThemeService.CurrentAppVersion = "2.3.1";
        try
        {
            string themes = Path.Combine(_tempDir, "themes-block");
            WriteTheme(Path.Combine(themes, "fits"), "fits", "2.3.1");
            WriteTheme(Path.Combine(themes, "too-new"), "too-new", "2.3.2"); // dropped into the folder by hand
            var svc = new ThemeService(themesDirectory: themes);

            // Not listed at all.
            var ids = svc.DiscoverThemes().Select(t => t.Id).ToList();
            Assert.Contains("fits", ids);
            Assert.DoesNotContain("too-new", ids);
            Assert.Contains(svc.DiscoverTooNewThemes(), t => t.Id == "too-new");

            // Applying it (e.g. remembered from before) fails cleanly with a clear message.
            var apply = svc.ApplyTheme("too-new");
            Assert.False(apply.Success);
            Assert.Contains("needs overlay v2.3.2 or newer", apply.ErrorMessage);

            // Installing from a folder or a .zip is refused before anything is copied.
            string source = Path.Combine(_tempDir, "src-too-new");
            WriteTheme(source, "shiny", "2.4.0");
            var fromFolder = svc.InstallTheme(Path.Combine(source, "theme.json"));
            Assert.False(fromFolder.Success);
            Assert.Contains("needs overlay v2.4.0 or newer", fromFolder.ErrorMessage);

            string zip = Path.Combine(_tempDir, "shiny.zip");
            ZipFile.CreateFromDirectory(source, zip);
            var fromZip = svc.InstallTheme(zip);
            Assert.False(fromZip.Success);
            Assert.Contains("needs overlay v2.4.0 or newer", fromZip.ErrorMessage);
            Assert.False(Directory.Exists(Path.Combine(themes, "shiny")));
        }
        finally
        {
            ThemeService.CurrentAppVersion = old;
        }
    }

    [Fact]
    public void TestMinAppVersionCompatibilityCheck()
    {
        Assert.True(ThemeService.IsCompatibleWithAppVersion(null, "2.3.0"));
        Assert.True(ThemeService.IsCompatibleWithAppVersion("2.3.0", "2.3.0"));
        Assert.True(ThemeService.IsCompatibleWithAppVersion("2.2.1", "2.3.0"));
        Assert.False(ThemeService.IsCompatibleWithAppVersion("2.4.0", "2.3.0"));
        Assert.False(ThemeService.IsCompatibleWithAppVersion("v3.0.0", "2.3.0"));
    }

    [Fact]
    public void TestInstallFromZipRejectsExcessiveEntryCount()
    {
        var svc = new ThemeService(themesDirectory: _tempDir);
        string zipPath = Path.Combine(_tempDir, "too-many.zip");
        using (var archive = ZipFile.Open(zipPath, ZipArchiveMode.Create))
        {
            for (int i = 0; i < 205; i++)
            {
                var entry = archive.CreateEntry($"f{i}.txt");
                using var w = new StreamWriter(entry.Open());
                w.Write("x");
            }
        }

        var (ok, _, err) = svc.InstallTheme(zipPath);
        Assert.False(ok);
        Assert.Contains("maximum allowed entry count", err, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void TestCornerRadiusEdgeConverterInsetsTopAndBottomCorners()
    {
        var outer = new Avalonia.CornerRadius(10, 10, 10, 10);
        var top = (Avalonia.CornerRadius)RbwrOverlay.UI.Converters.CornerRadiusEdgeConverter.TopOnly.Convert(
            outer, typeof(Avalonia.CornerRadius), null, System.Globalization.CultureInfo.InvariantCulture);
        var bottom = (Avalonia.CornerRadius)RbwrOverlay.UI.Converters.CornerRadiusEdgeConverter.BottomOnly.Convert(
            outer, typeof(Avalonia.CornerRadius), null, System.Globalization.CultureInfo.InvariantCulture);

        Assert.Equal(new Avalonia.CornerRadius(9, 9, 0, 0), top);
        Assert.Equal(new Avalonia.CornerRadius(0, 0, 9, 9), bottom);
    }

    private class MockThemeApiClient : IApiClient
    {
        public Task<List<ServerInfo>> GetLatestServersAsync(CancellationToken ct = default) => Task.FromResult(new List<ServerInfo>());
        public Task<ServerFetchResult> GetLatestServersDetailedAsync(CancellationToken ct = default) => Task.FromResult(ServerFetchResult.Success(new List<ServerInfo>()));
        public ServerInfo? FindServerByIdOrJobId(IEnumerable<ServerInfo> servers, string query) => null;
        public Task<bool> SubmitSuggestionAsync(string name, string suggestion, bool anonymous, CancellationToken ct = default) => Task.FromResult(true);
        public Task<bool> SubmitCrashReportAsync(string version, string traceback, string logData, string osInfo, CancellationToken ct = default) => Task.FromResult(true);
        public Task<UpdateInfo> CheckForUpdatesAsync(string currentVersion, string skippedVersion, CancellationToken ct = default) => Task.FromResult(new UpdateInfo());
        public Task DownloadUpdateAsync(string downloadUrl, string destinationPath, IProgress<double>? progress = null, CancellationToken ct = default) => Task.CompletedTask;
    }

    private class MockThemeProcessMonitor : IProcessMonitor
    {
        public bool IsRobloxActive { get; set; }
        public bool IsRobloxRunning { get; set; }
        public long? CurrentPlaceId { get; set; }
        public string? CurrentJobId { get; set; }
#pragma warning disable CS0067
        public event EventHandler<bool>? RobloxActiveChanged;
#pragma warning restore CS0067
        public void StartMonitoring() { }
        public void StopMonitoring() { }
        public string GetForegroundWindowInfo() => "RobloxPlayerBeta";
        public void Dispose() { }
    }
}