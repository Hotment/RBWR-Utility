namespace RbwrThemeCreator.Services.Ai;

public enum AiApiStyle { OpenAi, Anthropic }

public enum AiCacheKind { Auto, Explicit, None }

public sealed record AiModelInfo(string Id, string Note = "");

public sealed record AiProvider(
    string Id,
    string Name,
    string Tagline,
    string Glyph,
    AiApiStyle Style,
    string BaseUrl,
    IReadOnlyList<AiModelInfo> Models,
    string KeyUrl,
    string KeyHint,
    bool NeedsKey = true,
    bool Vision = true,
    bool Pdf = false,
    AiCacheKind Cache = AiCacheKind.Auto,
    string CacheNote = "");

public static class AiProviders
{
    public static readonly IReadOnlyList<AiProvider> All =
    [
        new("openai", "ChatGPT", "OpenAI GPT models", "G", AiApiStyle.OpenAi, "https://api.openai.com/v1",
            [new("gpt-5", "Strongest GPT"), new("gpt-5-mini", "Cheaper, fast"), new("gpt-4.1", "Good tool use"), new("gpt-4o-mini", "Cheapest")],
            "https://platform.openai.com/api-keys", "sk-…", Pdf: true,
            CacheNote: "Automatic from 1024 tokens; cached input is billed at a discount."),
        new("anthropic", "Claude", "Anthropic Claude models", "C", AiApiStyle.Anthropic, "https://api.anthropic.com/v1",
            [new("claude-sonnet-5-5", "Best balance — recommended"), new("claude-opus-5-5", "Most capable, slower and pricier"),
             new("claude-haiku-5-5", "Fastest and cheapest"), new("claude-fable-5-2", "Fable 5.2")],
            "https://console.anthropic.com/settings/keys", "sk-ant-…", Pdf: true, Cache: AiCacheKind.Explicit,
            CacheNote: "Cache points on tools, system and the newest message. Reads cost 10% of input; 5 min or 1 h lifetime."),
        new("github", "Copilot", "GitHub Models (Copilot account)", "◆", AiApiStyle.OpenAi, "https://models.github.ai/inference",
            [new("openai/gpt-4.1", "Good tool use"), new("openai/gpt-4o-mini", "Cheap, fast"), new("openai/gpt-5", "Strongest GPT"),
             new("deepseek/deepseek-v3-0324", "No images")],
            "https://github.com/settings/personal-access-tokens/new", "GitHub token with Models: read", Cache: AiCacheKind.None,
            CacheNote: "Free tier with rate limits; no cache discount."),
        new("gemini", "Gemini", "Google Gemini", "✦", AiApiStyle.OpenAi, "https://generativelanguage.googleapis.com/v1beta/openai",
            [new("gemini-2.5-flash", "Fast, cheap, sees images"), new("gemini-2.5-pro", "Strongest Gemini"), new("gemini-2.5-flash-lite", "Cheapest")],
            "https://aistudio.google.com/apikey", "AIza…", CacheNote: "Implicit caching on 2.5 models."),
        new("mistral", "Mistral", "Mistral AI", "M", AiApiStyle.OpenAi, "https://api.mistral.ai/v1",
            [new("mistral-medium-latest", "Sees images"), new("mistral-large-latest", "Strongest"), new("mistral-small-latest", "Cheap, sees images")],
            "https://console.mistral.ai/api-keys", "API key"),
        new("xai", "Grok", "xAI Grok", "X", AiApiStyle.OpenAi, "https://api.x.ai/v1",
            [new("grok-4", "Strongest, sees images"), new("grok-3-mini", "Cheap")],
            "https://console.x.ai", "xai-…", CacheNote: "Automatic prompt caching."),
        new("deepseek", "DeepSeek", "DeepSeek chat", "D", AiApiStyle.OpenAi, "https://api.deepseek.com/v1",
            [new("deepseek-chat", "Cheap, good tools"), new("deepseek-reasoner", "Thinks longer")],
            "https://platform.deepseek.com/api_keys", "sk-…", Vision: false,
            CacheNote: "Automatic disk cache in 64-token units."),
        new("groq", "Groq", "Fast open models", "Q", AiApiStyle.OpenAi, "https://api.groq.com/openai/v1",
            [new("openai/gpt-oss-120b", "Good tools"), new("llama-3.3-70b-versatile", "General"),
             new("meta-llama/llama-4-scout-17b-16e-instruct", "Sees images")],
            "https://console.groq.com/keys", "gsk_…", CacheNote: "Cached on some models."),
        new("openrouter", "OpenRouter", "Hundreds of models, one key", "R", AiApiStyle.OpenAi, "https://openrouter.ai/api/v1",
            [new("anthropic/claude-sonnet-4.5", "Claude via OpenRouter (cache points sent)"), new("openai/gpt-4o-mini", "Cheap"),
             new("google/gemini-2.5-flash", "Fast")],
            "https://openrouter.ai/keys", "sk-or-…", Pdf: true, CacheNote: "Claude models get cache points; others cache automatically."),
        new("ollama", "Ollama", "Local models, no key", "O", AiApiStyle.OpenAi, "http://localhost:11434/v1",
            [new("qwen2.5", "Good tools"), new("llama3.1", "General"), new("llama3.2-vision", "Sees images")],
            "https://ollama.com/download", "not needed", NeedsKey: false, Cache: AiCacheKind.None, CacheNote: "Runs on your PC — free."),
    ];

    public static AiProvider? Find(string? id) => All.FirstOrDefault(p => p.Id == id);
}
