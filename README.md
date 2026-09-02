# RBWR Utility & APRM Transparent Overlay Calculator

A comprehensive suite of tools designed for the Roblox **Realistic Boiling Water Reactor (RBWR)** simulation. This project includes both a lightweight, always-on-top **Desktop Transparent Overlay Calculator** and a full-featured **Web Application & Server Suite** featuring real-time plant monitors, interactive graphs, points calculators, and server browsing.

---

## Table of Contents

- [Features](#features)
  - [Desktop Transparent Overlay](#desktop-transparent-overlay)
  - [Web Application & Server Suite](#web-application--server-suite)
- [Installation & Running](#installation--running)
  - [Pre-built Releases (Desktop)](#pre-built-releases-desktop)
  - [Running Desktop Overlay from Source](#running-desktop-overlay-from-source)
  - [Running the Web Application Server](#running-the-web-application-server)
- [Overlay Controls & Shortcuts](#overlay-controls--shortcuts)
- [Web Application Pages](#web-application-pages)
- [Configuration & Environment Variables](#configuration--environment-variables)
- [Feedback & Suggestions](#feedback--suggestions)
- [Calculation Reference](#calculation-reference)

---

## Features

### Desktop Transparent Overlay

* **Transparent Overlay:** Borderless, always-on-top window that sits seamlessly over your Roblox game window. Opacity is adjustable (from 30% to 100%) via the settings panel.
* **Dual UI Modes:** Toggle between a detailed view and a compact bar mode (465×60 px) that acts as an unobtrusive in-game HUD.
* **Automatic Updates via Official API:** Synchronizes target demand values, live server data, and countdown timers in real-time via official server checker API integration.
* **Job ID & Server ID Sync:** Connect directly using either a full Roblox Job ID (UUID) or the in-game shortened Server ID (e.g. `77f6-4b2f`), with built-in countdown calibration (+/- seconds).
* **Dynamic Usage Solver:** Runs an iterative solver to calculate thermal requirements while dynamically accounting for current auxiliary site usage (recirculation pumps, feedwater pumps, condenser pumps, etc.).
* **Overpower Safe Limit Alert:** Flashes a red warning indicator if the calculated core power exceeds safe operating thresholds (108% for both units).
* **Smart Roblox Focus Detection:** Automatically brings the overlay to the front when Roblox is focused and can hide/minimize when Roblox is not active.
* **System Tray & Hotkeys:** Minimizes to system tray with quick context menu controls.
* **Automatic Update Checking:** Checks GitHub Releases on startup to notify you when a new release is available.
* **Multi-Unit Layouts:** Dedicated calculations and settings for both Unit 1 and Unit 2.

### Web Application & Server Suite

* **Web Calculator (`/calculator`):** Full-featured in-browser APRM / thermal power calculator with real-time server synchronization.
* **Points & Rank Calculator (`/points`):** Comprehensive points-per-second, shift earnings, and operational rank requirements calculator.
* **Operator Tablet (`/tablet`):** Live in-browser recreation of the game's Operator Tablet displaying reactor temperatures, APRM setpoints, pump speeds, control rod status, and SCRAM alarms.
* **Server Browser (`/servers`):** Real-time monitoring of all public and private RBWR servers, with 20-servers-per-page pagination and search by full Job ID or shortened Server ID (`xxxx-xxxx`).
* **Grid Analytics:** Pan and zoom global total power output graphs across the entire RBWR grid with customizable time windows (10m, 30m, 1h, 6h, 24h, or all).
* **Server Detail & Graphs (`/servers/<job_id>`):** Interactive historical graphs (APRM, Power, Generator Load, Steam Flow, etc.) with touch, wheel zoom, and pan controls.
* **Point History Graph & Local Viewer (`/points-graph`):** 100% client-side private parser and graph visualizer for local `sar_data.json` logs. No data leaves your browser.
* **Community Suggestions (`/suggestions`):** Community proposal submission and upvoting board with administrator review statuses.
* **Admin Portal (`/admin`):** Secure panel for managing persistent server tracking, reviewing crash reports, user suggestions, and contact messages.

---

## Installation & Running

### Pre-built Releases (Desktop)

* **Windows:** Download the latest `RBWR_APRM_Calculator_vX.X.X.exe` or portable `.zip` from the [Releases](https://github.com/Hotment/RBWR-Utility/releases) page.
* **Linux (x86_64):** Download `RBWR_APRM_Calculator_Linux_x86_64_vX.X.X.tar.gz` or standalone binary from the [Releases](https://github.com/Hotment/RBWR-Utility/releases) page. Extract and run `./RBWR_APRM_Calculator`.
* **macOS (Apple Silicon - M1/M2/M3/M4):** Download `RBWR_APRM_Calculator_macOS_arm64.zip` from Releases. Extract the archive, then right-click `RBWR APRM Calculator.app` and select **Open** (required once on first launch for security approval).

---

### Running Desktop Overlay from Source

Running natively from source is supported across Windows, Linux, and macOS (Python 3.10+):

1. Clone or download the repository:
   ```bash
   git clone https://github.com/Hotment/RBWR-Utility.git
   cd RBWR-Utility
   ```
2. Install desktop dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   python rbwr_overlay.py
   ```

To compile your own standalone executable:
* **Windows (`.exe`):**
  ```cmd
  compile.bat
  ```
* **Linux (`standalone binary`):**
  ```bash
  chmod +x compile.sh
  ./compile.sh
  ```

---

### Running the Web Application Server

The Flask web server powers the website, web tools, live server cache, and APIs:

1. Install web server dependencies:
   ```bash
   pip install -r server/requirements.txt
   ```
2. Start the server:
   ```bash
   python server/app.py
   ```
3. Open your browser and navigate to:
   ```
   http://localhost:8400
   ```

To run in production with Gunicorn (Linux):
```bash
gunicorn -c server/gunicorn.conf.py server.app:app
```

---

## Overlay Controls & Shortcuts

* **Reposition Window:** Left-click and drag anywhere on the header bar or background panel.
* **Toggle Always-on-Top:** Click the pin icon (`📌` / `📍`) in the top-right corner.
* **Toggle Compact Mode:** Click the window expand/shrink icon (`⛶`) to switch to the minimal HUD bar. Double-clicking the compact bar background returns to detailed mode.
* **Adjust Opacity:** Open the configuration panel (gear icon) and adjust the transparency slider (30%–100%).
* **Toggle Unit:** Click the **UNIT 1** / **UNIT 2** tabs in detailed mode, or click the **U1** / **U2** indicator in compact mode.
* **Server Sync:** Click the sync/link icon in the header to open the server connection dialog. Enter a full Job ID or in-game Server ID (e.g. `77f6-4b2f`) to auto-sync reactor demand.
* **Exit Utility:** Click the `✕` button or right-click anywhere on the overlay to open the context menu and select Exit.

---

## Web Application Pages

| Route | Description |
|---|---|
| `/` | Landing page introducing features and download links. |
| `/calculator` | In-browser Thermal Power & APRM Calculator with server auto-sync. |
| `/points` | Points & Rank Calculator for shift earnings and goal progression. |
| `/tablet` | Web recreation of the in-game Operator Tablet with real-time plant parameters. |
| `/servers` | Server Browser with 20-per-page pagination and global power analytics. |
| `/servers/<job_id>` | Detailed graphs, reactor history, and snapshot metrics for a specific server. |
| `/points-graph` | Private, client-side Point History Graph & local `sar_data.json` log visualizer. |
| `/suggestions` | Community feedback board with submission form and upvoting. |
| `/contact` | Confidential direct contact form to the site administrator. |
| `/privacy` | Privacy policy and details on data handling. |
| `/admin` | Administrator portal for persistent server monitoring, crash reports, and suggestions moderation. |

---

## Configuration & Environment Variables

When running the web server (`server/app.py`), configuration can be customized via environment variables or a `.env` file in the `server/` directory:

| Variable | Default | Description |
|---|---|---|
| `SERVER_PORT` | `8400` | Port the web application listens on. |
| `HOST` | `0.0.0.0` | Host IP binding. |
| `ADMIN_USERNAME` | *(auto-generated)* | Administrator account username for `/admin`. |
| `ADMIN_PASSWORD` | *(auto-generated)* | Administrator account password for `/admin`. |
| `FLASK_SECRET_KEY` | *(auto-generated)* | Session encryption secret key. |
| `DISCORD_WEBHOOK_URL` | *(optional)* | Webhook for notifications on contact submissions and crash reports. |

---

## Feedback & Suggestions

I welcome your feedback and ideas! You can submit suggestions:
1. **Via the Desktop Overlay:** Click the **💬 Feedback** button in the title bar of the detailed view.
2. **Via the Web Application:** Visit the `/suggestions` page to post a new feature request or upvote existing ones.

---

## Calculation Reference

The calculator uses the following quadratic relationships to map core thermal power ($t$) to generator load and feedwater flow.

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