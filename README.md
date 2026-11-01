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
  * **Ultra-Compact Floating Pill:** Minimalist horizontal floating bar (465x60 px) with `U1 | U2 | TCR` mode selectors and dual-column readouts designed for distraction-free gameplay.
* **Unit 2 Turbine Control Room (TCR) Mode:** Dedicated `TCR` mode alongside `U1` and `U2` in both the Full HUD and Compact Pill HUD, computing Unit 2 **Main Steam Sealing (`MSS %`)** and **Oil Cooling (`OCL %`)** valve setpoints alongside Generator Load (`MWe`) and Steam Flow (`kg/s`).
* **Interactive Mouse-Following Tooltips:** Non-activating, click-through hover help popups that smoothly track the cursor across controls, badges, and readouts, dynamically adapting descriptions to the selected unit/mode (`U1`, `U2`, or `TCR`) with a toggle in the `CONFIG` tab.
* **Unified Interface:** Monitor, Server Sync, Configuration, Feedback, and Updates are consolidated into high-tech integrated tabs (`MONITOR`, `SYNC`, `CONFIG`, `FEEDBACK`), preventing secondary windows from getting hidden behind game sessions.
* **Bidirectional Physics Solver:** Fixed-point iterative solver mapping net grid demand or direct APRM/RTP (%) overrides to core thermal power, generator load, feedwater flow, and turbine auxiliary valves while dynamically calculating recirculation pump usage.
* **Live Server Synchronization:** Connects via full Roblox Job ID (UUID) or shortened in-game Server ID (e.g. `77f6-4b2f`). Features sub-second countdown timers, -1s/+1s calibration offsets, and automatic demand transition tracking.
* **Multi-Unit Polynomial Regression Models:** Independent quadratic (Unit 1) and cubic (Unit 2) regression curves imported directly from the [RBWR Operation Reference Google Sheet](https://docs.google.com/spreadsheets/d/1Izstp_2PZhQNmFyyr_5Una5GCcLBhgORVTX-CMkse2I/), paired with recirculation flow tables and auxiliary usage formulas.
* **Roblox Window Focus Tracking:** Automatically detects when the Roblox game window is focused and brings the overlay topmost, automatically managing visibility.
* **In-App Auto-Updater:** Side-by-side build comparison dialog (`INSTALLED BUILD -> NEW RELEASE`) with scrollable release notes, version skipping, and automated package updates.
* **Resilient Crash Handler:** 
  * Captures runtime and startup exceptions with full stack traces and inner exception chains in `RBWR_APRM_Calculator.log`.
  * Generates an actionable `RBWR_Crash_Report.txt` dump on disk with system diagnostics.
  * Displays a cyberpunk-themed modal window with copy traceback and GitHub reporting options, or a native Win32 system fallback dialog if the graphics engine cannot initialize.
* **Standalone Single-File Distribution:** Supports building as a single, self-contained executable with embedded native libraries and runtime, requiring no external files or pre-installed .NET runtimes.

### Web Application & Server Suite (Python / Flask)

* **Web Calculator (`/calculator`):** Full-featured in-browser APRM, thermal power, and regression model calculator with live server synchronization.
* **Points & Rank Calculator (`/points`):** Comprehensive points-per-second, shift earnings, and operational rank requirements calculator.
* **Operator Tablet (`/tablet`):** Live in-browser recreation of the game's Operator Tablet displaying reactor temperatures, APRM setpoints, pump speeds, control rod status, and SCRAM alarms.
* **Server Browser (`/servers`):** Real-time monitoring of all public and tracked RBWR servers with pagination, search by Job ID or short ID, and grid power analytics.
* **Server Detail & Analytics (`/servers/<job_id>`):** Interactive historical graphs for APRM, generator power, steam flow, turbine health, and reactor metrics with touch and zoom controls.
* **Performance Scoring Engine:** Rolling 60-minute evaluation engine rating operational efficiency, PPS sustainability, outage recovery, and multi-unit synergy.
* **Point History Graph (`/points-graph`):** Client-side parser and interactive visualizer for local `sar_data.json` logs with zero server uploads.
* **Feedback & Support Tickets (`/tickets`):** Unified support ticket and community feedback system with Discord OAuth2 sign-in, interactive ticket chat threads, and Discord DM notifications.
* **Admin Portal (`/admin`):** Management portal for persistent server tracking, ticket moderation, crash reports, and operational metrics.

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
|   |   |-- Behaviors/                # AutoComplete, cursor-following tooltips, UI behaviors
|   |   |-- Services/                 # CrashHandler, TooltipCatalog & error presentation
|   |   |-- Styles/                   # CyberpunkTheme dark aesthetic tokens
|   |   |-- ViewModels/               # MVVM reactive view models
|   |   `-- Views/                    # Overlay, Sync, Config, Feedback, Update, Crash windows
|   |-- RbwrOverlay.Tests/            # xUnit test suite (62 unit tests)
|   `-- RbwrOverlay.slnx              # Modern .NET solution definition
|
|-- server/                           # Web Application & Backend (Python / Flask)
|   |-- app.py                        # Flask server, WebSocket routes, API endpoints
|   |-- calculator.py                 # Polynomial regression models & physics solver
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

* **Windows x64 Standalone (Recommended):** `RBWR_APRM_Calculator_win-x64.exe` — Single-file executable, double-click to run with zero installation or extraction required.
* **Windows ARM64 Standalone:** `RBWR_APRM_Calculator_win-arm64.exe` — Native build for Snapdragon X and Surface Pro ARM64 devices.
* **Linux x86_64 AppImage:** `RBWR_APRM_Calculator_linux-x64.AppImage` — Universal single-file Linux package, double-click to run or execute in terminal (`chmod +x && ./RBWR_APRM_Calculator_linux-x64.AppImage`).
* **Linux x86_64 / ARM64 Tarball:** `RBWR_APRM_Calculator_Linux_linux-x64.tar.gz` and `linux-arm64` — Includes `./RbwrOverlay`, launcher script (`run.sh`), and desktop entry (`rbwr-overlay.desktop`).
* **macOS Apple Silicon & Intel:** `RBWR_APRM_Calculator_macOS_osx-arm64.zip` and `osx-x64.zip` — Includes `RBWR APRM Calculator.app` bundle and terminal executable.

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

The repository includes an interactive and automated builder for Windows, Linux, and macOS targets:

```cmd
build.bat [target]
```

#### Available Targets:
* `all`: Builds all release packages (Windows x64/ARM64, Linux x64/ARM64/AppImage, macOS Apple Silicon/Intel).
* `win-standalone`: Builds the single-file Windows x64 executable.
* `win-arm64`: Builds the single-file Windows ARM64 executable.
* `linux-standalone`: Builds the self-contained Linux x64 package.
* `linux-arm64`: Builds the Linux ARM64 standalone package.
* `appimage`: Builds the Linux x64 `.AppImage` package via WSL or Linux.
* `mac-arm64`: Builds macOS Apple Silicon (.app bundle + binary).
* `mac-x64`: Builds macOS Intel (.app bundle + binary).
* `clean`: Removes the `publish/` output directory.

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
* **Adjust Transparency & Tooltips:** Switch to the `CONFIG` tab to adjust the opacity slider (30% to 100%) or toggle `Hover Help Tooltips` (`ENABLED` / `DISABLED`).
* **Toggle Unit / TCR Mode:** Click `UNIT 1`, `UNIT 2`, or `TCR (MSS/OCL)` in the detailed view, or click `U1`, `U2`, or `TCR` in the compact view.
* **Server Sync:** Switch to the `SYNC` tab. Enter a full Job ID or shortened Server ID (`xxxx-xxxx`) and press Enter to synchronize live demand setpoints and timers.
* **Calibration Stepper:** Use the `-1s` / `+1s` calibration buttons in the sync tab to align countdown timers with actual server cycles.
* **Exit Application:** Click the `X` button in the header bar, or right-click the system tray icon and select Exit.

---

## Web Application Routes

| Route | Description |
| :--- | :--- |
| `/` | Landing page introducing features, guides, and download links. |
| `/calculator` | In-browser Thermal Power, APRM & Regression Model Calculator with server auto-sync. |
| `/points` | Points & Rank Calculator for shift earnings and goal progression. |
| `/tablet` | Real-time web recreation of the in-game Operator Tablet. |
| `/servers` | Server Browser with search, pagination, and grid analytics. |
| `/servers/<job_id>` | Historical snapshot graphs, operational logs, and score breakdown. |
| `/api/servers/<job_id>/score_breakdown` | JSON API endpoint returning comprehensive top score breakdown. |
| `/points-graph` | Client-side visualizer for local `sar_data.json` logs. |
| `/tickets` | Support ticket & community feedback center with Discord OAuth2 sign-in and ticket chat threads. |
| `/admin` | Administrative portal for persistent tracking, ticket management, and server moderation. |

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

All polynomial regression models (`UNIT_1_REGRESSION_MODELS` and `UNIT_2_REGRESSION_MODELS`) are imported directly from the [RBWR Operation Reference Google Sheet](https://docs.google.com/spreadsheets/d/1Izstp_2PZhQNmFyyr_5Una5GCcLBhgORVTX-CMkse2I/). The calculation engine evaluates these curves to map core thermal power ($t$, in % RTP/APRM) to generator load ($TGL$, in MWe), feedwater flow ($FWF$, in kg/s), and turbine auxiliary valves, solving iteratively with dynamic recirculation pump auxiliary usage ($u$, in MWe) to satisfy net demand ($d$, in MWe) where $TGL(t) = d + u$:

### Unit 1 (Quadratic Models: $y = ax^2 + bx + c$)
* **Turbine Generator Load (`TGL`, MWe):**
  $$TGL = \max\left(0,\; 0.00539683 \times t^2 + 12.99801221 \times t - 135.3540904\right)$$
* **Feedwater Flow (`FWF`, kg/s):**
  $$FWF = \max\left(0,\; 0.00588645 \times t^2 + 13.73489499 \times t + 105.928083\right)$$
* **Additional Unit 1 Regression Models:** `TCV` (Turbine Control Valve %), `CRP` (Condenser Recirculation Pump %), `DIO Intake` (Deaerator Intake %), and `DIO Output` (Deaerator Output %).

### Unit 2 & TCR (Cubic Models: $y = ax^3 + bx^2 + cx + d$)
* **Turbine Generator Load (`TGL`, MWe):**
  $$TGL = \max\left(0,\; -1.03199 \times 10^{-6} t^3 + 0.00551084 t^2 + 12.99032508 t - 135.0562436\right)$$
* **Feedwater Flow (`FWF`, kg/s):**
  $$FWF = \max\left(0,\; 0.000500711 t^3 - 0.06112934 t^2 + 15.90900097 t + 101.8426385\right)$$
* **Main Steam Sealing (`MSS`, % — Negative = Supply Valve %, Positive = Leak-Off Valve %):**
  $$MSS = 1.37370 \times 10^{-5} t^3 - 0.00464052 t^2 + 1.60987673 t - 41.59191606$$
* **Oil Cooling (`OCL`, % — Cold Water minus Hot Water valve %):**
  $$OCL = 7.57023 \times 10^{-5} t^3 - 0.01113141 t^2 + 1.52927531 t - 29.78538012$$
* **Additional Unit 2 Regression Models:** `TCV` (Turbine Control Valve %), `CRP` (Condenser Recirculation Pump %), `SJAE` (Steam Jet Air Ejector %), `DIO Intake` (Deaerator Intake %), `DIO Output` (Deaerator Output %), `OCV` (Oil Cooler Valve %), and `MCV` (Motor Coolant Valve %).

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