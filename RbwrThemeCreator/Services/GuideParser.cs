using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;

namespace RbwrThemeCreator.Services;

/// <summary>One block of the in-app user guide.</summary>
public abstract record GuideBlock;

/// <summary>"# Title" at the top of the guide.</summary>
public sealed record GuideTitle(string Text) : GuideBlock;

/// <summary>"## 4. Colours": starts a new card. <see cref="Anchor"/> matches GitHub's heading links.</summary>
public sealed record GuideSection(string Title, string Anchor) : GuideBlock;

/// <summary>"### Search"</summary>
public sealed record GuideSubheading(string Text) : GuideBlock;

public sealed record GuideParagraph(string Text) : GuideBlock;

public sealed record GuideList(bool Numbered, IReadOnlyList<string> Items) : GuideBlock;

public sealed record GuideTable(IReadOnlyList<string> Header, IReadOnlyList<IReadOnlyList<string>> Rows) : GuideBlock;

public enum GuideInlineKind { Text, Bold, Italic, Code, Link }

/// <summary>A run of text inside a paragraph, list item or table cell.</summary>
public sealed record GuideInline(GuideInlineKind Kind, string Text, string? Target = null);

/// <summary>
/// Reads GUIDE.md (embedded in the app) into blocks for the GUIDE tab, so the guide on GitHub and the
/// one inside the creator are the same file. Supports the small Markdown subset the guide uses:
/// headings, paragraphs, bullet and numbered lists, tables, **bold**, *italic*, `code` and [links](#x).
/// </summary>
public static class GuideParser
{
    public const string ResourceName = "Guide.GUIDE.md";

    private static readonly Regex NumberedItem = new(@"^\d+\.\s+(.*)$", RegexOptions.CultureInvariant);
    private static readonly Regex BulletItem = new(@"^[-*]\s+(.*)$", RegexOptions.CultureInvariant);
    private static readonly Regex InlineToken = new(
        @"\*\*(?<bold>.+?)\*\*|`(?<code>[^`]+)`|\[(?<ltext>[^\]]+)\]\((?<lurl>[^)]+)\)|(?<![\w*])\*(?<italic>[^*\s][^*]*?)\*(?![\w*])",
        RegexOptions.CultureInvariant);

    /// <summary>The guide shipped inside the app.</summary>
    public static string LoadEmbedded()
    {
        using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream(ResourceName)
            ?? throw new InvalidOperationException($"Embedded guide '{ResourceName}' not found.");
        using var reader = new StreamReader(stream, Encoding.UTF8);
        return reader.ReadToEnd();
    }

