using System;

namespace RbwrOverlay.Core.Services;

/// <summary>
/// Provides matching and filtering logic for Roblox Job IDs and Server Short IDs.
/// Supports matching by:
/// 1. Start of the Job ID (e.g. "ed10" matches "ed10e9ed-e83c-4cfe-a9a0-bb8361a51818")
/// 2. 2nd part of the Job ID (e.g. "e83" or "e83c" matches "ed10e9ed-e83c-4cfe-a9a0-bb8361a51818")
/// 3. Server Short ID format (e.g. "e83c-4cfe" matches "ed10e9ed-e83c-4cfe-a9a0-bb8361a51818")
/// 4. Substring containment across the full Job ID
/// </summary>
public static class JobIdMatcher
{
    public static bool IsMatch(string? query, string? target)
    {
        if (string.IsNullOrWhiteSpace(query))
            return true;
        if (string.IsNullOrWhiteSpace(target))
            return false;

        var q = query.Trim();
        var t = target.Trim();

        if (t.StartsWith(q, StringComparison.OrdinalIgnoreCase))
            return true;

        var firstHyphen = t.IndexOf('-');
        if (firstHyphen >= 0 && firstHyphen + 1 < t.Length)
        {
            var fromSecondPart = t.Substring(firstHyphen + 1);
            if (fromSecondPart.StartsWith(q, StringComparison.OrdinalIgnoreCase))
                return true;
        }

        var parts = t.Split('-', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (parts.Length > 1)
        {
            for (int i = 1; i < parts.Length; i++)
            {
                if (parts[i].StartsWith(q, StringComparison.OrdinalIgnoreCase))
                    return true;
            }
        }

        if (t.Contains(q, StringComparison.OrdinalIgnoreCase))
            return true;

        return false;
    }
}