using System.Text.Json;
using RbwrOverlay.Core.Models;
using RbwrOverlay.Core.Services;
using RbwrOverlay.Platform;
using Xunit;

namespace RbwrOverlay.Tests;

public class ApiAndServiceTests
{
    [Fact]
    public void TestServerParsingAndValidation()
    {
        string json = """
        {
            "servers": [
                {
                    "jobId": "68c4aeb7-7b4f-4460-81ca-309f94ab4bd9",
                    "lastHeartbeat": "2026-09-24T20:30:00Z",
                    "state": {
                        "Unit1": {
                            "Demand Time Left": 45,
                            "DemandU1": 1200,
                            "NextDemandU1": 1400,
                            "TurbineHealth": 98.5
                        },
                        "Unit2": {
                            "dtl": 55,
                            "Demand": 850,
                            "next_demand": 900,
                            "turbine_health": 64.2
                        }
                    }
                }
            ]
        }
        """;

        using var doc = JsonDocument.Parse(json);
        var client = new ApiClient();
        var servers = client.ParseServersFromPayload(doc.RootElement);

        Assert.Single(servers);
        var server = servers[0];
        Assert.Equal("68c4aeb7-7b4f-4460-81ca-309f94ab4bd9", server.JobId);
        Assert.NotNull(server.Unit1);
        Assert.Equal(45, server.Unit1.DemandTimeLeft);
        Assert.Equal(1200, server.Unit1.Demand);
        Assert.Equal(1400, server.Unit1.NextDemand);
        Assert.Equal(98.5, server.Unit1.TurbineHealth);

        Assert.NotNull(server.Unit2);
        Assert.Equal(55, server.Unit2.DemandTimeLeft);
        Assert.Equal(850, server.Unit2.Demand);
        Assert.Equal(900, server.Unit2.NextDemand);
        Assert.Equal(64.2, server.Unit2.TurbineHealth);

        var missing = server.ValidateSync();
        Assert.Empty(missing);
    }

    [Theory]
    [InlineData("68c4aeb7-7b4f-4460-81ca-309f94ab4bd9", true)]
    [InlineData("7b4f-4460", true)]
    [InlineData("7b4f", true)]
    [InlineData("68c4", true)]
    [InlineData("non-existent-id", false)]
    public void TestFindServerByQuery(string query, bool shouldFind)
    {
        var client = new ApiClient();
        var servers = new List<ServerInfo>
        {
            new()
            {
                JobId = "68c4aeb7-7b4f-4460-81ca-309f94ab4bd9",
                Id = "68c4aeb7-7b4f-4460-81ca-309f94ab4bd9"
            }
        };

        var found = client.FindServerByIdOrJobId(servers, query);
        if (shouldFind)
        {
            Assert.NotNull(found);
            Assert.Equal("68c4aeb7-7b4f-4460-81ca-309f94ab4bd9", found.JobId);
        }
        else
        {
            Assert.Null(found);
        }
    }

    [Theory]
    [InlineData("ed10", "ed10e9ed-e83c-4cfe-a9a0-bb8361a51818", true)] // Start of job ID
    [InlineData("ed10e9ed", "ed10e9ed-e83c-4cfe-a9a0-bb8361a51818", true)] // Full 1st part
    [InlineData("e83", "ed10e9ed-e83c-4cfe-a9a0-bb8361a51818", true)] // Prefix of 2nd part
    [InlineData("e83c", "ed10e9ed-e83c-4cfe-a9a0-bb8361a51818", true)] // Full 2nd part
    [InlineData("e83c-4cfe", "ed10e9ed-e83c-4cfe-a9a0-bb8361a51818", true)] // 2nd part + 3rd part (short ID)
    [InlineData("E83C-4CFE", "ed10e9ed-e83c-4cfe-a9a0-bb8361a51818", true)] // Case-insensitive
    [InlineData("4cfe", "ed10e9ed-e83c-4cfe-a9a0-bb8361a51818", true)] // 3rd part
    [InlineData("", "ed10e9ed-e83c-4cfe-a9a0-bb8361a51818", true)] // Empty query matches all
    [InlineData("xyz", "ed10e9ed-e83c-4cfe-a9a0-bb8361a51818", false)] // Non-matching
    [InlineData("9999", "ed10e9ed-e83c-4cfe-a9a0-bb8361a51818", false)] // Non-matching
    public void TestJobIdMatcher(string query, string target, bool expected)
    {
        bool result = JobIdMatcher.IsMatch(query, target);
        Assert.Equal(expected, result);
    }

    [Fact]
    public void TestLogSystemInfo()
    {
        var logger = LoggingService.Instance;
        logger.LogSystemInfo("2.1.0");

        string content = logger.GetLogContent();
        Assert.Contains("=== RBWR APRM Calculator (Avalonia .NET) v2.1.0 Starting ===", content);
        Assert.Contains("Version: 2.1.0", content);
        Assert.Contains("Runtime:", content);
        Assert.Contains("OS:", content);
        Assert.Contains("Log file:", content);
    }