    public static IReadOnlyList<GuideBlock> Parse(string markdown)
    {
        var blocks = new List<GuideBlock>();
        var paragraph = new List<string>();
        List<string>? listItems = null;
        bool listNumbered = false;
        List<string[]>? tableRows = null;

        void FlushParagraph()
        {
            if (paragraph.Count > 0)
                blocks.Add(new GuideParagraph(string.Join(' ', paragraph)));
            paragraph.Clear();
        }
        void FlushList()
        {
            if (listItems is { Count: > 0 })
                blocks.Add(new GuideList(listNumbered, listItems));
            listItems = null;
        }
        void FlushTable()
        {
            if (tableRows is { Count: > 0 })
            {
                var header = tableRows[0];
                var rows = tableRows.Skip(1)
                    .Where(r => !r.All(c => c.Length > 0 && c.Trim('-', ':', ' ').Length == 0)) // the |---| row
                    .Select(r => (IReadOnlyList<string>)r).ToList();
                blocks.Add(new GuideTable(header, rows));
            }
            tableRows = null;
        }
        void FlushAll()
        {
            FlushParagraph();
            FlushList();
            FlushTable();
        }

        foreach (string raw in markdown.Replace("\r\n", "\n").Split('\n'))
        {
            string line = raw.TrimEnd();
            string trimmed = line.Trim();

            if (trimmed.Length == 0)
            {
                FlushParagraph();
                FlushTable();
                // A blank line ends a list only if the next line is not part of it; lists in the guide
                // never contain blank lines, so end it here.
                FlushList();
                continue;
            }

            if (trimmed == "---")
            {
                FlushAll();
                continue;
            }

            if (trimmed.StartsWith("|", StringComparison.Ordinal))
            {
                FlushParagraph();
                FlushList();
                tableRows ??= new List<string[]>();
                tableRows.Add(trimmed.Trim('|').Split('|').Select(c => c.Trim()).ToArray());
                continue;
            }
            FlushTable();

            if (trimmed.StartsWith("### ", StringComparison.Ordinal))
            {
                FlushAll();
                blocks.Add(new GuideSubheading(trimmed[4..].Trim()));
                continue;
            }
            if (trimmed.StartsWith("## ", StringComparison.Ordinal))
            {
                FlushAll();
                string title = trimmed[3..].Trim();
                blocks.Add(new GuideSection(title, Slug(title)));
                continue;
            }
            if (trimmed.StartsWith("# ", StringComparison.Ordinal))
            {
                FlushAll();
                blocks.Add(new GuideTitle(trimmed[2..].Trim()));
                continue;
            }

            // Indented line right after a list item: continuation of that item.
            if (listItems is { Count: > 0 } && line.StartsWith(' ') && paragraph.Count == 0
                && !NumberedItem.IsMatch(trimmed) && !BulletItem.IsMatch(trimmed))
            {
                listItems[^1] += " " + trimmed;
                continue;
            }

            var numbered = NumberedItem.Match(trimmed);
            var bullet = numbered.Success ? Match.Empty : BulletItem.Match(trimmed);
            if (numbered.Success || bullet.Success)
            {
                FlushParagraph();
                bool isNumbered = numbered.Success;
                if (listItems != null && listNumbered != isNumbered)
                    FlushList();
                listItems ??= new List<string>();
                listNumbered = isNumbered;
                listItems.Add((isNumbered ? numbered : bullet).Groups[1].Value.Trim());
                continue;
            }

            FlushList();
            paragraph.Add(trimmed);
        }
        FlushAll();
        return blocks;
    }

    /// <summary>Splits text into plain, **bold**, *italic*, `code` and [link](target) runs.</summary>
    public static IReadOnlyList<GuideInline> ParseInlines(string text)
    {
        var result = new List<GuideInline>();
        int pos = 0;
        foreach (Match m in InlineToken.Matches(text))
        {
            if (m.Index > pos)
                result.Add(new GuideInline(GuideInlineKind.Text, text[pos..m.Index]));

            if (m.Groups["bold"].Success)
                result.Add(new GuideInline(GuideInlineKind.Bold, m.Groups["bold"].Value));
            else if (m.Groups["code"].Success)
                result.Add(new GuideInline(GuideInlineKind.Code, m.Groups["code"].Value));
            else if (m.Groups["ltext"].Success)
                result.Add(new GuideInline(GuideInlineKind.Link, m.Groups["ltext"].Value, m.Groups["lurl"].Value));
            else
                result.Add(new GuideInline(GuideInlineKind.Italic, m.Groups["italic"].Value));

            pos = m.Index + m.Length;
        }
        if (pos < text.Length)
            result.Add(new GuideInline(GuideInlineKind.Text, text[pos..]));
        return result;
    }

    /// <summary>GitHub-style heading anchor: "5. Picking colours (eyedropper)" -> "5-picking-colours-eyedropper".</summary>
    public static string Slug(string heading)
    {
        var sb = new StringBuilder();
        foreach (char c in heading.ToLowerInvariant())
        {
            if (char.IsLetterOrDigit(c) || c is '-' or '_')
                sb.Append(c);
            else if (c == ' ')
                sb.Append('-');
        }
        return sb.ToString();
    }
}
