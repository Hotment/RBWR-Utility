# RBWR Utility & APRM Transparent Overlay Calculator

A comprehensive suite of tools designed for the Roblox **Realistic Boiling Water Reactor (RBWR)** simulation. This project includes both a lightweight, hardware-accelerated **Desktop Transparent Overlay Calculator** (.NET 8 / Avalonia UI) and a full-featured **Web Application & Server Suite** (Python 3.12 / Flask) with real-time plant monitors, interactive graphs, point generation analytics, and server browsing.

---

## Table of Contents

- [Features](#features)
  - [Desktop Transparent Overlay (.NET 8 / Avalonia UI)](#desktop-transparent-overlay-net-8--avalonia-ui)
  - [Web Application & Server Suite (Python / Flask)](#web-application--server-suite-python--flask)
- [Architecture & Project Structure](#architecture--project-structure)
- [Installation & Running](#installation--running)
  - [Pre-built Desktop Releases](#pre-built-desktop-releases)
  - [Building & Running Desktop Overlay from Source](#building--running-desktop-overlay-from-source)
  - [Multi-Platform Build Script (`build.bat`)](#multi-platform-build-script-buildbat)
  - [Running the Web Application Server](#running-the-web-application-server)
- [Overlay Controls & Shortcuts](#overlay-controls--shortcuts)
- [Web Application Routes](#web-application-routes)
- [Server Performance Scoring Engine](#server-performance-scoring-engine)
- [Calculation Reference](#calculation-reference)
- [Configuration & Environment Variables](#configuration--environment-variables)
- [License](#license)

---

## Features

### Desktop Transparent Overlay (.NET 8 / Avalonia UI)

* **Hardware-Accelerated Alpha Transparency:** Uses native GPU-accelerated Alpha composition (`TransparencyLevelHint="Transparent"`), eliminating magenta color-key fringing, click-through dropouts, and OS lag.
* **Dual UI Modes:**
  * **Detailed Tactical Deck:** Full monitoring view with neon gauge displays, one-click power presets (0%, 20%, 40%, 60%, 80%, 100%), rapid stepper adjustments (+/- 10 MWe), and real-time turbine health alerts.
  * **Ultra-Compact Floating Pill:** Minimalist horizontal floating bar (465x60 px) designed for distraction-free gameplay.
* **Unified Interface:** Monitor, Server Sync, Configuration, Feedback, and Updates are consolidated into high-tech integrated tabs (`MONITOR`, `SYNC`, `CONFIG`, `FEEDBACK`), preventing secondary windows from getting hidden behind game sessions.
* **Bidirectional Physics Solver:** Fixed-point iterative solver mapping demand to core thermal power, generator load, and feedwater flow while dynamically calculating auxiliary recirculation pump usage.
* **Live Server Synchronization:** Connects via full Roblox Job ID (UUID) or shortened in-game Server ID (e.g. `77f6-4b2f`). Features sub-second countdown timers, -1s/+1s calibration offsets, and automatic demand transition tracking.
* **Multi-Unit Layouts:** Independent quadratic curves, recirculation flow tables, and auxiliary usage formulas for Unit 1 and Unit 2.
* **Roblox Window Focus Tracking:** Automatically detects when the Roblox game window is focused and brings the overlay topmost, automatically managing visibility.
* **Resilient Crash Handler:** 
  * Captures runtime and startup exceptions with full stack traces and inner exception chains in `RBWR_APRM_Calculator.log`.
  * Generates an actionable `RBWR_Crash_Report.txt` dump on disk with system diagnostics.
  * Displays a cyberpunk-themed modal window with copy traceback and GitHub reporting options, or a native Win32 system fallback dialog if the graphics engine cannot initialize.
* **Standalone Single-File Distribution:** Supports building as a single, self-contained executable with embedded native libraries and runtime, requiring no external files or pre-installed .NET runtimes.

### Web Application & Server Suite (Python / Flask)

* **Web Calculator (`/calculator`):** Full-featured in-browser APRM and thermal power calculator with live server synchronization.
* **Points & Rank Calculator (`/points`):** Comprehensive points-per-second, shift earnings, and operational rank requirements calculator.
* **Operator Tablet (`/tablet`):** Live in-browser recreation of the game's Operator Tablet displaying reactor temperatures, APRM setpoints, pump speeds, control rod status, and SCRAM alarms.
* **Server Browser (`/servers`):** Real-time monitoring of all public and tracked RBWR servers with pagination, search by Job ID or short ID, and grid power analytics.
* **Server Detail & Analytics (`/servers/<job_id>`):** Interactive historical graphs for APRM, generator power, steam flow, turbine health, and reactor metrics with touch and zoom controls.
* **Performance Scoring Engine:** Rolling 60-minute evaluation engine rating operational efficiency, PPS sustainability, outage recovery, and multi-unit synergy.
* **Point History Graph (`/points-graph`):** Client-side parser and interactive visualizer for local `sar_data.json` logs with zero server uploads.
* **Community Suggestions (`/suggestions`):** Community feature request and upvoting board with administrator review statuses.
* **Admin Portal (`/admin`):** Management portal for persistent server tracking, moderation, crash reports, and operational metrics.

---

## Architecture & Project Structure

```
RBWR-Utility/
|
|-- RbwrOverlay/                      # Desktop Application (.NET 8 / Avalonia UI)
|   |-- RbwrOverlay.Core/             # Core calculation engine & models
|   |   |-- Calculations/             # Reactor models, solvers, recirculation tables
|   |   |-- Models/                   # AppSettings, ServerInfo, UpdateInfo
|   |   `-- Services/                 # ApiClient, LoggingService, SettingsService
|   |-- RbwrOverlay.Platform/         # Cross-platform OS abstractions
|   |   `-- Process tracking for Windows, Linux, and macOS
|   |-- RbwrOverlay.UI/               # Avalonia UI desktop application
|   |   |-- Assets/                   # Embedded icons and resources
|   |   |-- Behaviors/                # AutoComplete and UI event behaviors
|   |   |-- Services/                 # CrashHandler & error presentation
|   |   |-- Styles/                   # CyberpunkTheme dark aesthetic tokens
|   |   |-- ViewModels/               # MVVM reactive view models
|   |   `-- Views/                    # Overlay, Sync, Config, Feedback, Crash windows
|   |-- RbwrOverlay.Tests/            # xUnit test suite (50 unit tests)
|   `-- RbwrOverlay.slnx              # Modern .NET solution definition
|
|-- server/                           # Web Application & Backend (Python / Flask)
|   |-- app.py                        # Flask server, WebSocket routes, API endpoints
|   |-- scoring.py                    # Server top score engine & PPS calculations
|   |-- templates/                    # Jinja2 templates for web interface
|   |-- static/                       # CSS stylesheets, JS utilities, brand icons
|   `-- data/                         # Server state, persistent tracking, archives
|
|-- bot/                              # Optional Discord integration bot
|-- build.bat                         # Multi-target builder for Windows & Linux
`-- rbwr_overlay.py                   # Legacy Python Tkinter implementation
```

---

## Installation & Running

### Pre-built Desktop Releases

Pre-compiled desktop releases are available on the [Releases](https://github.com/Hotment/RBWR-Utility/releases) page:

* **Windows Standalone (Recommended):** Download `RbwrOverlay.exe` (or `RBWR_APRM_Calculator.exe`) from `publish/win-x64-standalone/`. This single executable is fully self-contained, requiring zero external files, no zip extraction, and no .NET installation.
* **Windows Framework-Dependent:** Download the portable folder from `publish/win-x64/` (requires .NET 8 Desktop Runtime).
* **Linux Standalone:** Download `RbwrOverlay` from `publish/linux-x64-standalone/`. Includes a ready-to-use desktop entry file (`rbwr-overlay.desktop`).
* **Linux Framework-Dependent:** Download `publish/linux-x64/` (requires .NET 8 runtime).

---

### Building & Running Desktop Overlay from Source

#### Prerequisites
* [.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0) (Version 8.0.x or newer).

#### Run Directly:
```bash
dotnet run --project RbwrOverlay/RbwrOverlay.UI/RbwrOverlay.UI.csproj
```

#### Run Automated Test Suite:
```bash
dotnet test RbwrOverlay/RbwrOverlay.Tests/RbwrOverlay.Tests.csproj
```

---

### Multi-Platform Build Script (`build.bat`)

The repository includes an interactive and automated builder for Windows and Linux targets:

```cmd
build.bat [target]
```

#### Available Targets:
* `all`: Builds all 4 release targets (default).
* `windows-standalone` (or `win-standalone`): Builds the single-file Windows executable with embedded native libraries and runtime (no external files needed).
* `windows` (or `win`): Builds the lightweight framework-dependent Windows executable.
* `linux-standalone`: Builds the self-contained Linux executable with desktop launcher.
* `linux`: Builds the framework-dependent Linux executable.
* `clean`: Removes the `publish/` output directory.

Output binaries are placed in:
```
publish/
|-- win-x64-standalone/     # RbwrOverlay.exe / RBWR_APRM_Calculator.exe (Single-file)
|-- win-x64/                # RbwrOverlay.exe + extracted native DLLs
|-- linux-x64-standalone/   # RbwrOverlay (Self-contained) + rbwr-overlay.desktop
`-- linux-x64/              # RbwrOverlay (Framework-dependent) + rbwr-overlay.desktop
```

---

### Running the Web Application Server

The Flask application powers the browser tools, public APIs, live server tracking, and metrics calculation:

1. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # Linux/macOS:
   source venv/bin/activate
   ```
2. Install server dependencies:
   ```bash
   pip install -r server/requirements.txt
   ```
3. Start the application:
   ```bash
   python server/app.py
   ```
4. Access the web interface at `http://127.0.0.1:8400`.

---

## Overlay Controls & Shortcuts

* **Reposition HUD:** Left-click and drag anywhere on the header bar or background panel.
* **Toggle Compact Mode:** Click the layout toggle button in the header to switch between Detailed Deck mode and Compact Bar mode. Double-clicking the compact bar returns to detailed mode.
* **Toggle Always-on-Top:** Toggle the pin button in the header bar.
* **Adjust Transparency:** Switch to the `CONFIG` tab and adjust the opacity slider (30% to 100%).
* **Toggle Unit Focus:** Click the `UNIT 1` or `UNIT 2` header tabs in detailed view, or click `U1`/`U2` in compact view.
* **Server Sync:** Switch to the `SYNC` tab. Enter a full Job ID or shortened Server ID (`xxxx-xxxx`) and press Enter to synchronize live demand setpoints and timers.
* **Calibration Stepper:** Use the `-1s` / `+1s` calibration buttons in the sync tab to align countdown timers with actual server cycles.
* **Exit Application:** Click the `X` button in the header bar, or right-click the system tray icon and select Exit.

---

## Web Application Routes

| Route | Description |
| :--- | :--- |
| `/` | Landing page introducing features, guides, and download links. |
| `/calculator` | In-browser Thermal Power & APRM Calculator with server auto-sync. |
| `/points` | Points & Rank Calculator for shift earnings and goal progression. |
| `/tablet` | Real-time web recreation of the in-game Operator Tablet. |
| `/servers` | Server Browser with search, pagination, and grid analytics. |
| `/servers/<job_id>` | Historical snapshot graphs, operational logs, and score breakdown. |
| `/api/servers/<job_id>/score_breakdown` | JSON API endpoint returning comprehensive top score breakdown. |
| `/points-graph` | Client-side visualizer for local `sar_data.json` logs. |
| `/suggestions` | Community feedback board with submission form and upvoting. |
| `/contact` | Direct communication form to the administrator. |
| `/admin` | Administrative portal for persistent tracking and server moderation. |

---

## Server Performance Scoring Engine

The scoring engine in `server/scoring.py` (`calculate_server_top_score`) evaluates plant performance over a rolling 60-minute window of snapshot history, outputting a Top Score between `0.0` and `100.0`.

### Core Evaluation Mechanics:
1. **Point Generation Sustainability (PPS):**
   * Combined maximum sustainable plant output is **2.9 pts/s** (Unit 1: 1.2 pts/s, Unit 2: 1.7 pts/s).
   * Rather than an additive bonus, point generation acts as a recency-weighted efficiency multiplier ($W_{\text{pps}} \le 1.0$). If a plant cannot sustain point output, its score scales downward proportionally.
2. **Recency Weighting:**
   * Snapshots decay with a 10-minute half-life (`600s`).
   * Current snapshot receives a **1.50x** weight boost; previous snapshot receives a **1.25x** boost.
3. **The +/- 40 MW Generation Deadband:**
   * Generation within +/- 40 MW of target demand receives full 1.0 ratio credit.
   * Includes a 60-second grace window following demand changes to permit rod and flow adjustments.
4. **Unit 2 Refueling Outage Detection:**
   * Outages beginning with qualified demand event codes (-1 Maintenance, -2 LOOP, -3 Reset, -4 Evacuation) are evaluated against an optimal 50-minute profile, avoiding unexcused downtime penalties.
5. **Synergy & Incident Deductions:**
   * **1.25x** multiplier when both reactor units generate power simultaneously.
   * -60% snapshot reduction during active SCRAM or turbine trip events, with cumulative deductions for unrecovered incidents.

---

## Calculation Reference

The calculation engine uses quadratic relationships to map core thermal power ($t$, in %) to generator load ($GenLoad$, in MWe) and feedwater flow ($Flow$, in kg/s):

### Unit 1
* **Thermal Power (%)** from Demand ($d$) and auxiliary usage ($u$):
  $$t = \max\left(0, \frac{-13 + \sqrt{169 + 0.02132 \times (d + 135 + u)}}{0.01066}\right)$$
* **Generator Load (MWe):**
  $$GenLoad = \max\left(0, -135 + 13 \times t + 5.33 \times 10^{-3} \times t^2\right)$$
* **Feedwater Flow (kg/s):**
  $$Flow = \max\left(0, 82.8 + 13.7 \times t + 5.87 \times 10^{-3} \times t^2\right) + 2$$

### Unit 2
* **Thermal Power (%)** from Demand ($d$) and auxiliary usage ($u$):
  $$t = \max\left(0, \frac{-10.9 + \sqrt{118.81 + 0.0952 \times (82.3 + d + u)}}{0.0476}\right)$$
* **Generator Load (MWe):**
  $$GenLoad = \max\left(0, -82.3 + 10.9 \times t + 0.0238 \times t^2\right)$$
* **Feedwater Flow (kg/s):**
  $$Flow = \max\left(0, 160.0 + 11.6 \times t + 0.0249 \times t^2\right) + 2$$

---

## Configuration & Environment Variables

When running the web server (`server/app.py`), configuration can be customized via environment variables or a `.env` file:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `SERVER_PORT` | `8400` | Port the web application listens on. |
| `HOST` | `0.0.0.0` | Host IP address binding. |
| `ADMIN_USERNAME` | *(auto-generated)* | Administrator username for `/admin`. |
| `ADMIN_PASSWORD` | *(auto-generated)* | Administrator password for `/admin`. |
| `FLASK_SECRET_KEY` | *(auto-generated)* | Session encryption key. |
| `DISCORD_WEBHOOK_URL` | *(optional)* | Webhook for notifications on contact submissions and crash reports. |
| `DISCORD_BOT_TOKEN` | *(optional)* | Token for optional Discord bot integration. |

---

## License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.