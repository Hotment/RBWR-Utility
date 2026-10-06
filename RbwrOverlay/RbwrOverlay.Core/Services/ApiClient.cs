using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Net.Sockets;
using System.Text.Json;
using RbwrOverlay.Core.Models;

namespace RbwrOverlay.Core.Services;

public interface IApiClient
{
    Task<List<ServerInfo>> GetLatestServersAsync(CancellationToken ct = default);
    Task<ServerFetchResult> GetLatestServersDetailedAsync(CancellationToken ct = default);
    ServerInfo? FindServerByIdOrJobId(IEnumerable<ServerInfo> servers, string query);
    Task<bool> SubmitSuggestionAsync(string name, string suggestion, bool anonymous, CancellationToken ct = default);
    Task<bool> SubmitCrashReportAsync(string version, string traceback, string logData, string osInfo, CancellationToken ct = default);
    Task<UpdateInfo> CheckForUpdatesAsync(string currentVersion, string skippedVersion, CancellationToken ct = default);
    Task DownloadUpdateAsync(string downloadUrl, string destinationPath, IProgress<double>? progress = null, CancellationToken ct = default);
}

public class ApiClient : IApiClient
{
    private const string BackendBaseUrl = "https://rbwr.hotment.dev";
    private const string GitHubRepoReleasesUrl = "https://api.github.com/repos/Hotment/RBWR-Utility/releases/latest";
    private readonly HttpClient _httpClient;
    private readonly ILoggingService _logger;

    public ApiClient(HttpClient? httpClient = null, ILoggingService? logger = null)
    {
        _httpClient = httpClient ?? CreateDefaultHttpClient();
        _logger = logger ?? LoggingService.Instance;
    }

    private static HttpClient CreateDefaultHttpClient()
    {
        var handler = new SocketsHttpHandler
        {
            ConnectTimeout = TimeSpan.FromSeconds(6),
            PooledConnectionLifetime = TimeSpan.FromMinutes(2),
            PooledConnectionIdleTimeout = TimeSpan.FromMinutes(1),
            AutomaticDecompression = DecompressionMethods.All,
            ConnectCallback = async (context, cancellationToken) =>
            {
                var entry = await Dns.GetHostEntryAsync(context.DnsEndPoint.Host, cancellationToken);
                var addresses = entry.AddressList
                    .OrderBy(a => a.AddressFamily == AddressFamily.InterNetwork ? 0 : 1)
                    .ToArray();

                Exception? lastEx = null;
                foreach (var address in addresses)
                {
                    var socket = new Socket(address.AddressFamily, SocketType.Stream, ProtocolType.Tcp)
                    {
                        NoDelay = true
                    };

                    try
                    {
                        using var connectCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
                        connectCts.CancelAfter(TimeSpan.FromSeconds(4));

                        await socket.ConnectAsync(new IPEndPoint(address, context.DnsEndPoint.Port), connectCts.Token);
                        return new NetworkStream(socket, ownsSocket: true);
                    }
                    catch (Exception ex)
                    {
                        lastEx = ex;
                        socket.Dispose();
                    }
                }

                if (lastEx != null)
                    throw lastEx;

                throw new SocketException((int)SocketError.HostNotFound);
            }
        };

        var client = new HttpClient(handler)
        {
            Timeout = TimeSpan.FromSeconds(15),
            DefaultRequestVersion = HttpVersion.Version11,
            DefaultVersionPolicy = HttpVersionPolicy.RequestVersionOrLower
        };

        client.DefaultRequestHeaders.Add("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 (RBWR-Overlay-Client/2.0)");
        client.DefaultRequestHeaders.Add("Accept", "application/json, text/plain, */*");
        client.DefaultRequestHeaders.Add("Accept-Language", "en-US,en;q=0.9");

        return client;
    }

