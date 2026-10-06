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

    private void InitializeSanitization()
    {
        var sources = new (string VarName, string Placeholder)[]
        {
            ("TEMP", "%temp%"),
            ("TMP", "%temp%"),
            ("LOCALAPPDATA", "%localappdata%"),
            ("APPDATA", "%appdata%"),
            ("USERPROFILE", "%userprofile%")
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