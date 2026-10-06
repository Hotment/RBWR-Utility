using RbwrOverlay.Core.Calculations;
using Xunit;

namespace RbwrOverlay.Tests;

public class CalculationTests
{
    [Theory]
    [InlineData(0.0)]
    [InlineData(100.0)]
    [InlineData(500.0)]
    [InlineData(1000.0)]
    [InlineData(1500.0)]
    public void TestUnit1BidirectionalConversion(double demand)
    {
        var calc = new Calculator(61.32) { SelectedUnit = 1 };
        double thermal = calc.CalcThermal(demand);
        double genLoad = calc.CalcGenLoad(thermal);
        double flow = calc.CalcFlow(thermal);
        double recalculatedDemand = Math.Max(0.0, Math.Round(genLoad - calc.Usage, 2));

        Assert.True(thermal >= 0.0);
        Assert.True(flow >= 0.0);

        if (demand > 0.0)
        {
            Assert.True(Math.Abs(demand - recalculatedDemand) <= 0.05,
                $"Deviation for Demand {demand}: Recalc={recalculatedDemand}");
        }
    }

    [Theory]
    [InlineData(0.0)]
    [InlineData(100.0)]
    [InlineData(500.0)]
    [InlineData(1000.0)]
    [InlineData(1500.0)]
    public void TestUnit2BidirectionalConversion(double demand)
    {
        var calc = new Calculator(61.32) { SelectedUnit = 2 };
        double thermal = calc.CalcThermal(demand);
        double genLoad = calc.CalcGenLoad(thermal);
        double flow = calc.CalcFlow(thermal);
        double recalculatedDemand = Math.Max(0.0, Math.Round(genLoad - calc.Usage, 2));

        Assert.True(thermal >= 0.0);
        Assert.True(flow >= 0.0);

        if (demand > 0.0)
        {
            Assert.True(Math.Abs(demand - recalculatedDemand) <= 2.0,
                $"Deviation for Demand {demand}: Recalc={recalculatedDemand}");
        }
    }

    [Fact]
    public void TestDynamicUsageIncreasesWithDemand()
    {
        var calc = new Calculator(61.32) { SelectedUnit = 1 };
        calc.CalcThermal(500.0);
        double usage500 = calc.Usage;

        calc.CalcThermal(1000.0);
        double usage1000 = calc.Usage;

        Assert.True(usage1000 > usage500, $"Expected usage at 1000 MW ({usage1000}) > usage at 500 MW ({usage500})");
    }

    [Fact]
    public void TestRecirculationOverride()
    {
        var calc = new Calculator(61.32) { SelectedUnit = 1, RecircOverride = null };
        double thermalDefault = calc.CalcThermal(1000.0);

        calc.RecircOverride = 60.0;
        double thermalOverride = calc.CalcThermal(1000.0);

        Assert.True(thermalDefault > 0.0);
        Assert.True(thermalOverride > 0.0);
        Assert.NotEqual(thermalDefault, thermalOverride);
    }
}