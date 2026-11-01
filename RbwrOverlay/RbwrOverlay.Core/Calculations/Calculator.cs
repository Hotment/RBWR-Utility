using System.Globalization;
using System.Text.RegularExpressions;

namespace RbwrOverlay.Core.Calculations;

public sealed record RegressionModel(
    string Key,
    string Name,
    string Unit,
    string Type,
    double A,
    double B,
    double C,
    double D,
    string Equation);

public class Calculator
{
    public const string RegressionModelsSource = """
# =========================================================================
# REGRESSION MODEL EQUATIONS
# Unit 1: Quadratic (y = a*x^2 + b*x + c)
# Unit 2: Cubic (y = a*x^3 + b*x^2 + c*x + d)
# Parameter x = Core RTP / APRM (%)
# =========================================================================

UNIT_1_REGRESSION_MODELS: dict[str, dict[str, Any]] = {
    "FWF": {
        "name": "Feedwater Flow",
        "unit": "kg/s",
        "type": "quadratic",
        "a": 0.005886446886,
        "b": 13.73489499,
        "c": 105.928083,
        "equation": "y = 0.0059x^2 + 13.7349x + 105.9281",
    },
    "TCV": {
        "name": "Turbine Control Valve",
        "unit": "%",
        "type": "quadratic",
        "a": -0.00118974359,
        "b": 0.935565812,
        "c": 5.905726496,
        "equation": "y = -0.0012x^2 + 0.9356x + 5.9057",
    },
    "CRP": {
        "name": "Condenser Recirculation Pump",
        "unit": "%",
        "type": "quadratic",
        "a": -8.805860806e-05,
        "b": 0.7933676679,
        "c": 6.818485958,
        "equation": "y = -0.0001x^2 + 0.7934x + 6.8185",
    },
    "DIO Intake": {
        "name": "Deaerator Intake",
        "unit": "%",
        "type": "quadratic",
        "a": 0.006874236874,
        "b": -1.526903541,
        "c": 98.06593407,
        "equation": "y = 0.0069x^2 - 1.5269x + 98.0659",
    },
    "DIO Output": {
        "name": "Deaerator Output",
        "unit": "%",
        "type": "quadratic",
        "a": -0.0017997558,
        "b": -0.03670573871,
        "c": 75.81684982,
        "equation": "y = -0.0018x^2 - 0.0367x + 75.8168",
    },
    "TGL": {
        "name": "Turbine Generator Load",
        "unit": "MWe",
        "type": "quadratic",
        "a": 0.005396825397,
        "b": 12.99801221,
        "c": -135.3540904,
        "equation": "y = 0.0054x^2 + 12.9980x - 135.3541",
    },
}

UNIT_2_REGRESSION_MODELS: dict[str, dict[str, Any]] = {
    "FWF": {
        "name": "Feedwater Flow",
        "unit": "kg/s",
        "type": "cubic",
        "a": 0.0005007109276,
        "b": -0.06112934297,
        "c": 15.90900097,
        "d": 101.8426385,
        "equation": "y = 0.0005x^3 - 0.0611x^2 + 15.9090x + 101.8426",
    },
    "TCV": {
        "name": "Turbine Control Valve",
        "unit": "%",
        "type": "cubic",
        "a": 2.797844284e-05,
        "b": -0.005614723082,
        "c": 1.142296755,
        "d": 4.254317165,
        "equation": "y = 0.0000x^3 - 0.0056x^2 + 1.1423x + 4.2543",
    },
    "CRP": {
        "name": "Condenser Recirculation Pump",
        "unit": "%",
        "type": "cubic",
        "a": 1.414975347e-05,
        "b": -0.001052287582,
        "c": 0.7989324619,
        "d": 8.249466804,
        "equation": "y = 0.0000x^3 - 0.0011x^2 + 0.7989x + 8.2495",
    },
    "SJAE": {
        "name": "Steam Jet Air Ejector",
        "unit": "%",
        "type": "cubic",
        "a": 9.104460498e-05,
        "b": -0.01512108703,
        "c": 1.279841188,
        "d": 8.240626075,
        "equation": "y = 0.0001x^3 - 0.0151x^2 + 1.2798x + 8.2406",
    },
    "DIO Intake": {
        "name": "Deaerator Intake",
        "unit": "%",
        "type": "cubic",
        "a": -8.852195849e-05,
        "b": 0.02103887169,
        "c": -2.055509689,
        "d": 99.02339181,
        "equation": "y = -0.0001x^3 + 0.0210x^2 - 2.0555x + 99.0234",
    },
    "DIO Output": {
        "name": "Deaerator Output",
        "unit": "%",
        "type": "cubic",
        "a": 1.364522417e-05,
        "b": -0.003620571035,
        "c": -0.01696479761,
        "d": 78.64877881,
        "equation": "y = 0.0000x^3 - 0.0036x^2 - 0.0170x + 78.6488",
    },
    "TGL": {
        "name": "Turbine Generator Load",
        "unit": "MWe",
        "type": "cubic",
        "a": -1.031991744e-06,
        "b": 0.005510835913,
        "c": 12.99032508,
        "d": -135.0562436,
        "equation": "y = 0.0000x^3 + 0.0055x^2 + 12.9903x - 135.0562",
    },
    "MSS": {
        "name": "Main Steam Sealing",
        "unit": "%",
        "type": "cubic",
        "a": 1.373695677e-05,
        "b": -0.004640522876,
        "c": 1.609876734,
        "d": -41.59191606,
        "equation": "y = 0.0000x^3 - 0.0046x^2 + 1.6099x - 41.5919",
    },
    "OCL": {
        "name": "Oil Cooling",
        "unit": "%",
        "type": "cubic",
        "a": 7.570232771e-05,
        "b": -0.01113140695,
        "c": 1.529275312,
        "d": -29.78538012,
        "equation": "y = 0.0001x^3 - 0.0111x^2 + 1.5293x - 29.7854",
    },
    "OCV": {
        "name": "Oil Cooler Valve",
        "unit": "%",
        "type": "cubic",
        "a": -1.688034188e-05,
        "b": 0.001993589744,
        "c": 0.8435936286,
        "d": -14.32666667,
        "equation": "y = 0.0000x^3 + 0.0020x^2 + 0.8436x - 14.3267",
    },
    "MCV": {
        "name": "Motor Coolant Valve",
        "unit": "%",
        "type": "cubic",
        "a": -9.712509713e-07,
        "b": -0.000460955711,
        "c": 0.8748815074,
        "d": -3.63,
        "equation": "y = 0.0000x^3 - 0.0005x^2 + 0.8749x - 3.6300",
    },
}
""";

