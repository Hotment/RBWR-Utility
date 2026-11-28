using System.Net;
using System.Text;
using System.Text.Json.Nodes;

namespace RbwrThemeCreator.Services.Ai;

public sealed class McpServer : IDisposable
{
    private const string ServerName = "rbwr-theme-creator";
    private readonly Func<IReadOnlyList<AiTool>> _tools;
    private HttpListener? _listener;
    private CancellationTokenSource? _cts;

    public McpServer(Func<IReadOnlyList<AiTool>> tools) => _tools = tools;

    public bool IsRunning => _listener?.IsListening == true;
    public int Port { get; private set; }
    public string Url => $"http://localhost:{Port}/mcp";

    public static string UrlFor(int port) => $"http://localhost:{port}/mcp";

    // =====================================================================
    // Lifecycle
    // =====================================================================

    public void Start(int port)
    {
        Stop();
        var listener = new HttpListener();
        listener.Prefixes.Add($"http://localhost:{port}/");
        listener.Start();
        _listener = listener;
        Port = port;
        _cts = new CancellationTokenSource();
        _ = Task.Run(() => LoopAsync(listener, _cts.Token));
    }

    public void Stop()
    {
        _cts?.Cancel();
        try { _listener?.Stop(); _listener?.Close(); } catch { }
        _listener = null;
    }

    public void Dispose() => Stop();

    private async Task LoopAsync(HttpListener listener, CancellationToken ct)
    {
        while (!ct.IsCancellationRequested && listener.IsListening)
        {
            HttpListenerContext ctx;
            try { ctx = await listener.GetContextAsync(); }
            catch { break; }
            _ = Task.Run(() => HandleAsync(ctx));
        }
    }

    // =====================================================================
    // Streamable HTTP transport (JSON responses)
    // =====================================================================

    private async Task HandleAsync(HttpListenerContext ctx)
    {
        var res = ctx.Response;
        try
        {
            string? origin = ctx.Request.Headers["Origin"];
            if (!string.IsNullOrEmpty(origin) && !IsLocalOrigin(origin)) { res.StatusCode = 403; return; }
            if (!ctx.Request.Url!.AbsolutePath.TrimEnd('/').Equals("/mcp", StringComparison.OrdinalIgnoreCase)) { res.StatusCode = 404; return; }
            if (ctx.Request.HttpMethod == "DELETE") { res.StatusCode = 200; return; }
            if (ctx.Request.HttpMethod != "POST") { res.StatusCode = 405; res.AddHeader("Allow", "POST"); return; }

            using var reader = new StreamReader(ctx.Request.InputStream, Encoding.UTF8);
            var body = JsonNode.Parse(await reader.ReadToEndAsync());

            JsonNode? reply;
            if (body is JsonArray batch)
            {
                var replies = new JsonArray();
                foreach (var item in batch)
                    if (await DispatchAsync(item as JsonObject) is { } r) replies.Add(r);
                reply = replies.Count > 0 ? replies : null;
            }
            else reply = await DispatchAsync(body as JsonObject);

            if (reply == null) { res.StatusCode = 202; return; }
            res.ContentType = "application/json";
            res.AddHeader("Mcp-Session-Id", "rbwr");
            byte[] bytes = Encoding.UTF8.GetBytes(reply.ToJsonString());
            await res.OutputStream.WriteAsync(bytes);
        }
        catch
        {
            res.StatusCode = 400;
        }
        finally
        {
            try { res.Close(); } catch { }
        }
    }

    private static bool IsLocalOrigin(string origin) =>
        Uri.TryCreate(origin, UriKind.Absolute, out var u) && (u.IsLoopback || u.Host == "localhost");

    private async Task<JsonObject?> DispatchAsync(JsonObject? msg)
    {
        if (msg == null) return Error(null, -32600, "Invalid request");
        var id = msg["id"]?.DeepClone();
        string method = msg["method"]?.GetValue<string>() ?? string.Empty;
        if (id == null) return null;

        switch (method)
        {
            case "initialize":
                return Ok(id, new JsonObject
                {
                    ["protocolVersion"] = msg["params"]?["protocolVersion"]?.GetValue<string>() ?? "2025-06-18",
                    ["capabilities"] = new JsonObject { ["tools"] = new JsonObject() },
                    ["serverInfo"] = new JsonObject { ["name"] = ServerName, ["version"] = ViewModels.MainViewModel.AppVersion },
                    ["instructions"] = "Edits the theme open in RBWR Theme Creator. Call get_theme first; changes show in the live preview at once.",
                });
            case "ping":
                return Ok(id, new JsonObject());
            case "tools/list":
                return Ok(id, new JsonObject
                {
                    ["tools"] = new JsonArray(_tools().Select(t => (JsonNode)new JsonObject
                    {
                        ["name"] = t.Name, ["description"] = t.Description, ["inputSchema"] = t.Schema.DeepClone(),
                    }).ToArray()),
                });
            case "tools/call":
                string name = msg["params"]?["name"]?.GetValue<string>() ?? string.Empty;
                var tool = _tools().FirstOrDefault(t => t.Name == name);
                if (tool == null) return Error(id, -32602, $"Unknown tool {name}");
                string text;
                bool isError = false;
                try { text = await tool.Run(msg["params"]?["arguments"] as JsonObject ?? new JsonObject()); }
                catch (Exception ex) { text = ex.Message; isError = true; }
                return Ok(id, new JsonObject
                {
                    ["content"] = new JsonArray(new JsonObject { ["type"] = "text", ["text"] = text }),
                    ["isError"] = isError || text.StartsWith("error:", StringComparison.Ordinal),
                });
            default:
                return Error(id, -32601, $"Method not found: {method}");
        }
    }

    private static JsonObject Ok(JsonNode id, JsonNode result) => new() { ["jsonrpc"] = "2.0", ["id"] = id, ["result"] = result };

    private static JsonObject Error(JsonNode? id, int code, string message) =>
        new() { ["jsonrpc"] = "2.0", ["id"] = id, ["error"] = new JsonObject { ["code"] = code, ["message"] = message } };
}
