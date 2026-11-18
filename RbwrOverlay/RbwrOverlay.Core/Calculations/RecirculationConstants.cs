namespace RbwrOverlay.Core.Calculations;

public static class RecirculationConstants
{
    public static readonly IReadOnlyDictionary<int, double> Unit1AprmToRecircTable = new Dictionary<int, double>
    {
        { 0, 0 },
        { 10, 27 },
        { 20, 28 },
        { 30, 28 },
        { 40, 36 },
        { 50, 43 },
        { 60, 60 },
        { 70, 78 },
        { 80, 83 },
        { 90, 88 },
        { 100, 96 },
        { 110, 100 }
    };

    public static readonly IReadOnlyDictionary<int, double> Unit2AprmToRecircTable = new Dictionary<int, double>
    {
        { 0, 0 },
        { 10, 27 },
        { 20, 28 },
        { 30, 28 },
        { 40, 30 },
        { 50, 33 },
        { 60, 42 },
        { 70, 68 },
        { 80, 75 },
        { 90, 79 },
        { 100, 86 },
        { 110, 90 }
    };
}