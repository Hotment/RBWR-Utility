using System;
using System.Globalization;
using System.Text.RegularExpressions;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Media;

namespace RbwrOverlay.UI.Views;

public partial class CustomMessageWindow : Window
{
    private static readonly Regex HealthPercentRegex = new(@"LOW\s*\(([0-9]+(?:\.[0-9]+)?)\%\)", RegexOptions.Compiled | RegexOptions.IgnoreCase);
    private static readonly Regex GenericPercentRegex = new(@"([0-9]+(?:\.[0-9]+)?)\%", RegexOptions.Compiled);
    private static readonly Regex ThresholdRegex = new(@"Threshold:\s*([0-9]+(?:\.[0-9]+)?)\%", RegexOptions.Compiled | RegexOptions.IgnoreCase);
    private static readonly Regex UnitRegex = new(@"(Unit\s*[12])", RegexOptions.Compiled | RegexOptions.IgnoreCase);

    public CustomMessageWindow()
    {
        InitializeComponent();
        SetupDrag();
        KeyDown += OnWindowKeyDown;
    }

    public CustomMessageWindow(string title, string message, bool isError) : this()
    {
        ConfigureMessage(title, message, isError);
    }

    private void ConfigureMessage(string title, string message, bool isError)
    {
        TimestampText.Text = DateTime.Now.ToString("HH:mm:ss");

        bool isTurbineAlert = title.Contains("TURBINE", StringComparison.OrdinalIgnoreCase) ||
                              message.Contains("Turbine Health", StringComparison.OrdinalIgnoreCase);

        if (isTurbineAlert)
        {
            ApplyTurbineAlertStyle(title, message);
        }
        else if (isError)
        {
            ApplyErrorStyle(title, message);
        }
        else
        {
            ApplyInfoStyle(title, message);
        }
    }

    private void ApplyTurbineAlertStyle(string title, string message)
    {
        TitleText.Text = "TURBINE HEALTH WARNING";
        MessageText.Text = message;
        TurbineDiagnosticsCard.IsVisible = true;

        var unitMatch = UnitRegex.Match(message);
        if (unitMatch.Success)
        {
            TurbineUnitText.Text = unitMatch.Value.ToUpperInvariant();
        }
        else
        {
            TurbineUnitText.Text = "UNIT 2";
        }

        double healthVal = 0.0;
        bool hasHealth = false;
        var healthMatch = HealthPercentRegex.Match(message);
        if (healthMatch.Success && double.TryParse(healthMatch.Groups[1].Value, NumberStyles.Any, CultureInfo.InvariantCulture, out double parsedVal))
        {
            healthVal = parsedVal;
            hasHealth = true;
        }
        else
        {
            var genMatch = GenericPercentRegex.Match(message);
            if (genMatch.Success && double.TryParse(genMatch.Groups[1].Value, NumberStyles.Any, CultureInfo.InvariantCulture, out double genVal))
            {
                healthVal = genVal;
                hasHealth = true;
            }
        }

        double thresholdVal = 65.0;
        var threshMatch = ThresholdRegex.Match(message);
        if (threshMatch.Success && double.TryParse(threshMatch.Groups[1].Value, NumberStyles.Any, CultureInfo.InvariantCulture, out double parsedThresh))
        {
            thresholdVal = parsedThresh;
        }

        TurbineThresholdText.Text = $"{thresholdVal:F1}%";
        ThresholdBarMarker.Text = $"{thresholdVal:F0}% SAFE THRESHOLD";

        if (hasHealth)
        {
            TurbineHealthPercentText.Text = $"{healthVal:F1}%";
            TurbineHealthBar.Value = Math.Clamp(healthVal, 0, 100);
        }
        else
        {
            TurbineHealthPercentText.Text = "DEGRADED";
            TurbineHealthBar.Value = 40;
        }

        Color accentColor;
        string conditionText;
        string statusLabel;

        if (healthVal <= 45.0)
        {
            accentColor = Color.Parse("#ff003c"); // Neon Red
            conditionText = "CRITICAL DEGRADATION";
            statusLabel = "CRITICAL LOW";
        }
        else
        {
            accentColor = Color.Parse("#ffaa00"); // Neon Gold / Warning
            conditionText = "LOW HEALTH";
            statusLabel = "BELOW SAFE LIMIT";
        }

        var accentBrush = new SolidColorBrush(accentColor);
        var badgeBgBrush = healthVal <= 45.0
            ? new SolidColorBrush(Color.Parse("#290e14"))
            : new SolidColorBrush(Color.Parse("#261b0a"));

        RootBorder.BorderBrush = accentBrush;
        RootBorder.BoxShadow = BoxShadows.Parse(healthVal <= 45.0
            ? "0 8 32 0 #99000000, 0 0 20 0 #44ff003c"
            : "0 8 32 0 #99000000, 0 0 20 0 #44ffaa00");

        TitleText.Foreground = accentBrush;

        TurbineConditionBadge.BorderBrush = accentBrush;
        TurbineConditionBadge.Background = badgeBgBrush;
        TurbineConditionText.Text = conditionText;
        TurbineConditionText.Foreground = accentBrush;

        TurbineHealthPercentText.Foreground = accentBrush;
        TurbineHealthBar.Foreground = accentBrush;
        TurbineStatusLabel.Text = statusLabel;
        TurbineStatusLabel.Foreground = accentBrush;

        OkButton.Classes.Clear();
        OkButton.Classes.Add(healthVal <= 45.0 ? "cyber-red" : "cyber-gold");
        OkButton.Content = "ACKNOWLEDGE";
    }

