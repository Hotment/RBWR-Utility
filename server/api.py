from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import secrets
import sys
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_WORKSPACE_ROOT = os.path.abspath(os.path.join(_BASE_DIR, ".."))
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

try:
    from server import core
except ImportError:
    import core

logger = logging.getLogger("rbwr.api")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s | %(levelname)s | %(name)s]: %(message)s")

RATE_LIMIT_PER_MINUTE = int(os.environ.get("API_RATE_LIMIT_PER_MINUTE", "400"))
RATE_LIMIT_PER_SECOND = int(os.environ.get("API_RATE_LIMIT_PER_SECOND", "10"))

_RATE_EXEMPT_PATHS = {
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
    "/docs",
    "/redoc",
    "/openapi.json",
}

TAGS_METADATA = [
    {
        "name": "Status & Meta",
        "description": "Service health, uptime, and RBWR-Utility release metadata.",
    },
    {
        "name": "Calculator",
        "description": "RBWR reactor physics solver for APRM/RTP, electric output (MW), recirculation flow, MSS, and OCL.",
    },
    {
        "name": "Hydrogen Replacement",
        "description": "Drop-in replacement and enriched endpoints replacing upstream hydrogen.realisticbwr.org endpoints.",
    },
    {
        "name": "Servers",
        "description": "Active, historical, and filtered RBWR server listings, lookups, unit states, and leaderboard.",
    },
    {
        "name": "Server Analytics",
        "description": "Top Score breakdowns, Kalman-filtered fuel estimation, snapshot history, and time-series charts.",
    },
    {
        "name": "Archives",
        "description": "Daily archived server snapshot listings and per-day server summaries.",
    },
    {
        "name": "Community",
        "description": "Public read-only tickets and feature suggestions feed.",
    },
    {
        "name": "Ingestion",
        "description": "API-key protected data refresh and operational triggers.",
    },
]

API_DESCRIPTION = """
RBWR Utility public REST API built with **FastAPI**.

### Key Highlights
- **Hydrogen Replacement**: Query `/api/public/servers` as a drop-in, enriched replacement for upstream Hydrogen endpoints, plus `/api/servers`, `/api/servers/{job_id}`, `/api/leaderboard`, and `/api/grid/summary`.
- **Generous Dual-Window Rate Limits**: **10 requests/second** burst and **400 requests/minute** sustained per IP (`X-RateLimit-*` headers included on every response).
- **Protected Ingestion**: `POST /api/servers/refresh` requires a valid `X-API-Key` header.
""".strip()

app = FastAPI(
    title="RBWR Utility REST API",
    version="2.0.0",
    description=API_DESCRIPTION,
    openapi_tags=TAGS_METADATA,
    docs_url=None,
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "HEAD", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=[
        "X-RateLimit-Limit-Minute",
        "X-RateLimit-Remaining-Minute",
        "X-RateLimit-Limit-Second",
        "X-RateLimit-Remaining-Second",
        "Retry-After",
    ],
)

class _SlidingWindowRateLimiter:
    """Thread-safe dual-window (per-second burst + per-minute sustained) IP rate limiter."""

    def __init__(self, per_second: int = 10, per_minute: int = 400) -> None:
        self.per_second = max(1, per_second)
        self.per_minute = max(1, per_minute)
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_gc = time.monotonic()

    def check(self, client_ip: str) -> tuple[bool, int, int, int]:
        now = time.monotonic()
        with self._lock:
            if now - self._last_gc > 300:
                stale_ips = [ip for ip, dq in self._hits.items() if not dq or (now - dq[-1]) > 120]
                for ip in stale_ips:
                    del self._hits[ip]
                self._last_gc = now

            dq = self._hits[client_ip]
            cutoff_min = now - 60.0
            while dq and dq[0] <= cutoff_min:
                dq.popleft()

            cutoff_sec = now - 1.0
            sec_count = 0
            for ts in reversed(dq):
                if ts > cutoff_sec:
                    sec_count += 1
                else:
                    break

            min_count = len(dq)

            if sec_count >= self.per_second:
                rem_sec = 0
                rem_min = max(0, self.per_minute - min_count)
                return False, 1, rem_sec, rem_min

            if min_count >= self.per_minute:
                oldest_in_min = dq[0]
                retry_after = max(1, int(60.0 - (now - oldest_in_min)) + 1)
                rem_sec = max(0, self.per_second - sec_count)
                return False, retry_after, rem_sec, 0

            dq.append(now)
            rem_sec = max(0, self.per_second - (sec_count + 1))
            rem_min = max(0, self.per_minute - (min_count + 1))
            return True, 0, rem_sec, rem_min

_rate_limiter = _SlidingWindowRateLimiter(
    per_second=RATE_LIMIT_PER_SECOND,
    per_minute=RATE_LIMIT_PER_MINUTE,
)

def _extract_client_ip(request: Request) -> str:
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    if request.client and request.client.host:
        return request.client.host
    return "unknown"

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.method == "OPTIONS" or request.url.path in _RATE_EXEMPT_PATHS:
        return await call_next(request)

    client_ip = _extract_client_ip(request)
    allowed, retry_after, rem_sec, rem_min = _rate_limiter.check(client_ip)

    rl_headers = {
        "X-RateLimit-Limit-Minute": str(RATE_LIMIT_PER_MINUTE),
        "X-RateLimit-Remaining-Minute": str(rem_min),
        "X-RateLimit-Limit-Second": str(RATE_LIMIT_PER_SECOND),
        "X-RateLimit-Remaining-Second": str(rem_sec),
    }

    if not allowed:
        rl_headers["Retry-After"] = str(retry_after)
        return JSONResponse(
            status_code=429,
            content={
                "success": False,
                "detail": f"Rate limit exceeded ({RATE_LIMIT_PER_SECOND} req/s burst, {RATE_LIMIT_PER_MINUTE} req/min). Retry in {retry_after}s.",
                "retry_after_seconds": retry_after,
            },
            headers=rl_headers,
        )

    response = await call_next(request)
    for k, v in rl_headers.items():
        response.headers[k] = v
    return response

def require_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key", description="Admin/ingestion API key."),
) -> str:
    configured_key = (os.environ.get("API_REFRESH_KEY") or os.environ.get("RBWR_API_KEY") or "").strip()
    if not configured_key:
        raise HTTPException(
            status_code=503,
            detail="Server refresh API key is not configured. Set API_REFRESH_KEY in .env.",
        )

    provided = (x_api_key or "").strip()
    if not provided or not secrets.compare_digest(provided, configured_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
    return provided

class ErrorResponse(BaseModel):
    detail: str = Field(..., description="Human-readable error message.")
    success: Optional[bool] = Field(None, description="Explicit failure flag on rate-limit responses.")
    retry_after_seconds: Optional[int] = Field(None, description="Seconds to wait before retrying (HTTP 429).")

COMMON_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    429: {"model": ErrorResponse, "description": "Dual-window IP rate limit exceeded."},
}

