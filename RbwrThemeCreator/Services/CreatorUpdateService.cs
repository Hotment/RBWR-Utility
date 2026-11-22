using System.Net;
using System.Runtime.InteropServices;
using System.Text.Json;
using RbwrOverlay.Core.Models;
using RbwrThemeCreator.ViewModels;

namespace RbwrThemeCreator.Services;

public interface ICreatorUpdateService
{
    Task<UpdateInfo> CheckForUpdatesAsync(string currentVersion, string skippedVersion, CancellationToken ct = default);
    Task DownloadUpdateAsync(string downloadUrl, string destinationPath, IProgress<double>? progress = null, CancellationToken ct = default);
}

/// <summary>
/// Checks GitHub Releases for the latest <c>theme-creator-v*</c> release (non-draft, non-prerelease)
/// without interfering with the main overlay's <c>/releases/latest</c> stream.
/// </summary>
public sealed class CreatorUpdateService : ICreatorUpdateService
{
    public const string TagPrefix = "theme-creator-v";
    public const string ReleasesApiUrl = "https://api.github.com/repos/Hotment/RBWR-Utility/releases?per_page=20";

    private readonly HttpClient _httpClient;

    public CreatorUpdateService(HttpClient? httpClient = null)
    {
        _httpClient = httpClient ?? CreateDefaultHttpClient();
    }

    private static HttpClient CreateDefaultHttpClient()
    {
        var handler = new SocketsHttpHandler
        {
            ConnectTimeout = TimeSpan.FromSeconds(6),
            PooledConnectionLifetime = TimeSpan.FromMinutes(2),
            AutomaticDecompression = DecompressionMethods.All,
        };

        var client = new HttpClient(handler)
        {
            Timeout = TimeSpan.FromSeconds(20),
        };
        client.DefaultRequestHeaders.Add("User-Agent", $"RBWR-Theme-Creator/{MainViewModel.AppVersion}");
        client.DefaultRequestHeaders.Add("Accept", "application/vnd.github+json");
        return client;
    }

    public async Task<UpdateInfo> CheckForUpdatesAsync(string currentVersion, string skippedVersion, CancellationToken ct = default)
    {
        try
        {
            using var req = new HttpRequestMessage(HttpMethod.Get, ReleasesApiUrl);
            using var resp = await _httpClient.SendAsync(req, ct);
            if (!resp.IsSuccessStatusCode)
                return new UpdateInfo();

            string json = await resp.Content.ReadAsStringAsync(ct);
            return ParseLatestCreatorRelease(json, currentVersion, skippedVersion);
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            return new UpdateInfo();
        }
        catch
        {
            return new UpdateInfo();
        }
    }

    public async Task DownloadUpdateAsync(string downloadUrl, string destinationPath, IProgress<double>? progress = null, CancellationToken ct = default)
    {
        using var response = await _httpClient.GetAsync(downloadUrl, HttpCompletionOption.ResponseHeadersRead, ct);
        response.EnsureSuccessStatusCode();

        long? totalBytes = response.Content.Headers.ContentLength;
        await using var stream = await response.Content.ReadAsStreamAsync(ct);
        await using var fileStream = new FileStream(destinationPath, FileMode.Create, FileAccess.Write, FileShare.None, 8192, useAsync: true);

        byte[] buffer = new byte[8192];
        long totalRead = 0;
        int bytesRead;
        while ((bytesRead = await stream.ReadAsync(buffer, ct)) > 0)
        {
            await fileStream.WriteAsync(buffer.AsMemory(0, bytesRead), ct);
            totalRead += bytesRead;
            if (totalBytes.HasValue && totalBytes.Value > 0)
                progress?.Report((double)totalRead / totalBytes.Value);
        }
    }

    /// <summary>
    /// Parses a GitHub <c>/releases</c> JSON array and returns the newest non-draft, non-prerelease
    /// <c>theme-creator-v*</c> release if it is newer than <paramref name="currentVersion"/> and not skipped.
    /// </summary>
    public static UpdateInfo ParseLatestCreatorRelease(string json, string currentVersion, string skippedVersion)
    {
        var info = new UpdateInfo();
        if (string.IsNullOrWhiteSpace(json))
            return info;

        using var doc = JsonDocument.Parse(json);
        if (doc.RootElement.ValueKind != JsonValueKind.Array)
            return info;

        foreach (var release in doc.RootElement.EnumerateArray())
        {
            if (release.TryGetProperty("draft", out var draftProp) && draftProp.ValueKind == JsonValueKind.True)
                continue;
            if (release.TryGetProperty("prerelease", out var preProp) && preProp.ValueKind == JsonValueKind.True)
                continue;
            if (!release.TryGetProperty("tag_name", out var tagProp))
                continue;

            string tagName = (tagProp.GetString() ?? string.Empty).Trim();
            if (!tagName.StartsWith(TagPrefix, StringComparison.OrdinalIgnoreCase))
                continue;

            string latestVersion = tagName[TagPrefix.Length..].Trim();
            if (string.IsNullOrEmpty(latestVersion))
                continue;

            info.Version = latestVersion;

            bool isDifferent = !string.Equals(latestVersion, (currentVersion ?? string.Empty).Trim(), StringComparison.OrdinalIgnoreCase);
            bool isSkipped = !string.IsNullOrWhiteSpace(skippedVersion) &&
                             string.Equals(latestVersion, skippedVersion.Trim(), StringComparison.OrdinalIgnoreCase);

            if (isDifferent && !isSkipped)
            {
                info.IsAvailable = true;
                if (release.TryGetProperty("body", out var bodyProp))
                    info.ReleaseNotes = bodyProp.GetString() ?? string.Empty;

                if (release.TryGetProperty("assets", out var assetsProp) && assetsProp.ValueKind == JsonValueKind.Array)
                {
                    var (fileName, downloadUrl) = SelectBestAsset(assetsProp);
                    info.FileName = fileName;
                    info.DownloadUrl = downloadUrl;
                }
            }

            // Releases are returned newest-first by GitHub; stop at the first matching theme-creator-v* release.
            break;
        }

        return info;
    }

