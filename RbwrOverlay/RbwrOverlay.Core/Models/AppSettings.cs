using System.Text.Json.Serialization;

namespace RbwrOverlay.Core.Models;

public class AppSettings
{
    [JsonPropertyName("usage")]
    public double Usage { get; set; } = 61.32;

    [JsonPropertyName("opacity")]
    public double Opacity { get; set; } = 0.90;

    [JsonPropertyName("ui_scale")]
    public double UiScale { get; set; } = 1.0;

    [JsonPropertyName("compact_ui_scale")]
    public double CompactUiScale { get; set; } = 1.0;

    [JsonPropertyName("selected_unit")]
    public int SelectedUnit { get; set; } = 1;

    [JsonPropertyName("is_compact")]
    public bool IsCompact { get; set; } = false;

    [JsonPropertyName("is_topmost")]
    public bool IsTopmost { get; set; } = true;

    [JsonPropertyName("topmost_on_roblox")]
    public bool TopmostOnRoblox { get; set; } = true;

    [JsonPropertyName("skipped_version")]
    public string SkippedVersion { get; set; } = string.Empty;

    [JsonPropertyName("next_demand_threshold_seconds")]
    public int NextDemandThresholdSeconds { get; set; } = 60;

    [JsonPropertyName("last_job_id")]
    public string LastJobId { get; set; } = string.Empty;

    [JsonPropertyName("dtl_calibration_offset")]
    public double DtlCalibrationOffset { get; set; } = 0.0;

    [JsonPropertyName("enable_turbine_health_alert")]
    public bool EnableTurbineHealthAlert { get; set; } = false;

    [JsonPropertyName("turbine_health_threshold")]
    public double TurbineHealthThreshold { get; set; } = 65.0;

    public static AppSettings CreateDefault() => new();
}