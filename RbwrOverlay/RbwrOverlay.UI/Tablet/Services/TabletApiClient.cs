using System.Text.Json;
using RbwrOverlay.Core.Services;
using RbwrOverlay.UI.Tablet.Models;

namespace RbwrOverlay.UI.Tablet.Services;

public sealed record FetchResult(bool Ok, string? Error, List<TabletServer> Servers);

public sealed class TabletApiClient : IDisposable
{
    private const string Url = "https://rbwr.hotment.dev/api/public-servers";
    private readonly HttpClient _http;

    public TabletApiClient()
    {
        _http = new HttpClient { Timeout = TimeSpan.FromSeconds(15) };
        _http.DefaultRequestHeaders.UserAgent.ParseAdd("RBWR-Operator-Tablet-App/1.0");
        _http.DefaultRequestHeaders.Accept.ParseAdd("application/json");
    }

    public async Task<FetchResult> GetServersAsync(CancellationToken ct = default)
    {
        try
        {
            using var resp = await _http.GetAsync(Url, ct);
            if (!resp.IsSuccessStatusCode)
                return new FetchResult(false, $"HTTP {(int)resp.StatusCode}", new());

            await using var stream = await resp.Content.ReadAsStreamAsync(ct);
            using var doc = await JsonDocument.ParseAsync(stream, cancellationToken: ct);
            var root = doc.RootElement;

            JsonElement arr = default;
            if (root.ValueKind == JsonValueKind.Object &&
                root.TryGetProperty("data", out var data) && data.ValueKind == JsonValueKind.Object &&
                data.TryGetProperty("servers", out var s)) arr = s;
            else if (root.ValueKind == JsonValueKind.Object && root.TryGetProperty("servers", out var s2)) arr = s2;

            var list = new List<TabletServer>();
            if (arr.ValueKind == JsonValueKind.Array)
            {
                foreach (var item in arr.EnumerateArray())
                {
                    if (item.ValueKind != JsonValueKind.Object ||
                        !item.TryGetProperty("state", out var state) || state.ValueKind != JsonValueKind.Object)
                        continue;

                    string job = Str(item, "jobId"), id = Str(item, "id");
                    if (job.Length == 0) job = id;
                    if (id.Length == 0) id = job;

                    DateTimeOffset? hb = null;
                    if (DateTimeOffset.TryParse(Str(item, "lastHeartbeat"), out var dto)) hb = dto;

                    list.Add(new TabletServer
                    {
                        JobId = job, Id = id, Heartbeat = hb,
                        Unit1 = Sub(state, "Unit1"), Unit2 = Sub(state, "Unit2"), Misc = Sub(state, "Misc")
                    });
                }
            }
            return new FetchResult(true, null, list);
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            return new FetchResult(false, "Cancelled", new());
        }
        catch (Exception ex)
        {
            return new FetchResult(false, ex.Message, new());
        }
    }

    public static TabletServer? Find(IEnumerable<TabletServer> servers, string query)
    {
        query = query.Trim();
        if (query.Length == 0) return null;
        var all = servers.ToList();
        return all.FirstOrDefault(s => s.JobId.Equals(query, StringComparison.OrdinalIgnoreCase) ||
                                       s.Id.Equals(query, StringComparison.OrdinalIgnoreCase))
            ?? all.FirstOrDefault(s => JobIdMatcher.IsMatch(query, s.JobId) || JobIdMatcher.IsMatch(query, s.Id));
    }

    private static string Str(JsonElement e, string name) =>
        e.TryGetProperty(name, out var p) && p.ValueKind == JsonValueKind.String ? p.GetString() ?? "" : "";

    private static JsonElement Sub(JsonElement e, string name) =>
        e.TryGetProperty(name, out var p) ? p.Clone() : default;

    public void Dispose() => _http.Dispose();
}