    public static bool IsNewerVersion(string candidate, string current)
    {
        string cleanCandidate = StripVersionSuffix(candidate);
        string cleanCurrent = StripVersionSuffix(current);

        if (Version.TryParse(cleanCandidate, out var candVer) && Version.TryParse(cleanCurrent, out var currVer))
        {
            var normCand = new Version(Math.Max(0, candVer.Major), Math.Max(0, candVer.Minor), Math.Max(0, candVer.Build), Math.Max(0, candVer.Revision));
            var normCurr = new Version(Math.Max(0, currVer.Major), Math.Max(0, currVer.Minor), Math.Max(0, currVer.Build), Math.Max(0, currVer.Revision));
            return normCand > normCurr;
        }

        return !string.IsNullOrEmpty(cleanCandidate) &&
               !string.Equals(candidate.Trim(), current.Trim(), StringComparison.OrdinalIgnoreCase);
    }

    private static string StripVersionSuffix(string version)
    {
        string trimmed = (version ?? string.Empty).Trim().TrimStart('v', 'V');
        int cut = trimmed.IndexOfAny(['-', '+']);
        return cut >= 0 ? trimmed[..cut] : trimmed;
    }

    internal static (string FileName, string DownloadUrl) SelectBestAsset(JsonElement assetsProp)
    {
        var all = new List<(string Name, string Url)>();
        foreach (var asset in assetsProp.EnumerateArray())
        {
            if (asset.TryGetProperty("name", out var nameProp) &&
                asset.TryGetProperty("browser_download_url", out var urlProp))
            {
                string name = nameProp.GetString() ?? string.Empty;
                string url = urlProp.GetString() ?? string.Empty;
                if (!string.IsNullOrEmpty(name) && !string.IsNullOrEmpty(url))
                    all.Add((name, url));
            }
        }

        if (all.Count == 0)
            return (string.Empty, string.Empty);

        // Prefer assets explicitly named for Theme Creator if present.
        var creatorAssets = all.Where(a =>
            a.Name.StartsWith("RBWR_Theme_Creator", StringComparison.OrdinalIgnoreCase) ||
            a.Name.StartsWith("RbwrThemeCreator", StringComparison.OrdinalIgnoreCase)).ToList();
        var candidates = creatorAssets.Count > 0 ? creatorAssets : all;

        string arch = RuntimeInformation.ProcessArchitecture switch
        {
            Architecture.Arm64 => "arm64",
            _ => "x64",
        };

        if (OperatingSystem.IsWindows())
        {
            var match = candidates.FirstOrDefault(c => c.Name.EndsWith($"-{arch}.exe", StringComparison.OrdinalIgnoreCase));
            if (!string.IsNullOrEmpty(match.Name)) return match;

            match = candidates.FirstOrDefault(c => c.Name.EndsWith(".exe", StringComparison.OrdinalIgnoreCase));
            if (!string.IsNullOrEmpty(match.Name)) return match;

            match = candidates.FirstOrDefault(c => c.Name.Contains("win", StringComparison.OrdinalIgnoreCase) && c.Name.EndsWith(".zip", StringComparison.OrdinalIgnoreCase));
            if (!string.IsNullOrEmpty(match.Name)) return match;
        }
        else if (OperatingSystem.IsLinux())
        {
            var match = candidates.FirstOrDefault(c => c.Name.Contains(arch, StringComparison.OrdinalIgnoreCase) && c.Name.EndsWith(".AppImage", StringComparison.OrdinalIgnoreCase));
            if (!string.IsNullOrEmpty(match.Name)) return match;

            match = candidates.FirstOrDefault(c => c.Name.Contains(arch, StringComparison.OrdinalIgnoreCase) &&
                (c.Name.EndsWith(".tar.gz", StringComparison.OrdinalIgnoreCase) || c.Name.EndsWith(".zip", StringComparison.OrdinalIgnoreCase)));
            if (!string.IsNullOrEmpty(match.Name)) return match;

            match = candidates.FirstOrDefault(c => c.Name.Contains("linux", StringComparison.OrdinalIgnoreCase));
            if (!string.IsNullOrEmpty(match.Name)) return match;
        }
        else if (OperatingSystem.IsMacOS())
        {
            var match = candidates.FirstOrDefault(c => c.Name.Contains(arch, StringComparison.OrdinalIgnoreCase) && c.Name.EndsWith(".zip", StringComparison.OrdinalIgnoreCase));
            if (!string.IsNullOrEmpty(match.Name)) return match;

            match = candidates.FirstOrDefault(c => c.Name.Contains("osx", StringComparison.OrdinalIgnoreCase) || c.Name.Contains("macos", StringComparison.OrdinalIgnoreCase));
            if (!string.IsNullOrEmpty(match.Name)) return match;
        }

        var fallback = candidates.FirstOrDefault(c => c.Name.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) || c.Name.EndsWith(".zip", StringComparison.OrdinalIgnoreCase));
        return !string.IsNullOrEmpty(fallback.Name) ? fallback : candidates[0];
    }
}