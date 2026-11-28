using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace RbwrThemeCreator.Services.Ai;

public enum ChatRole { User, Assistant, Tool }

public sealed record ToolCall(string Id, string Name, string Arguments);

public sealed class ChatTurn
{
    public ChatRole Role { get; init; }
    public string Text { get; init; } = string.Empty;
    public IReadOnlyList<ToolCall> ToolCalls { get; init; } = [];
    public IReadOnlyList<ChatAttachment> Attachments { get; init; } = [];
    public string? ToolCallId { get; init; }
    public string? ToolName { get; init; }
}

public sealed record AiUsage(int Input, int Output, int CacheRead = 0, int CacheWrite = 0)
{
    public static AiUsage operator +(AiUsage a, AiUsage b) =>
        new(a.Input + b.Input, a.Output + b.Output, a.CacheRead + b.CacheRead, a.CacheWrite + b.CacheWrite);
}

public sealed record AiLimit(string Label, long Remaining, long Limit, string Reset)
{
    public double Fraction => Limit <= 0 ? 0 : Math.Clamp((double)Remaining / Limit, 0, 1);
    public string Text => $"{Label}: {Remaining:N0}/{Limit:N0}{(Reset.Length > 0 ? $" · resets in {Reset}" : "")}";
}

public sealed record AiRequest(AiProvider Provider, string Key, string Model, string BaseUrl, string System, bool LongCache);

