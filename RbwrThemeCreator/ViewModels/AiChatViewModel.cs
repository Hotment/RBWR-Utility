using System.Collections.ObjectModel;
using Avalonia.Media.Imaging;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using RbwrThemeCreator.Services;
using RbwrThemeCreator.Services.Ai;

namespace RbwrThemeCreator.ViewModels;

public interface IAiChatHost
{
    Task<Bitmap?> CaptureScreenAsync();
    Bitmap? RenderPreviewBitmap();
    Task<IReadOnlyList<string>> PickFilesAsync();
    Task<Bitmap?> ClipboardImageAsync();
}

public sealed partial class AiProviderItem : ObservableObject
{
    private readonly AiChatViewModel _owner;

    public AiProviderItem(AiProvider provider, AiChatViewModel owner)
    {
        Provider = provider;
        Logo = AiLogos.Paths.TryGetValue(provider.Id == "anthropic" ? "claude" : provider.Id, out var d) ? Avalonia.Media.StreamGeometry.Parse(d) : null;
        LogoBrush = new Avalonia.Media.SolidColorBrush(Avalonia.Media.Color.Parse(provider.Id switch
        {
            "anthropic" => "#D97757",
            "gemini" => "#8E75B2",
            "mistral" => "#FA520F",
            "deepseek" => "#4D6BFE",
            "openrouter" => "#94A3B8",
            _ => "#FFFFFF",
        }));
        _owner = owner;
        _keyInput = CreatorSettings.Current.AiKeys.GetValueOrDefault(provider.Id, string.Empty);
        _baseUrlInput = CreatorSettings.Current.AiBaseUrls.GetValueOrDefault(provider.Id, string.Empty);
    }

    public AiProvider Provider { get; }
    public string Name => Provider.Name;
    public string Tagline => Provider.Tagline;
    public string Glyph => Provider.Glyph;
    public Avalonia.Media.Geometry? Logo { get; }
    public bool HasLogo => Logo != null;
    public Avalonia.Media.IBrush LogoBrush { get; }
    public string KeyHint => Provider.KeyHint;
    public bool NeedsKey => Provider.NeedsKey;
    public bool IsReady => !Provider.NeedsKey || !string.IsNullOrWhiteSpace(CreatorSettings.Current.AiKeys.GetValueOrDefault(Provider.Id));
    public string StatusText => IsReady ? "READY" : "NO KEY";
    public string Features => string.Join(" · ", new[]
    {
        Provider.Vision ? "images" : null,
        Provider.Pdf ? "PDF" : null,
        Provider.Cache switch { AiCacheKind.Explicit => "cache", AiCacheKind.Auto => "auto cache", _ => null },
        "tools",
    }.Where(s => s != null));
    public string BaseUrl => string.IsNullOrWhiteSpace(CreatorSettings.Current.AiBaseUrls.GetValueOrDefault(Provider.Id))
        ? Provider.BaseUrl : CreatorSettings.Current.AiBaseUrls[Provider.Id].Trim();

    [ObservableProperty] private string _keyInput;
    [ObservableProperty] private string _baseUrlInput;

    [RelayCommand]
    private void SaveKey()
    {
        var s = CreatorSettings.Current;
        if (string.IsNullOrWhiteSpace(KeyInput)) s.AiKeys.Remove(Provider.Id);
        else s.AiKeys[Provider.Id] = KeyInput.Trim();
        if (string.IsNullOrWhiteSpace(BaseUrlInput)) s.AiBaseUrls.Remove(Provider.Id);
        else s.AiBaseUrls[Provider.Id] = BaseUrlInput.Trim();
        s.Save();
        OnPropertyChanged(nameof(IsReady));
        OnPropertyChanged(nameof(StatusText));
        _owner.RefreshKeyState();
        _owner.Main.SetStatus($"{Name}: saved.");
    }

    [RelayCommand]
    private void GetKey() => _owner.OpenUrl(Provider.KeyUrl);

    [RelayCommand]
    private void Choose() => _owner.Select(this);
}