    [Fact]
    public void TestSanitizationMasksUsernameAndProfile()
    {
        var logger = LoggingService.Instance;
        string rawPathWin = @"C:\Users\SecretUser\Downloads\RbwrOverlay.exe";
        string sanitizedWin = logger.SanitizeString(rawPathWin);
        Assert.DoesNotContain("SecretUser", sanitizedWin);
        Assert.Contains("%userprofile%", sanitizedWin);

        string rawPathUnix = "/home/linuxuser/app/RbwrOverlay";
        string sanitizedUnix = logger.SanitizeString(rawPathUnix);
        Assert.DoesNotContain("linuxuser", sanitizedUnix);
        Assert.Contains("$HOME", sanitizedUnix);

        string rawPathMac = "/Users/macuser/app/RbwrOverlay";
        string sanitizedMac = logger.SanitizeString(rawPathMac);
        Assert.DoesNotContain("macuser", sanitizedMac);
        Assert.Contains("$HOME", sanitizedMac);

        if (!string.IsNullOrWhiteSpace(Environment.UserName))
        {
            string currentPath = $@"C:\Users\{Environment.UserName}\Desktop\test.txt";
            string sanitizedCurrent = logger.SanitizeString(currentPath);
            Assert.DoesNotContain(Environment.UserName, sanitizedCurrent);
            Assert.Contains("%userprofile%", sanitizedCurrent);
        }
    }

    [Fact]
    public void TestRobloxJoinInfoRecord()
    {
        var info = new RobloxJoinInfo("d6386411-4385-4b3e-8f20-b4724bb4e357", 11765852158);
        Assert.Equal("d6386411-4385-4b3e-8f20-b4724bb4e357", info.JobId);
        Assert.Equal(11765852158, info.PlaceId);
    }

    [Fact]
    public void TestRobloxLogReader_ParsesJobIdAndIgnoresCrashHandler()
    {
        string tempDir = Path.Combine(Path.GetTempPath(), "RobloxLogReaderTests_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempDir);
        try
        {
            string playerLog = Path.Combine(tempDir, "0.746.0_Player_ABC12_last.log");
            string playerContent = """
            2026-11-07T10:40:00.000Z,1.000,100,6 [FLog::Output] ! Joining game 'job-old-session-111' place 12345 at 10.0.0.1
            2026-11-07T10:42:48.000Z,2.000,200,6 [FLog::Output] ! Joining game '240139be-5d8e-46ca-86c6-059050831aee' place 11765852158 at 10.18.6.21
            """;
            File.WriteAllText(playerLog, playerContent);
            File.SetLastWriteTimeUtc(playerLog, DateTime.UtcNow.AddMinutes(-5));

            string crashHandlerLog = Path.Combine(tempDir, "0.746.0_Player_C0819_CrashHandler_last.log");
            string crashContent = """
            [FLog::CrashpadHandlerLog] Crashpad handler logging initialized
            [FLog::CrashpadHandlerLog] Handler executable command line: RobloxCrashHandler.exe
            """;
            File.WriteAllText(crashHandlerLog, crashContent);
            File.SetLastWriteTimeUtc(crashHandlerLog, DateTime.UtcNow.AddMinutes(-1));

            var result = RobloxLogReader.GetLastJoinedGame(tempDir);
            Assert.NotNull(result);
            Assert.Equal("240139be-5d8e-46ca-86c6-059050831aee", result.Value.JobId);
            Assert.Equal(11765852158, result.Value.PlaceId);

            var placeId = RobloxLogReader.GetLastJoinedPlaceId(tempDir);
            Assert.Equal(11765852158, placeId);
        }
        finally
        {
            if (Directory.Exists(tempDir)) Directory.Delete(tempDir, true);
        }
    }

    [Fact]
    public void TestRobloxLogReader_ReturnsNull_WhenUserLeftGameAfterJoin()
    {
        string tempDir = Path.Combine(Path.GetTempPath(), "RobloxLogReaderTests_Leave_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempDir);
        try
        {
            string playerLog = Path.Combine(tempDir, "0.746.0_Player_XYZ_last.log");
            string playerContent = """
            2026-11-07T10:42:48.000Z,2.000,200,6 [FLog::Output] ! Joining game '240139be-5d8e-46ca-86c6-059050831aee' place 11765852158 at 10.18.6.21
            2026-11-07T10:51:44.716Z,537.716,a5ac,6 [FLog::SingleSurfaceApp] leaveUGCGameInternal
            2026-11-07T10:51:48.889Z,541.889,258c,6 [FLog::SessionTransitionFSM] Entered app session.
            """;
            File.WriteAllText(playerLog, playerContent);

            var result = RobloxLogReader.GetLastJoinedGame(tempDir);
            Assert.Null(result);

            var placeId = RobloxLogReader.GetLastJoinedPlaceId(tempDir);
            Assert.Null(placeId);
        }
        finally
        {
            if (Directory.Exists(tempDir)) Directory.Delete(tempDir, true);
        }
    }

    [Fact]
    public void TestRobloxLogReader_ReturnsSecondGame_WhenUserLeftFirstAndJoinedSecond()
    {
        string tempDir = Path.Combine(Path.GetTempPath(), "RobloxLogReaderTests_SecondJoin_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempDir);
        try
        {
            string playerLog = Path.Combine(tempDir, "0.746.0_Player_Second_last.log");
            string playerContent = """
            2026-11-07T10:42:48.000Z,2.000,200,6 [FLog::Output] ! Joining game 'rbwr-job-111' place 11765852158 at 10.18.6.21
            2026-11-07T10:51:44.716Z,537.716,a5ac,6 [FLog::SingleSurfaceApp] leaveUGCGameInternal
            2026-11-07T11:15:49.000Z,1982.00,4cd0,6 [FLog::Output] ! Joining game 'other-game-job-222' place 987654321 at 10.18.6.22
            """;
            File.WriteAllText(playerLog, playerContent);

            var result = RobloxLogReader.GetLastJoinedGame(tempDir);
            Assert.NotNull(result);
            Assert.Equal("other-game-job-222", result.Value.JobId);
            Assert.Equal(987654321, result.Value.PlaceId);
        }
        finally
        {
            if (Directory.Exists(tempDir)) Directory.Delete(tempDir, true);
        }
    }
}