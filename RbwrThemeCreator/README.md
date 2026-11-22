# RBWR Theme Creator

A standalone visual editor for RBWR APRM Calculator overlay themes. It outputs the same
format the overlay loads: `theme.json`, `theme.axaml`, `fonts/` and `assets/`.

## Run

```bash
dotnet run --project RbwrThemeCreator
```

Publish a single-file build:

```bash
dotnet publish RbwrThemeCreator -c Release -r win-x64 --self-contained -p:PublishSingleFile=true
```

**How to use every feature: see the [User Guide](GUIDE.md).**

## Features

- Live preview of the overlay windows (detailed, config and compact views, plus a tooltip). The preview
  uses the overlay's real `CyberpunkTheme.axaml`, which is embedded at build time.
- An editor for all 29 colour tokens, with colour pickers, hex input, opacity sliders and a contrast check.
- A screen eyedropper (Windows) next to every colour swatch (colour tokens, gradient colours, the palette
  generator) and inside the colour picker: pick any pixel on screen (the game, the overlay, a browser)
  with a magnifier. Left click or Enter picks, right click or Esc cancels, the arrow keys move the cursor
  1 px (Shift: 10 px).
- Colour search (Ctrl+F): filter the colour list by name, key, where it is used, or hex value.
- **FIND COLOUR**: Ctrl+click an element in the preview (or turn on the FIND COLOUR toggle) to jump to
  the colours that paint it. Their rows flash in the COLOURS tab.
- Thumbnails: Save, Export and Install also write `preview.png` (the MONITOR view) next to `theme.json`;
  the overlay's Theme Manager shows it next to the theme name. Opening a theme without one creates it,
  and on start-up every installed overlay theme without one gets it (a toast in the bottom-right corner
  says so).
  **PNG** saves the current preview as an image and **COPY** puts it on the clipboard.
- Keyboard shortcuts: Ctrl+S / Ctrl+Shift+S save, Ctrl+O / Ctrl+Shift+O open, Ctrl+N new, Ctrl+E export,
  Ctrl+I install, Ctrl+Z / Ctrl+Y undo/redo, Ctrl+1…5 preview view, Ctrl+0 fit, Ctrl+P save preview image,
  Ctrl+Shift+C copy preview image, F1 shows the list.
- A palette generator that builds a full theme from one accent colour.
- Presets: Cyberpunk, Reactor Amber, Arctic Slate and Blank.
- Custom fonts (`.ttf`/`.otf`), corner radius and border settings, a window glow and a background image.
- An Advanced tab for your own `<Style>` and resource XAML.
- Save to a folder or export a `.zip` pack. **Install to overlay** finds the overlay's `themes` folder
  automatically: from a running overlay, from an overlay next to the creator, or from the dev build.
- Opens existing themes (folder, `theme.json`, `.zip`, `.axaml`), including hand-written ones. The
  creator keeps any styles it does not recognise as custom XAML.

The creator applies the same safety rules as the overlay's `ThemeService`: no `clr-namespace`,
`x:Class` or `StyleInclude`. If you change those rules, update `Services/ThemeValidator.cs` to match.
