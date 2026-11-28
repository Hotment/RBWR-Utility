using System.Text.Json.Nodes;

namespace RbwrThemeCreator.Services.Mcp;

public sealed class McpContentBlock
{
    public string Type { get; init; } = "text";
    public string? Text { get; init; }
    public string? Data { get; init; }
    public string? MimeType { get; init; }

    public static McpContentBlock FromText(string text) => new() { Type = "text", Text = text };

    public static McpContentBlock FromImage(byte[] bytes, string mimeType = "image/png") => new()
    {
        Type = "image",
        Data = Convert.ToBase64String(bytes),
        MimeType = mimeType,
    };

    public JsonObject ToJson() => Type == "image"
        ? new JsonObject
        {
            ["type"] = "image",
            ["data"] = Data ?? string.Empty,
            ["mimeType"] = MimeType ?? "image/png",
        }
        : new JsonObject
        {
            ["type"] = "text",
            ["text"] = Text ?? string.Empty,
        };
}

public sealed class McpToolResult
{
    public IReadOnlyList<McpContentBlock> Content { get; init; } = [];
    public bool IsError { get; init; }

    public static McpToolResult Ok(string text) => new()
    {
        Content = [McpContentBlock.FromText(text)],
        IsError = false,
    };

    public static McpToolResult Ok(params McpContentBlock[] blocks) => new()
    {
        Content = blocks,
        IsError = false,
    };

    public static McpToolResult Error(string message) => new()
    {
        Content = [McpContentBlock.FromText(message)],
        IsError = true,
    };
}

public sealed record McpTool(
    string Name,
    string Description,
    JsonObject InputSchema,
    Func<JsonObject, Task<McpToolResult>> RunAsync);

public sealed class McpResourceContent
{
    public string Uri { get; init; } = string.Empty;
    public string MimeType { get; init; } = "text/plain";
    public string? Text { get; init; }
    public byte[]? Blob { get; init; }

    public JsonObject ToJson()
    {
        var o = new JsonObject
        {
            ["uri"] = Uri,
            ["mimeType"] = MimeType,
        };
        if (Blob != null) o["blob"] = Convert.ToBase64String(Blob);
        else o["text"] = Text ?? string.Empty;
        return o;
    }
}

public sealed record McpResource(
    string Uri,
    string Name,
    string Description,
    string MimeType,
    Func<Task<McpResourceContent>> ReadAsync);

public static class McpSchema
{
    public static JsonObject Obj(params (string Name, JsonObject Prop, bool Required)[] props)
    {
        var p = new JsonObject();
        var req = new JsonArray();
        foreach (var (name, prop, required) in props)
        {
            p[name] = prop;
            if (required) req.Add(name);
        }
        var o = new JsonObject { ["type"] = "object", ["properties"] = p };
        if (req.Count > 0) o["required"] = req;
        return o;
    }

    public static JsonObject Str(string description) => new() { ["type"] = "string", ["description"] = description };
    public static JsonObject Num(string description) => new() { ["type"] = "number", ["description"] = description };
    public static JsonObject Int(string description) => new() { ["type"] = "integer", ["description"] = description };
    public static JsonObject Bool(string description) => new() { ["type"] = "boolean", ["description"] = description };

    public static JsonObject Enum(string description, params string[] values)
    {
        var arr = new JsonArray();
        foreach (string v in values) arr.Add(v);
        return new JsonObject { ["type"] = "string", ["description"] = description, ["enum"] = arr };
    }

    public static JsonObject Arr(JsonObject items, string description) =>
        new() { ["type"] = "array", ["items"] = items, ["description"] = description };
}
