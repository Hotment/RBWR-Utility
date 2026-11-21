# RBWR Theme Creator: User Guide

The RBWR Theme Creator lets you design themes for the RBWR APRM Calculator overlay without writing
any XAML. You pick colours, fonts and shapes, see the result live, and install the theme into the
overlay with one click.

Press **F1** at any time to see the keyboard shortcuts.

---

## Contents

1. [Quick start](#1-quick-start)
2. [The window at a glance](#2-the-window-at-a-glance)
3. [Live preview](#3-live-preview)
4. [Colours](#4-colours)
5. [Picking colours from the screen (eyedropper)](#5-picking-colours-from-the-screen-eyedropper)
6. [Gradients](#6-gradients)
7. [Fonts](#7-fonts)
8. [Shape: corners, borders, glow](#8-shape-corners-borders-glow)
9. [Images and backgrounds](#9-images-and-backgrounds)
10. [Advanced: custom styles](#10-advanced-custom-styles)
11. [Saving, exporting and installing](#11-saving-exporting-and-installing)
12. [Thumbnails and sharing on Discord](#12-thumbnails-and-sharing-on-discord)
13. [Opening and editing existing themes](#13-opening-and-editing-existing-themes)
14. [Keyboard shortcuts](#14-keyboard-shortcuts)
15. [Updates](#15-updates)
16. [Troubleshooting](#16-troubleshooting)

---

## 1. Quick start

Five steps from nothing to a working theme:

1. **NEW** (top bar) → pick a preset, for example *Cyberpunk* or *Synthwave*.
2. **THEME** tab → give it a **Name**. The **ID** fills in by itself.
3. **COLOURS** tab → pick one accent colour under *Generate from one colour* and click **GENERATE**.
   Then fine-tune any colour you like.
4. Click **INSTALL TO OVERLAY** (green button, top right).
5. In the overlay: **CONFIG → Reload**, then choose your theme.

That's it. Everything below explains each feature in more detail.

---

## 2. The window at a glance

| Area | What it does |
|---|---|
| **Top bar** | Undo/redo, NEW, OPEN, SAVE, EXPORT, INSTALL TO OVERLAY. The green version badge checks for updates. |
| **Left tabs** | THEME, COLOURS, FONTS, SHAPE, IMAGES, ADVANCED, CODE, OVERLAY. |
| **Right side** | The live preview of the overlay with your theme. |
| **Status bar** (bottom) | What just happened, errors, and where the theme is saved. |

The header shows **UNSAVED** when you have changes that are not saved yet. If you close the window with
unsaved changes, the creator asks first.

---

## 3. Live preview

The preview on the right is a copy of the real overlay. It updates as you edit.

- **View**: MONITOR, CONFIG, COMPACT, TABLET or ALL (all views at once). Shortcut: **Ctrl+1 … Ctrl+5**.
- **Backdrop**: what is behind the overlay (*Dark desktop*, *Game scene*, *Light desktop*,
  *Checkerboard*). Use *Game scene* and *Light desktop* to check that semi-transparent colours still
  look good over a bright game.
- **Zoom**: mouse wheel zooms at the cursor. **FIT** (or **Ctrl+0**, or double-click on an empty spot)
  fits the preview to the panel.
- **Move**: drag with the mouse (left button on an empty spot, or the middle/right button anywhere).
- The mock overlay is interactive: hover and click its buttons to see the hover and pressed colours.

### Find which colour paints something (FIND COLOUR)

Not sure which colour controls a border or a text? Ask the preview:

- **Ctrl+click** any element in the preview, or
- turn on **FIND COLOUR** in the preview bar and click elements. Elements light up under the
  mouse; press **Esc** to stop.

The creator jumps to the **COLOURS** tab, scrolls to the colours used by that element and makes their
rows flash. The status bar lists them, for example *"GenLoadCard uses: Card background, Border"*.

It works the other way round too: **double-click a row in COLOURS** to see where that colour is used
in the preview.

---

## 4. Colours

The **COLOURS** tab holds every colour of the overlay, grouped as *Surfaces*, *Accents*, *Text*,
*Control states*, *Tooltips* and *Sliders*.

For each colour you can:

- click the **swatch** to open the colour picker (spectrum, hue, opacity, hex and the overlay's own
  palette);
- type a **hex** value: `#rrggbb`, or `#aarrggbb` with transparency (press Enter or Tab to apply);
- click the **eyedropper** next to the swatch to take a colour from anywhere on the screen
  (see [section 5](#5-picking-colours-from-the-screen-eyedropper));
- use the **opacity slider** (backgrounds only). Lower values let the game show through the overlay.

### Search

Type in the search box (or press **Ctrl+F**) to filter the list. It searches names, keys, where the
colour is used and hex values. Examples: `slider`, `tooltip`, `border hover`, `#00f0ff`.
**Esc** or **CLEAR** shows everything again.

### Generate a whole palette from one colour

Under **Generate from one colour**:

1. Pick an accent colour (the swatch or its eyedropper).
2. Choose a mood: **Dark** (near-black, tinted), **Tinted** (more colour in the backgrounds) or
   **Neutral** (grey backgrounds; only the accents are coloured).
3. Click **GENERATE**.

Tick *Also change status colours* if you want green, red and gold to follow the accent too.
**Reset to default** brings back the original Cyberpunk colours.

### Contrast check

The green or gold box above the list tells you whether text is readable on your backgrounds. Aim for
at least **4.5:1** for normal text and **3:1** for muted text and accents. A gold box means something
may be hard to read.

---

## 5. Picking colours from the screen (eyedropper)

*Windows only.*

Every colour has a small **eyedropper** button next to its swatch: colour rows, gradient colours and
the palette generator. There is one inside the colour picker too.

1. Click the eyedropper. A magnifier appears next to the mouse cursor.
2. Move over anything on screen: the game, the overlay, a browser, a picture.
3. **Left click** (or **Enter**) takes the colour. **Right click** (or **Esc**) cancels.

Tips:

- **Arrow keys** move the cursor by 1 pixel and **Shift + arrows** by 10 pixels, so you can hit
  thin lines exactly.
- The magnifier shows the hex value and screen coordinates live.
- The click is caught by the eyedropper, so it never fires in the game or the window underneath.
- The colour's opacity is kept; only the colour itself changes.
- Works over games in borderless or windowed mode. In exclusive fullscreen the magnifier may not be
  visible.

---

## 6. Gradients

Backgrounds, borders and accents can be gradients instead of solid colours.

1. Click **GRADIENT** on a colour row.
2. Each colour of the gradient is a small card. Click **+** to add colours (up to 6) and **×** to remove one.
3. Set where each colour sits along the gradient (0% = start, 100% = end).
4. Choose a direction with the arrow buttons, the angle slider, or by typing degrees.

Helpers:

- **REVERSE** flips the gradient.
- **SOFT** resets to a gentle two-colour fade.
- **EVEN** spreads the colours evenly.

For a ready-made example, start from **NEW → Synthwave (gradients)**.

---

## 7. Fonts

**FONTS** tab:

- **Main font** and **Numbers / mono font** take a comma-separated list. The first font that exists
  on the player's PC is used, for example `Rajdhani, Segoe UI, sans-serif`.
- **ADD FONT…** bundles a `.ttf`, `.otf` or `.ttc` file with the theme, so players don't need to
  install it. Then click **Main** or **Mono** next to it to use it.
- **Reset to default** brings back the overlay's fonts.

You can also drag font files onto the window.

---

## 8. Shape: corners, borders, glow

**SHAPE** tab. Turn on **Custom shapes** first, then adjust:

| Setting | Changes |
|---|---|
| Window corners | Rounding of the main overlay window |
| Window border | Thickness of its outer border |
| Card corners | Rounding of the cards inside |
| Button / input corners | Rounding of buttons and text boxes |
| Compact pill corners | Rounding of the compact view |

**Glow** adds a soft light around the main window in the *Shell border (glow)* colour. **Glow size**
controls how far it spreads.

**Reset to default** goes back to the overlay's standard shapes.

---

## 9. Images and backgrounds

**IMAGES** tab:

- **Background image**: **CHOOSE…** a picture to place behind the overlay window. Set its
  **opacity** and **fit** (*UniformToFill* fills and crops, *Uniform* shows all of it, *Fill*
  stretches, *None* keeps the original size). **REMOVE** takes it off.
- **Image files**: extra pictures (`.png`, `.jpg`, `.webp`, `.bmp`, `.gif`) for your own custom styles.
  They are stored in `assets/`. Use them in styles as `Source="assets/name.png"`.

Tip: keep the background opacity low (20–40%) so the numbers stay readable.

---

## 10. Advanced: custom styles

The **ADVANCED** tab is for people who know Avalonia XAML. Everything else works without it.

- **Custom styles**: your own `<Style>` blocks. **INSERT EXAMPLE** adds ready snippets: bigger title,
  thicker active tab line, bigger power readout, image behind the power banner.
- **Extra resources**: brushes and other resources your styles use.
- **Selector reference**: the class names and element names you can target.

Errors show in red above the preview.

**Not allowed** (the overlay refuses them for safety): `x:Class`, `StyleInclude` / `ResourceInclude`,
and `clr-namespace` or other non-Avalonia namespaces.

The **CODE** tab shows the exact `theme.axaml` that will be saved. **COPY** puts it on the clipboard.

---

## 11. Saving, exporting and installing

### Theme info (THEME tab)

- **Name**: what players see in the overlay.
- **ID**: the folder name. Lowercase letters, digits, `-` and `_` only. It follows the name until you
  edit it yourself. `default` and `reactor-amber` are reserved for the built-in themes.
- **Author**, **Version** (like `1.0.0`), **Min. overlay** (oldest overlay version the theme needs)
  and **Description**.

### Where your theme goes

| Action | What happens |
|---|---|
| **SAVE** (Ctrl+S) | Saves into the theme's current folder. The first time, it asks where (like *Save as*). |
| **EXPORT → Save as new folder…** (Ctrl+Shift+S) | Saves a copy into a new folder. |
| **EXPORT → Export .zip pack…** (Ctrl+E) | One `.zip` file to share. Players install it in the overlay with **CONFIG → Install**. |
| **INSTALL TO OVERLAY** (Ctrl+I) | Copies the theme straight into the overlay's `themes` folder. Then in the overlay: **CONFIG → Reload** and pick the theme. Click Reload again after every update. |

A theme folder contains `theme.json`, `theme.axaml`, `fonts/`, `assets/` and `preview.png`.

### OVERLAY tab

- **Detect** finds the overlay's themes folder (a running overlay, or one next to the creator).
  **Find overlay…** lets you pick it yourself. **Folder** opens it in Explorer.
- **Installed themes**: **OPEN SELECTED** loads an installed theme into the editor.
  **DELETE SELECTED** removes it from the overlay permanently.

---

## 12. Thumbnails and sharing on Discord

### Thumbnails (preview.png)

Every saved, exported or installed theme gets a `preview.png`: a picture of the overlay's MONITOR view
in that theme. Newer overlay versions show it next to the theme name in the **Theme Manager**.

You don't have to do anything:

- **Save / Export / Install** write it automatically.
- **Opening** a theme folder (or its `theme.json`) that has no thumbnail creates one.
- **When the creator starts**, every installed overlay theme without a thumbnail gets one.
  This covers themes made before thumbnails existed.

A small message in the **bottom-right corner** tells you when thumbnails were created. Existing
thumbnails are never overwritten by these automatic passes. Themes without a thumbnail still work
normally; they just show no picture.

### Showing your theme on Discord

- **COPY** in the preview bar (or **Ctrl+Shift+C**) copies the preview as a picture. Paste it on
  Discord with **Ctrl+V**.
- **PNG** (or **Ctrl+P**) saves the preview as a high-resolution image file.
- To share the theme itself, send the `.zip` from **EXPORT → Export .zip pack**.

Both capture the view you have selected, so switch to ALL first to show every view at once.

---

## 13. Opening and editing existing themes

- **OPEN** (Ctrl+O) opens `theme.json`, a `.zip` pack or a `.axaml` file. **Ctrl+Shift+O** opens a
  theme folder.
- **Drag and drop** works too: drop a theme (`.zip`, `.axaml`, folder), a font or an image onto the
  window.
- Hand-written themes open as well. Styles the creator doesn't recognise are kept in
  **ADVANCED → Custom styles**, so nothing is lost.

### Undo and redo

**Ctrl+Z** undoes and **Ctrl+Y** (or **Ctrl+Shift+Z**) redoes, up to 50 steps.

---

## 14. Keyboard shortcuts

| Shortcut | Action |
|---|---|
| **Ctrl+S** | Save |
| **Ctrl+Shift+S** | Save as new folder |
| **Ctrl+O** / **Ctrl+Shift+O** | Open theme file / folder |
| **Ctrl+N** | New theme from a preset |
| **Ctrl+E** | Export .zip pack |
| **Ctrl+I** | Install to overlay |
| **Ctrl+Z** | Undo |
| **Ctrl+Y** / **Ctrl+Shift+Z** | Redo |
| **Ctrl+F** | Search colours |
| **Ctrl+1 … Ctrl+5** | Preview view: Monitor, Config, Compact, Tablet, All |
| **Ctrl+0** | Fit preview |
| **Ctrl+P** | Save preview image |
| **Ctrl+Shift+C** | Copy preview image |
| **Ctrl+click** (preview) | Find the colours of an element |
| **Esc** | Clear the search / stop FIND COLOUR |
| **F1** | Show this list in the app |

**Eyedropper:** left click or Enter picks, right click or Esc cancels, arrows move 1 px, Shift+arrows 10 px.

---

## 15. Updates

The creator checks for new versions when it starts. Click the **green version badge** next to the
title (or **CHECK UPDATES** in the THEME tab) to check now. When an update is found you can read what
changed, install it, or skip that version.

---

## 16. Troubleshooting

**My theme doesn't appear in the overlay.**
Click **CONFIG → Reload** in the overlay after installing. Check that **OVERLAY → Themes folder**
points to the right overlay, and use **Detect** or **Find overlay…** if not.

**"Fix the theme info first" when saving.**
Fill in the **Name**. The **ID** must be lowercase letters, digits, `-` or `_`, and must not be
`default` or `reactor-amber`. The **Version** must look like `1.0.0`.

**A red message appears above the preview.**
Your custom styles in ADVANCED contain an error. The message says what is wrong. Fix it or remove
the style.

**The text is hard to read in the game.**
Check the contrast box in COLOURS, raise the background opacity, and preview with the *Game scene*
and *Light desktop* backdrops.

**The eyedropper button is missing.**
It is available on Windows only.

**Still stuck?**
Send a report through the ticket system on the website.
