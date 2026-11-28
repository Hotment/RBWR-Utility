using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using RbwrThemeCreator.Services;
using RbwrThemeCreator.Services.Mcp;

namespace RbwrThemeCreator.ViewModels;

/// <summary>
/// ViewModel for the built-in localhost MCP server configuration card in the SETTINGS tab.
/// </summary>
public sealed partial class McpServerViewModel : ObservableObject
{
    private readonly MainViewModel _main;
    private readonly McpServer _server;

    public McpServerViewModel(MainViewModel main)
    {
        _main = main;
        _server = new McpServer(
            () => _main.McpTools,
            () => _main.McpResources,
            MainViewModel.AppVersion);
        _portInput = CreatorSettings.Current.McpServerPort.ToString();

        if (CreatorSettings.Current.McpServerEnabled)
            StartServer();

        AppDomain.CurrentDomain.ProcessExit += (_, _) => Shutdown();
    }

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(StatusBadgeText), nameof(ServerStatusText), nameof(ServerUrl))]
    private bool _serverRunning;

    [ObservableProperty]
    private string _portInput;

    public bool ServerEnabled
    {
        get => CreatorSettings.Current.McpServerEnabled;
        set
        {
            if (value == CreatorSettings.Current.McpServerEnabled && value == ServerRunning)
                return;
            CreatorSettings.Current.McpServerEnabled = value;
            CreatorSettings.Current.Save();
            if (value) StartServer();
            else StopServer();
            OnPropertyChanged();
            OnPropertyChanged(nameof(ServerStatusText));
        }
    }

    public int Port => CreatorSettings.Current.McpServerPort;
    public string ServerUrl => McpServer.UrlFor(Port);
    public string StatusBadgeText => ServerRunning ? "RUNNING" : "STOPPED";
    public int ToolCount => _main.McpTools.Count;
    public int ResourceCount => _main.McpResources.Count;

    public string CapabilitiesSummary =>
        $"Exposes {ToolCount} tools and {ResourceCount} resources (colours, gradients, animations, shape, APRM box, fonts, image assets, custom XAML, presets, save/export/install, and live PNG preview rendering).";

    public string ServerStatusText => ServerRunning
        ? $"Listening locally at {ServerUrl}"
        : "Stopped. Enable to let external MCP agents (Claude Code, VS Code Copilot, Cursor, Codex, Antigravity) inspect, edit, and preview themes live.";

    public string ClaudeCodeSnippet =>
        $"claude mcp add --transport http rbwr-theme-creator {ServerUrl}";

    public string VsCodeSnippet =>
        $"{{\n  \"servers\": {{\n    \"rbwr-theme-creator\": {{ \"type\": \"http\", \"url\": \"{ServerUrl}\" }}\n  }}\n}}";

    public string CursorSnippet =>
        $"{{\n  \"mcpServers\": {{\n    \"rbwr-theme-creator\": {{ \"url\": \"{ServerUrl}\" }}\n  }}\n}}";

    public string CodexSnippet =>
        $"[mcp_servers.rbwr-theme-creator]\nurl = \"{ServerUrl}\"";

    public string ClaudeDesktopSnippet =>
        $"{{\n  \"mcpServers\": {{\n    \"rbwr-theme-creator\": {{ \"command\": \"npx\", \"args\": [\"-y\", \"mcp-remote\", \"{ServerUrl}\"] }}\n  }}\n}}";

    private void StartServer()
    {
        try
        {
            _server.Start(Port);
            ServerRunning = true;
            _main.SetStatus($"MCP server started at {ServerUrl}");
        }
        catch (Exception ex)
        {
            ServerRunning = false;
            CreatorLogging.Instance.Warning($"[MCP] Failed to start on port {Port}: {ex.Message}");
            _main.SetStatus($"MCP server could not start on port {Port}: {ex.Message}", isError: true);
        }
    }

    private void StopServer()
    {
        _server.Stop();
        ServerRunning = false;
        _main.SetStatus("MCP server stopped.");
    }

    [RelayCommand]
    private void ApplyPort()
    {
        if (!int.TryParse(PortInput?.Trim(), out int port) || port is < 1024 or > 65535)
        {
            _main.SetStatus("MCP port must be an integer between 1024 and 65535.", isError: true);
            return;
        }
        CreatorSettings.Current.McpServerPort = port;
        CreatorSettings.Current.Save();
        PortInput = port.ToString();
        if (ServerEnabled) StartServer();
        NotifySnippetProperties();
        if (!ServerEnabled)
            _main.SetStatus($"MCP server port set to {port}.");
    }

    [RelayCommand]
    private async Task CopyUrlAsync()
    {
        if (_main.Dialogs != null) await _main.Dialogs.CopyTextAsync(ServerUrl);
        _main.SetStatus($"Copied {ServerUrl} to clipboard.");
    }

    [RelayCommand]
    private async Task CopySnippetAsync(string? which)
    {
        string text = which switch
        {
            "vscode" => VsCodeSnippet,
            "cursor" => CursorSnippet,
            "codex" => CodexSnippet,
            "desktop" => ClaudeDesktopSnippet,
            _ => ClaudeCodeSnippet,
        };
        if (_main.Dialogs != null) await _main.Dialogs.CopyTextAsync(text);
        _main.SetStatus("Copied MCP configuration snippet to clipboard.");
    }

    private void NotifySnippetProperties()
    {
        foreach (string name in new[]
        {
            nameof(Port), nameof(ServerUrl), nameof(ServerStatusText),
            nameof(ClaudeCodeSnippet), nameof(VsCodeSnippet), nameof(CursorSnippet),
            nameof(CodexSnippet), nameof(ClaudeDesktopSnippet),
        })
        {
            OnPropertyChanged(name);
        }
    }

    public void Shutdown()
    {
        _server.Stop();
        ServerRunning = false;
    }
}