class CalculateRequest(BaseModel):
    unit: int = Field(1, ge=1, le=2, description="Reactor unit number (1 or 2).")
    demand: Optional[float] = Field(None, description="Target electrical demand (MW).")
    thermal: Optional[float] = Field(None, description="Reactor thermal power / APRM / RTP (%).")
    recirc_override: Optional[float] = Field(None, description="Optional recirculation flow override (%).")

class ReactorMetrics(BaseModel):
    model_config = ConfigDict(extra="allow")

    unit: int
    demand_mwe: float
    thermal_percent: float
    rtp_percent: float
    aprm_percent: float
    flow_kg_s: float
    gen_load_mwe: float
    station_usage_mwe: float
    net_output_mwe: float
    recirc_pump_speed: float
    is_recirc_overridden: bool
    scram_risk: bool
    scram_limit_percent: float
    parameters: dict[str, Any]
    regression_parameters: dict[str, Any]

class CalculateResponse(BaseModel):
    success: bool = True
    data: ReactorMetrics

class StatusResponse(BaseModel):
    status: str = Field(..., examples=["ok"])
    service: str = Field(..., examples=["RBWR Utility REST API"])
    timestamp: str
    uptime_seconds: float
    uptime: str
    version: str

class VersionReleaseResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: str = Field(..., examples=["v2.0.0"])
    tag_name: Optional[str] = None
    name: Optional[str] = None
    published_at: Optional[str] = None
    html_url: Optional[str] = None
    body: Optional[str] = None

class PublicServerState(BaseModel):
    model_config = ConfigDict(extra="allow")

    Unit1: Optional[dict[str, Any]] = None
    Unit2: Optional[dict[str, Any]] = None
    version: Optional[Any] = None

class PublicServerEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    jobId: str
    id: Optional[str] = None
    playerCount: int = 0
    lastHeartbeat: Optional[str] = None
    privateServerOwnerId: Optional[str] = None
    is_private: Optional[bool] = None
    top_score: Optional[float] = None
    state: Optional[PublicServerState] = None

class PublicServersData(BaseModel):
    model_config = ConfigDict(extra="allow")

    servers: list[PublicServerEntry] = []

class PublicServersResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    success: bool = True
    data: PublicServersData

class LatestServersResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    success: Optional[bool] = None
    servers: Optional[dict[str, Any]] = None

class ServerCard(BaseModel):
    model_config = ConfigDict(extra="allow")

    job_id: str
    short_id: Optional[str] = None
    player_count: Optional[int] = None
    is_private: Optional[bool] = None
    private_server_owner_id: Optional[str] = None
    is_persistent: Optional[bool] = None
    is_archived: Optional[bool] = None
    top_score: Optional[float] = None
    total_mw: Optional[float] = None
    last_seen: Optional[Any] = None

class ServerListResponse(BaseModel):
    success: bool = True
    total: int
    limit: int
    offset: int
    servers: list[ServerCard]

class ActiveServersResponse(BaseModel):
    success: bool = True
    total: int
    servers: list[ServerCard]

class HistoricalServersResponse(BaseModel):
    success: bool = True
    servers: list[ServerCard]
    total: int
    page: int
    per_page: int
    total_pages: int

class ServerLookupResponse(BaseModel):
    success: bool = True
    found: bool
    server: Optional[ServerCard] = None

class UnitFuelStats(BaseModel):
    model_config = ConfigDict(extra="allow")

    estimated_fuel: Optional[float] = None

class UnitSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    unit: int
    running: bool
    aprm: float
    rtp: float
    demand: Optional[float] = None
    demand_label: str
    demand_time_left: float
    output_mw: float
    reactor_temp: float
    pressure: float
    reactor_level: float
    deaerator_level: float
    hotwell_level: float
    xenon: float
    iodine: float
    recirc: float
    scram: bool
    turbine_trip: bool
    offsite_power: Optional[Any] = None
    points_per_second: float
    fuel: UnitFuelStats
    raw: dict[str, Any] = {}

class ServerDetailResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    success: bool = True
    job_id: str
    short_id: str
    is_private: bool
    is_historical: bool
    player_count: Optional[int] = None
    latest_timestamp: Optional[str] = None
    age_seconds: float
    age_human: str
    snapshot_count: int
    top_score: float
    points_rate: float
    points_rate_str: str
    unit1: Optional[UnitSnapshot] = None
    unit2: Optional[UnitSnapshot] = None

class ServerUnitsResponse(BaseModel):
    success: bool = True
    job_id: str
    timestamp: Optional[str] = None
    unit1: UnitSnapshot
    unit2: UnitSnapshot

class ScoreBreakdownResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    success: bool = True
    job_id: str
    score: float
    breakdown: dict[str, Any]

class SnapshotsResponse(BaseModel):
    success: bool = True
    job_id: str
    snapshot_count: int
    snapshots: dict[str, Any]

class FuelEstimateResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    success: bool = True
    job_id: str

class IncidentEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp: str
    unit: int
    event: str
    aprm: Optional[float] = None
    output_mw: Optional[float] = None
    offsite_power: Optional[Any] = None
    demand_code: Optional[int] = None
    label: Optional[str] = None

class IncidentsResponse(BaseModel):
    success: bool = True
    job_id: str
    snapshots_scanned: int
    counts: dict[str, int]
    total_events: int
    events: list[IncidentEvent]

class ChartsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    success: bool = True
    job_id: str
    last_heartbeat_age: Any = 0
    charts: list[Any] = []

class LeaderboardEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    rank: int
    job_id: str
    short_id: Optional[str] = None
    is_private: bool
    is_historical: bool
    player_count: Optional[int] = None
    max_players: Optional[int] = None
    top_score: Optional[float] = None
    points_rate: Optional[float] = None
    total_mw: Optional[float] = None
    u1_mw: Optional[float] = None
    u2_mw: Optional[float] = None
    uptime_str: Optional[str] = None
    latest_timestamp: Optional[str] = None

class LeaderboardResponse(BaseModel):
    success: bool = True
    sort: str
    total: int
    leaderboard: list[LeaderboardEntry]

class GridSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    success: bool = True
    timestamp: str
    active_servers: int
    public_servers: int
    private_servers: int
    total_public_players: int
    unit1_total_mw: float
    unit2_total_mw: float
    plant_total_mw: float
    combined_pps: float
    charts: Optional[list[Any]] = None

class RefreshResponse(BaseModel):
    success: bool
    refreshed_at: str

class ArchiveDayInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    date: str
    filename: Optional[str] = None
    is_compressed: Optional[bool] = None
    server_count: Optional[int] = None
    size_bytes: Optional[int] = None

class ArchivesListResponse(BaseModel):
    success: bool = True
    days: list[ArchiveDayInfo]
    stats: dict[str, Any]

class ArchiveDayResponse(BaseModel):
    success: bool = True
    date: str
    filename: str
    is_compressed: bool
    total_servers: int
    servers: list[ServerCard]

class TicketItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: Optional[int] = None
    title: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None

class TicketsResponse(BaseModel):
    tickets: list[TicketItem]

