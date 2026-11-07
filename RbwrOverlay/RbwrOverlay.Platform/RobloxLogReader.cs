using System.Text.RegularExpressions;

namespace RbwrOverlay.Platform;

public readonly record struct RobloxJoinInfo(string JobId, long PlaceId);

public static class RobloxLogReader
{
    public const long RbwrPlaceId = 11765852158;

    private static readonly Regex JoinRegex = new(@"Joining game '([^']*)' place (\d+)", RegexOptions.Compiled);
    private static readonly Regex LeaveRegex = new(
        @"(?:leaveUGCGameInternal|Entered app session|Tearing down\.|Client:Disconnect|shutDown:|Disconnected from server)",
        RegexOptions.Compiled);

    private const int MaxReadBytes = 4 * 1024 * 1024;

    public static RobloxJoinInfo? GetLastJoinedGame(string? customLogsDir = null)
    {
        try
        {
            string dir = customLogsDir ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Roblox", "logs");
            if (!Directory.Exists(dir)) return null;

            var logFiles = new DirectoryInfo(dir).GetFiles("*.log")
                .Where(f => !f.Name.Contains("CrashHandler", StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(f => f.LastWriteTimeUtc)
                .Take(5);

            foreach (var file in logFiles)
            {
                using var fs = new FileStream(file.FullName, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
                if (fs.Length > MaxReadBytes) fs.Seek(-MaxReadBytes, SeekOrigin.End);
                using var reader = new StreamReader(fs);
                string content = reader.ReadToEnd();

                var joinMatches = JoinRegex.Matches(content);
                if (joinMatches.Count == 0) continue;

                var lastJoin = joinMatches[^1];
                int lastJoinPos = lastJoin.Index;

                var leaveMatches = LeaveRegex.Matches(content);
                int lastLeavePos = leaveMatches.Count > 0 ? leaveMatches[^1].Index : -1;

                if (lastLeavePos > lastJoinPos)
                {
                    return null;
                }

                string jobId = lastJoin.Groups[1].Value.Trim();
                if (!long.TryParse(lastJoin.Groups[2].Value, out long placeId)) continue;

                return new RobloxJoinInfo(jobId, placeId);
            }

            return null;
        }
        catch
        {
            return null;
        }
    }

    public static long? GetLastJoinedPlaceId(string? customLogsDir = null) => GetLastJoinedGame(customLogsDir)?.PlaceId;
}