public static class AiChatClient
{
    private const int MaxToolRounds = 10;
    private const int MaxToolResultChars = 6000;
    private const int KeepBinaryInLastTurns = 2;
    private const string CacheKey = "rbwr-theme-creator";

    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromMinutes(3) };

    // =====================================================================
    // Agent loop
    // =====================================================================

    public static async Task<AiUsage> RunAsync(AiRequest r, List<ChatTurn> history, IReadOnlyList<AiTool> tools, Action<ChatTurn> onTurn, CancellationToken ct)
    {
        var total = new AiUsage(0, 0);
        for (int round = 0; round <= MaxToolRounds; round++)
        {
            var (turn, usage) = await SendAsync(r, history, tools, ping: false, ct);
            total += usage;
            history.Add(turn);
            onTurn(turn);
            if (turn.ToolCalls.Count == 0 || round == MaxToolRounds) break;

            foreach (var call in turn.ToolCalls)
            {
                string result;
                var tool = tools.FirstOrDefault(t => t.Name == call.Name);
                if (tool == null) result = $"error: unknown tool {call.Name}";
                else
                {
                    try
                    {
                        var args = string.IsNullOrWhiteSpace(call.Arguments) ? new JsonObject() : JsonNode.Parse(call.Arguments) as JsonObject ?? new JsonObject();
                        result = await tool.Run(args);
                    }
                    catch (Exception ex) { result = $"error: {ex.Message}"; }
                }
                if (result.Length > MaxToolResultChars) result = result[..MaxToolResultChars] + "…(truncated)";
                var toolTurn = new ChatTurn { Role = ChatRole.Tool, Text = result, ToolCallId = call.Id, ToolName = call.Name };
                history.Add(toolTurn);
                onTurn(toolTurn);
            }
        }
        return total;
    }

    public static async Task<AiUsage> WarmAsync(AiRequest r, List<ChatTurn> history, IReadOnlyList<AiTool> tools, CancellationToken ct)
    {
        var (_, usage) = await SendAsync(r, history, tools, ping: true, ct);
        return usage;
    }

    private static Task<(ChatTurn, AiUsage)> SendAsync(AiRequest r, List<ChatTurn> history, IReadOnlyList<AiTool> tools, bool ping, CancellationToken ct) =>
        r.Provider.Style == AiApiStyle.Anthropic ? AnthropicAsync(r, history, tools, ping, ct) : OpenAiAsync(r, history, tools, ping, ct);

    private static HashSet<ChatTurn> TurnsKeepingBinary(List<ChatTurn> turns) =>
        turns.Where(t => t.Role == ChatRole.User && t.Attachments.Any(a => a.Kind != AttachmentKind.Text))
            .TakeLast(KeepBinaryInLastTurns).ToHashSet();

    private static string Placeholder(ChatAttachment a, string why) => $"[{a.Kind.ToString().ToLowerInvariant()} '{a.Name}' {why}]";

    private static string TextFile(ChatAttachment a) => $"--- file: {a.Name} ---\n{a.Text}\n--- end of {a.Name} ---";

    // =====================================================================
    // OpenAI-compatible
    // =====================================================================

    private static async Task<(ChatTurn, AiUsage)> OpenAiAsync(AiRequest r, List<ChatTurn> turns, IReadOnlyList<AiTool> tools, bool ping, CancellationToken ct)
    {
        var p = r.Provider;
        bool claudeViaRouter = p.Id == "openrouter" && r.Model.StartsWith("anthropic/", StringComparison.OrdinalIgnoreCase);
        var keep = TurnsKeepingBinary(turns);

        JsonNode systemContent = claudeViaRouter
            ? new JsonArray(new JsonObject { ["type"] = "text", ["text"] = r.System, ["cache_control"] = new JsonObject { ["type"] = "ephemeral" } })
            : JsonValue.Create(r.System)!;
        var messages = new JsonArray { new JsonObject { ["role"] = "system", ["content"] = systemContent } };
        JsonArray? lastUserParts = null;

        foreach (var t in turns)
        {
            switch (t.Role)
            {
                case ChatRole.User:
                    var parts = new JsonArray();
                    var text = new StringBuilder(t.Text);
                    foreach (var a in t.Attachments)
                    {
                        if (a.Kind == AttachmentKind.Text) { text.Append("\n\n").Append(TextFile(a)); continue; }
                        if (!keep.Contains(t)) { text.Append('\n').Append(Placeholder(a, "sent earlier, removed to save tokens")); continue; }
                        if (a.Kind == AttachmentKind.Image && p.Vision)
                            parts.Add(new JsonObject { ["type"] = "image_url", ["image_url"] = new JsonObject { ["url"] = a.DataUrl } });
                        else if (a.Kind == AttachmentKind.Pdf && p.Pdf)
                            parts.Add(new JsonObject { ["type"] = "file", ["file"] = new JsonObject { ["filename"] = a.Name, ["file_data"] = a.DataUrl } });
                        else text.Append('\n').Append(Placeholder(a, "not sent: this AI can't read it"));
                    }
                    parts.Insert(0, new JsonObject { ["type"] = "text", ["text"] = text.ToString() });
                    lastUserParts = parts;
                    messages.Add(new JsonObject { ["role"] = "user", ["content"] = parts.Count == 1 && !claudeViaRouter ? text.ToString() : parts });
                    break;
                case ChatRole.Assistant:
                    var m = new JsonObject { ["role"] = "assistant", ["content"] = t.Text.Length == 0 && t.ToolCalls.Count > 0 ? null : t.Text };
                    if (t.ToolCalls.Count > 0)
                        m["tool_calls"] = new JsonArray(t.ToolCalls.Select(c => (JsonNode)new JsonObject
                        {
                            ["id"] = c.Id, ["type"] = "function",
                            ["function"] = new JsonObject { ["name"] = c.Name, ["arguments"] = string.IsNullOrEmpty(c.Arguments) ? "{}" : c.Arguments },
                        }).ToArray());
                    messages.Add(m);
                    break;
                case ChatRole.Tool:
                    messages.Add(new JsonObject { ["role"] = "tool", ["tool_call_id"] = t.ToolCallId, ["content"] = t.Text });
                    break;
            }
        }
        if (claudeViaRouter && lastUserParts is { Count: > 0 })
            lastUserParts[^1]!["cache_control"] = new JsonObject { ["type"] = "ephemeral" };
        if (ping) messages.Add(new JsonObject { ["role"] = "user", ["content"] = "Keep-alive. Reply with one dot." });

        var body = new JsonObject { ["model"] = r.Model, ["messages"] = messages };
        if (p.Id == "openai") body["prompt_cache_key"] = CacheKey;
        if (ping) body[p.Id == "openai" ? "max_completion_tokens" : "max_tokens"] = 16;
        if (tools.Count > 0)
            body["tools"] = new JsonArray(tools.Select(t => (JsonNode)new JsonObject
            {
                ["type"] = "function",
                ["function"] = new JsonObject { ["name"] = t.Name, ["description"] = t.Description, ["parameters"] = t.Schema.DeepClone() },
            }).ToArray());

        using var req = new HttpRequestMessage(HttpMethod.Post, r.BaseUrl.TrimEnd('/') + "/chat/completions");
        if (!string.IsNullOrWhiteSpace(r.Key)) req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", r.Key.Trim());
        req.Content = new StringContent(body.ToJsonString(), Encoding.UTF8, "application/json");
        var json = await SendJsonAsync(req, ct, r.Provider.Id);

        var msg = json["choices"]?[0]?["message"];
        var calls = new List<ToolCall>();
        if (msg?["tool_calls"] is JsonArray tc)
            foreach (var c in tc)
            {
                string id = c?["id"]?.GetValue<string>() is { Length: > 0 } cid ? cid : "call_" + Guid.NewGuid().ToString("N")[..10];
                calls.Add(new ToolCall(id, c?["function"]?["name"]?.GetValue<string>() ?? string.Empty, c?["function"]?["arguments"]?.GetValue<string>() ?? "{}"));
            }

        var u = json["usage"];
        int cached = Int(u?["prompt_tokens_details"]?["cached_tokens"]) + Int(u?["prompt_cache_hit_tokens"]);
        var usage = new AiUsage(Int(u?["prompt_tokens"]), Int(u?["completion_tokens"]), cached, Int(u?["prompt_tokens_details"]?["cache_write_tokens"]));
        return (new ChatTurn { Role = ChatRole.Assistant, Text = msg?["content"]?.ToString() ?? string.Empty, ToolCalls = calls }, usage);
    }

    // =====================================================================
    // Anthropic Messages API
    // =====================================================================

    private static async Task<(ChatTurn, AiUsage)> AnthropicAsync(AiRequest r, List<ChatTurn> turns, IReadOnlyList<AiTool> tools, bool ping, CancellationToken ct)
    {
        JsonObject Cache() => r.LongCache ? new JsonObject { ["type"] = "ephemeral", ["ttl"] = "1h" } : new JsonObject { ["type"] = "ephemeral" };
        var keep = TurnsKeepingBinary(turns);
        var messages = new JsonArray();
        JsonArray? pendingResults = null;

        void FlushResults()
        {
            if (pendingResults == null) return;
            messages.Add(new JsonObject { ["role"] = "user", ["content"] = pendingResults });
            pendingResults = null;
        }

        foreach (var t in turns)
        {
            if (t.Role == ChatRole.Tool)
            {
                pendingResults ??= new JsonArray();
                pendingResults.Add(new JsonObject { ["type"] = "tool_result", ["tool_use_id"] = t.ToolCallId, ["content"] = t.Text });
                continue;
            }
            FlushResults();
            var content = new JsonArray();
            if (t.Role == ChatRole.User)
            {
                var text = new StringBuilder(t.Text);
                foreach (var a in t.Attachments)
                {
                    if (a.Kind == AttachmentKind.Text) { text.Append("\n\n").Append(TextFile(a)); continue; }
                    if (!keep.Contains(t)) { text.Append('\n').Append(Placeholder(a, "sent earlier, removed to save tokens")); continue; }
                    content.Add(new JsonObject
                    {
                        ["type"] = a.Kind == AttachmentKind.Image ? "image" : "document",
                        ["source"] = new JsonObject { ["type"] = "base64", ["media_type"] = a.MediaType, ["data"] = a.Base64 },
                    });
                }
                content.Add(new JsonObject { ["type"] = "text", ["text"] = text.Length == 0 ? "…" : text.ToString() });
                messages.Add(new JsonObject { ["role"] = "user", ["content"] = content });
                continue;
            }
            if (!string.IsNullOrWhiteSpace(t.Text)) content.Add(new JsonObject { ["type"] = "text", ["text"] = t.Text });
            foreach (var c in t.ToolCalls)
                content.Add(new JsonObject
                {
                    ["type"] = "tool_use", ["id"] = c.Id, ["name"] = c.Name,
                    ["input"] = (string.IsNullOrWhiteSpace(c.Arguments) ? null : JsonNode.Parse(c.Arguments)) ?? new JsonObject(),
                });
            if (content.Count == 0) content.Add(new JsonObject { ["type"] = "text", ["text"] = "…" });
            messages.Add(new JsonObject { ["role"] = "assistant", ["content"] = content });
        }
        FlushResults();

        if (messages.Count > 0 && messages[^1]!["content"] is JsonArray lastBlocks && lastBlocks.Count > 0)
            lastBlocks[^1]!["cache_control"] = Cache();
        if (ping) messages.Add(new JsonObject { ["role"] = "user", ["content"] = "Keep-alive. Reply with one dot." });

        var toolArr = new JsonArray(tools.Select(t => (JsonNode)new JsonObject
        {
            ["name"] = t.Name, ["description"] = t.Description, ["input_schema"] = t.Schema.DeepClone(),
        }).ToArray());
        if (toolArr.Count > 0) toolArr[^1]!["cache_control"] = Cache();

        var body = new JsonObject
        {
            ["model"] = r.Model,
            ["max_tokens"] = ping ? 1 : 4096,
            ["system"] = new JsonArray(new JsonObject { ["type"] = "text", ["text"] = r.System, ["cache_control"] = Cache() }),
            ["messages"] = messages,
        };
        if (toolArr.Count > 0) body["tools"] = toolArr;

        using var req = new HttpRequestMessage(HttpMethod.Post, r.BaseUrl.TrimEnd('/') + "/messages");
        AddAnthropicHeaders(req, r.Key);
        req.Content = new StringContent(body.ToJsonString(), Encoding.UTF8, "application/json");
        var json = await SendJsonAsync(req, ct, r.Provider.Id);

        var sb = new StringBuilder();
        var calls = new List<ToolCall>();
        if (json["content"] is JsonArray blocks)
            foreach (var b in blocks)
            {
                string type = b?["type"]?.GetValue<string>() ?? string.Empty;
                if (type == "text") sb.Append(b?["text"]?.GetValue<string>());
                else if (type == "tool_use")
                    calls.Add(new ToolCall(b?["id"]?.GetValue<string>() ?? string.Empty, b?["name"]?.GetValue<string>() ?? string.Empty, b?["input"]?.ToJsonString() ?? "{}"));
            }

        var u = json["usage"];
        int read = Int(u?["cache_read_input_tokens"]), write = Int(u?["cache_creation_input_tokens"]);
        var usage = new AiUsage(Int(u?["input_tokens"]) + read + write, Int(u?["output_tokens"]), read, write);
        return (new ChatTurn { Role = ChatRole.Assistant, Text = sb.ToString(), ToolCalls = calls }, usage);
    }

    private static void AddAnthropicHeaders(HttpRequestMessage req, string key)
    {
        req.Headers.Add("x-api-key", key.Trim());
        req.Headers.Add("anthropic-version", "2023-06-01");
    }

    // =====================================================================
    // Model lists
    // =====================================================================

    public static async Task<IReadOnlyList<AiModelInfo>> ListModelsAsync(AiProvider p, string key, string baseUrl, CancellationToken ct)
    {
        string url = p.Id switch
        {
            "github" => "https://models.github.ai/catalog/models",
            "anthropic" => baseUrl.TrimEnd('/') + "/models?limit=100",
            _ => baseUrl.TrimEnd('/') + "/models",
        };
        using var req = new HttpRequestMessage(HttpMethod.Get, url);
        if (p.Style == AiApiStyle.Anthropic) AddAnthropicHeaders(req, key);
        else if (!string.IsNullOrWhiteSpace(key)) req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", key.Trim());
        var json = await SendJsonAsync(req, ct, p.Id);

        var items = json as JsonArray ?? json["data"] as JsonArray ?? json["models"] as JsonArray ?? [];
        var list = new List<AiModelInfo>();
        foreach (var m in items)
        {
            string id = (m?["id"] ?? m?["name"])?.ToString() ?? string.Empty;
            if (id.StartsWith("models/")) id = id[7..];
            if (id.Length == 0) continue;
            string note = (m?["display_name"] ?? m?["name"])?.ToString() ?? string.Empty;
            list.Add(new AiModelInfo(id, note == id ? string.Empty : note));
        }
        return list;
    }

    // =====================================================================
    // Rate limits and balance
    // =====================================================================

    public static readonly System.Collections.Concurrent.ConcurrentDictionary<string, IReadOnlyList<AiLimit>> Limits = new();

    private static readonly (string Prefix, string Label)[] AnthropicLimits =
        [("requests", "Requests/min"), ("input-tokens", "Input tokens/min"), ("output-tokens", "Output tokens/min"), ("tokens", "Tokens/min")];

    private static readonly (string Suffix, string Label)[] OpenAiLimits = [("requests", "Requests"), ("tokens", "Tokens")];

    private static List<AiLimit> ReadLimits(HttpResponseMessage res)
    {
        string? H(string name) => res.Headers.TryGetValues(name, out var v) ? v.FirstOrDefault() : null;
        var list = new List<AiLimit>();
        foreach (var (prefix, label) in AnthropicLimits)
            if (long.TryParse(H($"anthropic-ratelimit-{prefix}-limit"), out long lim) && long.TryParse(H($"anthropic-ratelimit-{prefix}-remaining"), out long rem))
            {
                if (prefix == "tokens" && list.Any(l => l.Label.StartsWith("Input"))) continue;
                list.Add(new AiLimit(label, rem, lim, ResetText(H($"anthropic-ratelimit-{prefix}-reset"))));
            }
        foreach (var (suffix, label) in OpenAiLimits)
            if (long.TryParse(H($"x-ratelimit-limit-{suffix}"), out long lim) && long.TryParse(H($"x-ratelimit-remaining-{suffix}"), out long rem))
                list.Add(new AiLimit(label, rem, lim, ResetText(H($"x-ratelimit-reset-{suffix}"))));
        return list;
    }

    private static string ResetText(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return string.Empty;
        if (DateTimeOffset.TryParse(raw, out var at))
        {
            var left = at - DateTimeOffset.UtcNow;
            return left <= TimeSpan.Zero ? "now" : FormatSpan(left);
        }
        if (double.TryParse(raw, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out double secs))
            return FormatSpan(TimeSpan.FromSeconds(secs));
        return raw;
    }

    private static string FormatSpan(TimeSpan t) =>
        t.TotalHours >= 1 ? $"{(int)t.TotalHours}h {t.Minutes}m" : t.TotalMinutes >= 1 ? $"{(int)t.TotalMinutes}m {t.Seconds}s" : $"{Math.Max(1, (int)t.TotalSeconds)}s";

    public static async Task<string?> GetBalanceAsync(AiProvider p, string key, string baseUrl, CancellationToken ct)
    {
        string? url = p.Id switch
        {
            "openrouter" => baseUrl.TrimEnd('/') + "/key",
            "deepseek" => "https://api.deepseek.com/user/balance",
            _ => null,
        };
        if (url == null || string.IsNullOrWhiteSpace(key)) return null;
        using var req = new HttpRequestMessage(HttpMethod.Get, url);
        req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", key.Trim());
        var json = await SendJsonAsync(req, ct);
        if (p.Id == "deepseek")
        {
            var b = json["balance_infos"]?[0];
            return b == null ? null : $"Balance: {b["total_balance"]} {b["currency"]}";
        }
        var d = json["data"];
        if (d == null) return null;
        string free = d["is_free_tier"]?.ToString() == "true" ? " (free tier)" : string.Empty;
        string left = d["limit_remaining"] is JsonValue lr ? $"${lr} left" : "no credit limit";
        return $"Credits used: ${d["usage"]} · {left}{free}";
    }

    // =====================================================================
    // HTTP
    // =====================================================================

    private static int Int(JsonNode? n) => n is JsonValue v && v.TryGetValue<int>(out int i) ? i : 0;

    private static async Task<JsonNode> SendJsonAsync(HttpRequestMessage req, CancellationToken ct, string? providerId = null)
    {
        using var res = await Http.SendAsync(req, ct);
        if (providerId != null && ReadLimits(res) is { Count: > 0 } limits) Limits[providerId] = limits;
        string raw = await res.Content.ReadAsStringAsync(ct);
        JsonNode? json = null;
        try { json = JsonNode.Parse(raw); } catch (JsonException) { }
        if (!res.IsSuccessStatusCode)
        {
            string detail = json?["error"]?["message"]?.ToString() ?? json?["error"]?.ToString() ?? json?["message"]?.ToString() ?? raw;
            if (detail.Length > 400) detail = detail[..400];
            throw new InvalidOperationException($"{(int)res.StatusCode} {res.ReasonPhrase}: {detail}");
        }
        return json ?? throw new InvalidOperationException("Empty response.");
    }
}