    public async Task<ServerFetchResult> GetLatestServersDetailedAsync(CancellationToken ct = default)
    {
        try
        {
            using var req = new HttpRequestMessage(HttpMethod.Get, $"{BackendBaseUrl}/api/servers/latest");
            using var resp = await _httpClient.SendAsync(req, ct);
            if (resp.IsSuccessStatusCode)
            {
                string json = await resp.Content.ReadAsStringAsync(ct);
                try
                {
                    using var doc = JsonDocument.Parse(json);
                    var root = doc.RootElement;
                    var servers = ParseServersFromPayload(root);
                    return ServerFetchResult.Success(servers);
                }
                catch (JsonException jex)
                {
                    _logger.Warning($"Error parsing server JSON from {BackendBaseUrl}: {jex.Message}");
                    return ServerFetchResult.ParseFailure($"Invalid JSON response: {jex.Message}", jex);
                }
            }
            else
            {
                _logger.Warning($"Server API returned status code {resp.StatusCode}");
                return ServerFetchResult.HttpFailure(resp.StatusCode, $"Server returned HTTP {(int)resp.StatusCode} ({resp.StatusCode})");
            }
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            return ServerFetchResult.ConnectionFailure("Request was cancelled");
        }
        catch (OperationCanceledException ex) when (!ct.IsCancellationRequested)
        {
            _logger.Warning($"Timeout fetching servers from {BackendBaseUrl}: {ex.Message}");
            return ServerFetchResult.ConnectionFailure("Connection timed out", ex);
        }
        catch (HttpRequestException ex)
        {
            _logger.Warning($"HTTP request error fetching servers: {ex.Message}");
            string detail = !string.IsNullOrWhiteSpace(ex.Message) ? ex.Message : "HTTP connection failure";
            return ServerFetchResult.ConnectionFailure($"Connection error: {detail}", ex);
        }
        catch (SocketException ex)
        {
            _logger.Warning($"Socket error fetching servers: {ex.Message}");
            return ServerFetchResult.ConnectionFailure($"Network socket error ({ex.SocketErrorCode}): {ex.Message}", ex);
        }
        catch (TimeoutException ex)
        {
            _logger.Warning($"Timeout fetching servers: {ex.Message}");
            return ServerFetchResult.ConnectionFailure("Connection timed out", ex);
        }
        catch (Exception ex)
        {
            _logger.Warning($"Error fetching servers from {BackendBaseUrl}: {ex.Message}");
            if (ex.InnerException is SocketException or HttpRequestException)
            {
                return ServerFetchResult.ConnectionFailure($"Connection lost: {ex.InnerException.Message}", ex);
            }
            return ServerFetchResult.ConnectionFailure($"Connection error: {ex.Message}", ex);
        }
    }

    public async Task<List<ServerInfo>> GetLatestServersAsync(CancellationToken ct = default)
    {
        var result = await GetLatestServersDetailedAsync(ct);
        return result.Servers;
    }

    public List<ServerInfo> ParseServersFromPayload(JsonElement root)
    {
        var servers = new List<ServerInfo>();

        if (root.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in root.EnumerateArray())
            {
                servers.Add(ServerInfo.FromJsonElement(item));
            }
        }
        else if (root.ValueKind == JsonValueKind.Object)
        {
            if (root.TryGetProperty("servers", out var sProp) && sProp.ValueKind == JsonValueKind.Array)
            {
                foreach (var item in sProp.EnumerateArray())
                {
                    servers.Add(ServerInfo.FromJsonElement(item));
                }
            }
            else if (root.TryGetProperty("data", out var dProp))
            {
                if (dProp.ValueKind == JsonValueKind.Array)
                {
                    foreach (var item in dProp.EnumerateArray())
                    {
                        servers.Add(ServerInfo.FromJsonElement(item));
                    }
                }
                else if (dProp.ValueKind == JsonValueKind.Object)
                {
                    if (dProp.TryGetProperty("servers", out var dsProp) && dsProp.ValueKind == JsonValueKind.Array)
                    {
                        foreach (var item in dsProp.EnumerateArray())
                        {
                            servers.Add(ServerInfo.FromJsonElement(item));
                        }
                    }
                }
            }
        }

