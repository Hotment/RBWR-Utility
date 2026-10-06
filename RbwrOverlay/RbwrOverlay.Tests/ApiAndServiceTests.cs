using System.Text.Json;
using RbwrOverlay.Core.Models;
using RbwrOverlay.Core.Services;
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
}