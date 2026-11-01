namespace RbwrOverlay.UI;

public sealed record TooltipItem(string Title, string Description);

/// <summary>
/// Central catalog for all hover tooltips across the RBWR Overlay UI.
/// Modify any Title or Description string in <see cref="Items"/> below to customize hover notes.
/// </summary>
public static class TooltipCatalog
{
    public static bool IsEnabled { get; private set; } = true;

    public static event Action? EnabledChanged;

    public static void SetEnabled(bool enabled)
    {
        if (IsEnabled == enabled) return;
        IsEnabled = enabled;
        EnabledChanged?.Invoke();
    }

    // =========================================================================
    // EDIT TOOLTIP TITLES AND DESCRIPTIONS BELOW
    // =========================================================================
    public static readonly Dictionary<string, TooltipItem> Items = new(StringComparer.OrdinalIgnoreCase)
    {
        // --- Window & Header Controls ---
        ["DragHandle"] = new(
            Title: "MOVE & TOGGLE HUD",
            Description: "Click and drag to move the overlay window. Double-click empty background space to toggle between Full HUD and Compact HUD."
        ),
        ["SyncBadge"] = new(
            Title: "SERVER SYNC STATUS",
            Description: "Shows whether the overlay is receiving live demand and countdown updates from an active RBWR server. Open the SERVER SYNC tab to connect."
        ),
        ["RecircBadge"] = new(
            Title: "RECIRCULATION OVERRIDE ACTIVE",
            Description: "Manual recirculation pump speed override is currently active and affecting auxiliary power calculations. Click OVR in Compact mode or Reset in CONFIG to return to auto."
        ),
        ["PinButton"] = new(
            Title: "ALWAYS ON TOP",
            Description: "Click to pin or unpin the overlay window above other applications. Can also be automated when Roblox is focused via CONFIG."
        ),
        ["CompactButton"] = new(
            Title: "COMPACT PILL HUD",
            Description: "Minimizes the window into a compact floating bar for minimal screen footprint while operating."
        ),
        ["ExpandButton"] = new(
            Title: "EXPAND FULL HUD",
            Description: "Restores the full overlay interface with demand presets, server sync controls, and configuration settings."
        ),
        ["QuitButton"] = new(
            Title: "EXIT APPLICATION",
            Description: "Closes RBWR Overlay and saves your current configuration."
        ),

        // --- Navigation Tabs ---
        ["TabMonitor"] = new(
            Title: "REACTOR & TCR MONITOR",
            Description: "Main operational calculator for Unit 1 (APRM), Unit 2 (RTP), and Unit 2 Turbine Control Room (MSS & OCL)."
        ),
        ["TabSync"] = new(
            Title: "LIVE SERVER SYNC",
            Description: "Connect to an active public RBWR server to automatically track grid demand, upcoming demand countdowns (DTL), and turbine health."
        ),
        ["TabSettings"] = new(
            Title: "HUD CONFIGURATION",
            Description: "Customize window opacity, UI scaling, hover tooltips, recirculation speed overrides, DTL pre-load timing, and alarms."
        ),
        ["TabFeedback"] = new(
            Title: "COMMUNITY & UPDATES",
            Description: "Open the bug/feature tickets portal, linking to the Discord community, and allowing you to check for software updates."
        ),

        // --- Unit & Section Selectors ---
        ["Unit1"] = new(
            Title: "UNIT 01 (APRM MODE)",
            Description: "Switches calculations and live server sync to Unit 1 using Unit 1 quadratic regression models (APRM %, Gross MWe, and Feedwater Flow)."
        ),
        ["Unit2"] = new(
            Title: "UNIT 02 (RTP MODE)",
            Description: "Switches calculations and live server sync to Unit 2 using Unit 2 cubic regression models (RTP %, Gross MWe, and Feedwater Flow)."
        ),
        ["Tcr"] = new(
            Title: "TURBINE CONTROL ROOM (TCR)",
            Description: "Switches to Unit 2 TCR view showing Main Steam Sealing (MSS %) and Oil Cooling (OCL %) setpoints alongside Steam Flow and Gross MWe."
        ),

        // --- Monitor Inputs & Presets ---
        ["DemandInput"] = new(
            Title: "NET GRID DEMAND (MWe)",
            Description: "Enter the target net electrical demand in MWe. The overlay automatically accounts for station auxiliary usage to compute exact setpoints."
        ),
        ["DemandAdjustMinus50"] = new(
            Title: "DECREASE DEMAND (-50 MW)",
            Description: "Click to step the target grid demand down by 50 MWe."
        ),
        ["DemandAdjustMinus10"] = new(
            Title: "DECREASE DEMAND (-10 MW)",
            Description: "Click to step the target grid demand down by 10 MWe."
        ),
        ["DemandAdjustPlus10"] = new(
            Title: "INCREASE DEMAND (+10 MW)",
            Description: "Click to step the target grid demand up by 10 MWe."
        ),
        ["DemandAdjustPlus50"] = new(
            Title: "INCREASE DEMAND (+50 MW)",
            Description: "Click to step the target grid demand up by 50 MWe."
        ),
        ["DemandSlider"] = new(
            Title: "DEMAND SETPOINT SLIDER",
            Description: "Drag to adjust net generator demand in 10 MW increments, or click the quick-snap MW buttons below."
        ),
        ["DemandPresetTick"] = new(
            Title: "QUICK DEMAND PRESET",
            Description: "Click to immediately snap the demand calculator to this MWe setpoint."
        ),
        ["RtpInput"] = new(
            Title: "CORE THERMAL POWER (%)",
            Description: "Bidirectional solver: type any APRM / RTP percentage here to reverse-calculate the resulting Net Demand, Gross MWe, Flow, MSS, and OCL."
        ),

        // --- Mode-Aware Monitor Readouts (Detailed & Compact) ---
        ["MainBannerReactor"] = new(
            Title: "TARGET CORE THERMAL POWER",
            Description: "Required reactor thermal power (APRM / RTP %) to satisfy net grid demand plus auxiliary station load. Turns red above 108% overpower SCRAM limit."
        ),
        ["MainBannerTcr"] = new(
            Title: "MAIN STEAM SEALING (MSS %)",
            Description: "Target Unit 2 Main Steam Sealing setpoint (%). Negative values indicate the required Supply Valve opening (with Leak-Off at 0%), while positive values indicate the required Leak-Off Valve opening (with Supply at 0%)."
        ),
        ["DetailedLoadReactor"] = new(
            Title: "GROSS GENERATOR LOAD",
            Description: "Required gross electrical output (MWe) at the generator terminals (Net Grid Demand + Station Auxiliary Usage)."
        ),
        ["DetailedLoadTcr"] = new(
            Title: "OIL COOLING (OCL %)",
            Description: "Required difference between Cold Water and Hot Water valves (Cold Water - Hot Water). Positive values mean opening Cold Water; negative values mean opening Hot Water (e.g. -40% means Hot Water open to 40% and Cold Water at 0%)."
        ),
        ["DetailedFlowReactor"] = new(
            Title: "FEEDWATER FLOW",
            Description: "Required feedwater mass flow rate (kg/s) to match steam generation and keep reactor vessel water level steady."
        ),
        ["DetailedFlowTcr"] = new(
            Title: "MAIN STEAM FLOW",
            Description: "Estimated mass flow rate (kg/s) of steam/feedwater at the current Unit 2 thermal power level."
        ),
        ["UpcomingDemand"] = new(
            Title: "UPCOMING GRID DEMAND",
            Description: "Displays the next scheduled grid demand or special event (Maint, LOOP, RST, Evac) reported by live server sync."
        ),
        ["DetailedBottomReactor"] = new(
            Title: "STATION AUXILIARY USAGE",
            Description: "Estimated internal plant power consumption (MWe) drawn by feedwater, condenser, and core recirculation pumps."
        ),
        ["DetailedBottomTcr"] = new(
            Title: "GROSS GENERATOR LOAD",
            Description: "Required gross electrical output (MWe) for Unit 2 at the current demand setpoint."
        ),
        ["CompactPrimaryReactor"] = new(
            Title: "CORE POWER & FLOW",
            Description: "Top: Target reactor thermal power (APRM / RTP %). Bottom: Target feedwater / steam mass flow rate in kg/s."
        ),
        ["CompactPrimaryTcr"] = new(
            Title: "MSS & STEAM FLOW",
            Description: "Top: Main Steam Sealing (negative = Supply Valve %, positive = Leak-Off Valve %). Bottom: Steam / feedwater mass flow rate in kg/s."
        ),
        ["CompactSecondaryReactor"] = new(
            Title: "GROSS MWe & AUX USAGE",
            Description: "Top: Required gross generator load (MWe). Bottom: Estimated station auxiliary power usage (MWe)."
        ),
        ["CompactSecondaryTcr"] = new(
            Title: "OCL & GROSS MWe",
            Description: "Top: Oil Cooling difference (Cold Water - Hot Water %, e.g. -40% = Hot Water at 40%). Bottom: Required gross generator load (MWe)."
        ),

        // --- Compact Sync Counter States ---
        ["CompactCounterCountdown"] = new(
            Title: "DEMAND TIME LEFT (DTL)",
            Description: "Live countdown until the next grid demand change. Click to toggle this readout to show the Upcoming Demand MW target."
        ),
        ["CompactCounterNextDemand"] = new(
            Title: "UPCOMING DEMAND TARGET",
            Description: "Next scheduled demand setpoint or plant event. Click to switch back to the Demand Time Left (DTL) countdown."
        ),
        ["CompactCounterUnsynced"] = new(
            Title: "NOT SYNCED TO SERVER",
            Description: "No live server connected. Expand Full HUD and open SERVER SYNC to connect via Job ID, or click to toggle display mode."
        ),
        ["CompactCounterRetrying"] = new(
            Title: "RECONNECTING TO SERVER",
            Description: "Connection to the server API was interrupted. Automatically retrying..."
        ),
        ["CompactCounterError"] = new(
            Title: "SERVER SYNC WARNING",
            Description: "Unable to sync with the selected server. Open the SERVER SYNC tab in Full HUD for details."
        ),

        // --- Server Sync Tab ---
        ["SyncNowButton"] = new(
            Title: "SYNC WITH SERVER",
            Description: "Connects to the entered Roblox Job ID or short server code and pulls live demand, upcoming demand, and turbine health."
        ),
        ["JobIdInput"] = new(
            Title: "SERVER JOB ID / SHORT CODE",
            Description: "Type or select an active Roblox Job ID or short ID (e.g. 77f6-4b2f) from the dropdown list, then click Sync Now."
        ),
        ["DtlPanel"] = new(
            Title: "DEMAND TIME LEFT (DTL)",
            Description: "Tracks seconds remaining until the next demand change. Automatically pre-loads upcoming demand when reaching your configured switch timer."
        ),
        ["CalibStepButton"] = new(
            Title: "CALIBRATE DTL TIMER",
            Description: "Nudges the local countdown clock forward or backward to compensate for network delay and match the in-game board."
        ),
        ["CalibCustomInput"] = new(
            Title: "EXACT DTL CALIBRATION",
            Description: "Enter the exact seconds currently shown on the in-game demand timer and click Set to synchronize immediately."
        ),
        ["TurbineHealthPanel"] = new(
            Title: "TURBINE HEALTH MONITOR",
            Description: "Displays live turbine health condition (%) from synced server state. Configure low-health alerts in the CONFIG tab."
        ),

        // --- Config Tab ---
        ["HudOpacity"] = new(
            Title: "WINDOW OPACITY",
            Description: "Drag to adjust overall HUD transparency between 20% and 100%."
        ),
        ["FullHudScale"] = new(
            Title: "FULL HUD UI SCALE",
            Description: "Resizes the expanded Full HUD window. Drag the slider and release, or click a preset percentage button."
        ),
        ["CompactHudScale"] = new(
            Title: "COMPACT MODE UI SCALE",
            Description: "Independently resizes the Compact Pill HUD without changing the Full HUD size."
        ),
        ["HoverTooltipsToggle"] = new(
            Title: "HOVER HELP TOOLTIPS",
            Description: "Click to enable or disable popup help notes when hovering over controls and readouts."
        ),
        ["RobloxTopmostToggle"] = new(
            Title: "AUTO-TOPMOST ON ROBLOX",
            Description: "When enabled, automatically keeps the overlay on top while Roblox is in the foreground and lets other windows cover it when you tab out. (May be a bit buggy)"
        ),
        ["RecircOverrideConfig"] = new(
            Title: "MANUAL RECIRCULATION OVERRIDE",
            Description: "Enter a fixed recirculation pump speed (0-100%) if not following the standard APRM curve (e.g. When running the reacotr in Self-Circ mode), or click Reset for automatic speed."
        ),
        ["NextDemandTimerConfig"] = new(
            Title: "NEXT DEMAND PRE-LOAD TIMER",
            Description: "Number of seconds left on DTL when the overlay automatically switches its calculator to the upcoming demand setpoint."
        ),
        ["TurbineAlarmConfig"] = new(
            Title: "TURBINE HEALTH ALARM",
            Description: "Triggers a warning popup when synced turbine health drops at or below the specified threshold percentage."
        ),
        ["OpenLogButton"] = new(
            Title: "DIAGNOSTIC LOG FILE",
            Description: "Opens the local application log file to inspect sync events and troubleshooting details."
        ),

        // --- Feedback & Updates Tab ---
        ["OpenTicketsButton"] = new(
            Title: "ONLINE TICKETS PORTAL",
            Description: "Opens rbwr.hotment.dev/tickets in your web browser to submit bug reports or feature requests."
        ),
        ["JoinDiscordButton"] = new(
            Title: "DISCORD COMMUNITY",
            Description: "Opens the RBWR Utility Discord invite in your browser for support, updates, and discussion."
        ),
        ["CheckUpdatesButton"] = new(
            Title: "CHECK FOR UPDATES",
            Description: "Queries for the latest RBWR Overlay release and offers one-click download and installation if a newer build exists."
        ),
    };

    public static TooltipItem? Get(string? key)
    {
        if (!IsEnabled || string.IsNullOrWhiteSpace(key))
        {
            return null;
        }

        return Items.TryGetValue(key, out var item) ? item : null;
    }

    public static TooltipItem? Custom(string title, string description)
    {
        if (!IsEnabled)
        {
            return null;
        }

        return new TooltipItem(title, description);
    }
}