def _get_latest_snapshot_from_dict(snapshots: dict) -> tuple[Optional[str], dict]:
    valid_ts = [k for k in core.safe_dict_keys(snapshots) if not str(k).startswith("_")]
    if not valid_ts:
        return None, {}
    latest_ts = max(valid_ts)
    st = snapshots.get(latest_ts)
    return latest_ts, st if isinstance(st, dict) else {}

def _extract_unit_snapshot(unit_dict: Any, unit_num: int, snapshots: Optional[dict] = None) -> dict[str, Any]:
    u = unit_dict if isinstance(unit_dict, dict) else {}
    demand_key = "DemandU1" if unit_num == 1 else "DemandU2"
    demand_val = core.safe_demand_numeric(u.get(demand_key) if u.get(demand_key) is not None else u.get("Demand"))
    aprm_val = core.safe_float(u.get("APRM"), 0.0)
    rtp_val = core.safe_float(u.get("RTP"), aprm_val)
    output_mw = round(core.get_unit_output_mw(u), 2)
    fuel_stats = core.get_card_unit_fuel_stats(snapshots, f"Unit{unit_num}", u) if snapshots else {
        "estimated_fuel": core.safe_demand_numeric(u.get("EstimatedFuel")),
    }
    return {
        "unit": unit_num,
        "running": aprm_val > 5.0,
        "aprm": aprm_val,
        "rtp": rtp_val,
        "demand": demand_val,
        "demand_label": core.format_demand_value(demand_val),
        "demand_time_left": core.safe_float(u.get("Demand Time Left"), 0.0),
        "output_mw": output_mw,
        "reactor_temp": core.safe_float(u.get("Reactor Temp"), 0.0),
        "pressure": core.safe_float(u.get("Pressure"), 0.0),
        "reactor_level": core.safe_float(u.get("ReactorLevel"), 0.0),
        "deaerator_level": core.safe_float(u.get("Deareator Level", u.get("Deaerator Level")), 0.0),
        "hotwell_level": core.safe_float(u.get("Hotwell Level"), 0.0),
        "xenon": core.safe_float(u.get("Xenon"), 0.0),
        "iodine": core.safe_float(u.get("Iodine"), 0.0),
        "recirc": core.safe_float(u.get(f"Recirc{unit_num}"), 0.0),
        "scram": bool(u.get("SCRAM") or u.get("Reactor Scram State")),
        "turbine_trip": bool(u.get("TurbineTrip") or u.get("Turbine Trip")),
        "offsite_power": u.get("Offsite Power"),
        "points_per_second": core.safe_float(u.get("PointsPerSecond"), 0.0),
        "fuel": fuel_stats,
        "raw": u,
    }

def _collect_all_server_cards(
    status: Literal["active", "historical", "all"] = "active",
    visibility: Literal["all", "public", "private"] = "all",
    query: str = "",
) -> list[dict]:
    servers_data = core.get_sc_data("servers.json") or {}
    if not servers_data:
        return []
    persistent_ids = set(core.load_persistent_servers().get("persistent", {}).keys())

    cards: list[dict] = []
    if status in ("active", "all"):
        cards.extend(core.get_active_cards_base(servers_data, persistent_ids))
    if status in ("historical", "all"):
        active_jids = {c["job_id"] for c in cards}
        for hc in core.get_historical_cards_base(servers_data, persistent_ids):
            if hc["job_id"] not in active_jids:
                cards.append(hc)

    if visibility == "public":
        cards = [c for c in cards if not c.get("is_private")]
    elif visibility == "private":
        cards = [c for c in cards if c.get("is_private")]

    q = query.strip().lower()
    if q:
        clean_q = q.replace("-", "")
        filtered = []
        for c in cards:
            jid = (c.get("job_id") or "").lower()
            sid = (c.get("short_id") or "").lower()
            if (
                q in jid
                or (sid and q in sid)
                or (clean_q and clean_q in jid.replace("-", ""))
                or (sid and clean_q in sid.replace("-", ""))
                or core.is_exact_job_or_server_id_match(q, c.get("job_id", ""))
            ):
                filtered.append(c)
        cards = filtered

    return [_normalize_api_server_card(c) for c in cards]

def _normalize_api_server_card(card: dict) -> dict:
    out = dict(card)
    if "privateServerOwnerId" in out:
        out["private_server_owner_id"] = out.pop("privateServerOwnerId")
    return out

SCALAR_DOCS_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>RBWR Utility REST API — Reference</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
  <style>
    :root {
      --scalar-font: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      --scalar-font-code: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
      --scalar-background-1: #09090b;
      --scalar-background-2: #111116;
      --scalar-background-3: #18181f;
      --scalar-background-accent: rgba(56, 189, 248, 0.12);
      --scalar-color-1: #f4f4f5;
      --scalar-color-2: #a1a1aa;
      --scalar-color-3: #71717a;
      --scalar-color-accent: #38bdf8;
      --scalar-border-color: rgba(255, 255, 255, 0.08);
    }
    html, body {
      margin: 0;
      padding: 0;
      background-color: #09090b;
      color: #f4f4f5;
    }
    .rbwr-api-topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.75rem 1.5rem;
      background: #0c0c10;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      font-family: var(--scalar-font);
      font-size: 0.8125rem;
    }
    .rbwr-api-topbar-brand {
      display: flex;
      align-items: center;
      gap: 0.625rem;
      font-weight: 600;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: #f4f4f5;
    }
    .rbwr-api-topbar-badge {
      padding: 0.125rem 0.5rem;
      border-radius: 9999px;
      background: rgba(56, 189, 248, 0.12);
      border: 1px solid rgba(56, 189, 248, 0.3);
      color: #38bdf8;
      font-family: var(--scalar-font-code);
      font-size: 0.7rem;
      font-weight: 500;
    }
    .rbwr-api-topbar-links {
      display: flex;
      align-items: center;
      gap: 1.25rem;
    }
    .rbwr-api-topbar-links a {
      color: #a1a1aa;
      text-decoration: none;
      transition: color 0.15s ease;
    }
    .rbwr-api-topbar-links a:hover {
      color: #38bdf8;
    }
  </style>
</head>
<body>
  <header class="rbwr-api-topbar">
    <div class="rbwr-api-topbar-brand">
      <span>RBWR Utility REST API</span>
      <span class="rbwr-api-topbar-badge">v2.0.0</span>
    </div>
    <nav class="rbwr-api-topbar-links">
      <a href="/api/openapi.json" target="_blank" rel="noopener">OpenAPI JSON</a>
      <a href="/servers">Server Browser</a>
      <a href="/">Home</a>
    </nav>
  </header>
  <div id="scalar-root"></div>
  <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
  <script>
    Scalar.createApiReference('#scalar-root', {
      url: '/api/openapi.json',
      theme: 'kepler',
      darkMode: true,
      forceDarkModeState: 'dark',
      hideDarkModeToggle: true,
      hideClientButton: true,
      showSidebar: true,
      defaultOpenAllTags: false,
      metaData: {
        title: 'RBWR Utility REST API Reference'
      }
    });
  </script>
