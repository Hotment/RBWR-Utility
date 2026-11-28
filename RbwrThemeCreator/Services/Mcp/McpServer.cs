using System.Net;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace RbwrThemeCreator.Services.Mcp;

/// <summary>
/// Localhost-only Streamable HTTP MCP server exposing RBWR Theme Creator tools and resources
/// (including live rendered PNG preview images) to external AI agents.
/// </summary>
public sealed class McpServer : IDisposable
{
    private const string ServerName = "rbwr-theme-creator";
    private const string DefaultProtocolVersion = "2025-06-18";

    private readonly Func<IReadOnlyList<McpTool>> _tools;
    private readonly Func<IReadOnlyList<McpResource>> _resources;
    private readonly string _serverVersion;
    private readonly object _lifecycleLock = new();

    private HttpListener? _listener;
    private CancellationTokenSource? _cts;

    public McpServer(
        Func<IReadOnlyList<McpTool>> tools,
        Func<IReadOnlyList<McpResource>> resources,
        string serverVersion)
    {
        _tools = tools;
        _resources = resources;
        _serverVersion = serverVersion;
    }

    public bool IsRunning => _listener?.IsListening == true;
    public int Port { get; private set; }
    public string Url => UrlFor(Port);

    public static string UrlFor(int port) => $"http://localhost:{port}/mcp";

    // =====================================================================
    // Lifecycle
    // =====================================================================

    public void Start(int port)
    {
        lock (_lifecycleLock)
        {
            StopLocked();

            HttpListener listener = CreateAndStartListener(port);
            _listener = listener;
            Port = port;
            _cts = new CancellationTokenSource();
            var ct = _cts.Token;
            _ = Task.Run(() => LoopAsync(listener, ct), ct);
        }
    }

    private static HttpListener CreateAndStartListener(int port)
    {
        // Try binding both localhost and 127.0.0.1 so clients using either loopback host work.
        var listener = new HttpListener();
        listener.Prefixes.Add($"http://localhost:{port}/");
        listener.Prefixes.Add($"http://127.0.0.1:{port}/");
        try
        {
            listener.Start();
            return listener;
        }
        catch
        {
            try { listener.Close(); } catch { }
            var fallback = new HttpListener();
            fallback.Prefixes.Add($"http://localhost:{port}/");
            fallback.Start();
            return fallback;
        }
    }

    public void Stop()
    {
        lock (_lifecycleLock)
        {
            StopLocked();
        }
    }

    private void StopLocked()
    {
        var cts = _cts;
        _cts = null;
        try { cts?.Cancel(); } catch { }
        try { cts?.Dispose(); } catch { }

        var listener = _listener;
        _listener = null;
        try { listener?.Stop(); } catch { }
        try { listener?.Close(); } catch { }
    }

    public void Dispose() => Stop();

    private async Task LoopAsync(HttpListener listener, CancellationToken ct)
    {
        while (!ct.IsCancellationRequested && listener.IsListening)
        {
            HttpListenerContext ctx;
            try
            {
                ctx = await listener.GetContextAsync();
            }
            catch
            {
                break;
            }
            _ = Task.Run(() => HandleAsync(ctx));
        }
    }

    // =====================================================================
    // Streamable HTTP transport (JSON-RPC 2.0)
    // =====================================================================

    private async Task HandleAsync(HttpListenerContext ctx)
    {
        var req = ctx.Request;
        var res = ctx.Response;
        bool responseStarted = false;
        try
        {
            string? origin = req.Headers["Origin"];
            if (!string.IsNullOrEmpty(origin))
            {
                if (!IsLocalOrigin(origin))
                {
                    res.StatusCode = 403;
                    return;
                }
                res.AddHeader("Access-Control-Allow-Origin", origin);
                res.AddHeader("Access-Control-Allow-Headers", "Content-Type, Accept, Mcp-Session-Id, MCP-Protocol-Version");
                res.AddHeader("Access-Control-Allow-Methods", "POST, DELETE, OPTIONS");
            }

            string path = req.Url?.AbsolutePath.TrimEnd('/') ?? string.Empty;
            if (!path.Equals("/mcp", StringComparison.OrdinalIgnoreCase))
            {
                res.StatusCode = 404;
                return;
            }

            if (req.HttpMethod == "OPTIONS")
            {
                res.StatusCode = 204;
                return;
            }

            if (req.HttpMethod == "DELETE")
            {
                res.StatusCode = 200;
                return;
            }

            if (req.HttpMethod != "POST")
            {
                res.StatusCode = 405;
                res.AddHeader("Allow", "POST, DELETE, OPTIONS");
                return;
            }

            string rawBody;
            using (var reader = new StreamReader(req.InputStream, req.ContentEncoding ?? Encoding.UTF8))
                rawBody = await reader.ReadToEndAsync();

            JsonNode? body;
            try
            {
                body = JsonNode.Parse(rawBody);
            }
            catch (JsonException ex)
            {
                responseStarted = true;
                await WriteJsonAsync(res, Error(null, -32700, $"Parse error: {ex.Message}"), 400);
                return;
            }

            JsonNode? reply;
            if (body is JsonArray batch)
            {
                if (batch.Count == 0)
                {
                    responseStarted = true;
                    await WriteJsonAsync(res, Error(null, -32600, "Invalid request: empty batch"), 400);
                    return;
                }
                var replies = new JsonArray();
                foreach (var item in batch)
                {
                    if (await DispatchAsync(item as JsonObject) is { } r)
                        replies.Add(r);
                }
                reply = replies.Count > 0 ? replies : null;
            }
            else
            {
                reply = await DispatchAsync(body as JsonObject);
            }

            if (reply == null)
            {
                res.StatusCode = 202;
                return;
            }

            responseStarted = true;
            await WriteJsonAsync(res, reply, 200);
        }
        catch (Exception ex)
        {
            CreatorLogging.Instance.Warning($"[MCP] Request handling error: {ex.Message}");
            if (!responseStarted)
            {
                try
                {
                    await WriteJsonAsync(res, Error(null, -32603, $"Internal error: {ex.Message}"), 500);
                }
                catch { }
            }
        }
        finally
        {
            try { res.Close(); } catch { }
        }
    }

