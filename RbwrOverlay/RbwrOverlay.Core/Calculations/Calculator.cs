using System.Globalization;

namespace RbwrOverlay.Core.Calculations;

public class Calculator
{
    public double Usage { get; set; }
    public int SelectedUnit { get; set; } = 1;
    public double? RecircOverride { get; set; }

    public UsageCalculator UsageCalc1 { get; }
    public UsageCalculator UsageCalc2 { get; }

    public Calculator(double usage = 61.32)
    {
        Usage = usage;
        UsageCalc1 = new UsageCalculator(1);
        UsageCalc2 = new UsageCalculator(2);
    }

    public void SetUsage(string valStr)
    {
        if (double.TryParse(valStr, NumberStyles.Any, CultureInfo.InvariantCulture, out double val))
        {
            Usage = val < 0 ? 0.0 : val;
        }
        else
        {
            Usage = 61.32;
        }
    }

    public double CalcFlow(double thermal)
    {
        if (SelectedUnit == 1)
        {
            return Math.Max(0.0, 82.8 + (13.7 * thermal) + (5.87e-3 * (thermal * thermal))) + 2.0;
        }
        else
        {
            return Math.Max(0.0, 160.0 + (11.6 * thermal) + (0.0249 * (thermal * thermal))) + 2.0;
        }
    }

    public double CalcGenLoad(double thermal)
    {
        if (SelectedUnit == 1)
        {
            return Math.Max(0.0, -135.0 + (13.0 * thermal) + (5.33e-3 * (thermal * thermal)));
        }
        else
        {
            return Math.Max(0.0, -82.3 + (10.9 * thermal) + (0.0238 * (thermal * thermal)));
        }
    }

    public double CalcThermal(double demand)
    {
        double currentUsage = Usage;
        double thermal = 0.0;

        for (int i = 0; i < 5; i++)
        {
            if (SelectedUnit == 1)
            {
                double inner = 169.0 + 0.02132 * (demand + 135.0 + currentUsage);
                thermal = (inner < 0) ? 0.0 : Math.Max(0.0, (-13.0 + Math.Sqrt(inner)) / 0.01066);
            }
            else
            {
                double inner = 118.81 + 0.0952 * (82.3 + demand + currentUsage);
                thermal = (inner < 0) ? 0.0 : Math.Max(0.0, (-10.9 + Math.Sqrt(inner)) / 0.0476);
            }

            double flow = CalcFlow(thermal);
            UsageCalculator uCalc = (SelectedUnit == 1) ? UsageCalc1 : UsageCalc2;
            currentUsage = uCalc.CalculateUsage(flow, thermal, RecircOverride);
        }

        Usage = currentUsage;
        return thermal;
    }
}