</body>
</html>
"""

@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/api/docs")

@app.get("/api/docs", include_in_schema=False)
def scalar_docs():
    return HTMLResponse(content=SCALAR_DOCS_HTML)

@app.get(
    "/api/status",
    response_model=StatusResponse,
    responses=COMMON_ERROR_RESPONSES,
    tags=["Status & Meta"],
    summary="API health and uptime status",
    description="Returns live service health status, UTC timestamp, uptime, and latest release version.",
)
@app.head("/api/status", include_in_schema=False)
def status_check(response: Response):
    uptime_sec = max(0.0, round(time.time() - core.SERVER_START_TIME, 2))
    release = core.get_github_latest_release()
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return {
        "status": "ok",
        "service": "RBWR Utility REST API",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": uptime_sec,
        "uptime": core.format_uptime(uptime_sec),
        "version": release.get("version", "unknown"),
    }

@app.get(
    "/api/version",
    response_model=VersionReleaseResponse,
    responses=COMMON_ERROR_RESPONSES,
    tags=["Status & Meta"],
    summary="Latest RBWR Utility release",
    description="Returns the latest RBWR-Utility release metadata fetched from GitHub (cached for 5 minutes).",
)
def get_latest_version(
    refresh: bool = Query(False, description="Force refresh cached GitHub release metadata."),
):
    return core.get_github_latest_release(force_refresh=refresh)

def _execute_calculation(
    unit: int,
    demand: Optional[float],
    thermal: Optional[float],
    recirc_override: Optional[float],
) -> dict:
    clean_unit = unit if unit in (1, 2) else 1
    try:
        metrics = core.calculate_reactor_metrics(
            unit=clean_unit,
            demand=demand,
            thermal=thermal,
            recirc_override=recirc_override,
        )
        return {"success": True, "data": metrics}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as ex:
        logger.error(f"Error executing reactor calculations: {ex}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(ex))

@app.get(
    "/api/calculate",
    response_model=CalculateResponse,
    responses={
        **COMMON_ERROR_RESPONSES,
        400: {"model": ErrorResponse, "description": "Invalid calculation input parameters."},
        500: {"model": ErrorResponse, "description": "Internal solver error."},
    },
    tags=["Calculator"],
    summary="Calculate reactor metrics (GET)",
    description="Solves RBWR Unit 1 / Unit 2 electrical output, APRM/RTP, recirculation flow, MSS, and OCL from either `demand` or `thermal`.",
)
def calculate_get(
    unit: int = Query(1, ge=1, le=2, description="Reactor unit (1 or 2)."),
    demand: Optional[float] = Query(None, description="Target electrical demand in MW."),
    thermal: Optional[float] = Query(None, description="Thermal power / APRM / RTP percentage."),
    recirc_override: Optional[float] = Query(None, description="Manual recirculation pump speed override (%)."),
):
    return _execute_calculation(unit, demand, thermal, recirc_override)

@app.post(
    "/api/calculate",
    response_model=CalculateResponse,
    responses={
        **COMMON_ERROR_RESPONSES,
        400: {"model": ErrorResponse, "description": "Invalid calculation input parameters."},
        500: {"model": ErrorResponse, "description": "Internal solver error."},
    },
    tags=["Calculator"],
    summary="Calculate reactor metrics (POST)",
    description="JSON POST counterpart to `GET /api/calculate` for programmatic reactor metric calculations.",
)
def calculate_post(body: CalculateRequest):
    return _execute_calculation(body.unit, body.demand, body.thermal, body.recirc_override)

def _filter_public_servers_payload(
    payload: dict,
    min_players: Optional[int] = None,
    min_mw: Optional[float] = None,
    running_only: bool = False,
) -> dict:
    servers = payload.get("data", {}).get("servers", [])
    if min_players is None and min_mw is None and not running_only:
        return payload

    filtered = []
    for s in servers:
        if min_players is not None and (s.get("playerCount") or 0) < min_players:
            continue
        st = s.get("state") or {}
        u1 = st.get("Unit1") or {}
        u2 = st.get("Unit2") or {}
        u1_mw = core.get_unit_output_mw(u1)
        u2_mw = core.get_unit_output_mw(u2)
        if min_mw is not None and (u1_mw + u2_mw) < min_mw:
            continue
        if running_only:
            u1_aprm = core.safe_float(u1.get("APRM"), 0.0)
            u2_aprm = core.safe_float(u2.get("APRM"), 0.0)
            if u1_aprm <= 5.0 and u2_aprm <= 5.0:
                continue
        filtered.append(s)

    out = dict(payload)
    out["data"] = dict(payload.get("data", {}), servers=filtered)
    return out

@app.get(
    "/api/public/servers",
    response_model=PublicServersResponse,
    responses={
        **COMMON_ERROR_RESPONSES,
        502: {"model": ErrorResponse, "description": "Upstream game API unreachable."},
        503: {"model": ErrorResponse, "description": "Upstream game API unavailable."},
    },
    tags=["Hydrogen Replacement"],
    summary="Drop-in Hydrogen public servers endpoint",
    operation_id="get_public_servers_hydrogen",
    description=(
        "Direct replacement for `https://hydrogen.realisticbwr.org/api/public/servers`. "
        "Returns the upstream-compatible server list enriched with computed MW output, `EstimatedFuel`, `top_score`, "
        "and accurate public/private visibility & player counts, with optional filters."
    ),
)
@app.get(
    "/api/public-servers",
    response_model=PublicServersResponse,
    include_in_schema=False,
)
def public_servers_endpoint(
    public_only: bool = Query(False, description="When true, exclude private servers."),
    min_players: Optional[int] = Query(None, ge=0, description="Filter to servers with at least N players."),
    min_mw: Optional[float] = Query(None, ge=0, description="Filter to servers producing at least X combined MW."),
    running_only: bool = Query(False, description="When true, include only servers with at least one unit above 5% APRM."),
):
    payload, status_code = core.fetch_or_get_public_servers(public_only=public_only)
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=payload.get("error", "Unable to reach game API"))
    return _filter_public_servers_payload(payload, min_players=min_players, min_mw=min_mw, running_only=running_only)

@app.get(
    "/api/servers/latest",
    response_model=LatestServersResponse,
    responses=COMMON_ERROR_RESPONSES,
    tags=["Hydrogen Replacement"],
    summary="Latest raw upstream snapshot batch",
    description="Returns the most recent snapshot batch polled from upstream, or falls back to stored server data.",
)
def get_latest_servers():
    latest = core.get_latest_servers_data()
    if latest:
        return latest
    servers_data = core.get_sc_data("servers.json")
    return {"success": True, "servers": servers_data}

@app.get(
    "/api/servers",
    response_model=ServerListResponse,
    responses=COMMON_ERROR_RESPONSES,
    tags=["Servers"],
    summary="Unified filterable server directory",
    description="Lists RBWR servers with filtering by lifecycle status, visibility, search query, minimum players/MW, and sorting.",
)
def list_servers(
    status: Literal["active", "historical", "all"] = Query("active", description="Server lifecycle filter."),
    visibility: Literal["all", "public", "private"] = Query("all", description="Server visibility filter."),
    q: str = Query("", description="Search by full Job ID, compact UUID, 8-char prefix, or short ID (e.g. `481e-4429`)."),
    min_players: Optional[int] = Query(None, ge=0, description="Minimum player count."),
    min_mw: Optional[float] = Query(None, ge=0, description="Minimum combined plant output (MW)."),
    running_only: bool = Query(False, description="Only include servers where Unit 1 or Unit 2 is above 5% APRM."),
    sort: Literal[
        "top_servers",
        "players_desc",
        "players_asc",
        "points_desc",
        "running_first",
        "snapshots_desc",
        "snapshots_asc",
        "oldest",
        "newest",
        "public_first",
        "private_first",
    ] = Query("top_servers", description="Sort order."),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of servers to return."),
    offset: int = Query(0, ge=0, description="Pagination offset."),
):
    cards = _collect_all_server_cards(status=status, visibility=visibility, query=q)

    if min_players is not None:
        cards = [c for c in cards if (c.get("player_count") or 0) >= min_players]
    if min_mw is not None:
        cards = [
            c for c in cards
            if ((c.get("unit1", {}).get("output_mw") or 0.0) + (c.get("unit2", {}).get("output_mw") or 0.0)) >= min_mw
        ]
    if running_only:
        cards = [c for c in cards if c.get("u1_running") or c.get("u2_running")]

    sorted_cards = core.sort_historical_cards(cards, sort)
    total = len(sorted_cards)
    sliced = sorted_cards[offset:offset + limit]
    return {
        "success": True,
        "total": total,
        "limit": limit,
        "offset": offset,
        "servers": sliced,
    }

@app.get(
    "/api/servers/active",
    response_model=ActiveServersResponse,
    responses=COMMON_ERROR_RESPONSES,
    tags=["Servers"],
    summary="Active servers list (JSON)",
    description="Returns currently active (and persistent) servers with summarized unit metrics, Top Score, and fuel assessments.",
)
def get_active_servers(
    q: str = Query("", description="Optional Job ID / short ID filter."),
    visibility: Literal["all", "public", "private"] = Query("all", description="Visibility filter."),
    sort: str = Query("top_servers", description="Sort order (`top_servers`, `players_desc`, `points_desc`, etc.)."),
):
    cards = _collect_all_server_cards(status="active", visibility=visibility, query=q)
    cards = core.sort_historical_cards(cards, sort)
    return {
        "success": True,
        "total": len(cards),
        "servers": cards,
    }

@app.get(
    "/api/servers/historical",
    response_model=HistoricalServersResponse,
    responses=COMMON_ERROR_RESPONSES,
    tags=["Servers"],
    summary="Historical servers list (JSON)",
    description="Paginated list of historical servers with search and sorting.",
)
def get_historical_servers(
    page: int = Query(1, ge=1, description="Page number (1-indexed)."),
    per_page: int = Query(21, ge=1, le=100, description="Items per page (1-100)."),
    q: str = Query("", description="Optional Job ID or short ID search query."),
    sort: str = Query("top_servers", description="Sort order."),
):
    servers_data = core.get_sc_data("servers.json")
    if not servers_data:
        return {"success": True, "servers": [], "total": 0, "page": page, "per_page": per_page, "total_pages": 0}

    persistent_ids = set(core.load_persistent_servers().get("persistent", {}).keys())
    base_cards = core.get_historical_cards_base(servers_data, persistent_ids)

    clean_q_raw = q.strip().lower()
    if clean_q_raw:
        clean_q = clean_q_raw.replace("-", "")
        filtered = []
        for c in base_cards:
            jid = c.get("job_id", "")
            sid = c.get("short_id", "")
            if (
                clean_q_raw in jid.lower()
                or (sid and clean_q_raw in sid.lower())
                or (clean_q and clean_q in jid.lower().replace("-", ""))
                or (sid and clean_q in sid.lower().replace("-", ""))
                or core.is_exact_job_or_server_id_match(clean_q_raw, jid)
            ):
                filtered.append(c)
    else:
        filtered = list(base_cards)

    sorted_cards = core.sort_historical_cards(filtered, sort)
    total = len(sorted_cards)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    clamped_page = min(page, total_pages)
    start_idx = (clamped_page - 1) * per_page
    page_cards = [_normalize_api_server_card(c) for c in sorted_cards[start_idx:start_idx + per_page]]

    return {
        "success": True,
        "servers": page_cards,
        "total": total,
        "page": clamped_page,
        "per_page": per_page,
        "total_pages": total_pages,
    }

@app.get(
    "/api/servers/lookup",
    response_model=ServerLookupResponse,
    responses=COMMON_ERROR_RESPONSES,
    tags=["Servers"],
    summary="Lookup a single server card",
    description="Searches live servers and daily archives for an exact Job ID, compact UUID, 8-char prefix, or short ID.",
)
def lookup_server(
    q: str = Query(..., min_length=1, description="Job ID, compact UUID, 8-char prefix, or short ID (e.g. `77f6-4b2f`)."),
):
    query = q.strip()
    servers_data = core.get_sc_data("servers.json") or {}
    matched_cards = core.build_server_cards(servers_data, search_query=query)
    target_card = next((c for c in matched_cards if core.is_exact_job_or_server_id_match(query, c.get("job_id", ""))), None)

    if not target_card:
        archived_jid, archived_snaps = core.get_archived_server_snapshots(query)
        if archived_jid and archived_snaps:
            archived_cards = core.build_server_cards({archived_jid: archived_snaps}, search_query=query, is_archived=True)
            if archived_cards:
                target_card = archived_cards[0]

    if not target_card:
        return {"success": True, "found": False}
    return {"success": True, "found": True, "server": _normalize_api_server_card(target_card)}

@app.get(
    "/api/servers/{job_id}",
    response_model=ServerDetailResponse,
    responses={
        **COMMON_ERROR_RESPONSES,
        404: {"model": ErrorResponse, "description": "Server not found in active, historical, or archived storage."},
    },
    tags=["Servers"],
    summary="Get full server state and summary",
    description="Returns complete server metadata, normalized Unit 1 & Unit 2 operational stats, fuel assessment, and Top Score.",
)
def get_server_detail(
    job_id: str = Path(..., description="Full Job ID, 8-char prefix, or short ID (e.g. `481e-4429`)."),
    unit: Optional[int] = Query(None, ge=1, le=2, description="Optional reactor unit filter (`1` or `2`). When set, returns only that unit's operational stats."),
):
    matched_job_id, snapshots = core.resolve_server_snapshots(job_id)
    if not snapshots or not matched_job_id:
        raise HTTPException(status_code=404, detail=f"Server '{job_id}' not found.")

    clean_snaps = {k: v for k, v in core.safe_dict_items(snapshots) if not str(k).startswith("_")}
    latest_ts, latest_state = _get_latest_snapshot_from_dict(clean_snaps)
    now_utc = datetime.now(timezone.utc)
    age_sec = core.convert_ISO_to_secs(latest_ts, now=now_utc) if latest_ts else 0
    is_private = core.get_server_visibility(matched_job_id, snapshots, latest_state, is_active=(age_sec <= 600))
    is_historical = core.is_server_historical(matched_job_id, snapshots, latest_state, is_private=is_private, age_sec=age_sec)
    player_count = None if is_private else core.get_server_player_count(matched_job_id, snapshots, latest_state, is_private=False)

    u1_raw = latest_state.get("Unit1", {})
    u2_raw = latest_state.get("Unit2", {})
    pts_info = core.calculate_server_points_rate(u1_raw, u2_raw, job_id=matched_job_id, latest_state=latest_state)
    score = core.calculate_server_top_score(clean_snaps, now_utc=now_utc)
    j_parts = [p for p in matched_job_id.split("-") if p]
    short_id = f"{j_parts[1]}-{j_parts[2]}" if len(j_parts) >= 3 else ""

    payload: dict[str, Any] = {
        "success": True,
        "job_id": matched_job_id,
        "short_id": short_id,
        "is_private": is_private,
        "is_historical": is_historical,
        "player_count": player_count,
        "latest_timestamp": latest_ts,
        "age_seconds": age_sec,
        "age_human": core.format_heartbeat_age(age_sec),
        "snapshot_count": len(clean_snaps),
        "top_score": score,
        "points_rate": pts_info["points_rate"],
        "points_rate_str": pts_info["points_rate_str"],
    }
    if unit in (None, 1):
        payload["unit1"] = _extract_unit_snapshot(u1_raw, 1, clean_snaps)
    if unit in (None, 2):
        payload["unit2"] = _extract_unit_snapshot(u2_raw, 2, clean_snaps)
    return payload

@app.get(
    "/api/servers/{job_id}/units",
    response_model=ServerUnitsResponse,
    responses={
        **COMMON_ERROR_RESPONSES,
        404: {"model": ErrorResponse, "description": "Server not found."},
    },
    tags=["Servers"],
    summary="Get normalized Unit 1 & Unit 2 operational stats",
)
def get_server_units(
    job_id: str = Path(..., description="Full Job ID or short ID."),
):
    matched_job_id, snapshots = core.resolve_server_snapshots(job_id)
    if not snapshots or not matched_job_id:
        raise HTTPException(status_code=404, detail=f"Server '{job_id}' not found.")

    clean_snaps = {k: v for k, v in core.safe_dict_items(snapshots) if not str(k).startswith("_")}
    latest_ts, latest_state = _get_latest_snapshot_from_dict(clean_snaps)
    return {
        "success": True,
        "job_id": matched_job_id,
        "timestamp": latest_ts,
        "unit1": _extract_unit_snapshot(latest_state.get("Unit1", {}), 1, clean_snaps),
        "unit2": _extract_unit_snapshot(latest_state.get("Unit2", {}), 2, clean_snaps),
    }

@app.get(
    "/api/servers/{job_id}/score_breakdown",
    response_model=ScoreBreakdownResponse,
    responses={
        **COMMON_ERROR_RESPONSES,
        400: {"model": ErrorResponse, "description": "Job ID is required."},
        404: {"model": ErrorResponse, "description": "Server not found."},
    },
    tags=["Server Analytics"],
    summary="Detailed Top Score breakdown",
    description="Evaluates the rolling 60-minute snapshot window and returns Top Score (0-100), PPS sustainability weight, synergy, and per-snapshot log.",
)
def server_score_breakdown(
    job_id: str = Path(..., description="Full Job ID or short ID."),
):
    query = (job_id or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Job ID is required.")

    matched_job_id, snapshots = core.resolve_server_snapshots(query)
    if not snapshots or not matched_job_id:
        raise HTTPException(status_code=404, detail=f"Server '{query}' not found.")

    now_utc = datetime.now(timezone.utc)
    score, breakdown = core.calculate_server_top_score(snapshots, now_utc=now_utc, return_breakdown=True)
    breakdown["job_id"] = matched_job_id
    j_parts = [p for p in matched_job_id.split("-") if p]
    breakdown["short_id"] = f"{j_parts[1]}-{j_parts[2]}" if len(j_parts) >= 3 else ""

    return {
        "success": True,
        "job_id": matched_job_id,
        "score": score,
        "breakdown": breakdown,
    }

@app.get(
    "/api/servers/{job_id}/snapshots",
    response_model=SnapshotsResponse,
    responses={
        **COMMON_ERROR_RESPONSES,
        404: {"model": ErrorResponse, "description": "Server not found."},
    },
    tags=["Server Analytics"],
    summary="Raw timestamped snapshot history",
    description="Returns timestamped state snapshots for a server, optionally limited to the most recent N or filtered by age.",
)
def server_snapshots_by_id(
    job_id: str = Path(..., description="Full Job ID or short ID."),
    limit: Optional[int] = Query(None, ge=1, le=5000, description="Return only the N most recent snapshots."),
    max_age_seconds: Optional[int] = Query(None, ge=1, description="Only include snapshots newer than N seconds."),
):
    matched_job_id, snapshots = core.resolve_server_snapshots(job_id.strip())
    if not snapshots or not matched_job_id:
        raise HTTPException(status_code=404, detail=f"Server '{job_id}' not found.")

    clean_items = sorted(
        [(k, v) for k, v in core.safe_dict_items(snapshots) if not str(k).startswith("_")],
        key=lambda x: str(x[0]),
    )
    if max_age_seconds is not None:
        now_utc = datetime.now(timezone.utc)
        clean_items = [(k, v) for k, v in clean_items if core.convert_ISO_to_secs(str(k), now=now_utc) <= max_age_seconds]
    if limit is not None:
        clean_items = clean_items[-limit:]

    clean_snapshots = dict(clean_items)
    return {
        "success": True,
        "job_id": matched_job_id,
        "snapshot_count": len(clean_snapshots),
        "snapshots": clean_snapshots,
    }

@app.get(
    "/api/servers/{job_id}/fuel",
    response_model=FuelEstimateResponse,
    responses={
        **COMMON_ERROR_RESPONSES,
        404: {"model": ErrorResponse, "description": "Server not found."},
    },
    tags=["Server Analytics"],
    summary="Kalman-filtered fuel assessment",
    description="Evaluates Unit 1 and Unit 2 fuel percentages, uncertainty, and projected depletion/refuel state.",
)
def server_fuel_by_id(
    job_id: str = Path(..., description="Full Job ID or short ID."),
):
    matched_job_id, snapshots = core.resolve_server_snapshots(job_id.strip())
    if not snapshots or not matched_job_id:
        raise HTTPException(status_code=404, detail=f"Server '{job_id}' not found.")

    clean_snapshots = {k: v for k, v in core.safe_dict_items(snapshots) if not str(k).startswith("_")}
    fuel_eval = core.evaluate_server_fuel(clean_snapshots)
    return {
        "success": True,
        "job_id": matched_job_id,
        **fuel_eval.to_dict(),
    }

@app.get(
    "/api/servers/{job_id}/incidents",
    response_model=IncidentsResponse,
    responses={
        **COMMON_ERROR_RESPONSES,
        404: {"model": ErrorResponse, "description": "Server not found."},
    },
    tags=["Server Analytics"],
    summary="Server incident & grid event timeline",
    description="Scans stored snapshots to detect SCRAMs, turbine trips, Loss of Offsite Power (LOOP), and special demand events (Maintenance/Reset/Evacuation).",
)
def server_incidents(
    job_id: str = Path(..., description="Full Job ID or short ID."),
    max_age_seconds: Optional[int] = Query(None, ge=1, description="Only inspect snapshots newer than N seconds."),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of incident events to return (newest first)."),
):
    matched_job_id, snapshots = core.resolve_server_snapshots(job_id.strip())
    if not snapshots or not matched_job_id:
        raise HTTPException(status_code=404, detail=f"Server '{job_id}' not found.")

    clean_items = sorted(
        [(str(k), v) for k, v in core.safe_dict_items(snapshots) if not str(k).startswith("_") and isinstance(v, dict)],
        key=lambda x: x[0],
    )
    if max_age_seconds is not None:
        now_utc = datetime.now(timezone.utc)
        clean_items = [
            (ts, st) for ts, st in clean_items
            if core.convert_ISO_to_secs(ts, now=now_utc) <= max_age_seconds
        ]

    special_codes = {-1: "Maintenance", -2: "LOOP", -3: "Reset", -4: "Evacuation"}
    prev_state: dict[str, tuple[bool, bool, bool, Optional[int]]] = {}
    events: list[dict[str, Any]] = []
    counts = {"scram": 0, "turbine_trip": 0, "loop": 0, "special_demand": 0}

    for ts, st in clean_items:
        for unit_num in (1, 2):
            ukey = f"Unit{unit_num}"
            u = st.get(ukey)
            if not isinstance(u, dict) or not u:
                continue
            scram = bool(u.get("SCRAM") or u.get("Reactor Scram State"))
            trip = bool(u.get("TurbineTrip") or u.get("Turbine Trip"))
            dem_num = core.safe_demand_numeric(u.get(f"DemandU{unit_num}") if u.get(f"DemandU{unit_num}") is not None else u.get("Demand"))
            dem_int = int(round(dem_num)) if dem_num is not None else None
            offsite_down = (u.get("Offsite Power") is False) or (dem_int == -2)

            prev_scram, prev_trip, prev_loop, prev_dem = prev_state.get(ukey, (False, False, False, None))
            if scram and not prev_scram:
                counts["scram"] += 1
                events.append({
                    "timestamp": ts,
                    "unit": unit_num,
                    "event": "scram",
                    "aprm": core.safe_float(u.get("APRM"), 0.0),
                    "output_mw": round(core.get_unit_output_mw(u), 2),
                })
            if trip and not prev_trip:
                counts["turbine_trip"] += 1
                events.append({
                    "timestamp": ts,
                    "unit": unit_num,
                    "event": "turbine_trip",
                    "aprm": core.safe_float(u.get("APRM"), 0.0),
                    "output_mw": round(core.get_unit_output_mw(u), 2),
                })
            if offsite_down and not prev_loop:
                counts["loop"] += 1
                events.append({
                    "timestamp": ts,
                    "unit": unit_num,
                    "event": "loop",
                    "offsite_power": u.get("Offsite Power"),
                })
            if dem_int in special_codes and dem_int != prev_dem:
                counts["special_demand"] += 1
                events.append({
                    "timestamp": ts,
                    "unit": unit_num,
                    "event": "special_demand",
                    "demand_code": dem_int,
                    "label": special_codes[dem_int],
                })
            prev_state[ukey] = (scram, trip, offsite_down, dem_int)

    events.reverse()
    return {
        "success": True,
        "job_id": matched_job_id,
        "snapshots_scanned": len(clean_items),
        "counts": counts,
        "total_events": len(events),
        "events": events[:limit],
    }

@app.get(
    "/api/servers/{job_id}/charts",
    response_model=ChartsResponse,
    responses={
        **COMMON_ERROR_RESPONSES,
        404: {"model": ErrorResponse, "description": "Server not found."},
    },
    tags=["Server Analytics"],
    summary="Downsampled time-series charts for a server",
    description="Returns LTTB-downsampled time-series datasets (output, demand, APRM, RTP, xenon, pressure, temperature, levels).",
)
def server_charts(
    job_id: str = Path(..., description="Full Job ID or short ID."),
):
    matched_job_id, snapshots = core.resolve_server_snapshots(job_id.strip())
    if not snapshots or not matched_job_id:
        raise HTTPException(status_code=404, detail=f"Server '{job_id}' not found.")

    payload = core.build_chart_payload(matched_job_id, snapshots)
    return {
        "success": True,
        "job_id": matched_job_id,
        "last_heartbeat_age": payload.get("last_heartbeat_age", 0),
        "charts": payload.get("charts", []),
    }

@app.get(
    "/api/leaderboard",
    response_model=LeaderboardResponse,
    responses=COMMON_ERROR_RESPONSES,
    tags=["Servers"],
    summary="Server performance leaderboard",
    description="Ranks active (and optionally historical) RBWR servers by Top Score, total MW output, points/sec, or player count.",
)
def server_leaderboard(
    sort: Literal["score", "mw", "pps", "players"] = Query("score", description="Ranking metric."),
    limit: int = Query(25, ge=1, le=100, description="Number of ranked entries to return."),
    include_historical: bool = Query(False, description="Include historical servers in leaderboard."),
    visibility: Literal["all", "public", "private"] = Query("all", description="Visibility filter."),
):
    cards = _collect_all_server_cards(status=("all" if include_historical else "active"), visibility=visibility)

    def _sort_key(c: dict) -> tuple:
        total_mw = (c.get("unit1", {}).get("output_mw") or 0.0) + (c.get("unit2", {}).get("output_mw") or 0.0)
        if sort == "mw":
            return (total_mw, c.get("top_score") or 0.0)
        if sort == "pps":
            return (c.get("points_rate") or 0.0, c.get("top_score") or 0.0)
        if sort == "players":
            return (c.get("player_count") or 0, c.get("top_score") or 0.0)
        return (c.get("top_score") or 0.0, c.get("points_rate") or 0.0, total_mw)

    ranked = sorted(cards, key=_sort_key, reverse=True)[:limit]
    entries = []
    for idx, c in enumerate(ranked, 1):
        u1_mw = c.get("unit1", {}).get("output_mw") or 0.0
        u2_mw = c.get("unit2", {}).get("output_mw") or 0.0
        entries.append({
            "rank": idx,
            "job_id": c["job_id"],
            "short_id": c["short_id"],
            "is_private": c["is_private"],
            "is_historical": c["is_historical"],
            "player_count": c["player_count"],
            "max_players": c["max_players"],
            "top_score": c["top_score"],
            "points_rate": c["points_rate"],
            "total_mw": round(u1_mw + u2_mw, 1),
            "u1_mw": u1_mw,
            "u2_mw": u2_mw,
            "uptime_str": c["uptime_str"],
            "latest_timestamp": c["latest_timestamp"],
        })

    return {
        "success": True,
        "sort": sort,
        "total": len(entries),
        "leaderboard": entries,
    }

@app.get(
    "/api/grid/summary",
    response_model=GridSummaryResponse,
    responses=COMMON_ERROR_RESPONSES,
    tags=["Hydrogen Replacement"],
    summary="Global RBWR plant grid summary",
    description="Aggregates live active server counts, player totals, combined Unit 1/Unit 2 MW output, combined PPS, and global power output chart series.",
)
def global_grid_summary(
    include_chart: bool = Query(True, description="Include downsampled global MW history chart series."),
):
    cards = _collect_all_server_cards(status="active", visibility="all")
    live_cards = [c for c in cards if not c.get("is_historical")]

    total_players = sum((c.get("player_count") or 0) for c in live_cards if not c.get("is_private"))
    u1_mw_total = round(sum((c.get("unit1", {}).get("output_mw") or 0.0) for c in live_cards), 1)
    u2_mw_total = round(sum((c.get("unit2", {}).get("output_mw") or 0.0) for c in live_cards), 1)
    total_pps = round(sum((c.get("points_rate") or 0.0) for c in live_cards), 2)
    public_count = sum(1 for c in live_cards if not c.get("is_private"))
    private_count = sum(1 for c in live_cards if c.get("is_private"))

    result: dict[str, Any] = {
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "active_servers": len(live_cards),
        "public_servers": public_count,
        "private_servers": private_count,
        "total_public_players": total_players,
        "unit1_total_mw": u1_mw_total,
        "unit2_total_mw": u2_mw_total,
        "plant_total_mw": round(u1_mw_total + u2_mw_total, 1),
        "combined_pps": total_pps,
    }
    if include_chart:
        global_data = core.get_sc_data("global.json") or {}
        result["charts"] = core.build_global_chart_payload(global_data).get("charts", [])
    return result

@app.post(
    "/api/servers/refresh",
    response_model=RefreshResponse,
    responses={
        **COMMON_ERROR_RESPONSES,
        401: {"model": ErrorResponse, "description": "Invalid or missing API key."},
        503: {"model": ErrorResponse, "description": "API_REFRESH_KEY is not configured on the server."},
    },
    tags=["Ingestion"],
    summary="Trigger immediate upstream server data pull (API key required)",
    description="Manually pulls fresh snapshot data from upstream RBWR endpoints and updates local JSON caches. Requires a valid `X-API-Key` header.",
)
def refresh_servers(_api_key: str = Depends(require_api_key)):
    success = core.pull_server_checker_data()
    return {"success": success, "refreshed_at": datetime.now(timezone.utc).isoformat()}

@app.get(
    "/api/archives",
    response_model=ArchivesListResponse,
    responses={
        **COMMON_ERROR_RESPONSES,
        200: {
            "description": "Archive date listing JSON, or SSE progress stream when `stream=1`.",
            "content": {"text/event-stream": {}},
        },
    },
    tags=["Archives"],
    summary="List daily server archives",
    description="Lists available archive dates and summary statistics. Pass `?stream=1` for Server-Sent Events (SSE) progress updates.",
)
async def get_archives(
    stream: int = Query(0, description="Set to `1` to stream SSE progress events (`text/event-stream`)."),
):
    if stream == 1:
        async def event_stream():
            q_events: queue.Queue = queue.Queue()
            done = object()

            def worker():
                try:
                    def on_progress(cur, total, fname, pct):
                        q_events.put({
                            "type": "progress",
                            "current": cur,
                            "total": total,
                            "filename": fname,
                            "percent": pct,
                            "status": f"Scanning archive {cur} of {total} ({fname})...",
                        })

                    days, stats = core.get_all_archive_days_info(progress_callback=on_progress)
                    q_events.put({"type": "complete", "days": days, "stats": stats})
                except Exception as e:
                    q_events.put({"type": "error", "message": str(e)})
                finally:
                    q_events.put(done)

            threading.Thread(target=worker, daemon=True).start()
            while True:
                try:
                    item = q_events.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.05)
                    continue
                if item is done:
                    break
                yield f"data: {json.dumps(item)}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    days_list, summary_stats = core.get_all_archive_days_info()
    return {"success": True, "days": days_list, "stats": summary_stats}

@app.get(
    "/api/archives/{date_str}",
    response_model=ArchiveDayResponse,
    responses={
        **COMMON_ERROR_RESPONSES,
        404: {"model": ErrorResponse, "description": "No archive found for the requested date."},
        500: {"model": ErrorResponse, "description": "Failed to read archive data."},
    },
    tags=["Archives"],
    summary="Get archived servers for a date",
    description="Returns summarized server cards archived on `YYYY-MM-DD`, optionally filtered by `?q=`.",
)
def get_archive_day(
    date_str: str = Path(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Archive date in `YYYY-MM-DD` format."),
    q: str = Query("", description="Optional Job ID / short ID filter."),
):
    clean_date = date_str.strip()
    gz_path = os.path.join(core.ARCHIVES_DIR, f"servers_{clean_date}.json.gz")
    json_path = os.path.join(core.ARCHIVES_DIR, f"servers_{clean_date}.json")

    if os.path.exists(gz_path):
        target_rel = os.path.join("archives", f"servers_{clean_date}.json.gz")
        is_compressed = True
        filename = f"servers_{clean_date}.json.gz"
    elif os.path.exists(json_path):
        target_rel = os.path.join("archives", f"servers_{clean_date}.json")
        is_compressed = False
        filename = f"servers_{clean_date}.json"
    else:
        raise HTTPException(status_code=404, detail=f"No archive found for date {clean_date}.")

    day_data = core.get_sc_data(target_rel)
    if not isinstance(day_data, dict):
        raise HTTPException(status_code=500, detail="Failed to read archive data.")

    server_cards = [
        _normalize_api_server_card(c)
        for c in core.build_server_cards(day_data, search_query=q.strip(), is_archived=True, exact_search_only=False)
    ]
    return {
        "success": True,
        "date": clean_date,
        "filename": filename,
        "is_compressed": is_compressed,
        "total_servers": len(server_cards),
        "servers": server_cards,
    }

@app.get(
    "/api/tickets",
    response_model=TicketsResponse,
    responses=COMMON_ERROR_RESPONSES,
    tags=["Community"],
    summary="List public tickets and bug reports",
)
def get_tickets():
    public = core.get_public_tickets()
    return {"tickets": public}


if __name__ == "__main__":
    import uvicorn

    api_host = os.environ.get("API_HOST", "0.0.0.0")
    try:
        api_port = int(os.environ.get("API_PORT", "8401"))
    except ValueError:
        api_port = 8401
    uvicorn.run(app, host=api_host, port=api_port, log_level="info")