public sealed class ChatMessageItem
{
    public string Author { get; init; } = string.Empty;
    public string Text { get; init; } = string.Empty;
    public bool IsUser { get; init; }
    public bool IsAssistant { get; init; }
    public bool IsTool { get; init; }
    public bool IsError { get; init; }
    public IReadOnlyList<ChatAttachment> Attachments { get; init; } = [];
    public bool HasAttachments => Attachments.Count > 0;
}

public sealed record ChatCommand(string Name, string Args, string Help);

public sealed partial class AttachmentItem(ChatAttachment attachment, AiChatViewModel owner) : ObservableObject
{
    public ChatAttachment Attachment { get; } = attachment;
    public string Label => Attachment.Label;
    public Bitmap? Thumbnail => Attachment.Thumbnail;

    [RelayCommand]
    private void Remove() => owner.Pending.Remove(this);
}

public sealed partial class McpServerItem : ObservableObject
{
    public McpServerItem(McpServerConfig config, AiChatViewModel owner)
    {
        Config = config;
        Owner = owner;
    }

    public McpServerConfig Config { get; }
    public AiChatViewModel Owner { get; }
    public string Name => Config.Name;
    public string Target => Config.Target;
    public string Kind => Config.Target.StartsWith("http", StringComparison.OrdinalIgnoreCase) ? "HTTP" : "STDIO";

    public bool Enabled
    {
        get => Config.Enabled;
        set
        {
            Config.Enabled = value;
            CreatorSettings.Current.Save();
            OnPropertyChanged();
        }
    }

    [ObservableProperty] private string _state = "not connected";

    [RelayCommand]
    private void Remove() => Owner.RemoveMcpServer(this);
}

public sealed partial class AiChatViewModel : ObservableObject
{
    private const string SystemPrompt =
        "You are the assistant inside RBWR Theme Creator, an editor for themes of the RBWR overlay (a game HUD). " +
        "Use the tools to read and change the open theme; changes appear in the live preview immediately. " +
        "Call get_theme before editing. Batch colour changes in one set_tokens call. Keep good text contrast. " +
        "Images the user attaches may be screenshots of the game or the overlay, or inspiration. " +
        "Answer briefly, in the user's language.";

    public static readonly IReadOnlyList<ChatCommand> AllCommands =
    [
        new("/help", "", "List the commands"),
        new("/clear", "", "Clear the chat (and its memory)"),
        new("/model", "[name]", "Show or change the model"),
        new("/models", "", "Load the model list from the provider"),
        new("/compact", "", "Summarise the chat to save tokens"),
        new("/tokens", "", "Token and cache usage"),
        new("/undo", "", "Undo the last theme change"),
        new("/theme", "", "Send the current theme with your next message"),
        new("/preview", "", "Attach a picture of the live preview"),
        new("/screenshot", "", "Attach a screenshot of the screen"),
        new("/paste", "", "Attach an image from the clipboard"),
        new("/file", "", "Attach files"),
        new("/cache", "[5m|1h|warm|cold]", "Claude cache length and keep-warm"),
        new("/back", "", "Pick another AI"),
    ];

    private readonly McpServer _server;
    private readonly List<ChatTurn> _history = new();
    private readonly List<McpClient> _mcpClients = new();
    private readonly DispatcherTimer _warmTimer;
    private List<AiTool> _mcpTools = new();
    private CancellationTokenSource? _cts;
    private AiUsage _session = new(0, 0);
    private AiUsage? _last;
    private DateTime _lastActivity;
    private bool _attachTheme;

    public AiChatViewModel(MainViewModel main)
    {
        Main = main;
        Providers = AiProviders.All.Select(p => new AiProviderItem(p, this)).ToList();
        foreach (var cfg in CreatorSettings.Current.McpServers) McpServers.Add(new McpServerItem(cfg, this));
        _server = new McpServer(() => Main.ThemeTools);
        _mcpPortInput = CreatorSettings.Current.McpServerPort.ToString();
        _historyLimit = Math.Clamp(CreatorSettings.Current.AiHistoryLimit, 2, 60);
        _warmTimer = new DispatcherTimer();
        _warmTimer.Tick += async (_, _) => await WarmTickAsync();
        Pending.CollectionChanged += (_, _) => OnPropertyChanged(nameof(HasPending));
        if (CreatorSettings.Current.McpServerEnabled) StartServer();
        AppDomain.CurrentDomain.ProcessExit += (_, _) => Shutdown();
    }

