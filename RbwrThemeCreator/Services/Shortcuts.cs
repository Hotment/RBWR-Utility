using Avalonia.Input;

namespace RbwrThemeCreator.Services;

/// <summary>A key plus modifiers, e.g. Ctrl+Shift+S. Digits are stored as D0..D9.</summary>
public readonly record struct ShortcutGesture(Key Key, KeyModifiers Modifiers)
{
    private const KeyModifiers UsedModifiers = KeyModifiers.Control | KeyModifiers.Shift | KeyModifiers.Alt | KeyModifiers.Meta;

    /// <summary>The gesture of a key press (number pad digits count as the normal digits).</summary>
    public static ShortcutGesture FromKeyPress(Key key, KeyModifiers modifiers) =>
        new(key is >= Key.NumPad0 and <= Key.NumPad9 ? Key.D0 + (key - Key.NumPad0) : key, modifiers & UsedModifiers);

    /// <summary>Keys that are only modifiers (waiting for the real key while recording).</summary>
    public static bool IsModifierKey(Key key) => key is Key.LeftCtrl or Key.RightCtrl or Key.LeftShift or Key.RightShift
        or Key.LeftAlt or Key.RightAlt or Key.LWin or Key.RWin;

    /// <summary>
    /// Shortcuts need Ctrl, Alt or Win, or must be an F-key; otherwise they would fire while typing
    /// a name or a hex value.
    /// </summary>
    public bool IsAllowed =>
        !IsModifierKey(Key) && Key != Key.None
        && ((Modifiers & (KeyModifiers.Control | KeyModifiers.Alt | KeyModifiers.Meta)) != 0 || Key is >= Key.F1 and <= Key.F24);

    public KeyGesture ToKeyGesture() => new(Key, Modifiers);

    /// <summary>"Ctrl+Shift+S", "Ctrl+1", "F1".</summary>
    public override string ToString()
    {
        var parts = new List<string>();
        if (Modifiers.HasFlag(KeyModifiers.Control)) parts.Add("Ctrl");
        if (Modifiers.HasFlag(KeyModifiers.Alt)) parts.Add("Alt");
        if (Modifiers.HasFlag(KeyModifiers.Shift)) parts.Add("Shift");
        if (Modifiers.HasFlag(KeyModifiers.Meta)) parts.Add("Win");
        parts.Add(KeyName(Key));
        return string.Join('+', parts);
    }

    public static bool TryParse(string? text, out ShortcutGesture gesture)
    {
        gesture = default;
        if (string.IsNullOrWhiteSpace(text)) return false;

        var mods = KeyModifiers.None;
        Key? key = null;
        foreach (string raw in text.Split('+', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries))
        {
            switch (raw.ToLowerInvariant())
            {
                case "ctrl" or "control": mods |= KeyModifiers.Control; continue;
                case "shift": mods |= KeyModifiers.Shift; continue;
                case "alt": mods |= KeyModifiers.Alt; continue;
                case "win" or "meta" or "cmd": mods |= KeyModifiers.Meta; continue;
            }
            if (key != null) return false; // two keys
            if (raw.Length == 1 && char.IsDigit(raw[0]))
                key = Key.D0 + (raw[0] - '0');
            else if (Enum.TryParse<Key>(raw, ignoreCase: true, out var k) && Enum.IsDefined(k))
                key = k;
            else
                return false;
        }
        if (key is not { } found || found == Key.None) return false;
        gesture = FromKeyPress(found, mods);
        return true;
    }

    private static string KeyName(Key key) => key switch
    {
        >= Key.D0 and <= Key.D9 => ((char)('0' + (key - Key.D0))).ToString(),
        Key.OemPlus => "Plus",
        Key.OemMinus => "Minus",
        Key.OemComma => "Comma",
        Key.OemPeriod => "Period",
        Key.Oem2 => "Slash",
        _ => key.ToString(),
    };
}

/// <summary>An action that can have a keyboard shortcut.</summary>
public sealed record ShortcutDefinition(string Id, string Label, string Group, string DefaultGesture);

/// <summary>Every action with a shortcut, and the defaults (Esc and Ctrl+click are fixed).</summary>
public static class ShortcutCatalog
{
    public const string GroupFile = "FILE";
    public const string GroupEdit = "EDIT";
    public const string GroupPreview = "PREVIEW";
    public const string GroupHelp = "HELP";

