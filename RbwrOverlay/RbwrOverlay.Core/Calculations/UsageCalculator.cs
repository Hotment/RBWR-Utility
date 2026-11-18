namespace RbwrOverlay.Core.Calculations;

public class UsageCalculator
{
    public int Unit { get; }
    public double FeedwaterUsage { get; }
    public double CondenserUsage { get; }
    public double CondenserCircUsage { get; }
    public double RecirculationUsage { get; }
    public double TowerMakeupUsage { get; }

    public UsageCalculator(int unit = 1)
    {
        Unit = unit;
        if (unit == 1)
        {
            FeedwaterUsage = 0.014;
            CondenserUsage = 0.007; // per kg
            CondenserCircUsage = 6.5;
            RecirculationUsage = 0.028;
            TowerMakeupUsage = 0.0;
        }
        else if (unit == 2)
        {
            FeedwaterUsage = 0.014;
            CondenserUsage = 3.5; // per pump
            CondenserCircUsage = 6.5;
            RecirculationUsage = 0.01;
            TowerMakeupUsage = 0.5;
        }
        else
        {
            throw new ArgumentException("Invalid unit number. Unit must be 1 or 2.", nameof(unit));
        }
    }

    public double AprmToRecircPumpSpeed(double aprm, double? currentAprm = null, double? currentRecirc = null)
    {
        var table = Unit == 2 ? RecirculationConstants.Unit2AprmToRecircTable : RecirculationConstants.Unit1AprmToRecircTable;
        double baseTarget = InterpolateTable(table, aprm);
        if (currentAprm.HasValue && currentRecirc.HasValue && currentAprm.Value > 5.0 && currentRecirc.Value >= 10.0)
        {
            double baseCur = InterpolateTable(table, currentAprm.Value);
            return Math.Clamp(currentRecirc.Value + (baseTarget - baseCur), 0.0, 100.0);
        }
        return baseTarget;
    }

    private static double InterpolateTable(IReadOnlyDictionary<int, double> table, double aprm)
    {
        var keys = table.Keys.OrderBy(k => k).ToArray();
        if (aprm <= keys[0])
        {
            return table[keys[0]];
        }
        if (aprm >= keys[^1])
        {
            return table[keys[^1]];
        }
        for (int i = 0; i < keys.Length - 1; i++)
        {
            int k0 = keys[i];
            int k1 = keys[i + 1];
            if (aprm >= k0 && aprm <= k1)
            {
                double t = (aprm - k0) / (k1 - k0);
                return table[k0] + t * (table[k1] - table[k0]);
            }
        }
        return table[keys[^1]];
    }

    public double CalculateUsage(double feedwaterFlow, double aprm, double? overrideSpeed = null, double? currentAprm = null, double? currentRecirc = null)
    {
        double feedwater = FeedwaterUsage * feedwaterFlow;
        double condenser = (Unit == 2) ? CondenserUsage : CondenserUsage * feedwaterFlow;
        double speed = overrideSpeed ?? AprmToRecircPumpSpeed(aprm, currentAprm, currentRecirc);
        double recirculation = RecirculationUsage * speed * 10.0; // 'speed' is in % 'recirculation' is in kg/s

        double totalUsage = feedwater + condenser + (CondenserCircUsage * 2.0) + recirculation;
        return Math.Round(totalUsage, 2);
    }
}