    public MainViewModel Main { get; }
    public IAiChatHost? Host { get; set; }
    public IReadOnlyList<AiProviderItem> Providers { get; }
    public ObservableCollection<ChatMessageItem> Messages { get; } = new();
    public ObservableCollection<string> Models { get; } = new();
    public ObservableCollection<AiModelInfo> ModelInfos { get; } = new();
    public ObservableCollection<McpServerItem> McpServers { get; } = new();
    public ObservableCollection<AttachmentItem> Pending { get; } = new();
    public ObservableCollection<ChatCommand> CommandSuggestions { get; } = new();
    public bool HasPending => Pending.Count > 0;
    public bool HasCommandSuggestions => CommandSuggestions.Count > 0;

    // =====================================================================
    // Provider and model selection
    // =====================================================================

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(HasProvider), nameof(ShowPicker), nameof(ProviderTitle), nameof(NeedsKeyWarning), nameof(CacheInfo), nameof(IsClaude))]
    private AiProviderItem? _selected;

    public bool HasProvider => Selected != null;
    public bool ShowPicker => Selected == null;
    public bool IsClaude => Selected?.Provider.Cache == AiCacheKind.Explicit;
    public string ProviderTitle => Selected == null ? "AI" : $"{Selected.Name} · {Selected.Features}";
    public bool NeedsKeyWarning => Selected is { IsReady: false };
    public string CacheInfo => Selected?.Provider.CacheNote ?? string.Empty;

    public void RefreshKeyState() => OnPropertyChanged(nameof(NeedsKeyWarning));

    [ObservableProperty] private string _model = string.Empty;
    [ObservableProperty] private bool _isLoadingModels;

    public void Select(AiProviderItem item)
    {
        Selected = item;
        SetModelList(item.Provider.Models);
        Model = CreatorSettings.Current.AiModels.GetValueOrDefault(item.Provider.Id) ?? item.Provider.Models[0].Id;
        CreatorSettings.Current.LastAiProvider = item.Provider.Id;
        CreatorSettings.Current.Save();
        OnPropertyChanged(nameof(NeedsKeyWarning));
        UpdateUsageText();
    }

    private void SetModelList(IEnumerable<AiModelInfo> models)
    {
        ModelInfos.Clear();
        Models.Clear();
        foreach (var m in models)
        {
            ModelInfos.Add(m);
            Models.Add(m.Id);
        }
    }

    partial void OnModelChanged(string value)
    {
        if (Selected == null || string.IsNullOrWhiteSpace(value)) return;
        CreatorSettings.Current.AiModels[Selected.Provider.Id] = value.Trim();
        CreatorSettings.Current.Save();
    }

    [RelayCommand]
    private void PickModel(AiModelInfo? info)
    {
        if (info != null) Model = info.Id;
    }

    [RelayCommand]
    private async Task RefreshModelsAsync()
    {
        if (Selected == null) return;
        IsLoadingModels = true;
        try
        {
            var list = await AiChatClient.ListModelsAsync(Selected.Provider, KeyFor(Selected), Selected.BaseUrl, CancellationToken.None);
            if (list.Count == 0) { Main.SetStatus("The provider returned no models."); return; }
            var known = Selected.Provider.Models.ToDictionary(m => m.Id, m => m.Note);
            SetModelList(list.Select(m => known.TryGetValue(m.Id, out var note) ? m with { Note = note } : m).OrderBy(m => m.Id));
            Main.SetStatus($"{Selected.Name}: {list.Count} model(s) loaded.");
        }
        catch (Exception ex)
        {
            Main.SetStatus($"Could not load models: {ex.Message}", isError: true);
        }
        finally
        {
            IsLoadingModels = false;
        }
    }

    [RelayCommand]
    private void Back()
    {
        _cts?.Cancel();
        _warmTimer.Stop();
        Selected = null;
    }

    [RelayCommand]
    private void OpenAiSettings() => RequestOpenSettings?.Invoke();

    public event Action? RequestOpenSettings;

    private static string KeyFor(AiProviderItem item) => CreatorSettings.Current.AiKeys.GetValueOrDefault(item.Provider.Id, string.Empty);

    private AiRequest RequestFor(AiProviderItem item) =>
        new(item.Provider, KeyFor(item), Model.Trim(), item.BaseUrl, SystemPrompt, LongCache);

    // =====================================================================
    // Chat
    // =====================================================================

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(SendCommand))]
    private string _input = string.Empty;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(SendCommand))]
    [NotifyPropertyChangedFor(nameof(IsIdle))]
    private bool _isBusy;

    public bool IsIdle => !IsBusy;

    [ObservableProperty] private bool _useThemeTools = true;
    [ObservableProperty] private bool _useMcpServers = true;
    [ObservableProperty] private string _usageText = "Tokens: 0";
    [ObservableProperty] private int _historyLimit;

    partial void OnHistoryLimitChanged(int value)
    {
        CreatorSettings.Current.AiHistoryLimit = Math.Clamp(value, 2, 60);
        CreatorSettings.Current.Save();
    }

    partial void OnInputChanged(string value)
    {
        CommandSuggestions.Clear();
        if (value.StartsWith('/') && !value.Contains(' '))
            foreach (var c in AllCommands.Where(c => c.Name.StartsWith(value, StringComparison.OrdinalIgnoreCase)))
                CommandSuggestions.Add(c);
        OnPropertyChanged(nameof(HasCommandSuggestions));
    }

    [RelayCommand]
    private void UseCommand(ChatCommand? command)
    {
        if (command == null) return;
        Input = command.Args.Length > 0 ? command.Name + " " : command.Name;
        if (command.Args.Length == 0) _ = SendAsync();
    }

    public bool HasMessages => Messages.Count > 0;

    private bool CanSend() => !IsBusy && Selected != null && (!string.IsNullOrWhiteSpace(Input) || HasPending);

    [RelayCommand(CanExecute = nameof(CanSend))]
    private async Task SendAsync()
    {
        string text = Input.Trim();
        if (text.StartsWith('/'))
        {
            Input = string.Empty;
            await RunCommandAsync(text);
            return;
        }

        var item = Selected!;
        if (item.Provider.NeedsKey && string.IsNullOrWhiteSpace(KeyFor(item)))
        {
            Notice($"Add your {item.Name} key in SETTINGS → AI ACCOUNTS first.", error: true);
            return;
        }

        var attachments = Pending.Select(p => p.Attachment).ToList();
        string sent = text;
        if (_attachTheme)
        {
            sent += "\n\nCurrent theme:\n" + await Main.ThemeTools.First(t => t.Name == "get_theme").Run(new());
            _attachTheme = false;
        }
        Input = string.Empty;
        Pending.Clear();
        _history.Add(new ChatTurn { Role = ChatRole.User, Text = sent, Attachments = attachments });
        AddMessage(new ChatMessageItem { Author = "YOU", Text = text, IsUser = true, Attachments = attachments });
        TrimHistory();
        await RunModelAsync(item, _history, showTurns: true);
    }

    private async Task<bool> RunModelAsync(AiProviderItem item, List<ChatTurn> history, bool showTurns, bool withTools = true)
    {
        IsBusy = true;
        _warmTimer.Stop();
        _cts = new CancellationTokenSource();
        try
        {
            var tools = new List<AiTool>();
            if (withTools && UseThemeTools) tools.AddRange(Main.ThemeTools);
            if (withTools && UseMcpServers) tools.AddRange(await EnsureMcpToolsAsync(_cts.Token));
            _lastTools = tools;

            var usage = await AiChatClient.RunAsync(RequestFor(item), history, tools,
                turn => { if (showTurns) Dispatcher.UIThread.Post(() => ShowTurn(item, turn)); }, _cts.Token);
            AddUsage(usage);
            return true;
        }
        catch (OperationCanceledException)
        {
            Notice("Stopped.", error: true);
        }
        catch (Exception ex)
        {
            AddMessage(new ChatMessageItem { Author = "ERROR", Text = ex.Message, IsError = true });
        }
        finally
        {
            IsBusy = false;
            _lastActivity = DateTime.UtcNow;
            ScheduleWarm();
        }
        return false;
    }

    private void TrimHistory()
    {
        var users = _history.Select((t, i) => (t, i)).Where(x => x.t.Role == ChatRole.User).Select(x => x.i).ToList();
        if (users.Count <= HistoryLimit) return;
        int keep = Math.Max(1, HistoryLimit / 2);
        _history.RemoveRange(0, users[^keep]);
        Notice($"Older messages are no longer sent (keeps the cache stable). Memory: {HistoryLimit} messages.");
    }

    private void ShowTurn(AiProviderItem item, ChatTurn turn)
    {
        if (turn.Role == ChatRole.Tool)
        {
            string r = turn.Text.Replace('\n', ' ');
            if (r.Length > 140) r = r[..140] + "…";
            AddMessage(new ChatMessageItem { Author = "TOOL", Text = $"{turn.ToolName} → {r}", IsTool = true });
            return;
        }
        if (!string.IsNullOrWhiteSpace(turn.Text))
            AddMessage(new ChatMessageItem { Author = $"{item.Name.ToUpperInvariant()} · {Model}", Text = turn.Text.Trim(), IsAssistant = true });
    }

    private void AddMessage(ChatMessageItem message)
    {
        Messages.Add(message);
        OnPropertyChanged(nameof(HasMessages));
        MessageAdded?.Invoke();
    }

    private void Notice(string text, bool error = false) =>
        AddMessage(new ChatMessageItem { Author = "SYSTEM", Text = text, IsTool = !error, IsError = error });

    public event Action? MessageAdded;

    [RelayCommand]
    private void Stop() => _cts?.Cancel();

    [RelayCommand]
    private void Clear()
    {
        _history.Clear();
        Messages.Clear();
        Pending.Clear();
        _warmTimer.Stop();
        _session = new AiUsage(0, 0);
        _last = null;
        UpdateUsageText();
        OnPropertyChanged(nameof(HasMessages));
    }

    [RelayCommand]
    private void UsePrompt(string? prompt)
    {
        if (!string.IsNullOrWhiteSpace(prompt)) Input = prompt;
    }

    // =====================================================================
    // Usage and cache
    // =====================================================================

    public bool LongCache
    {
        get => CreatorSettings.Current.AiLongCache;
        set
        {
            CreatorSettings.Current.AiLongCache = value;
            CreatorSettings.Current.Save();
            OnPropertyChanged();
            ScheduleWarm();
        }
    }

    public bool KeepWarm
    {
        get => CreatorSettings.Current.AiKeepWarm;
        set
        {
            CreatorSettings.Current.AiKeepWarm = value;
            CreatorSettings.Current.Save();
            OnPropertyChanged();
            ScheduleWarm();
        }
    }

    private List<AiTool> _lastTools = new();

    private void AddUsage(AiUsage usage)
    {
        _last = usage;
        _session += usage;
        UpdateUsageText();
    }

    private void UpdateUsageText()
    {
        static string Fmt(AiUsage u) => $"{u.Input:N0} in ({u.CacheRead:N0} cached{(u.CacheWrite > 0 ? $", {u.CacheWrite:N0} written" : "")}) · {u.Output:N0} out";
        UsageText = _last == null ? "Tokens: 0" : $"Last: {Fmt(_last)}   Session: {Fmt(_session)}";
        if (_warmTimer.IsEnabled) UsageText += "   · cache kept warm";
    }

    private void ScheduleWarm()
    {
        _warmTimer.Stop();
        if (!KeepWarm || !IsClaude || _history.Count == 0 || IsBusy) { UpdateUsageText(); return; }
        _warmTimer.Interval = LongCache ? TimeSpan.FromMinutes(55) : TimeSpan.FromSeconds(270);
        _warmTimer.Start();
        UpdateUsageText();
    }

    private async Task WarmTickAsync()
    {
        var limit = LongCache ? TimeSpan.FromHours(3) : TimeSpan.FromMinutes(30);
        if (Selected == null || IsBusy || DateTime.UtcNow - _lastActivity > limit) { _warmTimer.Stop(); UpdateUsageText(); return; }
        try
        {
            var usage = await AiChatClient.WarmAsync(RequestFor(Selected), _history, _lastTools, CancellationToken.None);
            AddUsage(usage);
        }
        catch (Exception ex)
        {
            _warmTimer.Stop();
            Main.SetStatus($"Cache keep-warm stopped: {ex.Message}", isError: true);
        }
    }

    // =====================================================================
    // Attachments
    // =====================================================================

    private void Attach(ChatAttachment a)
    {
        if (a.Kind == AttachmentKind.Image && Selected is { Provider.Vision: false })
            Main.SetStatus($"{Selected.Name} can't see images — it will only get the file name.", isError: true);
        Pending.Add(new AttachmentItem(a, this));
        SendCommand.NotifyCanExecuteChanged();
    }

    public void AttachFiles(IEnumerable<string> paths)
    {
        foreach (var path in paths)
        {
            if (FontTools.IsFontFile(path))
            {
                AttachFont(path);
                continue;
            }
            try { Attach(ChatAttachment.FromFile(path)); }
            catch (Exception ex) { Main.SetStatus(ex.Message, isError: true); }
        }
    }

    private void AttachFont(string path)
    {
        var font = Main.AddFontForAi(path);
        if (font == null) { Main.SetStatus($"Could not add {Path.GetFileName(path)}.", isError: true); return; }
        Pending.Add(new AttachmentItem(new ChatAttachment
        {
            Name = font.FileName,
            Kind = AttachmentKind.Text,
            Text = $"Font added to the theme: file {font.FileName}, family '{font.FamilyName}'. Apply it with use_font if the user wants it.",
            IsFont = true,
        }, this));
        SendCommand.NotifyCanExecuteChanged();
    }

    public void AttachBitmap(Bitmap bmp, string name)
    {
        try { Attach(ChatAttachment.FromBitmap(bmp, name)); }
        catch (Exception ex) { Main.SetStatus(ex.Message, isError: true); }
    }

    [RelayCommand]
    private async Task AttachFileAsync()
    {
        if (Host != null) AttachFiles(await Host.PickFilesAsync());
    }

    [RelayCommand]
    private async Task AttachScreenshotAsync()
    {
        if (Host == null) return;
        if (!ScreenCapture.IsSupported) { Main.SetStatus("Screen capture works on Windows. Use PASTE with a screenshot instead.", isError: true); return; }
        using var bmp = await Host.CaptureScreenAsync();
        if (bmp != null) AttachBitmap(bmp, $"screenshot-{DateTime.Now:HHmmss}.jpg");
    }

    [RelayCommand]
    private void AttachPreview()
    {
        using var bmp = Host?.RenderPreviewBitmap();
        if (bmp != null) AttachBitmap(bmp, "live-preview.jpg");
    }

    [RelayCommand]
    private async Task AttachClipboardAsync()
    {
        if (Host == null) return;
        using var bmp = await Host.ClipboardImageAsync();
        if (bmp != null) AttachBitmap(bmp, $"pasted-{DateTime.Now:HHmmss}.jpg");
        else Main.SetStatus("No image in the clipboard.");
    }

    // =====================================================================
    // Commands
    // =====================================================================

    private async Task RunCommandAsync(string line)
    {
        string[] parts = line.Split(' ', 2, StringSplitOptions.TrimEntries);
        string cmd = parts[0].ToLowerInvariant();
        string arg = parts.Length > 1 ? parts[1] : string.Empty;
        switch (cmd)
        {
            case "/help":
                Notice(string.Join("\n", AllCommands.Select(c => $"{c.Name} {c.Args}".TrimEnd() + " — " + c.Help)));
                break;
            case "/clear":
                Clear();
                break;
            case "/model":
                if (arg.Length > 0) { Model = arg; Notice($"Model: {arg}"); }
                else Notice($"Model: {Model}\n" + string.Join("\n", ModelInfos.Select(m => $"• {m.Id}{(m.Note.Length > 0 ? " — " + m.Note : "")}")));
                break;
            case "/models":
                await RefreshModelsAsync();
                Notice(string.Join("\n", ModelInfos.Select(m => $"• {m.Id}{(m.Note.Length > 0 ? " — " + m.Note : "")}")));
                break;
            case "/compact":
                await CompactAsync();
                break;
            case "/tokens":
                Notice($"{UsageText}\nMessages sent each time: up to {HistoryLimit}. Cache: {CacheInfo}");
                break;
            case "/undo":
                if (Main.CanUndo) { Main.Undo(); Notice("Undone."); } else Notice("Nothing to undo.");
                break;
            case "/theme":
                _attachTheme = true;
                Notice("The current theme will be sent with your next message.");
                break;
            case "/preview":
                AttachPreview();
                break;
            case "/screenshot":
                await AttachScreenshotAsync();
                break;
            case "/paste":
                await AttachClipboardAsync();
                break;
            case "/file":
                await AttachFileAsync();
                break;
            case "/cache":
                switch (arg.ToLowerInvariant())
                {
                    case "1h": LongCache = true; break;
                    case "5m": LongCache = false; break;
                    case "warm": KeepWarm = true; break;
                    case "cold": KeepWarm = false; break;
                }
                Notice($"Cache: {(LongCache ? "1 hour" : "5 minutes")}, keep warm: {(KeepWarm ? "on" : "off")}. {CacheInfo}");
                break;
            case "/back":
                Back();
                break;
            default:
                Notice($"Unknown command {cmd}. Type /help.", error: true);
                break;
        }
    }

    private async Task CompactAsync()
    {
        if (Selected == null || _history.Count == 0) { Notice("Nothing to compact."); return; }
        var temp = new List<ChatTurn>(_history)
        {
            new() { Role = ChatRole.User, Text = "Summarise our conversation so far in under 150 words: what the user wants and what was changed in the theme. Only the summary." },
        };
        int before = temp.Count;
        if (!await RunModelAsync(Selected, temp, showTurns: false, withTools: false)) return;
        string summary = temp.Skip(before).LastOrDefault(t => t.Role == ChatRole.Assistant)?.Text ?? string.Empty;
        if (summary.Length == 0) { Notice("Compact failed.", error: true); return; }
        _history.Clear();
        _history.Add(new ChatTurn { Role = ChatRole.User, Text = "Summary of our earlier conversation:\n" + summary });
        _history.Add(new ChatTurn { Role = ChatRole.Assistant, Text = "Got it." });
        Notice("Chat compacted:\n" + summary);
    }

    // =====================================================================
    // External MCP servers
    // =====================================================================

    [ObservableProperty] private string _newMcpName = string.Empty;
    [ObservableProperty] private string _newMcpTarget = string.Empty;

    [RelayCommand]
    private async Task AddMcpServerAsync()
    {
        if (string.IsNullOrWhiteSpace(NewMcpTarget)) return;
        var cfg = new McpServerConfig
        {
            Name = string.IsNullOrWhiteSpace(NewMcpName) ? $"mcp{McpServers.Count + 1}" : NewMcpName.Trim(),
            Target = NewMcpTarget.Trim(),
        };
        CreatorSettings.Current.McpServers.Add(cfg);
        CreatorSettings.Current.Save();
        McpServers.Add(new McpServerItem(cfg, this));
        NewMcpName = NewMcpTarget = string.Empty;
        await ReconnectMcpAsync();
    }

    public void RemoveMcpServer(McpServerItem item)
    {
        CreatorSettings.Current.McpServers.Remove(item.Config);
        CreatorSettings.Current.Save();
        McpServers.Remove(item);
        _ = ReconnectMcpAsync();
    }

    [RelayCommand]
    private async Task ReconnectMcpAsync()
    {
        await DisconnectMcpAsync();
        await EnsureMcpToolsAsync(CancellationToken.None);
    }

    private async Task<IReadOnlyList<AiTool>> EnsureMcpToolsAsync(CancellationToken ct)
    {
        if (_mcpClients.Count > 0) return _mcpTools;
        var tools = new List<AiTool>();
        foreach (var item in McpServers.Where(s => s.Enabled))
        {
            var client = new McpClient(item.Config);
            try
            {
                item.State = "connecting…";
                var list = await client.ConnectAsync(ct);
                tools.AddRange(list);
                _mcpClients.Add(client);
                item.State = $"{list.Count} tool(s)";
            }
            catch (Exception ex)
            {
                item.State = "error: " + ex.Message;
                await client.DisposeAsync();
            }
        }
        _mcpTools = tools;
        return tools;
    }

    private async Task DisconnectMcpAsync()
    {
        foreach (var c in _mcpClients) await c.DisposeAsync();
        _mcpClients.Clear();
        _mcpTools = new();
        foreach (var s in McpServers) s.State = "not connected";
    }

    // =====================================================================
    // Built-in MCP server
    // =====================================================================

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(ServerStatusText))]
    private bool _serverRunning;

    [ObservableProperty] private string _mcpPortInput;

    public bool ServerEnabled
    {
        get => CreatorSettings.Current.McpServerEnabled;
        set
        {
            CreatorSettings.Current.McpServerEnabled = value;
            CreatorSettings.Current.Save();
            if (value) StartServer();
            else StopServer();
            OnPropertyChanged();
        }
    }

    private int Port => CreatorSettings.Current.McpServerPort;
    private string ServerUrl => McpServer.UrlFor(Port);

    public string ServerStatusText => ServerRunning ? $"Running at {ServerUrl}" : "Off — turn it on to let Claude Code, Copilot (VS Code), Codex or Cursor edit this theme.";
    public string ClaudeCodeSnippet => $"claude mcp add --transport http rbwr-theme-creator {ServerUrl}";
    public string VsCodeSnippet => $"{{\n  \"servers\": {{\n    \"rbwr-theme-creator\": {{ \"type\": \"http\", \"url\": \"{ServerUrl}\" }}\n  }}\n}}";
    public string ClaudeDesktopSnippet => $"{{\n  \"mcpServers\": {{\n    \"rbwr-theme-creator\": {{ \"command\": \"npx\", \"args\": [\"-y\", \"mcp-remote\", \"{ServerUrl}\"] }}\n  }}\n}}";
    public string CodexSnippet => $"[mcp_servers.rbwr-theme-creator]\nurl = \"{ServerUrl}\"";
    public string CursorSnippet => $"{{\n  \"mcpServers\": {{\n    \"rbwr-theme-creator\": {{ \"url\": \"{ServerUrl}\" }}\n  }}\n}}";

    private void StartServer()
    {
        try
        {
            _server.Start(Port);
            ServerRunning = true;
        }
        catch (Exception ex)
        {
            ServerRunning = false;
            Main.SetStatus($"MCP server could not start on port {Port}: {ex.Message}", isError: true);
        }
    }

    private void StopServer()
    {
        _server.Stop();
        ServerRunning = false;
    }

    [RelayCommand]
    private void ApplyPort()
    {
        if (!int.TryParse(McpPortInput, out int port) || port is < 1024 or > 65535)
        {
            Main.SetStatus("Port must be 1024–65535.", isError: true);
            return;
        }
        CreatorSettings.Current.McpServerPort = port;
        CreatorSettings.Current.Save();
        if (ServerEnabled) StartServer();
        foreach (string name in new[] { nameof(ServerStatusText), nameof(ClaudeCodeSnippet), nameof(VsCodeSnippet), nameof(ClaudeDesktopSnippet), nameof(CodexSnippet), nameof(CursorSnippet) })
            OnPropertyChanged(name);
    }

    [RelayCommand]
    private async Task CopySnippetAsync(string? which)
    {
        string text = which switch
        {
            "vscode" => VsCodeSnippet,
            "desktop" => ClaudeDesktopSnippet,
            "codex" => CodexSnippet,
            "cursor" => CursorSnippet,
            _ => ClaudeCodeSnippet,
        };
        if (Main.Dialogs != null) await Main.Dialogs.CopyTextAsync(text);
        Main.SetStatus("Copied to clipboard.");
    }

    // =====================================================================
    // Misc
    // =====================================================================

    public void OpenUrl(string url)
    {
        try { System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(url) { UseShellExecute = true }); }
        catch (Exception ex) { Main.SetStatus(ex.Message, isError: true); }
    }

    public void Shutdown()
    {
        _server.Stop();
        foreach (var c in _mcpClients) c.DisposeAsync().AsTask().Wait(500);
    }
}
