using System.Text.Json;

namespace RbwrThemeCreator.Services.Ai;

public sealed class StoredTurn
{
    public ChatRole Role { get; set; }
    public string Text { get; set; } = string.Empty;
    public List<ToolCall> ToolCalls { get; set; } = new();
    public List<string> Attachments { get; set; } = new();
    public string? ToolCallId { get; set; }
    public string? ToolName { get; set; }
}

public sealed class StoredMessage
{
    public string Author { get; set; } = string.Empty;
    public string Text { get; set; } = string.Empty;
    public string Kind { get; set; } = "assistant";
    public List<string> Attachments { get; set; } = new();
}

public sealed class ChatSession
{
    public string Id { get; set; } = Guid.NewGuid().ToString("N")[..12];
    public string ProviderId { get; set; } = string.Empty;
    public string Model { get; set; } = string.Empty;
    public string Title { get; set; } = "New chat";
    public DateTime Updated { get; set; } = DateTime.Now;
    public List<StoredTurn> Turns { get; set; } = new();
    public List<StoredMessage> Messages { get; set; } = new();
}

public static class ChatStore
{
    private const int MaxSessions = 60;
    private static readonly JsonSerializerOptions Options = new() { WriteIndented = false };

    public static string Folder => Path.Combine(CreatorSettings.FolderPath, "chats");

    // =====================================================================
    // Conversion
    // =====================================================================

    public static StoredTurn ToStored(ChatTurn t) => new()
    {
        Role = t.Role, Text = t.Text, ToolCalls = t.ToolCalls.ToList(), ToolCallId = t.ToolCallId, ToolName = t.ToolName,
        Attachments = t.Attachments.Select(a => a.Name).ToList(),
    };

    public static ChatTurn FromStored(StoredTurn s) => new()
    {
        Role = s.Role, Text = s.Text, ToolCalls = s.ToolCalls, ToolCallId = s.ToolCallId, ToolName = s.ToolName,
        Attachments = s.Attachments.Select(n => new ChatAttachment
        {
            Name = n, Kind = AttachmentKind.Text, Text = $"[attachment '{n}' from an earlier session is not kept]",
        }).ToList(),
    };

    // =====================================================================
    // Disk
    // =====================================================================

    public static void Save(ChatSession session)
    {
        try
        {
            Directory.CreateDirectory(Folder);
            session.Updated = DateTime.Now;
            File.WriteAllText(Path.Combine(Folder, session.Id + ".json"), JsonSerializer.Serialize(session, Options));
            Prune();
        }
        catch (Exception ex)
        {
            CreatorLogging.Instance.Warning($"Chat save failed: {ex.Message}");
        }
    }

    public static List<ChatSession> LoadAll()
    {
        var list = new List<ChatSession>();
        if (!Directory.Exists(Folder)) return list;
        foreach (var file in Directory.EnumerateFiles(Folder, "*.json"))
        {
            try
            {
                if (JsonSerializer.Deserialize<ChatSession>(File.ReadAllText(file)) is { } s) list.Add(s);
            }
            catch
            {
            }
        }
        return list.OrderByDescending(s => s.Updated).ToList();
    }

    public static void Delete(string id)
    {
        try { File.Delete(Path.Combine(Folder, id + ".json")); }
        catch
        {
        }
    }

    private static void Prune()
    {
        var files = new DirectoryInfo(Folder).GetFiles("*.json").OrderByDescending(f => f.LastWriteTimeUtc).Skip(MaxSessions);
        foreach (var f in files)
            try { f.Delete(); }
            catch
            {
            }
    }
}
