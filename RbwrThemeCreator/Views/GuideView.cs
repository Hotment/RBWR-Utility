using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Documents;
using Avalonia.Controls.Primitives;
using Avalonia.Layout;
using Avalonia.Media;
using RbwrThemeCreator.Services;

namespace RbwrThemeCreator.Views;

/// <summary>
/// The GUIDE tab: renders the embedded GUIDE.md in the creator's HUD style (cards, cyan headings,
/// tables, a clickable table of contents). The same file is the guide on GitHub, so there is only
/// one text to keep up to date.
/// </summary>
public sealed class GuideView : UserControl
{
    private readonly ScrollViewer _scroll;
    private readonly StackPanel _page;
    private readonly Dictionary<string, Control> _sections = new(StringComparer.OrdinalIgnoreCase);

    public GuideView()
    {
        _page = new StackPanel { Margin = new Thickness(18, 16) };
        _scroll = new ScrollViewer { Content = _page };
        Content = _scroll;

        try
        {
            Build(GuideParser.Parse(GuideParser.LoadEmbedded()));
        }
        catch (Exception ex)
        {
            _page.Children.Add(new TextBlock { Classes = { "error" }, Text = $"Could not load the guide: {ex.Message}", TextWrapping = TextWrapping.Wrap });
        }
    }

    /// <summary>Scrolls so the section with this anchor (e.g. "14-keyboard-shortcuts") is at the top.</summary>
    public void ShowSection(string anchor)
    {
        if (!_sections.TryGetValue(anchor.TrimStart('#'), out var target)) return;
        var p = target.TranslatePoint(new Point(0, 0), _page);
        if (p != null)
            _scroll.Offset = new Vector(0, Math.Max(0, p.Value.Y + _page.Margin.Top - 8));
    }

    public void ScrollToTop() => _scroll.Offset = default;

    // ===================== Building =====================

    private void Build(IReadOnlyList<GuideBlock> blocks)
    {
        Panel target = _page;
        bool introDone = false;
        bool inContents = false;

        foreach (var block in blocks)
        {
            switch (block)
            {
                case GuideTitle t:
                    _page.Children.Add(new TextBlock { Classes = { "page-title" }, Text = t.Text.ToUpperInvariant() });
                    break;

                case GuideSection s:
                    introDone = true;
                    inContents = s.Title.Equals("Contents", StringComparison.OrdinalIgnoreCase);
                    var body = new StackPanel { Spacing = 8 };
                    var card = new Border { Classes = { "card" }, Child = body };
                    if (inContents) card.Classes.Add("accent-card");
                    body.Children.Add(SectionHeader(s.Title, showTopButton: !inContents));
                    _page.Children.Add(card);
                    _sections[s.Anchor] = card;
                    target = body;
                    break;

                case GuideSubheading h:
                    target.Children.Add(new TextBlock
                    {
                        Classes = { "guide-sub" },
                        Text = h.Text,
                    });
                    break;

                case GuideParagraph p when !introDone:
                    var intro = Rich(p.Text);
                    intro.Classes.Add("guide-intro");
                    _page.Children.Add(intro);
                    break;

                case GuideParagraph p:
                    target.Children.Add(Rich(p.Text));
                    break;

                case GuideList l when inContents:
                    target.Children.Add(ContentsGrid(l));
                    break;

                case GuideList l:
                    target.Children.Add(List(l));
                    break;

                case GuideTable tbl:
                    target.Children.Add(Table(tbl));
                    break;
            }
        }
    }

    private Control SectionHeader(string title, bool showTopButton)
    {
        var grid = new Grid { ColumnDefinitions = new ColumnDefinitions("*,Auto"), Margin = new Thickness(0, 0, 0, 2) };
        grid.Children.Add(new TextBlock
        {
            Classes = { "section-title" },
            Text = title.ToUpperInvariant(),
            VerticalAlignment = VerticalAlignment.Center,
            TextWrapping = TextWrapping.Wrap,
        });
        if (showTopButton)
        {
            var top = new Button { Classes = { "guide-link" }, Content = "TOP ↑", FontSize = 9.5 };
            ToolTip.SetTip(top, "Back to the contents");
            top.Click += (_, _) => ScrollToTop();
            Grid.SetColumn(top, 1);
            grid.Children.Add(top);
        }
        return grid;
    }