    private static async Task WriteJsonAsync(HttpListenerResponse res, JsonNode payload, int statusCode)
    {
        res.StatusCode = statusCode;
        res.ContentType = "application/json; charset=utf-8";
        res.AddHeader("Mcp-Session-Id", ServerName);
        byte[] bytes = Encoding.UTF8.GetBytes(payload.ToJsonString());
        res.ContentLength64 = bytes.Length;
        await res.OutputStream.WriteAsync(bytes);
    }

    private static bool IsLocalOrigin(string origin) =>
        Uri.TryCreate(origin, UriKind.Absolute, out var u)
        && (u.IsLoopback || u.Host.Equals("localhost", StringComparison.OrdinalIgnoreCase));

    private async Task<JsonObject?> DispatchAsync(JsonObject? msg)
    {
        if (msg == null)
            return Error(null, -32600, "Invalid request");

        var id = msg["id"]?.DeepClone();
        string method = msg["method"]?.GetValue<string>() ?? string.Empty;

        // Notifications have no id and expect HTTP 202 Accepted with no JSON-RPC body.
        if (id == null)
            return null;

        switch (method)
        {
            case "initialize":
                return Ok(id, new JsonObject
                {
                    ["protocolVersion"] = msg["params"]?["protocolVersion"]?.GetValue<string>() ?? DefaultProtocolVersion,
                    ["capabilities"] = new JsonObject
                    {
                        ["tools"] = new JsonObject { ["listChanged"] = false },
                        ["resources"] = new JsonObject { ["subscribe"] = false, ["listChanged"] = false },
                    },
                    ["serverInfo"] = new JsonObject
                    {
                        ["name"] = ServerName,
                        ["version"] = _serverVersion,
                    },
                    ["instructions"] =
                        "Controls RBWR Theme Creator live. Call get_theme first to inspect the open theme, " +
                        "describe_tokens to discover colour tokens, set_tokens / set_shape / set_aprm_box / set_custom_xaml " +
                        "to edit the theme, and render_preview to inspect rendered PNG images of MONITOR, CONFIG, COMPACT, TABLET, or ALL views.",
                });

            case "ping":
                return Ok(id, new JsonObject());

            case "tools/list":
            {
                var arr = new JsonArray();
                foreach (var t in _tools())
                {
                    arr.Add(new JsonObject
                    {
                        ["name"] = t.Name,
                        ["description"] = t.Description,
                        ["inputSchema"] = t.InputSchema.DeepClone(),
                    });
                }
                return Ok(id, new JsonObject { ["tools"] = arr });
            }

            case "tools/call":
            {
                string name = msg["params"]?["name"]?.GetValue<string>() ?? string.Empty;
                var tool = _tools().FirstOrDefault(t => t.Name == name);
                if (tool == null)
                    return Error(id, -32602, $"Unknown tool '{name}'");

                var args = msg["params"]?["arguments"] as JsonObject ?? new JsonObject();
                McpToolResult result;
                try
                {
                    result = await tool.RunAsync(args);
                }
                catch (Exception ex)
                {
                    result = McpToolResult.Error($"Tool '{name}' failed: {ex.Message}");
                }

                var content = new JsonArray();
                foreach (var block in result.Content)
                    content.Add(block.ToJson());

                return Ok(id, new JsonObject
                {
                    ["content"] = content,
                    ["isError"] = result.IsError,
                });
            }

            case "resources/list":
            {
                var arr = new JsonArray();
                foreach (var r in _resources())
                {
                    arr.Add(new JsonObject
                    {
                        ["uri"] = r.Uri,
                        ["name"] = r.Name,
                        ["description"] = r.Description,
                        ["mimeType"] = r.MimeType,
                    });
                }
                return Ok(id, new JsonObject { ["resources"] = arr });
            }

            case "resources/read":
            {
                string uri = msg["params"]?["uri"]?.GetValue<string>() ?? string.Empty;
                var resource = _resources().FirstOrDefault(r => r.Uri.Equals(uri, StringComparison.OrdinalIgnoreCase));
                if (resource == null)
                    return Error(id, -32602, $"Unknown resource '{uri}'");

                try
                {
                    var content = await resource.ReadAsync();
                    return Ok(id, new JsonObject
                    {
                        ["contents"] = new JsonArray(content.ToJson()),
                    });
                }
                catch (Exception ex)
                {
                    return Error(id, -32603, $"Failed to read resource '{uri}': {ex.Message}");
                }
            }

            default:
                return Error(id, -32601, $"Method not found: {method}");
        }
    }

    private static JsonObject Ok(JsonNode id, JsonNode result) => new()
    {
        ["jsonrpc"] = "2.0",
        ["id"] = id,
        ["result"] = result,
    };

    private static JsonObject Error(JsonNode? id, int code, string message) => new()
    {
        ["jsonrpc"] = "2.0",
        ["id"] = id,
        ["error"] = new JsonObject
        {
            ["code"] = code,
            ["message"] = message,
        },
    };
}
