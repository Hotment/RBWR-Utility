# RBWR APRM Transparent Overlay Calculator

A transparent desktop overlay tool designed for the Roblox **Realistic Boiling Water Reactor (RBWR)** simulation. This utility calculates Reactor Thermal Power (RTP% / APRM) and other essential values from MWt demand (and vice-versa) in real-time, directly on your screen while playing.

---

## Features

*   **Transparent Overlay:** Borderless, always-on-top window that sits on top of your Roblox game. Opacity is adjustable (from 30% to 100%) via a configuration slider.
*   **Dual UI Modes:** Toggle between a detailed telemetry view and a compact bar mode (465x60 px) that acts as a minimal in-game HUD.
*   **Automatic Updates via Official API:** Automatically synchronizes target demand values, server telemetry, and demand time left countdowns in real-time directly via official server checker API integration.
*   **Dynamic Usage Solver:** Runs a 5-step iterative solver to calculate thermal requirements while dynamically accounting for current auxiliary site usage (recirculation pumps, feedwater pumps, condenser pumps, etc.).
*   **Overpower Safe Limit Alert:** Flashes a red warning indicator if the calculated core power goes above safe limits (108% for both units).
*   **Multi-Unit Layouts:** Dedicated calculations and settings for both Unit 1 and Unit 2.

---

## Installation & Running

The overlay requires Python 3.10+ and uses lightweight external libraries for GUI rendering.

1. Clone or download the repository files.
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   python rbwr_overlay.py
   ```

### Pre-built Releases

* **Windows:** Download the latest `RBWR_APRM_Calculator_vX.X.X.exe` or portable `.zip` from the [Releases](https://github.com/Hotment/rbwr_themal_calculator/releases) page.
* **macOS (Apple Silicon - M1/M2/M3/M4):** Download `RBWR_APRM_Calculator_macOS_arm64.zip` from Releases. Extract the archive, then right-click `RBWR APRM Calculator.app` and select **Open** (required once on first launch for security approval).

---

### Running from Source (Windows, Linux & macOS)

Running the application **natively from source** is fully supported across Windows, Linux, and macOS (both Apple Silicon and Intel):

1. Clone or download the repository files.
2. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   python rbwr_overlay.py
   ```

*Note for Intel Mac users: Intel Macs can run the application directly from source using the steps above.*
*Note for Linux users: Running natively is strongly recommended over Wine to avoid Wayland compositing and window transparency issues.*

To compile your own Windows executable (`rbwr_overlay.exe`), run:
```cmd
compile.bat
```

---

## Overlay Controls

*   **Reposition Window:** Left-click and hold anywhere on the title bar or background panel, then drag.
*   **Toggle Always-on-Top:** Click the pin icon (`📌` / `📍`) in the top right.
*   **Toggle Compact Mode:** Click the window icon (`⛶`) to shrink the UI to a tiny HUD. Double-clicking the compact bar background also returns the window to detailed mode.
*   **Adjust Opacity:** Open the configuration panel (gear icon) and adjust the transparency slider.
*   **Toggle Unit:** Click the **UNIT 1** / **UNIT 2** buttons in detailed mode, or the **U1** / **U2** badges in compact mode.
*   **Exit Utility:** Click the `✕` button or right-click the overlay to select Exit from the context menu.

---

## Feedback & Suggestions

I welcome your feedback and ideas for new features! You can submit suggestions directly within the overlay window:
1. Open the detailed telemetry view.
2. Click the **💬 Feedback** button in the top title bar.
3. Fill out the dialog (submissions can be named or entirely anonymous) and click Submit.

*Note: To prevent spam, the update server enforces a rate limit of 1 submission per 12 hours per IP address.*

---

## Calculation Reference

The calculator uses the following quadratic relationships to map core thermal power ($t$) to generator load and feedwater flow.

### Unit 1
*   **Thermal Power (%)** from Demand ($d$) and current auxiliary usage ($u$):
    $$t = \max\left(0, \frac{-13 + \sqrt{169 + 0.02132 \times (d + 135 + u)}}{0.01066}\right)$$
*   **Generator Load (MWe):**
    $$GenLoad = \max\left(0, -135 + 13 \times t + 5.33 \times 10^{-3} \times t^2\right)$$
*   **Feedwater Flow (kg/s):**
    $$Flow = \max\left(0, 82.8 + 13.7 \times t + 5.87 \times 10^{-3} \times t^2\right) + 2$$

### Unit 2
*   **Thermal Power (%)** from Demand ($d$) and current auxiliary usage ($u$):
    $$t = \max\left(0, \frac{-10.9 + \sqrt{118.81 + 0.0952 \times (82.3 + d + u)}}{0.0476}\right)$$
*   **Generator Load (MWe):**
    $$GenLoad = \max\left(0, -82.3 + 10.9 \times t + 0.0238 \times t^2\right)$$
*   **Feedwater Flow (kg/s):**
    $$Flow = \max\left(0, 160.0 + 11.6 \times t + 0.0249 \times t^2\right) + 2$$
