using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Text;
using System.Text.Json.Nodes;
using RbwrThemeCreator.Services;
using RbwrThemeCreator.Services.Mcp;

namespace RbwrThemeCreator.Tests;

public sealed class McpServerTests
{
    // Minimal valid 1x1 transparent PNG image (67 bytes).
    private static readonly byte[] SamplePng = Convert.FromBase64String(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=");

    private static int GetFreeLoopbackPort()
    {
        using var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        return ((IPEndPoint)listener.LocalEndpoint).Port;
    }

    private static async Task<(HttpStatusCode Status, HttpResponseMessage Response, string Body)> PostRpcAsync(
        HttpClient http,
        string url,
        string json,
        string? origin = null)
    {
        using var req = new HttpRequestMessage(HttpMethod.Post, url)
        {
            Content = new StringContent(json, Encoding.UTF8, "application/json"),
        };
        if (origin != null)
            req.Headers.Add("Origin", origin);

        var res = await http.SendAsync(req);
        string body = await res.Content.ReadAsStringAsync();
        return (res.StatusCode, res, body);
    }

    [Fact]
    public async Task Initialize_And_Ping_And_Notification_WorkOverStreamableHttp()
    {
        int port = GetFreeLoopbackPort();
        using var server = new McpServer(() => [], () => [], "1.1.1");
        server.Start(port);
        Assert.True(server.IsRunning);
        Assert.Equal($"http://localhost:{port}/mcp", server.Url);

        using var http = new HttpClient();

        // 1. initialize
        var (status, res, body) = await PostRpcAsync(
            http,
            server.Url,
            """{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}""");

        Assert.Equal(HttpStatusCode.OK, status);
        Assert.Equal("rbwr-theme-creator", res.Headers.GetValues("Mcp-Session-Id").Single());

        var json = JsonNode.Parse(body)!.AsObject();
        var result = json["result"]!.AsObject();
        Assert.Equal("2025-06-18", result["protocolVersion"]!.GetValue<string>());
        Assert.Equal("rbwr-theme-creator", result["serverInfo"]!["name"]!.GetValue<string>());
        Assert.Equal("1.1.1", result["serverInfo"]!["version"]!.GetValue<string>());
        Assert.NotNull(result["capabilities"]!["tools"]);
        Assert.NotNull(result["capabilities"]!["resources"]);

        // 2. notifications/initialized (no id -> 202 Accepted)
        var (notifStatus, _, notifBody) = await PostRpcAsync(
            http,
            server.Url,
            """{"jsonrpc":"2.0","method":"notifications/initialized"}""");

        Assert.Equal(HttpStatusCode.Accepted, notifStatus);
        Assert.Equal(string.Empty, notifBody);

        // 3. ping
        var (pingStatus, _, pingBody) = await PostRpcAsync(
            http,
            server.Url,
            """{"jsonrpc":"2.0","id":"p1","method":"ping"}""");

        Assert.Equal(HttpStatusCode.OK, pingStatus);
        var pingJson = JsonNode.Parse(pingBody)!.AsObject();
        Assert.Equal("p1", pingJson["id"]!.GetValue<string>());
        Assert.NotNull(pingJson["result"]);

        server.Stop();
        Assert.False(server.IsRunning);
    }

    [Fact]
    public async Task Tools_ListAndCall_ReturnTextAndNativePngImageBlocks()
    {
        var tools = new List<McpTool>
        {
            new(
                "echo_text",
                "Echoes back a string",
                McpSchema.Obj(("msg", McpSchema.Str("Message"), true)),
                args => Task.FromResult(McpToolResult.Ok("echo:" + args["msg"]?.GetValue<string>()))),
            new(
                "render_preview",
                "Returns a rendered PNG preview image",
                McpSchema.Obj(("mode", McpSchema.Enum("View mode", "monitor", "all"), false)),
                args =>
                {
                    string mode = args["mode"]?.GetValue<string>() ?? "monitor";
                    return Task.FromResult(McpToolResult.Ok(
                        McpContentBlock.FromImage(SamplePng, "image/png"),
                        McpContentBlock.FromText($"Rendered {mode} preview (1x1 px).")));
                }),
        };

        int port = GetFreeLoopbackPort();
        using var server = new McpServer(() => tools, () => [], "1.1.1");
        server.Start(port);
        using var http = new HttpClient();

        // tools/list
        var (listStatus, _, listBody) = await PostRpcAsync(
            http,
            server.Url,
            """{"jsonrpc":"2.0","id":2,"method":"tools/list"}""");
        Assert.Equal(HttpStatusCode.OK, listStatus);
        var listed = JsonNode.Parse(listBody)!["result"]!["tools"]!.AsArray();
        Assert.Equal(2, listed.Count);
        Assert.Equal("echo_text", listed[0]!["name"]!.GetValue<string>());
        Assert.Equal("render_preview", listed[1]!["name"]!.GetValue<string>());

        // tools/call -> text tool
        var (echoStatus, _, echoBody) = await PostRpcAsync(
            http,
            server.Url,
            """{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"echo_text","arguments":{"msg":"reactor"}}}""");
        Assert.Equal(HttpStatusCode.OK, echoStatus);
        var echoResult = JsonNode.Parse(echoBody)!["result"]!.AsObject();
        Assert.False(echoResult["isError"]!.GetValue<bool>());
        Assert.Equal("echo:reactor", echoResult["content"]![0]!["text"]!.GetValue<string>());

        // tools/call -> image + text tool (render_preview)
        var (imgStatus, _, imgBody) = await PostRpcAsync(
            http,
            server.Url,
            """{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"render_preview","arguments":{"mode":"all"}}}""");
        Assert.Equal(HttpStatusCode.OK, imgStatus);
        var imgResult = JsonNode.Parse(imgBody)!["result"]!.AsObject();
        Assert.False(imgResult["isError"]!.GetValue<bool>());
        var content = imgResult["content"]!.AsArray();
        Assert.Equal(2, content.Count);

        var imageBlock = content[0]!.AsObject();
        Assert.Equal("image", imageBlock["type"]!.GetValue<string>());
        Assert.Equal("image/png", imageBlock["mimeType"]!.GetValue<string>());
        byte[] decoded = Convert.FromBase64String(imageBlock["data"]!.GetValue<string>());
        Assert.Equal(SamplePng, decoded);

        var textBlock = content[1]!.AsObject();
        Assert.Equal("text", textBlock["type"]!.GetValue<string>());
        Assert.Contains("Rendered all preview", textBlock["text"]!.GetValue<string>());
    }

    [Fact]
    public async Task Resources_ListAndRead_SupportTextAndBinaryPngBlobs()
    {
        var resources = new List<McpResource>
        {
            new(
                "rbwr://theme/state",
                "Theme State",
                "Theme JSON",
                "application/json",
                () => Task.FromResult(new McpResourceContent
                {
                    Uri = "rbwr://theme/state",
                    MimeType = "application/json",
                    Text = """{"id":"cyberpunk"}""",
                })),
            new(
                "rbwr://preview/monitor.png",
                "Live MONITOR Preview PNG",
                "PNG bytes",
                "image/png",
                () => Task.FromResult(new McpResourceContent
                {
                    Uri = "rbwr://preview/monitor.png",
                    MimeType = "image/png",
                    Blob = SamplePng,
                })),
        };

        int port = GetFreeLoopbackPort();
        using var server = new McpServer(() => [], () => resources, "1.1.1");
        server.Start(port);
        using var http = new HttpClient();

        // resources/list
        var (listStatus, _, listBody) = await PostRpcAsync(
            http,
            server.Url,
            """{"jsonrpc":"2.0","id":10,"method":"resources/list"}""");
        Assert.Equal(HttpStatusCode.OK, listStatus);
        var list = JsonNode.Parse(listBody)!["result"]!["resources"]!.AsArray();
        Assert.Equal(2, list.Count);
        Assert.Equal("rbwr://theme/state", list[0]!["uri"]!.GetValue<string>());
        Assert.Equal("rbwr://preview/monitor.png", list[1]!["uri"]!.GetValue<string>());

        // resources/read text
        var (textStatus, _, textBody) = await PostRpcAsync(
            http,
            server.Url,
            """{"jsonrpc":"2.0","id":11,"method":"resources/read","params":{"uri":"rbwr://theme/state"}}""");
        Assert.Equal(HttpStatusCode.OK, textStatus);
        var textContent = JsonNode.Parse(textBody)!["result"]!["contents"]![0]!.AsObject();
        Assert.Equal("application/json", textContent["mimeType"]!.GetValue<string>());
        Assert.Equal("""{"id":"cyberpunk"}""", textContent["text"]!.GetValue<string>());

        // resources/read binary PNG blob
        var (blobStatus, _, blobBody) = await PostRpcAsync(
            http,
            server.Url,
            """{"jsonrpc":"2.0","id":12,"method":"resources/read","params":{"uri":"rbwr://preview/monitor.png"}}""");
        Assert.Equal(HttpStatusCode.OK, blobStatus);
        var blobContent = JsonNode.Parse(blobBody)!["result"]!["contents"]![0]!.AsObject();
        Assert.Equal("image/png", blobContent["mimeType"]!.GetValue<string>());
        Assert.Equal(SamplePng, Convert.FromBase64String(blobContent["blob"]!.GetValue<string>()));
    }

    [Fact]
    public async Task BatchRequest_DispatchesRequestsAndSkipsNotifications()
    {
        int port = GetFreeLoopbackPort();
        using var server = new McpServer(() => [], () => [], "1.1.1");
        server.Start(port);
        using var http = new HttpClient();

        var (status, _, body) = await PostRpcAsync(
            http,
            server.Url,
            """[{"jsonrpc":"2.0","method":"notifications/initialized"},{"jsonrpc":"2.0","id":7,"method":"ping"}]""");

        Assert.Equal(HttpStatusCode.OK, status);
        var arr = JsonNode.Parse(body)!.AsArray();
        Assert.Single(arr);
        Assert.Equal(7, arr[0]!["id"]!.GetValue<int>());
    }

    [Fact]
    public async Task SecurityAndErrors_EnforceLocalOriginAndJsonRpcErrorCodes()
    {
        int port = GetFreeLoopbackPort();
        using var server = new McpServer(() => [], () => [], "1.1.1");
        server.Start(port);
        using var http = new HttpClient();

        // Non-local Origin -> 403 Forbidden
        var (evilStatus, _, _) = await PostRpcAsync(
            http,
            server.Url,
            """{"jsonrpc":"2.0","id":1,"method":"ping"}""",
            origin: "https://evil.example");
        Assert.Equal(HttpStatusCode.Forbidden, evilStatus);

        // Local Origin OPTIONS preflight -> 204 NoContent with CORS header
        using (var optReq = new HttpRequestMessage(HttpMethod.Options, server.Url))
        {
            optReq.Headers.Add("Origin", "http://localhost:5173");
            var optRes = await http.SendAsync(optReq);
            Assert.Equal(HttpStatusCode.NoContent, optRes.StatusCode);
            Assert.Equal("http://localhost:5173", optRes.Headers.GetValues("Access-Control-Allow-Origin").Single());
        }

        // Wrong path -> 404
        var wrongPathRes = await http.PostAsync(
            $"http://localhost:{port}/not-mcp",
            new StringContent("{}", Encoding.UTF8, "application/json"));
        Assert.Equal(HttpStatusCode.NotFound, wrongPathRes.StatusCode);

        // GET /mcp -> 405
        var getRes = await http.GetAsync(server.Url);
        Assert.Equal(HttpStatusCode.MethodNotAllowed, getRes.StatusCode);

        // DELETE /mcp -> 200
        var delRes = await http.DeleteAsync(server.Url);
        Assert.Equal(HttpStatusCode.OK, delRes.StatusCode);

        // Malformed JSON -> 400 with -32700
        var (parseStatus, _, parseBody) = await PostRpcAsync(http, server.Url, "{not-valid-json");
        Assert.Equal(HttpStatusCode.BadRequest, parseStatus);
        Assert.Equal(-32700, JsonNode.Parse(parseBody)!["error"]!["code"]!.GetValue<int>());

        // Unknown method -> -32601
        var (_, _, unknownMethodBody) = await PostRpcAsync(
            http,
            server.Url,
            """{"jsonrpc":"2.0","id":20,"method":"no/such/method"}""");
        Assert.Equal(-32601, JsonNode.Parse(unknownMethodBody)!["error"]!["code"]!.GetValue<int>());

        // Unknown tool -> -32602
        var (_, _, unknownToolBody) = await PostRpcAsync(
            http,
            server.Url,
            """{"jsonrpc":"2.0","id":21,"method":"tools/call","params":{"name":"does_not_exist"}}""");
        Assert.Equal(-32602, JsonNode.Parse(unknownToolBody)!["error"]!["code"]!.GetValue<int>());

        // Unknown resource -> -32602
        var (_, _, unknownResBody) = await PostRpcAsync(
            http,
            server.Url,
            """{"jsonrpc":"2.0","id":22,"method":"resources/read","params":{"uri":"rbwr://missing"}}""");
        Assert.Equal(-32602, JsonNode.Parse(unknownResBody)!["error"]!["code"]!.GetValue<int>());
    }

    [Fact]
    public void FontTools_And_CreatorSettings_Defaults_AreValid()
    {
        Assert.True(FontTools.IsFontFile("JetBrainsMono.ttf"));
        Assert.True(FontTools.IsFontFile("Inter.OTF"));
        Assert.True(FontTools.IsFontFile("Family.ttc"));
        Assert.False(FontTools.IsFontFile("bg.png"));

        Assert.True(FontTools.IsImageFile("bg.png"));
        Assert.True(FontTools.IsImageFile("photo.JPEG"));
        Assert.True(FontTools.IsImageFile("backdrop.webp"));
        Assert.False(FontTools.IsImageFile("theme.axaml"));

        var defaults = new CreatorSettings();
        Assert.False(defaults.McpServerEnabled);
        Assert.Equal(3917, defaults.McpServerPort);
    }
}
