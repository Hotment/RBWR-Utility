using System.Runtime.InteropServices;
using System.Text.RegularExpressions;

namespace RbwrOverlay.Core.Services;

public interface ILoggingService
{
    void Info(string message);
    void Warning(string message);
    void Error(string message, Exception? ex = null);
    void Critical(string message, Exception? ex = null);
    void LogSystemInfo(string version);
    string GetLogFilePath();
    string GetLogContent();
    string SanitizeString(string text);
}

public class LoggingService : ILoggingService
{
    private static readonly Lazy<LoggingService> _instance = new(() => new LoggingService());
    public static LoggingService Instance => _instance.Value;

    private readonly string _logPath;
    private readonly object _lock = new();
    private readonly List<(Regex Pattern, string Placeholder)> _sanitizationMappings = new();

    public LoggingService()
    {
        string baseDir = AppDomain.CurrentDomain.BaseDirectory;
        _logPath = Path.Combine(baseDir, "RBWR_APRM_Calculator.log");
        InitializeSanitization();
        
        try
        {
            File.WriteAllText(_logPath, string.Empty);
        }
        catch
        {
            // Ignore if file cannot be created immediately
        }
    }

    public void LogSystemInfo(string version)
    {
        Info($"=== RBWR APRM Calculator (Avalonia .NET) v{version} Starting ===");
        Info($"Version: {version}");
        Info($"Runtime: {RuntimeInformation.FrameworkDescription} [{RuntimeInformation.RuntimeIdentifier}]");
        Info($"OS: {RuntimeInformation.OSDescription} ({RuntimeInformation.OSArchitecture})");
        Info($"Process Architecture: {RuntimeInformation.ProcessArchitecture}");
        Info($"Executable: {Environment.ProcessPath ?? AppDomain.CurrentDomain.FriendlyName}");
        Info($"Base Directory: {AppDomain.CurrentDomain.BaseDirectory}");
        Info($"Log file: {_logPath}");
    }

    private static readonly Regex WindowsUsersRegex = new(@"[a-zA-Z]:[\\/]+Users[\\/]+[^\\/\r\n\s"",':;]+", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    private static readonly Regex UnixHomeRegex = new(@"[\\/]+home[\\/]+[^\\/\r\n\s"",':;]+", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    private static readonly Regex MacUsersRegex = new(@"[\\/]+Users[\\/]+[^\\/\r\n\s"",':;]+", RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private void InitializeSanitization()
    {
        bool isWindows = RuntimeInformation.IsOSPlatform(OSPlatform.Windows);
        string tempPlaceholder = isWindows ? "%temp%" : "$TMPDIR";
        string userPlaceholder = isWindows ? "%username%" : "$USER";

        var sources = new (string VarName, string Placeholder)[]
        {
            ("TEMP", tempPlaceholder),
            ("TMP", tempPlaceholder),
            ("TMPDIR", "$TMPDIR"),
            ("LOCALAPPDATA", "%localappdata%"),
            ("APPDATA", "%appdata%"),
            ("USERPROFILE", "%userprofile%"),
            ("HOME", "$HOME"),
            ("HOMEPATH", "%userprofile%"),
            ("XDG_CONFIG_HOME", "$XDG_CONFIG_HOME"),
            ("XDG_DATA_HOME", "$XDG_DATA_HOME")
        };

        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        foreach (var (varName, placeholder) in sources)
        {
            string? val = Environment.GetEnvironmentVariable(varName);
            if (string.IsNullOrEmpty(val) || val.Length < 4)
                continue;

            string[] variants = { val, val.Replace('/', '\\'), val.Replace('\\', '/') };
            foreach (var variant in variants)
            {
                if (seen.Add(variant))
                {
                    _sanitizationMappings.Add((new Regex(Regex.Escape(variant), RegexOptions.IgnoreCase | RegexOptions.Compiled), placeholder));
                }
            }
        }

        string[] usernameCandidates = [
            Environment.UserName,
            Environment.GetEnvironmentVariable("USERNAME") ?? string.Empty,
            Environment.GetEnvironmentVariable("USER") ?? string.Empty,
            Environment.GetEnvironmentVariable("LOGNAME") ?? string.Empty
        ];

        foreach (var u in usernameCandidates)
        {
            if (string.IsNullOrWhiteSpace(u) || u.Length < 2)
                continue;

            string winPattern = $@"[a-zA-Z]:[\\/]+Users[\\/]+{Regex.Escape(u)}";
            if (seen.Add(winPattern))
            {
                _sanitizationMappings.Add((new Regex(winPattern, RegexOptions.IgnoreCase | RegexOptions.Compiled), "%userprofile%"));
            }

            string unixPattern = $@"[\\/]+home[\\/]+{Regex.Escape(u)}";
            if (seen.Add(unixPattern))
            {
                _sanitizationMappings.Add((new Regex(unixPattern, RegexOptions.IgnoreCase | RegexOptions.Compiled), "$HOME"));
            }

            string macPattern = $@"[\\/]+Users[\\/]+{Regex.Escape(u)}";
            if (seen.Add(macPattern))
            {
                _sanitizationMappings.Add((new Regex(macPattern, RegexOptions.IgnoreCase | RegexOptions.Compiled), "$HOME"));
            }

            if (u.Length >= 3 && seen.Add(@"\b" + u + @"\b"))
            {
                _sanitizationMappings.Add((new Regex(@"\b" + Regex.Escape(u) + @"\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), userPlaceholder));
            }
        }

        _sanitizationMappings.Sort((a, b) => b.Pattern.ToString().Length.CompareTo(a.Pattern.ToString().Length));
    }

    public string SanitizeString(string text)
    {
        if (string.IsNullOrEmpty(text))
            return text;

        foreach (var (pattern, placeholder) in _sanitizationMappings)
        {
            text = pattern.Replace(text, placeholder);
        }

        text = WindowsUsersRegex.Replace(text, "%userprofile%");
        text = UnixHomeRegex.Replace(text, "$HOME");
        text = MacUsersRegex.Replace(text, "$HOME");

        return text;
    }

    private void Log(string level, string message, Exception? ex = null)
    {
        string fullMessage = message;
        if (ex != null)
        {
            fullMessage += $"\nException: {ex}";
        }

        string sanitized = SanitizeString(fullMessage);
        string formatted = $"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff} [{level}] {sanitized}";

        Console.WriteLine(formatted);

        try
        {
            lock (_lock)
            {
                File.AppendAllText(_logPath, formatted + Environment.NewLine);
            }
        }
        catch
        {
            // Logging failure fallback
        }
    }

    public void Info(string message) => Log("INFO", message);
    public void Warning(string message) => Log("WARN", message);
    public void Error(string message, Exception? ex = null) => Log("ERROR", message, ex);
    public void Critical(string message, Exception? ex = null) => Log("CRITICAL", message, ex);

    public string GetLogFilePath() => _logPath;

    public string GetLogContent()
    {
        try
        {
            lock (_lock)
            {
                if (File.Exists(_logPath))
                {
                    return File.ReadAllText(_logPath);
                }
            }
        }
        catch
        {
            // Ignore
        }
        return string.Empty;
    }
}