using System.Text.RegularExpressions;

namespace RbwrOverlay.Platform;

public static class RobloxLogReader
{
    private static readonly Regex JoinRegex = new(@"Joining game '[^']*' place (\d+)", RegexOptions.Compiled);
    private const int TailBytes = 512 * 1024;

    public static long? GetLastJoinedPlaceId()
    {
        try
        {
            string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Roblox", "logs");
            if (!Directory.Exists(dir)) return null;

            var newest = new DirectoryInfo(dir).GetFiles("*.log")
                .OrderByDescending(f => f.LastWriteTimeUtc)
                .FirstOrDefault();
            if (newest == null) return null;

            using var fs = new FileStream(newest.FullName, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            if (fs.Length > TailBytes) fs.Seek(-TailBytes, SeekOrigin.End);
            using var reader = new StreamReader(fs);
            var matches = JoinRegex.Matches(reader.ReadToEnd());
            if (matches.Count == 0) return null;
            return long.TryParse(matches[^1].Groups[1].Value, out long id) ? id : null;
        }
        catch
        {
            return null;
        }
    }
}