    /// <summary>Two-column clickable table of contents.</summary>
    private Control ContentsGrid(GuideList list)
    {
        var grid = new UniformGrid { Columns = 2 };
        int n = 1;
        foreach (string item in list.Items)
        {
            var link = GuideParser.ParseInlines(item).FirstOrDefault(i => i.Kind == GuideInlineKind.Link);
            string label = link?.Text ?? item;
            var button = new Button
            {
                Classes = { "guide-link" },
                HorizontalAlignment = HorizontalAlignment.Stretch,
                HorizontalContentAlignment = HorizontalAlignment.Left,
                Content = TocEntry(n, label),
            };
            string? anchor = link?.Target;
            if (anchor != null)
                button.Click += (_, _) => ShowSection(anchor);
            grid.Children.Add(button);
            n++;
        }
        return grid;
    }

    /// <summary>"05  Picking colours from the screen (eyedropper)": long titles wrap instead of being cut.</summary>
    private static Control TocEntry(int number, string label)
    {
        var grid = new Grid { ColumnDefinitions = new ColumnDefinitions("24,*") };
        grid.Children.Add(new TextBlock { Text = $"{number:00}", Classes = { "guide-num" }, VerticalAlignment = VerticalAlignment.Top });
        var text = new TextBlock { Text = label, TextWrapping = TextWrapping.Wrap };
        Grid.SetColumn(text, 1);
        grid.Children.Add(text);
        return grid;
    }

    private Control List(GuideList list)
    {
        var panel = new StackPanel { Spacing = 5, Margin = new Thickness(2, 0, 0, 0) };
        int n = 1;
        foreach (string item in list.Items)
        {
            var row = new Grid { ColumnDefinitions = new ColumnDefinitions(list.Numbered ? "24,*" : "16,*") };
            row.Children.Add(new TextBlock
            {
                Classes = { "guide-num" },
                Text = list.Numbered ? $"{n:00}" : "•",
                VerticalAlignment = VerticalAlignment.Top,
                Margin = new Thickness(0, 1, 0, 0),
            });
            var text = Rich(item);
            Grid.SetColumn(text, 1);
            row.Children.Add(text);
            panel.Children.Add(row);
            n++;
        }
        return panel;
    }

    private Control Table(GuideTable table)
    {
        int columns = Math.Max(table.Header.Count, table.Rows.Count == 0 ? 0 : table.Rows.Max(r => r.Count));
        string defs = columns <= 1 ? "*" : "2*," + string.Join(",", Enumerable.Repeat("3*", columns - 1));

        var panel = new StackPanel();
        panel.Children.Add(TableRow(table.Header, defs, header: true));
        foreach (var row in table.Rows)
            panel.Children.Add(TableRow(row, defs, header: false));

        return new Border { Classes = { "guide-table" }, Child = panel };
    }

    private Control TableRow(IReadOnlyList<string> cells, string defs, bool header)
    {
        var grid = new Grid { ColumnDefinitions = new ColumnDefinitions(defs) };
        for (int i = 0; i < cells.Count; i++)
        {
            Control cell;
            if (header)
                cell = new TextBlock { Classes = { "label" }, Margin = new Thickness(0), Text = cells[i].ToUpperInvariant(), TextWrapping = TextWrapping.Wrap };
            else
                cell = Rich(cells[i]);
            cell.Margin = new Thickness(0, 0, 12, 0);
            Grid.SetColumn(cell, i);
            grid.Children.Add(cell);
        }
        var border = new Border { Classes = { header ? "guide-th" : "guide-tr" }, Child = grid };
        return border;
    }

    /// <summary>Selectable text with **bold**, *italic*, `code` and links styled like the editor.</summary>
    private static SelectableTextBlock Rich(string text)
    {
        var block = new SelectableTextBlock { Classes = { "guide-text" } };
        var inlines = new InlineCollection();
        foreach (var part in GuideParser.ParseInlines(text))
        {
            var run = new Run(part.Text);
            switch (part.Kind)
            {
                case GuideInlineKind.Bold:
                    run.FontWeight = FontWeight.Bold;
                    run.Foreground = Brush("EdText");
                    break;
                case GuideInlineKind.Italic:
                    run.FontStyle = FontStyle.Italic;
                    break;
                case GuideInlineKind.Code:
                    run.Foreground = Brush("EdGold");
                    run.FontWeight = FontWeight.SemiBold;
                    break;
                case GuideInlineKind.Link:
                    run.Foreground = Brush("EdCyan");
                    break;
            }
            inlines.Add(run);
        }
        block.Inlines = inlines;
        return block;
    }

    private static IBrush? Brush(string key) =>
        Application.Current != null && Application.Current.TryGetResource(key, null, out var value) && value is IBrush b ? b : null;
}
