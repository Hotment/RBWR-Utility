using System.Text.Json.Nodes;

namespace RbwrThemeCreator.Services.Ai;

public sealed record AiTool(string Name, string Description, JsonObject Schema, Func<JsonObject, Task<string>> Run);

public static class Schema
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
    public static JsonObject Bool(string description) => new() { ["type"] = "boolean", ["description"] = description };

    public static JsonObject Arr(JsonObject items, string description) =>
        new() { ["type"] = "array", ["items"] = items, ["description"] = description };
}