    private static readonly Regex EntryRegex = new(
        "\"(?<key>[^\"]+)\"\\s*:\\s*\\{(?<body>[^}]*)\\}",
        RegexOptions.Compiled | RegexOptions.Singleline);

    private static readonly Regex StringFieldRegex = new(
        "\"(?<field>[^\"]+)\"\\s*:\\s*\"(?<val>[^\"]*)\"",
        RegexOptions.Compiled);

    private static readonly Regex NumberFieldRegex = new(
        "\"(?<field>[abcd])\"\\s*:\\s*(?<val>[-+]?\\d+(?:\\.\\d+)?(?:[eE][-+]?\\d+)?)",
        RegexOptions.Compiled);

    public static IReadOnlyDictionary<string, RegressionModel> DefaultUnit1Models { get; }
    public static IReadOnlyDictionary<string, RegressionModel> DefaultUnit2Models { get; }

    static Calculator()
    {
        var (u1, u2) = ParseRegressionModels(RegressionModelsSource);
        DefaultUnit1Models = u1;
        DefaultUnit2Models = u2;
    }

    public static (Dictionary<string, RegressionModel> Unit1, Dictionary<string, RegressionModel> Unit2) ParseRegressionModels(string source)
    {
        var u1 = new Dictionary<string, RegressionModel>(StringComparer.OrdinalIgnoreCase);
        var u2 = new Dictionary<string, RegressionModel>(StringComparer.OrdinalIgnoreCase);

        if (string.IsNullOrWhiteSpace(source))
        {
            return (u1, u2);
        }

        int u1Idx = source.IndexOf("UNIT_1_REGRESSION_MODELS", StringComparison.Ordinal);
        int u2Idx = source.IndexOf("UNIT_2_REGRESSION_MODELS", StringComparison.Ordinal);

        if (u1Idx >= 0 && u2Idx > u1Idx)
        {
            ParseSection(source.Substring(u1Idx, u2Idx - u1Idx), u1);
            ParseSection(source.Substring(u2Idx), u2);
        }
        else if (u1Idx >= 0)
        {
            ParseSection(source.Substring(u1Idx), u1);
        }
        else if (u2Idx >= 0)
        {
            ParseSection(source.Substring(u2Idx), u2);
        }

        return (u1, u2);
    }

    private static void ParseSection(string sectionText, Dictionary<string, RegressionModel> target)
    {
        foreach (Match match in EntryRegex.Matches(sectionText))
        {
            string key = match.Groups["key"].Value;
            string body = match.Groups["body"].Value;

            string name = key;
            string unit = string.Empty;
            string type = "quadratic";
            string equation = string.Empty;

            foreach (Match sm in StringFieldRegex.Matches(body))
            {
                string field = sm.Groups["field"].Value;
                string val = sm.Groups["val"].Value;
                switch (field)
                {
                    case "name": name = val; break;
                    case "unit": unit = val; break;
                    case "type": type = val; break;
                    case "equation": equation = val; break;
                }
            }

            double a = 0.0, b = 0.0, c = 0.0, d = 0.0;
            foreach (Match nm in NumberFieldRegex.Matches(body))
            {
                string field = nm.Groups["field"].Value;
                if (double.TryParse(nm.Groups["val"].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out double num))
                {
                    switch (field)
                    {
                        case "a": a = num; break;
                        case "b": b = num; break;
                        case "c": c = num; break;
                        case "d": d = num; break;
                    }
                }
            }

            target[key] = new RegressionModel(key, name, unit, type, a, b, c, d, equation);
        }
    }