    private void ApplyErrorStyle(string title, string message)
    {
        TurbineDiagnosticsCard.IsVisible = false;
        TitleText.Text = title.StartsWith("ERROR", StringComparison.OrdinalIgnoreCase) ? title.ToUpperInvariant() : $"ERROR: {title.ToUpperInvariant()}";
        MessageText.Text = message;

        var redColor = Color.Parse("#ff003c");
        var redBrush = new SolidColorBrush(redColor);

        RootBorder.BorderBrush = redBrush;
        RootBorder.BoxShadow = BoxShadows.Parse("0 8 32 0 #99000000, 0 0 20 0 #44ff003c");

        TitleText.Foreground = redBrush;

        OkButton.Classes.Clear();
        OkButton.Classes.Add("cyber-red");
        OkButton.Content = "OK";
    }

    private void ApplyInfoStyle(string title, string message)
    {
        TurbineDiagnosticsCard.IsVisible = false;
        TitleText.Text = title.StartsWith("INFO", StringComparison.OrdinalIgnoreCase) ? title.ToUpperInvariant() : $"INFO: {title.ToUpperInvariant()}";
        MessageText.Text = message;

        var cyanColor = Color.Parse("#00f0ff");
        var cyanBrush = new SolidColorBrush(cyanColor);

        RootBorder.BorderBrush = cyanBrush;
        RootBorder.BoxShadow = BoxShadows.Parse("0 8 32 0 #99000000, 0 0 18 0 #3300f0ff");

        TitleText.Foreground = cyanBrush;

        OkButton.Classes.Clear();
        OkButton.Classes.Add("cyber");
        OkButton.Content = "OK";
    }

    private void SetupDrag()
    {
        HeaderBorder.PointerPressed += (s, e) =>
        {
            if (e.GetCurrentPoint(this).Properties.IsLeftButtonPressed)
            {
                BeginMoveDrag(e);
            }
        };

        RootBorder.PointerPressed += (s, e) =>
        {
            if (e.GetCurrentPoint(this).Properties.IsLeftButtonPressed && e.Source is not Button)
            {
                BeginMoveDrag(e);
            }
        };
    }

    private void OnWindowKeyDown(object? sender, KeyEventArgs e)
    {
        if (e.Key is Key.Escape or Key.Enter)
        {
            Close();
            e.Handled = true;
        }
    }

    private void OnCloseClick(object? sender, RoutedEventArgs e)
    {
        Close();
    }
}