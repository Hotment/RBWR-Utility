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
            FeedwaterUsage = 0.013;
            CondenserUsage = 3.1850; // per pump
            CondenserCircUsage = 6.5;
            RecirculationUsage = 0.01;
            TowerMakeupUsage = 0.5;
        }
        else
        {
            throw new ArgumentException("Invalid unit number. Unit must be 1 or 2.", nameof(unit));
        }
    }

    public double AprmToRecircPumpSpeed(double aprm)
    {
        foreach (var key in RecirculationConstants.AprmToRecircTable.Keys.OrderBy(k => k))
        {
            if (key >= aprm)
            {
                return RecirculationConstants.AprmToRecircTable[key];
            }
        }
        return RecirculationConstants.AprmToRecircTable[RecirculationConstants.AprmToRecircTable.Keys.Max()];
    }

    public double CalculateUsage(double feedwaterFlow, double aprm, double? overrideSpeed = null)
    {
        double feedwater = FeedwaterUsage * feedwaterFlow;
        double condenser = (Unit == 2) ? CondenserUsage : CondenserUsage * feedwaterFlow;
        double speed = overrideSpeed ?? AprmToRecircPumpSpeed(aprm);
        double recirculation = RecirculationUsage * speed * 10.0;

        double totalUsage = feedwater + condenser + (CondenserCircUsage * 2.0) + recirculation;
        return Math.Round(totalUsage, 2);
    }
}