    public static double EvaluateRegressionModel(RegressionModel model, double x)
    {
        if (string.Equals(model.Type, "cubic", StringComparison.OrdinalIgnoreCase))
        {
            double x2 = x * x;
            double x3 = x2 * x;
            return (model.A * x3) + (model.B * x2) + (model.C * x) + model.D;
        }
        else
        {
            return (model.A * x * x) + (model.B * x) + model.C;
        }
    }

    public double Usage { get; set; }
    public int SelectedUnit { get; set; } = 1;
    public double? RecircOverride { get; set; }

    public UsageCalculator UsageCalc1 { get; }
    public UsageCalculator UsageCalc2 { get; }

    public IReadOnlyDictionary<string, RegressionModel> Unit1Models { get; private set; } = DefaultUnit1Models;
    public IReadOnlyDictionary<string, RegressionModel> Unit2Models { get; private set; } = DefaultUnit2Models;

    public IReadOnlyDictionary<string, RegressionModel> ActiveModels =>
        SelectedUnit == 1 ? Unit1Models : Unit2Models;

    public Calculator(double usage = 61.32)
    {
        Usage = usage;
        UsageCalc1 = new UsageCalculator(1);
        UsageCalc2 = new UsageCalculator(2);
    }

    public void LoadRegressionModels(string pythonModelsSource)
    {
        var (u1, u2) = ParseRegressionModels(pythonModelsSource);
        if (u1.Count > 0) Unit1Models = u1;
        if (u2.Count > 0) Unit2Models = u2;
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

    public double CalcParam(string paramKey, double thermal)
    {
        if (ActiveModels.TryGetValue(paramKey, out var model))
        {
            return EvaluateRegressionModel(model, thermal);
        }
        if (Unit2Models.TryGetValue(paramKey, out var fallbackModel))
        {
            return EvaluateRegressionModel(fallbackModel, thermal);
        }
        return 0.0;
    }

    public double CalcFlow(double thermal)
    {
        if (ActiveModels.TryGetValue("FWF", out var model))
        {
            return Math.Max(0.0, EvaluateRegressionModel(model, thermal));
        }
        return 0.0;
    }

    public double CalcGenLoad(double thermal)
    {
        if (ActiveModels.TryGetValue("TGL", out var model))
        {
            return Math.Max(0.0, EvaluateRegressionModel(model, thermal));
        }
        return 0.0;
    }

    public double CalcMss(double thermal)
    {
        return CalcParam("MSS", thermal);
    }

    public double CalcOcl(double thermal)
    {
        return CalcParam("OCL", thermal);
    }

    private double SolveThermalFromLoad(double targetGross)
    {
        if (targetGross <= 0.0) return 0.0;
        if (!ActiveModels.TryGetValue("TGL", out var model)) return 0.0;

        if (string.Equals(model.Type, "cubic", StringComparison.OrdinalIgnoreCase))
        {
            double a = model.A;
            double b = model.B;
            double c = model.C;
            double d = model.D;
            double x = c != 0.0 ? Math.Max(0.0, (targetGross - d) / c) : 0.0;
            for (int i = 0; i < 8; i++)
            {
                double x2 = x * x;
                double fx = (a * x2 * x) + (b * x2) + (c * x) + d - targetGross;
                double fpx = (3.0 * a * x2) + (2.0 * b * x) + c;
                if (fpx == 0.0) break;
                x = Math.Max(0.0, x - (fx / fpx));
            }
            return x;
        }
        else
        {
            double a = model.A;
            double b = model.B;
            double c = model.C;
            double inner = (b * b) - (4.0 * a * (c - targetGross));
            if (inner < 0.0 || a == 0.0) return 0.0;
            return Math.Max(0.0, (-b + Math.Sqrt(inner)) / (2.0 * a));
        }
    }

    public double CalcThermal(double demand)
    {
        double currentUsage = Usage;
        double thermal = 0.0;

        for (int i = 0; i < 5; i++)
        {
            double targetGross = demand + currentUsage;
            thermal = SolveThermalFromLoad(targetGross);
            double flow = CalcFlow(thermal);
            UsageCalculator uCalc = (SelectedUnit == 1) ? UsageCalc1 : UsageCalc2;
            currentUsage = uCalc.CalculateUsage(flow, thermal, RecircOverride);
        }

        Usage = currentUsage;
        return thermal;
    }
}