        return servers;
    }

    public ServerInfo? FindServerByIdOrJobId(IEnumerable<ServerInfo> servers, string query)
    {
        if (string.IsNullOrWhiteSpace(query))
            return null;

        query = query.Trim();

        foreach (var s in servers)
        {
            if (string.Equals(s.JobId, query, StringComparison.OrdinalIgnoreCase) ||
                string.Equals(s.Id, query, StringComparison.OrdinalIgnoreCase))
            {
                return s;
            }
        }

        var qParts = query.Split('-', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (qParts.Length >= 2)
        {
            foreach (var s in servers)
            {
                foreach (var candidate in new[] { s.JobId, s.Id })
                {
                    if (string.IsNullOrWhiteSpace(candidate)) continue;
                    var jParts = candidate.Split('-', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
                    if (jParts.Length >= 3)
                    {
                        if (string.Equals(jParts[1], qParts[0], StringComparison.OrdinalIgnoreCase) &&
                            string.Equals(jParts[2], qParts[1], StringComparison.OrdinalIgnoreCase))
                        {
                            return s;
                        }
                        if (qParts.Length >= 3 &&
                            string.Equals(jParts[1], qParts[1], StringComparison.OrdinalIgnoreCase) &&
                            string.Equals(jParts[2], qParts[2], StringComparison.OrdinalIgnoreCase))
                        {
                            return s;
                        }
                    }
                }
            }
        }

        foreach (var s in servers)
        {
            if (JobIdMatcher.IsMatch(query, s.JobId) || JobIdMatcher.IsMatch(query, s.Id))
            {
                return s;
            }
        }

        return null;
    }

    public async Task<bool> SubmitSuggestionAsync(string name, string suggestion, bool anonymous, CancellationToken ct = default)
    {
        try
        {
            var payload = new
            {
                name = anonymous ? string.Empty : name,
                suggestion,
                anonymous,
                target = "overlay",
                is_server_checker = false
            };

            using var resp = await _httpClient.PostAsJsonAsync($"{BackendBaseUrl}/suggestions", payload, ct);
            return resp.IsSuccessStatusCode;
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            return false;
        }
        catch (Exception ex)
        {
            _logger.Error("Failed to submit feedback", ex);
            return false;
        }
    }

    public async Task<bool> SubmitCrashReportAsync(string version, string traceback, string logData, string osInfo, CancellationToken ct = default)
    {
        try
        {
            var payload = new
            {
                version,
                traceback,
                log_data = logData,
                os_info = osInfo
            };

            using var resp = await _httpClient.PostAsJsonAsync($"{BackendBaseUrl}/crashes", payload, ct);
            return resp.IsSuccessStatusCode;
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            return false;
        }
        catch (Exception ex)
        {
            _logger.Error("Failed to submit crash report", ex);
            return false;
        }
    }

    public async Task<UpdateInfo> CheckForUpdatesAsync(string currentVersion, string skippedVersion, CancellationToken ct = default)
    {
        var info = new UpdateInfo();
        try
        {
            using var req = new HttpRequestMessage(HttpMethod.Get, GitHubRepoReleasesUrl);
            req.Headers.UserAgent.ParseAdd("Mozilla/5.0 (compatible; RBWR-Overlay-Client/2.0)");

            using var resp = await _httpClient.SendAsync(req, ct);
            if (resp.IsSuccessStatusCode)
            {
                string json = await resp.Content.ReadAsStringAsync(ct);
                using var doc = JsonDocument.Parse(json);
                var root = doc.RootElement;

                if (root.TryGetProperty("tag_name", out var tagProp))
                {
                    string tagName = tagProp.GetString() ?? string.Empty;
                    string latestVersion = tagName.TrimStart('v', 'V');
                    info.Version = latestVersion;

                    if (!string.IsNullOrEmpty(latestVersion) &&
                        !string.Equals(latestVersion, currentVersion, StringComparison.OrdinalIgnoreCase) &&
                        !string.Equals(latestVersion, skippedVersion, StringComparison.OrdinalIgnoreCase))
                    {
                        info.IsAvailable = true;
                        if (root.TryGetProperty("body", out var bodyProp))
                            info.ReleaseNotes = bodyProp.GetString() ?? "No release details available.";

                        if (root.TryGetProperty("assets", out var assetsProp) && assetsProp.ValueKind == JsonValueKind.Array)
                        {
                            foreach (var asset in assetsProp.EnumerateArray())
                            {
                                if (asset.TryGetProperty("name", out var nameProp) &&
                                    asset.TryGetProperty("browser_download_url", out var urlProp))
                                {
                                    string assetName = nameProp.GetString() ?? string.Empty;
                                    if (assetName.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) ||
                                        assetName.EndsWith(".zip", StringComparison.OrdinalIgnoreCase))
                                    {
                                        info.FileName = assetName;
                                        info.DownloadUrl = urlProp.GetString() ?? string.Empty;
                                        break;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            // Cancelled
        }
        catch (Exception ex)
        {
            _logger.Warning($"Update check skipped or failed: {ex.Message}");
        }

        return info;
    }

    public async Task DownloadUpdateAsync(string downloadUrl, string destinationPath, IProgress<double>? progress = null, CancellationToken ct = default)
    {
        using var response = await _httpClient.GetAsync(downloadUrl, HttpCompletionOption.ResponseHeadersRead, ct);
        response.EnsureSuccessStatusCode();

        long? totalBytes = response.Content.Headers.ContentLength;
        using var stream = await response.Content.ReadAsStreamAsync(ct);
        using var fileStream = new FileStream(destinationPath, FileMode.Create, FileAccess.Write, FileShare.None, 8192, true);

        byte[] buffer = new byte[8192];
        long totalRead = 0;
        int bytesRead;

        while ((bytesRead = await stream.ReadAsync(buffer, 0, buffer.Length, ct)) > 0)
        {
            await fileStream.WriteAsync(buffer.AsMemory(0, bytesRead), ct);
            totalRead += bytesRead;
            if (totalBytes.HasValue && totalBytes.Value > 0)
            {
                progress?.Report((double)totalRead / totalBytes.Value);
            }
        }
    }
}