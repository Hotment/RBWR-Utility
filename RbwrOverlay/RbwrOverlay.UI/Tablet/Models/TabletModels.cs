using System.Globalization;
using System.Text.Json;

namespace RbwrOverlay.UI.Tablet.Models;

public enum FieldType { Number, String, Bool }

public sealed record FieldDef(string Label, string Key, FieldType Type = FieldType.Number, int Dp = 2, string? Suffix = null);

public sealed record TabletRow(string Label, string Value);

public sealed class TabletServer
{
    public string JobId { get; init; } = string.Empty;
    public string Id { get; init; } = string.Empty;
    public DateTimeOffset? Heartbeat { get; init; }
    public JsonElement Unit1 { get; init; }
    public JsonElement Unit2 { get; init; }
    public JsonElement Misc { get; init; }

    public static double? DemandTimeLeft(JsonElement unit) => Num(unit, "Demand Time Left");

    public static double? Num(JsonElement unit, string key)
    {
        if (unit.ValueKind != JsonValueKind.Object || !unit.TryGetProperty(key, out var p)) return null;
        if (p.ValueKind == JsonValueKind.Number) return p.GetDouble();
        if (p.ValueKind == JsonValueKind.String &&
            double.TryParse(p.GetString(), NumberStyles.Any, CultureInfo.InvariantCulture, out var d)) return d;
        return null;
    }

    public double? Aprm(JsonElement unit) =>
        unit.ValueKind == JsonValueKind.Object && unit.TryGetProperty("APRM", out var p) && p.ValueKind == JsonValueKind.Number
            ? p.GetDouble() : null;
}

public static class TabletFields
{
    public static readonly FieldDef[] Unit1 =
    {
        new("APRM", "APRM"), new("APRM Setpoint", "APRM Setpoint"), new("Avg. Rod", "Avg. Rod"),
        new("Reactor Temp", "Reactor Temp"), new("Reactor Level", "ReactorLevel"),
        new("Dea Level", "Deareator Level"), new("Hotwell Level", "Hotwell Level"),
        new("Xenon", "Xenon"), new("Iodine", "Iodine"), new("Vibrations", "Vibrations"),
        new("Pressure", "Pressure"), new("Turbine RPM", "Turbine RPM", Dp: 0),
        new("Demand", "DemandU1", Dp: 0), new("Next Demand", "NextDemandU1", Dp: 0),
        new("Demand Time Left", "Demand Time Left", Dp: 0),
        new("Last Scram Reason", "SCRAMreason", FieldType.String),
        new("Trip Reason", "TRIPreason", FieldType.String),
        new("Offsite Power", "Offsite Power", FieldType.Bool),
        new("Fuel Burn", "Fuel Burn (default 0.54)"),
        new("Points Per Second", "PointsPerSecond"),
    };

    public static readonly FieldDef[] Unit2 =
    {
        new("RTP", "RTP"), new("APRM Setpoint", "APRM Setpoint"), new("Avg. Rod", "Avg. Rod"),
        new("Reactor Temp", "Reactor Temp"), new("FWP 1 Temp", "FWP1 Temp"), new("FWP 2 Temp", "FWP2 Temp"),
        new("Reactor Level", "ReactorLevel"), new("Dea Level", "Deareator Level"),
        new("Hotwell Level", "Hotwell Level"), new("Xenon", "Xenon"), new("Iodine", "Iodine"),
        new("Disc Ruptured", "Disk Ruptured", FieldType.Bool), new("Vibrations", "Vibrations"),
        new("Pressure", "Pressure"), new("Turbine RPM", "Turbine RPM", Dp: 0),
        new("Turbine Health", "TurbineHealth", Dp: 0, Suffix: "%"),
        new("Generator Temp", "GeneratorTemperature"), new("Casing Temp", "CasingTemperature"),
        new("Diff Pressure", "DiffPressure", Dp: 4), new("Diesel RPM", "DieselRPM", Dp: 0),
        new("Demand", "DemandU2", Dp: 0), new("Next Demand", "NextDemandU2", Dp: 0),
        new("Demand Time Left", "Demand Time Left", Dp: 0),
        new("Last Scram Reason", "SCRAMreason", FieldType.String),
        new("Trip Reason", "TRIPreason", FieldType.String),
        new("Offsite Power", "Offsite Power", FieldType.Bool),
        new("Fuel Burn", "Fuel Burn (default 0.54)"),
        new("Points Per Second", "PointsPerSecond"),
    };

    public static readonly FieldDef[] Misc =
    {
        new("Outside Temperature", "Outside Temperature", Dp: 1),
        new("EDG Diesel Storage", "EDG Diesel Storage", Dp: 0),
        new("Evacuation Cooldown", "Evacuation Cooldown", Dp: 0),
        new("FSS Smoke Detected", "FSS Smoke Detected", FieldType.Bool),
        new("U2 FSS Force Repair", "U2 FSS Force Repair", FieldType.Bool),
        new("Total points/second", "Total points/second", Dp: 3),
    };

    public static string Format(FieldDef def, JsonElement unit)
    {
        if (unit.ValueKind != JsonValueKind.Object || !unit.TryGetProperty(def.Key, out var raw) ||
            raw.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined)
            return "N/A";

        switch (def.Type)
        {
            case FieldType.Number:
                double num;
                if (raw.ValueKind == JsonValueKind.Number) num = raw.GetDouble();
                else if (!double.TryParse(raw.ToString(), NumberStyles.Any, CultureInfo.InvariantCulture, out num)) return "N/A";

                if (def.Label.Contains("Demand") || def.Key.Contains("Demand"))
                {
                    if (num == -4) return "Evacuation";
                    if (num == -3) return "RST";
                    if (num == -2) return "LOOP";
                    if (num == -1) return "Maintenance";
                }
                return num.ToString("F" + def.Dp, CultureInfo.InvariantCulture) + def.Suffix;

            case FieldType.Bool:
                bool b = raw.ValueKind switch
                {
                    JsonValueKind.True => true,
                    JsonValueKind.False => false,
                    JsonValueKind.Number => raw.GetDouble() != 0,
                    JsonValueKind.String => !string.IsNullOrEmpty(raw.GetString()) &&
                                            !raw.GetString()!.Equals("false", StringComparison.OrdinalIgnoreCase),
                    _ => false
                };
                return b ? "TRUE" : "FALSE";

            default:
                var s = (raw.ValueKind == JsonValueKind.String ? raw.GetString() : raw.ToString())?.Trim();
                return string.IsNullOrEmpty(s) || s == "No Reason Given" ? "None" : s;
        }
    }
}
