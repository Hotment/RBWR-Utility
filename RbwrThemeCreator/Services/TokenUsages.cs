using System.Text.RegularExpressions;

namespace RbwrThemeCreator.Services;

/// <summary>A place where the overlay's base styles use a colour token: a style selector and a property.</summary>
public sealed record TokenUsage(string Selector, string Property);

/// <summary>
/// Where the overlay draws each colour token, read from the overlay's own CyberpunkTheme.axaml (embedded
/// in the creator). An animated token is animated on exactly these selectors and properties, so it
/// changes everywhere the overlay uses that colour through its styles (cards, buttons, borders, …).
/// </summary>
public static class TokenUsages
{
    private static readonly Regex StyleBlock = new(
        @"<Style\s+Selector=""(?<sel>[^""]+)""\s*>(?<body>.*?)</Style>",
        RegexOptions.Singleline | RegexOptions.CultureInvariant);

    private static readonly Regex DynamicSetter = new(
        @"<Setter\s+Property=""(?<prop>[\w.]+)""\s+Value=""\{DynamicResource\s+(?<key>\w+)\}""",
        RegexOptions.CultureInvariant);

    private static Dictionary<string, List<TokenUsage>>? _map;

    /// <summary>Selectors and properties that use <paramref name="tokenKey"/> (empty when none).</summary>
    public static IReadOnlyList<TokenUsage> For(string tokenKey) =>
        (_map ??= Build(BuiltInThemes.CyberpunkXaml)).TryGetValue(tokenKey, out var list) ? list : [];

    public static Dictionary<string, List<TokenUsage>> Build(string baseXaml)
    {
        var map = new Dictionary<string, List<TokenUsage>>(StringComparer.Ordinal);
        foreach (Match style in StyleBlock.Matches(baseXaml))
        {
            string selector = style.Groups["sel"].Value.Trim();
            foreach (Match setter in DynamicSetter.Matches(style.Groups["body"].Value))
            {
                string key = setter.Groups["key"].Value;
                var usage = new TokenUsage(selector, setter.Groups["prop"].Value);
                if (!map.TryGetValue(key, out var list))
                    map[key] = list = new List<TokenUsage>();
                if (!list.Contains(usage))
                    list.Add(usage);
            }
        }
        return map;
    }
}
