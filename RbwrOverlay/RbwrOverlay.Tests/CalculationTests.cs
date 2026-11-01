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

    [Fact]
    public void TestTcrMssAndOclCalculations()
    {
        var calc = new Calculator(61.32) { SelectedUnit = 3 };
        Assert.Equal(0.0, calc.CalcMss(0.0));
        Assert.Equal(0.0, calc.CalcOcl(0.0));

        double thermal100 = 100.0;
        double mss = calc.CalcMss(thermal100);
        double ocl = calc.CalcOcl(thermal100);

        Assert.InRange(mss, 86.0, 87.5);
        Assert.InRange(ocl, 87.0, 88.0);
    }

    [Fact]
    public void TestPastedPythonRegressionModelsAreParsedAndUsed()
    {
        Assert.True(Calculator.DefaultUnit1Models.ContainsKey("FWF"));
        Assert.True(Calculator.DefaultUnit1Models.ContainsKey("TGL"));
        Assert.True(Calculator.DefaultUnit2Models.ContainsKey("FWF"));
        Assert.True(Calculator.DefaultUnit2Models.ContainsKey("TGL"));
        Assert.True(Calculator.DefaultUnit2Models.ContainsKey("MSS"));
        Assert.True(Calculator.DefaultUnit2Models.ContainsKey("OCL"));

        const string customModels = """
UNIT_1_REGRESSION_MODELS: dict[str, dict[str, Any]] = {
    "FWF": {
        "name": "Feedwater Flow",
        "unit": "kg/s",
        "type": "quadratic",
        "a": 0.0,
        "b": 10.0,
        "c": 100.0,
        "equation": "y = 10x + 100",
    },
    "TGL": {
        "name": "Turbine Generator Load",
        "unit": "MWe",
        "type": "quadratic",
        "a": 0.0,
        "b": 12.0,
        "c": -100.0,
        "equation": "y = 12x - 100",
    },
}

UNIT_2_REGRESSION_MODELS: dict[str, dict[str, Any]] = {
    "MSS": {
        "name": "Main Steam Sealing",
        "unit": "%",
        "type": "cubic",
        "a": 0.0,
        "b": 0.0,
        "c": 0.5,
        "d": 10.0,
        "equation": "y = 0.5x + 10",
    },
}
""";

        var calc = new Calculator(61.32) { SelectedUnit = 1 };
        calc.LoadRegressionModels(customModels);

        Assert.Equal(600.0, calc.CalcFlow(50.0), 3);
        Assert.Equal(500.0, calc.CalcGenLoad(50.0), 3);

        calc.SelectedUnit = 3;
        Assert.Equal(35.0, calc.CalcMss(50.0), 3);
    }
}