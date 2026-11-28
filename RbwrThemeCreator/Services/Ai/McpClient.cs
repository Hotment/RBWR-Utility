using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace RbwrThemeCreator.Services.Ai;

public sealed class McpClient : IAsyncDisposable
{
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromMinutes(2) };
    private readonly McpServerConfig _config;
    private readonly ConcurrentDictionary<int, TaskCompletionSource<JsonNode>> _pending = new();
    private Process? _process;
    private string? _sessionId;
    private int _nextId;

    public McpClient(McpServerConfig config) => _config = config;

    public string Name => _config.Name;
    private bool IsHttp => _config.Target.StartsWith("http://", StringComparison.OrdinalIgnoreCase)
                           || _config.Target.StartsWith("https://", StringComparison.OrdinalIgnoreCase);

    // =====================================================================
    // Public API
    // =====================================================================

    public async Task<IReadOnlyList<AiTool>> ConnectAsync(CancellationToken ct)
    {
        if (!IsHttp) StartProcess();
        await RequestAsync("initialize", new JsonObject
        {
            ["protocolVersion"] = "2025-06-18",
            ["capabilities"] = new JsonObject(),
            ["clientInfo"] = new JsonObject { ["name"] = "rbwr-theme-creator", ["version"] = ViewModels.MainViewModel.AppVersion },
        }, ct);
        await NotifyAsync("notifications/initialized", ct);

        var list = await RequestAsync("tools/list", new JsonObject(), ct);
        string prefix = Slug(_config.Name);
        var tools = new List<AiTool>();
        foreach (var t in list["tools"] as JsonArray ?? [])
        {
            string name = t?["name"]?.GetValue<string>() ?? string.Empty;
            if (name.Length == 0) continue;
            string full = $"{prefix}__{Slug(name)}";
            if (full.Length > 64) full = full[..64];
            var schema = t?["inputSchema"] as JsonObject ?? new JsonObject { ["type"] = "object" };
            tools.Add(new AiTool(full, $"[{_config.Name}] {t?["description"]?.ToString()}", (JsonObject)schema.DeepClone(),
                args => CallAsync(name, args)));
        }
        return tools;
    }

    private async Task<string> CallAsync(string tool, JsonObject args)
    {
        var result = await RequestAsync("tools/call", new JsonObject { ["name"] = tool, ["arguments"] = args.DeepClone() }, CancellationToken.None);
        var parts = (result["content"] as JsonArray ?? [])
            .Select(c => c?["type"]?.GetValue<string>() == "text" ? c["text"]?.GetValue<string>() : $"[{c?["type"]}]")
            .Where(s => !string.IsNullOrEmpty(s));
        string text = string.Join("\n", parts);
        return result["isError"]?.GetValue<bool>() == true ? "error: " + text : text;
    }

    public async ValueTask DisposeAsync()
    {
        if (_process is { HasExited: false })
            try { _process.Kill(entireProcessTree: true); } catch { }
        _process?.Dispose();
        if (IsHttp && _sessionId != null)
            try
            {
                using var req = new HttpRequestMessage(HttpMethod.Delete, _config.Target);
                req.Headers.Add("Mcp-Session-Id", _sessionId);
                await Http.SendAsync(req);
            }
            catch { }
    }

    private static string Slug(string s)
    {
        string slug = Regex.Replace(s.Trim().ToLowerInvariant(), "[^a-z0-9_-]+", "_").Trim('_');
        return slug.Length == 0 ? "mcp" : slug;
    }

    // =====================================================================
    // JSON-RPC
    // =====================================================================

    private async Task<JsonNode> RequestAsync(string method, JsonObject @params, CancellationToken ct)
    {
        int id = Interlocked.Increment(ref _nextId);
        var msg = new JsonObject { ["jsonrpc"] = "2.0", ["id"] = id, ["method"] = method, ["params"] = @params };
        JsonNode reply = IsHttp ? await PostAsync(msg, id, ct) : await StdioAsync(msg, id, ct);
        if (reply["error"] is JsonNode err) throw new InvalidOperationException($"{_config.Name}: {err["message"]}");
        return reply["result"] ?? new JsonObject();
    }

    private async Task NotifyAsync(string method, CancellationToken ct)
    {
        var msg = new JsonObject { ["jsonrpc"] = "2.0", ["method"] = method };
        if (IsHttp) await PostAsync(msg, null, ct);
        else await WriteLineAsync(msg);
    }

    // =====================================================================
    // HTTP transport
    // =====================================================================

    private async Task<JsonNode> PostAsync(JsonObject msg, int? id, CancellationToken ct)
    {
        using var req = new HttpRequestMessage(HttpMethod.Post, _config.Target);
        req.Headers.Add("Accept", "application/json, text/event-stream");
        if (_sessionId != null) req.Headers.Add("Mcp-Session-Id", _sessionId);
        req.Content = new StringContent(msg.ToJsonString(), Encoding.UTF8, "application/json");
        using var res = await Http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, ct);
        if (res.Headers.TryGetValues("Mcp-Session-Id", out var sid)) _sessionId = sid.FirstOrDefault();
        if (id == null) return new JsonObject();
        res.EnsureSuccessStatusCode();

        if (res.Content.Headers.ContentType?.MediaType != "text/event-stream")
            return JsonNode.Parse(await res.Content.ReadAsStringAsync(ct)) ?? new JsonObject();

        using var stream = await res.Content.ReadAsStreamAsync(ct);
        using var reader = new StreamReader(stream);
        var data = new StringBuilder();
        while (await reader.ReadLineAsync(ct) is { } line)
        {
            if (line.StartsWith("data:")) { data.Append(line[5..].TrimStart()); continue; }
            if (line.Length != 0 || data.Length == 0) continue;
            var node = JsonNode.Parse(data.ToString());
            data.Clear();
            if (node?["id"]?.GetValue<int>() == id) return node;
        }
        throw new InvalidOperationException($"{_config.Name}: no reply");
    }

    // =====================================================================
    // stdio transport
    // =====================================================================

    private void StartProcess()
    {
        var psi = OperatingSystem.IsWindows()
            ? new ProcessStartInfo("cmd.exe") { ArgumentList = { "/c", _config.Target } }
            : new ProcessStartInfo("/bin/sh") { ArgumentList = { "-c", _config.Target } };
        psi.RedirectStandardInput = true;
        psi.RedirectStandardOutput = true;
        psi.RedirectStandardError = true;
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        psi.StandardOutputEncoding = Encoding.UTF8;
        _process = Process.Start(psi) ?? throw new InvalidOperationException($"{_config.Name}: could not start");
        _process.ErrorDataReceived += (_, _) => { };
        _process.BeginErrorReadLine();
        _ = Task.Run(ReadLoopAsync);
    }

    private async Task ReadLoopAsync()
    {
        var output = _process!.StandardOutput;
        while (await output.ReadLineAsync() is { } line)
        {
            JsonNode? node;
            try { node = JsonNode.Parse(line); } catch { continue; }
            if (node?["id"] is JsonValue v && v.TryGetValue<int>(out int id) && _pending.TryRemove(id, out var tcs))
                tcs.TrySetResult(node);
        }
        foreach (var tcs in _pending.Values) tcs.TrySetException(new InvalidOperationException($"{_config.Name}: process exited"));
    }

    private async Task<JsonNode> StdioAsync(JsonObject msg, int id, CancellationToken ct)
    {
        var tcs = new TaskCompletionSource<JsonNode>(TaskCreationOptions.RunContinuationsAsynchronously);
        _pending[id] = tcs;
        await WriteLineAsync(msg);
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeout.CancelAfter(TimeSpan.FromSeconds(60));
        await using (timeout.Token.Register(() => tcs.TrySetException(new TimeoutException($"{_config.Name}: timed out"))))
            return await tcs.Task;
    }

    private async Task WriteLineAsync(JsonObject msg)
    {
        var input = _process!.StandardInput;
        await input.WriteLineAsync(msg.ToJsonString());
        await input.FlushAsync();
    }
}
