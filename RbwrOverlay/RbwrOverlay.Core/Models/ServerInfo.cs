using System.Text.Json;
using System.Text.Json.Serialization;

namespace RbwrOverlay.Core.Models;

public class UnitState
{
    public double? DemandTimeLeft { get; set; }
    public double? Demand { get; set; }
    public double? NextDemand { get; set; }
    public double? TurbineHealth { get; set; }

    public static UnitState FromJsonElement(JsonElement element)
    {
        var result = new UnitState();
        if (element.ValueKind != JsonValueKind.Object)
            return result;

        if (TryGetDoubleProperty(element, out double dtl, "Demand Time Left", "dtl", "demand_time_left", "DemandTimeLeft"))
            result.DemandTimeLeft = dtl;

        if (TryGetDoubleProperty(element, out double demand, "DemandU1", "DemandU2", "Demand", "demand", "demand_u1", "demand_u2"))
            result.Demand = demand;

        if (TryGetDoubleProperty(element, out double nextDemand, "NextDemandU1", "NextDemandU2", "Next Demand", "next_demand", "NextDemand", "nextDemand"))
            result.NextDemand = nextDemand;

        if (TryGetDoubleProperty(element, out double turbineHealth, "TurbineHealth", "Turbine Health", "turbine_health", "Turbine_Health", "turbineHealth"))
            result.TurbineHealth = turbineHealth;

        return result;
    }

    private static bool TryGetDoubleProperty(JsonElement element, out double value, params string[] propertyNames)
    {
        value = 0.0;
        foreach (var name in propertyNames)
        {
            if (element.TryGetProperty(name, out var prop))
            {
                if (prop.ValueKind == JsonValueKind.Number && prop.TryGetDouble(out value))
                    return true;
                if (prop.ValueKind == JsonValueKind.String && double.TryParse(prop.GetString(), System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out value))
                    return true;
            }
        }
        return false;
    }
}

public class ServerInfo
{
    public string JobId { get; set; } = string.Empty;
    public string Id { get; set; } = string.Empty;
    public string LastHeartbeat { get; set; } = string.Empty;
    public DateTimeOffset? HeartbeatTimestamp { get; set; }
    public UnitState? Unit1 { get; set; }
    public UnitState? Unit2 { get; set; }

    public static ServerInfo FromJsonElement(JsonElement element)
    {
        var server = new ServerInfo();
        if (element.ValueKind != JsonValueKind.Object)
            return server;

        if (element.TryGetProperty("jobId", out var jProp) && jProp.ValueKind == JsonValueKind.String)
            server.JobId = jProp.GetString() ?? string.Empty;

        if (element.TryGetProperty("id", out var idProp) && idProp.ValueKind == JsonValueKind.String)
            server.Id = idProp.GetString() ?? string.Empty;

        if (string.IsNullOrEmpty(server.JobId) && !string.IsNullOrEmpty(server.Id))
            server.JobId = server.Id;
        if (string.IsNullOrEmpty(server.Id) && !string.IsNullOrEmpty(server.JobId))
            server.Id = server.JobId;

        if (element.TryGetProperty("lastHeartbeat", out var hbProp) && hbProp.ValueKind == JsonValueKind.String)
        {
            server.LastHeartbeat = hbProp.GetString() ?? string.Empty;
            if (DateTimeOffset.TryParse(server.LastHeartbeat, out var dto))
            {
                server.HeartbeatTimestamp = dto;
            }
        }

        if (element.TryGetProperty("state", out var stateProp) && stateProp.ValueKind == JsonValueKind.Object)
        {
            if (stateProp.TryGetProperty("Unit1", out var u1Prop))
                server.Unit1 = UnitState.FromJsonElement(u1Prop);
            if (stateProp.TryGetProperty("Unit2", out var u2Prop))
                server.Unit2 = UnitState.FromJsonElement(u2Prop);
        }

        return server;
    }

    public List<string> ValidateSync()
    {
        var missing = new List<string>();
        if (Unit1 == null && Unit2 == null)
        {
            missing.Add("Server state payload empty");
            return missing;
        }

        if (Unit1 == null)
        {
            missing.Add("Unit1 state");
        }
        else
        {
            if (!Unit1.DemandTimeLeft.HasValue) missing.Add("Unit1.Demand Time Left");
            if (!Unit1.Demand.HasValue) missing.Add("Unit1.Demand");
            if (!Unit1.NextDemand.HasValue) missing.Add("Unit1.NextDemand");
        }

        if (Unit2 == null)
        {
            missing.Add("Unit2 state");
        }
        else
        {
            if (!Unit2.DemandTimeLeft.HasValue) missing.Add("Unit2.Demand Time Left");
            if (!Unit2.Demand.HasValue) missing.Add("Unit2.Demand");
            if (!Unit2.NextDemand.HasValue) missing.Add("Unit2.NextDemand");
        }

        return missing;
    }
}