    public static readonly IReadOnlyList<ShortcutDefinition> All =
    [
        new("save", "Save", GroupFile, "Ctrl+S"),
        new("save-as", "Save as new folder", GroupFile, "Ctrl+Shift+S"),
        new("open-file", "Open theme file", GroupFile, "Ctrl+O"),
        new("open-folder", "Open theme folder", GroupFile, "Ctrl+Shift+O"),
        new("new", "New theme from a preset", GroupFile, "Ctrl+N"),
        new("export-zip", "Export .zip pack", GroupFile, "Ctrl+E"),
        new("install", "Install to overlay", GroupFile, "Ctrl+I"),

        new("undo", "Undo", GroupEdit, "Ctrl+Z"),
        new("redo", "Redo", GroupEdit, "Ctrl+Y"),
        new("redo-alt", "Redo (second shortcut)", GroupEdit, "Ctrl+Shift+Z"),
        new("search", "Search colours", GroupEdit, "Ctrl+F"),
        new("find-colour", "FIND COLOUR on / off", GroupEdit, ""),

        new("view-monitor", "Preview: Monitor", GroupPreview, "Ctrl+1"),
        new("view-config", "Preview: Config", GroupPreview, "Ctrl+2"),
        new("view-compact", "Preview: Compact", GroupPreview, "Ctrl+3"),
        new("view-tablet", "Preview: Tablet", GroupPreview, "Ctrl+4"),
        new("view-all", "Preview: All", GroupPreview, "Ctrl+5"),
        new("fit", "Fit preview", GroupPreview, "Ctrl+0"),
        new("save-preview", "Save preview image", GroupPreview, "Ctrl+P"),
        new("copy-preview", "Copy preview image", GroupPreview, "Ctrl+Shift+C"),

        new("guide", "Open the guide (shortcuts)", GroupHelp, "F1"),
    ];

    public static ShortcutDefinition? Find(string id) => All.FirstOrDefault(d => d.Id == id);
}

/// <summary>
/// The shortcuts in use: defaults plus the user's changes. Changes are kept in <paramref name="overrides"/>
/// (action id -> gesture text, "" = no shortcut), which the app stores in its settings file.
/// </summary>
public sealed class ShortcutMap(IDictionary<string, string> overrides, Action save)
{
    public event EventHandler? Changed;

    public ShortcutGesture? Get(string id)
    {
        string text = overrides.TryGetValue(id, out var custom) ? custom : ShortcutCatalog.Find(id)?.DefaultGesture ?? string.Empty;
        return ShortcutGesture.TryParse(text, out var g) ? g : null;
    }

    public bool IsCustom(string id) => overrides.ContainsKey(id);

    /// <summary>The action bound to this gesture, if any.</summary>
    public string? FindAction(ShortcutGesture gesture) =>
        ShortcutCatalog.All.FirstOrDefault(d => Get(d.Id) == gesture)?.Id;

    /// <summary>
    /// Gives <paramref name="id"/> the gesture (null = no shortcut). An action that had the same
    /// gesture loses it; its id is returned so the caller can say so.
    /// </summary>
    public string? Set(string id, ShortcutGesture? gesture)
    {
        string? taken = null;
        if (gesture is { } g)
        {
            taken = ShortcutCatalog.All.FirstOrDefault(d => d.Id != id && Get(d.Id) == g)?.Id;
            if (taken != null)
                Store(taken, null);
        }
        Store(id, gesture);
        save();
        Changed?.Invoke(this, EventArgs.Empty);
        return taken;
    }

    public void ResetToDefault(string id)
    {
        var def = ShortcutCatalog.Find(id);
        if (def != null && ShortcutGesture.TryParse(def.DefaultGesture, out var g))
        {
            // Taking the default back may clash with another action's custom shortcut: that one loses it.
            var holder = ShortcutCatalog.All.FirstOrDefault(d => d.Id != id && Get(d.Id) == g);
            if (holder != null) Store(holder.Id, null);
        }
        overrides.Remove(id);
        save();
        Changed?.Invoke(this, EventArgs.Empty);
    }

    public void ResetAll()
    {
        overrides.Clear();
        save();
        Changed?.Invoke(this, EventArgs.Empty);
    }

    private void Store(string id, ShortcutGesture? gesture)
    {
        string text = gesture?.ToString() ?? string.Empty;
        string def = ShortcutCatalog.Find(id)?.DefaultGesture ?? string.Empty;
        bool isDefault = ShortcutGesture.TryParse(def, out var d) ? gesture == d : gesture == null;
        if (isDefault)
            overrides.Remove(id);
        else
            overrides[id] = text;
    }
}
