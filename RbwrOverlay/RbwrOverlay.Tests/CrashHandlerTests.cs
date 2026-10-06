using RbwrOverlay.UI.Services;
using RbwrOverlay.UI.ViewModels;
using Xunit;

namespace RbwrOverlay.Tests;

public class CrashHandlerTests
{
    [Fact]
    public void TestFormatExceptionDetails_ContainsEssentialInfo()
    {
        var testEx = new InvalidOperationException("Test exception for crash formatting");
        string context = "Unit Test Execution";

        string formatted = CrashHandler.FormatExceptionDetails(testEx, context);

        Assert.Contains("=== CRASH OCCURRED:", formatted);
        Assert.Contains("Context: Unit Test Execution", formatted);
        Assert.Contains("InvalidOperationException", formatted);
        Assert.Contains("Test exception for crash formatting", formatted);
        Assert.Contains("App Version:", formatted);
        Assert.Contains("OS:", formatted);
    }

    [Fact]
    public void TestFormatExceptionDetails_IncludesSkiaTroubleshooting()
    {
        var skiaEx = new TypeInitializationException("SkiaSharp.SKImageInfo", 
            new DllNotFoundException("Unable to load DLL 'libSkiaSharp' or one of its dependencies"));

        string formatted = CrashHandler.FormatExceptionDetails(skiaEx, "Startup Test");

        Assert.Contains("=== TROUBLESHOOTING SUGGESTION ===", formatted);
        Assert.Contains("libSkiaSharp", formatted);
        Assert.Contains("Microsoft Visual C++ 2015-2022 Redistributable", formatted);
    }

    [Fact]
    public void TestWriteCrashReportFile_CreatesFileOnDisk()
    {
        string sample = "Sample crash report content for unit testing.";
        string path = CrashHandler.WriteCrashReportFile(sample);

        Assert.True(File.Exists(path));
        string readBack = File.ReadAllText(path);
        Assert.Equal(sample, readBack);
    }

    [Fact]
    public void TestCrashReportViewModel_InstantiationAndProperties()
    {
        string traceback = "Test traceback sample";
        var vm = new CrashReportViewModel(traceback);

        Assert.Equal(traceback, vm.Traceback);
        Assert.Equal("Copy Traceback", vm.CopyButtonText);
        Assert.False(vm.IsSending);
    }
}