using System.Net;

namespace RbwrOverlay.Core.Models;

public enum ServerFetchErrorKind
{
    None,
    ConnectionLost,
    HttpError,
    ParseError,
    Unknown
}

public class ServerFetchResult
{
    public bool IsSuccess { get; set; }
    public List<ServerInfo> Servers { get; set; } = new();
    public ServerFetchErrorKind ErrorKind { get; set; } = ServerFetchErrorKind.None;
    public HttpStatusCode? StatusCode { get; set; }
    public string? ErrorMessage { get; set; }
    public Exception? Exception { get; set; }

    public static ServerFetchResult Success(List<ServerInfo> servers) => new()
    {
        IsSuccess = true,
        Servers = servers,
        ErrorKind = ServerFetchErrorKind.None
    };

    public static ServerFetchResult ConnectionFailure(string message, Exception? ex = null) => new()
    {
        IsSuccess = false,
        ErrorKind = ServerFetchErrorKind.ConnectionLost,
        ErrorMessage = message,
        Exception = ex
    };

    public static ServerFetchResult HttpFailure(HttpStatusCode statusCode, string message) => new()
    {
        IsSuccess = false,
        ErrorKind = (int)statusCode is 502 or 503 or 504 ? ServerFetchErrorKind.ConnectionLost : ServerFetchErrorKind.HttpError,
        StatusCode = statusCode,
        ErrorMessage = message
    };

    public static ServerFetchResult ParseFailure(string message, Exception? ex = null) => new()
    {
        IsSuccess = false,
        ErrorKind = ServerFetchErrorKind.ParseError,
        ErrorMessage = message,
        Exception = ex
    };
}
