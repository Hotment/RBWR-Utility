namespace RbwrOverlay.Core.Calculations;

public static class RecirculationConstants
{
    public static readonly IReadOnlyDictionary<int, double> AprmToRecircTable = new Dictionary<int, double>
    {
        { 0, 0 },
        { 10, 28 },
        { 20, 28 },
        { 30, 28 },
        { 40, 38 },
        { 50, 50 },
        { 60, 70 },
        { 70, 85 },
        { 80, 94 },
        { 90, 97 },
        { 100, 100 },
        { 110, 100 }
    };
}