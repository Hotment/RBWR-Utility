import asyncio
from datetime import datetime, timezone
import io
import json
import logging
import os
import sys
import threading
import time
import traceback
from typing import Any, Callable

import aiohttp
import disnake
from disnake.ext import commands
from dotenv import load_dotenv
import requests

try:
    from server.scoring import calculate_server_top_score
except ImportError:
    try:
        from scoring import calculate_server_top_score  # pyright: ignore[reportMissingImports]
    except ImportError:
        calculate_server_top_score = None  # pyright: ignore[reportConstantRedefinition]

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
GUILD_ID = os.getenv("DISCORD_GUILD_ID", "1547514559097733141").strip()
TICKETS_CATEGORY_ID = os.getenv("DISCORD_TICKETS_CATEGORY_ID", "1547529007334162432").strip()
SUGGESTIONS_DISCUSSION_CHANNEL_ID = int(os.getenv("DISCORD_SUGGESTIONS_DISCUSSION_CHANNEL_ID", "1555617766827098192").strip())
BUGS_DISCUSSION_CHANNEL_ID = int(os.getenv("DISCORD_BUGS_DISCUSSION_CHANNEL_ID", "1555618312333951066").strip())

ERROR_ALERT_CHANNEL_ID = int(os.getenv("DISCORD_ERROR_ALERT_CHANNEL_ID", "1559242589251702895").strip())
ERROR_ALERT_PING_USER_ID = os.getenv("DISCORD_ERROR_ALERT_PING_USER_ID", "1096176878575956119").strip()
CRASH_ALERT_CHANNEL_ID = int(os.getenv("DISCORD_CRASH_ALERT_CHANNEL_ID", "1562502830580048035").strip())

DEFAULT_SERVER_BASE_URL = os.getenv("SERVER_BASE_URL", "https://rbwr.hotment.dev").rstrip("/")
RBWR_API_URL = os.getenv("RBWR_API_URL", f"{DEFAULT_SERVER_BASE_URL}/api/public-servers")

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("rbwr-bot")

INFO_ALIASES = {
    "aprm": "APRM", "rtp": "RTP", "xenon": "Xenon",
    "reactor_temp": "Reactor Temp", "temperature": "Reactor Temp",
    "outputmw": "Output (MW)", "recirc1": "Recirc1", "recirc2": "Recirc2",
    "rpm": "Turbine RPM", "pps": "PointsPerSecond",
    "demandtimeleft": "Demand Time Left", "scramreason": "SCRAMreason",
}

INFO_CHOICES = [
    disnake.OptionChoice(name="APRM", value="aprm"),
    disnake.OptionChoice(name="RTP", value="rtp"),
    disnake.OptionChoice(name="Xenon", value="xenon"),
    disnake.OptionChoice(name="Reactor Temperature", value="reactor_temp"),
    disnake.OptionChoice(name="Output (MW)", value="outputmw"),
    disnake.OptionChoice(name="Recirc 1", value="recirc1"),
    disnake.OptionChoice(name="Recirc 2", value="recirc2"),
    disnake.OptionChoice(name="Turbine RPM", value="rpm"),
    disnake.OptionChoice(name="Points / second", value="pps"),
    disnake.OptionChoice(name="Demand Time Left", value="demandtimeleft"),
    disnake.OptionChoice(name="SCRAM reason", value="scramreason"),
    disnake.OptionChoice(name="ALL", value="all"),
]

def is_server_public(server: dict[str, Any]) -> bool:
    """
    Returns True only if the server is confirmed to be public.
    Filters out private/VIP servers based on is_private flags,
    privateServerOwnerId, or internal state metadata.
    """
    if not isinstance(server, dict):
        return False

    if server.get("is_private") is True:
        return False
    if server.get("IsPrivate") is True:
        return False

    owner_id = server.get("privateServerOwnerId")
    if owner_id not in (None, "", 0, "None", "null", False):
        return False

    st = server.get("state")
    if isinstance(st, dict):
        if st.get("IsPrivate") is True:
            return False

    return True

def is_exact_job_or_server_id_match(query: str, job_id: str) -> bool:
    """
    Returns True ONLY if query is an exact match for:
    1. The full Job ID (with or without hyphens).
    2. The shortened Server ID (e.g. '77f6-4b2f' or '77f64b2f'), which is parts[1]-parts[2] of the UUID.
    3. The first 8-character block of the UUID (e.g. '00109df1').
    Partial queries (e.g. '77f6', 'b', '001') return False.
    """
    if not query or not job_id:
        return False
    q = query.strip().lower()
    jid = job_id.strip().lower()
    if not q or not jid:
        return False

    if q == jid:
        return True

    clean_jid = jid.replace("-", "")
    clean_q = q.replace("-", "")
    if clean_q == clean_jid and len(clean_q) >= 8:
        return True

    j_parts = [p for p in jid.split("-") if p]
    if len(j_parts) >= 3:
        short_id = f"{j_parts[1]}-{j_parts[2]}"
        short_id_compact = f"{j_parts[1]}{j_parts[2]}"
        if q == short_id or q == short_id_compact:
            return True

        q_parts = [p for p in q.split("-") if p]
        if len(q_parts) == 2 and q_parts[0] == j_parts[1] and q_parts[1] == j_parts[2]:
            return True

    if len(j_parts) >= 1 and len(q) == 8 and q == j_parts[0]:
        return True

    return False

def normalize_server_power(server: dict[str, Any]) -> dict[str, Any]:
    """
    Ensures 'Output (MW)' is automatically populated on Unit 2 (and Unit 1)
    using 'PradDoSieci' or fallback keys so it is uniform and easy to consume.
    """
    if not isinstance(server, dict):
        return server
    state = server.get("state")
    if isinstance(state, dict):
        for u_name in ("Unit1", "Unit2"):
            u = state.get(u_name)
            if isinstance(u, dict) and u.get("Output (MW)") is None:
                p_val = u.get("PradDoSieci")
                if p_val is None:
                    p_val = u.get("Output") or u.get("Power") or u.get("megawatts")
                if p_val is not None:
                    u["Output (MW)"] = p_val
    return server

class RBWRClient:
    def __init__(
        self,
        api_url: str | None = None,
        data_supplier: Callable[[bool], dict[str, Any]] | None = None,
    ):
        self.api_url = api_url or RBWR_API_URL
        self.data_supplier = data_supplier
        self.session: aiohttp.ClientSession | None = None
        self.cache: dict[str, Any] | None = None

    def start(self) -> bool:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers={
                "User-Agent": "RBWR-Discord-Bot/1.0",
                "Accept": "application/json",
            })
        return True

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def fetch(self, public_only: bool = True) -> dict[str, Any]:
        if self.data_supplier is not None:
            try:
                res = self.data_supplier(public_only)
                if isinstance(res, dict):
                    servers = res.get("data", {}).get("servers", [])
                    if isinstance(servers, list):
                        for s in servers:
                            normalize_server_power(s)
                        if public_only:
                            res = dict(res, data=dict(res.get("data", {}), servers=[s for s in servers if is_server_public(s)]))
                    self.cache = res
                    return res
            except Exception as ex:
                log.warning(f"[RBWRClient] Direct server data supplier failed, falling back to HTTP: {ex}")

        if self.session is None or self.session.closed:
            self.start()

        session = self.session
        if session is None:
            raise RuntimeError("Failed to start RBWR HTTP client session")

        last_error = None
        params = {"public_only": "true"} if public_only else None
        try:
            async with session.get(self.api_url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    if isinstance(data, dict):
                        servers = data.get("data", {}).get("servers", [])
                        if isinstance(servers, list):
                            for s in servers:
                                normalize_server_power(s)
                            if public_only:
                                filtered = [s for s in servers if is_server_public(s)]
                                data["data"] = dict(data.get("data", {}), servers=filtered)
                        self.cache = data
                        return data
                last_error = f"HTTP {r.status}"
        except Exception as e:
            last_error = str(e)

        if self.cache is not None:
            if public_only:
                cached_copy = dict(self.cache)
                raw_servers = cached_copy.get("data", {}).get("servers", [])
                if isinstance(raw_servers, list):
                    cached_copy["data"] = dict(cached_copy.get("data", {}), servers=[s for s in raw_servers if is_server_public(s)])
                return cached_copy
            return self.cache
        raise RuntimeError(f"Failed to fetch RBWR data from server API: {last_error}")

    @staticmethod
    def norm(value: str) -> str:
        return value.strip().lower().replace("-", "")

    @staticmethod
    def short_id(job_id: str) -> str:
        parts = [p for p in job_id.split("-") if p]
        return f"{parts[1]}-{parts[2]}" if len(parts) >= 3 else job_id

    async def find_server(
        self,
        server_id: str,
        public_only: bool = True,
        allow_exact_private: bool = False,
    ) -> dict[str, Any] | None:
        can_check_private = allow_exact_private or not public_only
        payload = await self.fetch(public_only=not can_check_private)
        servers = payload.get("data", {}).get("servers", [])
        wanted = self.norm(server_id)

        for server in servers:
            if not is_server_public(server):
                continue
            job_id = str(server.get("jobId", ""))
            if not job_id:
                continue
            if (
                self.norm(job_id) == wanted or
                self.norm(self.short_id(job_id)) == wanted or
                is_exact_job_or_server_id_match(server_id, job_id)
            ):
                return server

        if can_check_private:
            for server in servers:
                if is_server_public(server):
                    continue
                job_id = str(server.get("jobId", ""))
                if not job_id:
                    continue
                if is_exact_job_or_server_id_match(server_id, job_id):
                    return server

        return None

    async def fetch_score_breakdown(self, server_id: str) -> dict[str, Any] | None:
        target_jid = server_id
        try:
            server = await self.find_server(server_id, allow_exact_private=True)
            if server:
                target_jid = str(server.get("jobId", server_id))
        except Exception:
            pass

        if self.session is None or self.session.closed:
            self.start()
        if not self.session:
            return None

        urls = [f"{DEFAULT_SERVER_BASE_URL}/api/servers/{target_jid}/score_breakdown"]
        if "127.0.0.1" not in DEFAULT_SERVER_BASE_URL and "localhost" not in DEFAULT_SERVER_BASE_URL:
            urls.append(f"http://127.0.0.1:8400/api/servers/{target_jid}/score_breakdown")

        for u in urls:
            try:
                async with self.session.get(u, timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status == 200:
                        data = await r.json(content_type=None)
                        if isinstance(data, dict) and data.get("success"):
                            return data
            except Exception:
                pass
        return None

    async def calculate(
        self,
        unit: int = 1,
        demand: float | None = None,
        thermal: float | None = None,
        recirc_override: float | None = None,
    ) -> dict[str, Any] | None:
        payload: dict[str, Any] = {"unit": unit}
        if demand is not None:
            payload["demand"] = demand
        if thermal is not None:
            payload["thermal"] = thermal
        if recirc_override is not None:
            payload["recirc_override"] = recirc_override

        if self.session is None or self.session.closed:
            self.start()

        if self.session and not self.session.closed:
            urls = [f"{DEFAULT_SERVER_BASE_URL}/api/calculate"]
            if "127.0.0.1" not in DEFAULT_SERVER_BASE_URL and "localhost" not in DEFAULT_SERVER_BASE_URL:
                urls.append("http://127.0.0.1:8400/api/calculate")

            for u in urls:
                try:
                    async with self.session.post(u, json=payload, timeout=aiohttp.ClientTimeout(total=8)) as r:
                        if r.status == 200:
                            data = await r.json(content_type=None)
                            if isinstance(data, dict) and data.get("success"):
                                return data.get("data")
                except Exception:
                    pass

        try:
            from server.calculator import calculate_reactor_metrics
            return calculate_reactor_metrics(unit=unit, demand=demand, thermal=thermal, recirc_override=recirc_override)
        except Exception:
            try:
                from calculator import calculate_reactor_metrics  # pyright: ignore[reportMissingImports]
                return calculate_reactor_metrics(unit=unit, demand=demand, thermal=thermal, recirc_override=recirc_override)
            except Exception:
                return None

    async def fetch_latest_version(self) -> dict[str, Any] | None:
        if self.session is None or self.session.closed:
            self.start()

        if self.session and not self.session.closed:
            urls = [f"{DEFAULT_SERVER_BASE_URL}/api/version/latest"]
            if "127.0.0.1" not in DEFAULT_SERVER_BASE_URL and "localhost" not in DEFAULT_SERVER_BASE_URL:
                urls.append("http://127.0.0.1:8400/api/version/latest")

            for u in urls:
                try:
                    async with self.session.get(u, timeout=aiohttp.ClientTimeout(total=8)) as r:
                        if r.status == 200:
                            data = await r.json(content_type=None)
                            if isinstance(data, dict) and "version" in data:
                                return data
                except Exception:
                    pass

            try:
                async with self.session.get(
                    "https://api.github.com/repos/Hotment/RBWR-Utility/releases/latest",
                    headers={"User-Agent": "RBWR-Discord-Bot/1.0"},
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as r:
                    if r.status == 200:
                        rel = await r.json(content_type=None)
                        tag_name = rel.get("tag_name", "")
                        version = tag_name.lstrip("vV") if tag_name else "unknown"
                        pub = rel.get("published_at", "")
                        release_date = pub.split("T")[0] if pub else ""
                        html_url = rel.get("html_url", "https://github.com/Hotment/RBWR-Utility/releases/latest")
                        download_url = html_url
                        assets = []
                        for a in rel.get("assets", []):
                            assets.append({"name": a.get("name"), "size": a.get("size"), "download_url": a.get("browser_download_url")})
                            if a.get("name", "").endswith((".exe", ".zip")) and download_url == html_url:
                                download_url = a.get("browser_download_url")
                        return {
                            "version": version,
                            "tag_name": tag_name,
                            "name": rel.get("name", f"Release {version}"),
                            "release_date": release_date,
                            "notes": rel.get("body", "") or "No release notes available.",
                            "html_url": html_url,
                            "download_url": download_url,
                            "assets": assets,
                        }
            except Exception:
                pass

        return {
            "version": "2.0.5",
            "tag_name": "v2.0.5",
            "name": "RBWR Utility v2.0.5",
            "release_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "published_at": datetime.now(timezone.utc).isoformat(),
            "notes": "Latest verified stable build of the RBWR Utility suite.",
            "html_url": "https://github.com/Hotment/RBWR-Utility/releases/latest",
            "download_url": "https://github.com/Hotment/RBWR-Utility/releases/latest",
            "assets": [
                {
                    "name": "RBWR_APR_Overlay_Windows_x64.zip",
                    "size": 75000000,
                    "download_url": "https://github.com/Hotment/RBWR-Utility/releases/latest"
                }
            ],
        }

disnake_bot: commands.InteractionBot | None = None
disnake_bot_loop: asyncio.AbstractEventLoop | None = None

_last_error_hashes: dict[str, float] = {}
_error_lock = threading.Lock()

def _should_suppress_error(origin: str, error_type: str, error_msg: str, cooldown_seconds: float = 5.0) -> bool:
    """
    Prevents flooding Discord channels / hitting 429 rate limits if identical errors
    occur rapidly in a loop. Allows new/different errors through immediately.
    """
    signature = f"{origin}:{error_type}:{error_msg[:120]}"
    now = time.time()
    with _error_lock:
        for k in list(_last_error_hashes.keys()):
            if now - _last_error_hashes[k] > 60:
                del _last_error_hashes[k]
        last_time = _last_error_hashes.get(signature, 0.0)
        if (now - last_time) < cooldown_seconds:
            return True
        _last_error_hashes[signature] = now
        return False

def _build_alert_payload_dict(
    origin: str,
    error: BaseException | str,
    full_traceback: str,
    context_info: dict[str, Any] | None = None,
    ping_user_id: str = ERROR_ALERT_PING_USER_ID,
) -> tuple[str, dict[str, Any], bytes | None]:
    err_type = type(error).__name__ if isinstance(error, BaseException) else "Exception"
    err_msg = str(error) if error else "Unknown error"

    mention_content = f"<@{ping_user_id}> [CRITICAL] Exception Alert in {origin}"

    embed = disnake.Embed(
        title=f"[{origin}] {err_type}"[:256],
        color=0xEF4444,
        timestamp=datetime.now(timezone.utc),
    )

    if context_info:
        for k, v in context_info.items():
            if v is not None and str(v).strip():
                embed.add_field(name=str(k)[:256], value=str(v)[:1024], inline=True)

    err_display = f"{err_type}: {err_msg}"
    embed.add_field(name="Error Details", value=err_display[:1024], inline=False)

    tb_clean = (full_traceback or "").strip()
    file_bytes: bytes | None = None

    if len(tb_clean) <= 3200:
        embed.description = f"```py\n{tb_clean}\n```" if tb_clean else "```py\nNo traceback available\n```"
    else:
        top_slice = tb_clean[:350]
        bottom_slice = tb_clean[-2600:]
        embed.description = (
            f"```py\n{top_slice}\n\n"
            f"... [Traceback truncated. Full stack trace attached as traceback.txt] ...\n\n"
            f"{bottom_slice}\n```"
        )
        file_bytes = tb_clean.encode("utf-8")

    embed.set_footer(text="RBWR System Fault Monitor")
    return mention_content, embed.to_dict(), file_bytes  # pyright: ignore[reportReturnType]

async def _send_alert_coro(
    channel_id: int,
    content: str,
    embed_dict: dict[str, Any],
    file_bytes: bytes | None = None,
) -> bool:
    global disnake_bot
    if not disnake_bot:
        return False
    try:
        channel = disnake_bot.get_channel(channel_id)
        if not channel:
            channel = await disnake_bot.fetch_channel(channel_id)

        if not channel or not hasattr(channel, "send") or not isinstance(channel, disnake.abc.Messageable):
            log.warning(f"[Discord Alert] Channel {channel_id} not found or cannot send messages.")
            return False

        embed = disnake.Embed.from_dict(embed_dict)  # pyright: ignore[reportArgumentType]
        if file_bytes:
            file_obj = disnake.File(io.BytesIO(file_bytes), filename="traceback.txt")
            await channel.send(content=content, embed=embed, file=file_obj)
        else:
            await channel.send(content=content, embed=embed)
        log.info(f"[Discord Alert] Successfully sent alert to channel {channel_id} via Disnake bot")
        return True
    except Exception as ex:
        log.warning(f"[Discord Alert] Disnake channel send failed: {ex}")
        return False

def _send_error_alert_http(
    content: str,
    embed_dict: dict[str, Any],
    file_bytes: bytes | None = None,
    channel_id: int = ERROR_ALERT_CHANNEL_ID,
    token: str | None = None,
) -> bool:
    bot_token = token or TOKEN or os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if not bot_token:
        log.warning("[Discord Alert] DISCORD_BOT_TOKEN not configured; cannot dispatch alert via REST API.")
        return False

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {bot_token}"}
    payload_data = {
        "content": content,
        "embeds": [embed_dict],
    }

    try:
        if file_bytes:
            data = {"payload_json": json.dumps(payload_data)}
            files = {"files[0]": ("traceback.txt", file_bytes, "text/plain")}
            resp = requests.post(url, headers=headers, data=data, files=files, timeout=8)
        else:
            headers["Content-Type"] = "application/json"
            resp = requests.post(url, headers=headers, json=payload_data, timeout=8)

        if resp.status_code in (200, 201):
            log.info(f"[Discord Alert] Error alert dispatched via HTTP REST API to channel {channel_id}")
            return True
        else:
            log.warning(f"[Discord Alert] Discord REST API error {resp.status_code}: {resp.text}")
            return False
    except Exception as ex:
        log.warning(f"[Discord Alert] HTTP REST request failed: {ex}")
        return False

async def send_error_alert_async(
    origin: str,
    error: BaseException | str,
    traceback_str: str | None = None,
    context_info: dict[str, Any] | None = None,
    channel_id: int = ERROR_ALERT_CHANNEL_ID,
    ping_user_id: str = ERROR_ALERT_PING_USER_ID,
) -> bool:
    try:
        err_type = type(error).__name__ if isinstance(error, BaseException) else "Exception"
        err_msg = str(error) if error else "Unknown"
        if _should_suppress_error(origin, err_type, err_msg):
            log.info(f"[Discord Alert] Suppressed duplicate alert for {origin} ({err_type}) within cooldown.")
            return False

        full_tb = traceback_str or (traceback.format_exc() if isinstance(error, BaseException) else str(error))
        content, embed_dict, file_bytes = _build_alert_payload_dict(
            origin=origin,
            error=error,
            full_traceback=full_tb,
            context_info=context_info,
            ping_user_id=ping_user_id,
        )

        sent = await _send_alert_coro(channel_id, content, embed_dict, file_bytes)
        if sent:
            return True

        return _send_error_alert_http(
            content=content,
            embed_dict=embed_dict,
            file_bytes=file_bytes,
            channel_id=channel_id,
        )
    except Exception as ex:
        log.error(f"[Discord Alert] Unexpected error in send_error_alert_async: {ex}", exc_info=True)
        return False

def report_error_to_discord(
    origin: str,
    error: BaseException | str,
    traceback_str: str | None = None,
    context_info: dict[str, Any] | None = None,
    channel_id: int = ERROR_ALERT_CHANNEL_ID,
    ping_user_id: str = ERROR_ALERT_PING_USER_ID,
    token: str | None = None,
) -> bool:
    try:
        err_type = type(error).__name__ if isinstance(error, BaseException) else "Exception"
        err_msg = str(error) if error else "Unknown"
        if _should_suppress_error(origin, err_type, err_msg):
            log.info(f"[Discord Alert] Suppressed duplicate alert for {origin} ({err_type}) within cooldown.")
            return False

        full_tb = traceback_str or (traceback.format_exc() if isinstance(error, BaseException) else str(error))
        content, embed_dict, file_bytes = _build_alert_payload_dict(
            origin=origin,
            error=error,
            full_traceback=full_tb,
            context_info=context_info,
            ping_user_id=ping_user_id,
        )

        global disnake_bot, disnake_bot_loop
        if disnake_bot and disnake_bot.is_ready() and disnake_bot_loop and disnake_bot_loop.is_running():
            try:
                fut = asyncio.run_coroutine_threadsafe(
                    _send_alert_coro(channel_id, content, embed_dict, file_bytes),
                    disnake_bot_loop,
                )
                if fut.result(timeout=6):
                    return True
            except Exception as bot_send_err:
                log.warning(f"[Discord Alert] Disnake loop send failed: {bot_send_err}. Falling back to REST API.")

        return _send_error_alert_http(
            content=content,
            embed_dict=embed_dict,
            file_bytes=file_bytes,
            channel_id=channel_id,
            token=token,
        )
    except Exception as ex:
        log.error(f"[Discord Alert] Unexpected error in report_error_to_discord: {ex}", exc_info=True)
        return False

def report_crash_to_discord(
    crash: dict[str, Any],
    occurrence_count: int = 1,
    channel_id: int = CRASH_ALERT_CHANNEL_ID,
    ping_user_id: str = ERROR_ALERT_PING_USER_ID,
    token: str | None = None,
) -> bool:
    try:
        crash_id = crash.get("id", "Unknown")
        version = crash.get("version", "Unknown")
        os_info = crash.get("os_info", "Unknown")
        raw_tb = (crash.get("traceback") or "").strip()
        first_line = raw_tb.splitlines()[0] if raw_tb else "Fatal Application Crash"

        if _should_suppress_error("DesktopCrash", f"v{version}", first_line, cooldown_seconds=8.0):
            log.info(f"[Discord Alert] Suppressed duplicate crash notification for v{version} within cooldown.")
            return False

        admin_url = f"{DEFAULT_SERVER_BASE_URL}/admin/crashes"
        content = f"<@{ping_user_id}> [CRASH REPORT] Fatal Desktop Overlay Crash (v{version})"

        embed = disnake.Embed(
            title=f"Fatal Desktop Application Crash (v{version})",
            color=0xEF4444,
            timestamp=datetime.now(timezone.utc),
        )

        embed.add_field(name="Crash ID", value=f"#{crash_id}", inline=True)
        embed.add_field(name="App Version", value=f"v{version}", inline=True)
        embed.add_field(name="Operating System", value=str(os_info)[:256], inline=True)
        embed.add_field(name="Occurrences", value=str(occurrence_count), inline=True)
        embed.add_field(name="Admin Panel", value=f"[Open Crashes Dashboard]({admin_url})", inline=False)

        file_bytes: bytes | None = None
        if len(raw_tb) <= 3200:
            embed.description = f"```py\n{raw_tb}\n```" if raw_tb else "```py\nNo traceback provided\n```"
        else:
            top_slice = raw_tb[:350]
            bottom_slice = raw_tb[-2600:]
            embed.description = (
                f"```py\n{top_slice}\n\n"
                f"... [Traceback truncated. Full stack trace attached as traceback.txt] ...\n\n"
                f"{bottom_slice}\n```"
            )
            file_bytes = raw_tb.encode("utf-8")

        embed.set_footer(text="RBWR Desktop Crash Monitoring")
        embed_dict: dict = embed.to_dict()  # pyright: ignore[reportAssignmentType]

        global disnake_bot, disnake_bot_loop
        if disnake_bot and disnake_bot.is_ready() and disnake_bot_loop and disnake_bot_loop.is_running():
            try:
                fut = asyncio.run_coroutine_threadsafe(
                    _send_alert_coro(channel_id, content, embed_dict, file_bytes),
                    disnake_bot_loop,
                )
                if fut.result(timeout=6):
                    return True
            except Exception as bot_send_err:
                log.warning(f"[Discord Alert] Disnake loop send failed for crash alert: {bot_send_err}. Falling back to REST API.")

        return _send_error_alert_http(
            content=content,
            embed_dict=embed_dict,
            file_bytes=file_bytes,
            channel_id=channel_id,
            token=token,
        )
    except Exception as ex:
        log.error(f"[Discord Alert] Unexpected error in report_crash_to_discord: {ex}", exc_info=True)
        return False

class TicketBridge:
    def __init__(self):
        self.load_suggestions: Callable[[], dict[str, Any]] | None = None
        self.save_suggestions: Callable[[dict[str, Any]], None] | None = None
        self.load_admins: Callable[[], dict[str, Any]] | None = None
        self.is_website_admin: Callable[[str], bool] | None = None
        self.broadcast_dashboard: Callable[[], None] | None = None
        self.broadcast_ticket_update: Callable[..., None] | None = None

    def is_configured(self) -> bool:
        return bool(self.load_suggestions and self.save_suggestions and self.is_website_admin)

ticket_bridge = TicketBridge()

def configure_ticket_bridge(
    load_suggestions: Callable[[], dict[str, Any]] | None = None,
    save_suggestions: Callable[[dict[str, Any]], None] | None = None,
    load_admins: Callable[[], dict[str, Any]] | None = None,
    is_website_admin: Callable[[str], bool] | None = None,
    broadcast_dashboard: Callable[[], None] | None = None,
    broadcast_ticket_update: Callable[..., None] | None = None,
):
    ticket_bridge.load_suggestions = load_suggestions
    ticket_bridge.save_suggestions = save_suggestions
    ticket_bridge.load_admins = load_admins
    ticket_bridge.is_website_admin = is_website_admin
    ticket_bridge.broadcast_dashboard = broadcast_dashboard
    ticket_bridge.broadcast_ticket_update = broadcast_ticket_update

def is_user_in_guild(discord_id: str | int | None) -> bool:
    """
    Checks if a Discord user is currently in the configured guild (GUILD_ID).
    Returns True if present, False otherwise.
    """
    global disnake_bot, disnake_bot_loop
    if not discord_id:
        return False
    try:
        uid = int(str(discord_id).strip())
    except (ValueError, TypeError):
        return False

    if not disnake_bot or not disnake_bot.is_ready() or not disnake_bot_loop or not disnake_bot_loop.is_running():
        return False

    bot_ref = disnake_bot

    async def _check():
        try:
            guild_id = int(GUILD_ID)
            guild = bot_ref.get_guild(guild_id)
            if not guild:
                guild = await bot_ref.fetch_guild(guild_id)
            if not guild:
                return False

            member = guild.get_member(uid)
            if member is not None:
                return True

            try:
                member = await guild.fetch_member(uid)
                return member is not None
            except disnake.NotFound:
                return False
            except Exception as e:
                log.warning(f"[Guild Check] fetch_member failed for {uid}: {e}")
                return False
        except Exception as ex:
            log.warning(f"[Guild Check] Guild check error for {uid}: {ex}")
            return False

    try:
        fut = asyncio.run_coroutine_threadsafe(_check(), disnake_bot_loop)
        return bool(fut.result(timeout=4))
    except Exception as ex:
        log.warning(f"[Guild Check] Guild check execution error: {ex}")
        return False

def notify_ticket_author_dm(
    ticket: dict[str, Any],
    event_type: str,
    details: dict[str, Any],
) -> None:
    """
    Sends a direct message to the ticket author if they are in the guild (GUILD_ID).
    event_type can be: 'message', 'note', or 'status'.
    """
    global disnake_bot, disnake_bot_loop
    if not disnake_bot or not disnake_bot.is_ready() or not disnake_bot_loop or not disnake_bot_loop.is_running():
        return

    author_id_str = ticket.get("discord_id")
    if not author_id_str:
        return
    try:
        author_id = int(str(author_id_str).strip())
    except (ValueError, TypeError):
        return

    bot_ref = disnake_bot

    async def _send_dm_async():
        try:
            guild_id = int(GUILD_ID)
            guild = bot_ref.get_guild(guild_id)
            if not guild:
                guild = await bot_ref.fetch_guild(guild_id)
            if not guild:
                return

            member = guild.get_member(author_id)
            if not member:
                try:
                    member = await guild.fetch_member(author_id)
                except disnake.NotFound:
                    return
                except Exception as e:
                    log.warning(f"[DM Notify] Could not fetch member {author_id}: {e}")
                    return

            if not member:
                return

            ticket_id = ticket.get("id")
            is_bug = (ticket.get("type") == "bug_report")
            type_label = "Bug Report" if is_bug else "Suggestion"
            ticket_title = ticket.get("title") or (ticket.get("suggestion") or ticket.get("description") or f"{type_label} #{ticket_id}")[:60]

            embed = None
            if event_type == "message":
                sender_name = details.get("sender_name", "Administrator")
                msg_content = details.get("message", "")
                embed = disnake.Embed(
                    title=f"New Message: {type_label} #{ticket_id}",
                    description=f"**{sender_name}** sent a message regarding your {type_label.lower()}:\n\n> {msg_content[:1500]}",
                    color=disnake.Color.blurple(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="Ticket Title", value=ticket_title, inline=False)
                embed.set_footer(text="RBWR Community Portal • rbwr.hotment.dev/tickets")

            elif event_type == "note":
                comment_by = details.get("comment_by", "Administrator")
                comment_text = details.get("comment", "")
                embed = disnake.Embed(
                    title=f"Developer Note: {type_label} #{ticket_id}",
                    description=f"A developer note was added or edited by **{comment_by}**:\n\n> {comment_text[:1500]}",
                    color=disnake.Color.gold(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="Ticket Title", value=ticket_title, inline=False)
                embed.set_footer(text="RBWR Community Portal • rbwr.hotment.dev/tickets")

            elif event_type == "status":
                new_status = str(details.get("status", "updated")).upper()
                changed_by = details.get("changed_by", "Administrator")
                embed_color = disnake.Color.green() if new_status in ("FIXED", "RESOLVED", "IMPLEMENTED", "ACCEPTED") else (
                    disnake.Color.red() if new_status in ("INVALID", "DECLINED", "CLOSED") else disnake.Color.blue()
                )
                embed = disnake.Embed(
                    title=f"Status Changed: {type_label} #{ticket_id}",
                    description=f"The status of your {type_label.lower()} has been changed to **`{new_status}`** by **{changed_by}**.",
                    color=embed_color,
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="Ticket Title", value=ticket_title, inline=False)
                embed.add_field(name="New Status", value=f"`{new_status}`", inline=True)
                embed.set_footer(text="RBWR Community Portal • rbwr.hotment.dev/tickets")

            if embed:
                try:
                    await member.send(embed=embed)
                    log.info(f"[DM Notify] Successfully sent {event_type} DM to user {member} (ID: {author_id}) for ticket #{ticket_id}")
                except disnake.Forbidden:
                    log.info(f"[DM Notify] Could not send DM to {member}: direct messages disabled by recipient.")
                except Exception as ex:
                    log.warning(f"[DM Notify] Failed to send DM to {member}: {ex}")

        except Exception as e:
            log.warning(f"[DM Notify] Error in _send_dm_async: {e}")

    try:
        asyncio.run_coroutine_threadsafe(_send_dm_async(), disnake_bot_loop)
    except Exception as ex:
        log.warning(f"[DM Notify] Failed to dispatch DM task: {ex}")

class TicketPanelView(disnake.ui.View):
    def __init__(self, ticket_id: int, ticket_type: str, current_status: str, has_note: bool = False):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        self.ticket_type = ticket_type
        self.current_status = (current_status or "open").lower()

        is_bug = (ticket_type == "bug_report")
        if is_bug:
            options = [
                disnake.SelectOption(label="Open", value="open", description="Newly reported bug", default=(self.current_status == "open")),
                disnake.SelectOption(label="Investigating", value="investigating", description="Investigating root cause", default=(self.current_status == "investigating")),
                disnake.SelectOption(label="Confirmed", value="confirmed", description="Bug reproduced and confirmed", default=(self.current_status == "confirmed")),
                disnake.SelectOption(label="Fixed", value="fixed", description="Bug resolved and deployed", default=(self.current_status in ("fixed", "resolved"))),
                disnake.SelectOption(label="Invalid", value="invalid", description="Not a bug or cannot reproduce", default=(self.current_status in ("invalid", "closed"))),
            ]
        else:
            options = [
                disnake.SelectOption(label="Pending", value="pending", description="Awaiting developer review", default=(self.current_status == "pending")),
                disnake.SelectOption(label="Considering", value="considering", description="Under active consideration", default=(self.current_status == "considering")),
                disnake.SelectOption(label="Planned", value="planned", description="Scheduled for implementation", default=(self.current_status == "planned")),
                disnake.SelectOption(label="Implemented", value="implemented", description="Feature is now live", default=(self.current_status in ("implemented", "accepted"))),
                disnake.SelectOption(label="Declined", value="declined", description="Will not be implemented", default=(self.current_status == "declined")),
            ]

        self.select_menu = disnake.ui.StringSelect(
            custom_id=f"ticket_status_select:{ticket_id}",
            placeholder=f"Change State (Current: {self.current_status.upper()})",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.add_item(self.select_menu)

        note_label = "Edit Note" if has_note else "Add Note"
        self.note_button = disnake.ui.Button(
            label=note_label,
            style=disnake.ButtonStyle.secondary,
            custom_id=f"ticket_edit_note:{ticket_id}",
        )
        self.add_item(self.note_button)

        self.discuss_button = disnake.ui.Button(
            label="Open Discussions",
            style=disnake.ButtonStyle.primary,
            custom_id=f"ticket_open_discussions:{ticket_id}",
        )
        self.add_item(self.discuss_button)

    async def on_error(self, error: Exception, item: disnake.ui.Item, interaction: disnake.MessageInteraction) -> None:
        log.error(f"[TicketPanelView] Interaction error in component {getattr(item, 'custom_id', item)}: {error}", exc_info=error)
        tb_str = "".join(traceback.format_exception(type(error), error, error.__traceback__)) if error and getattr(error, "__traceback__", None) else traceback.format_exc()
        ctx = {
            "View": "TicketPanelView",
            "Ticket ID": str(getattr(self, "ticket_id", "unknown")),
            "Component": str(getattr(item, "custom_id", item)),
            "User": f"{interaction.author.name} (ID: {interaction.author.id})",
            "Channel": f"#{getattr(interaction.channel, 'name', 'unknown')} (ID: {interaction.channel_id})",
        }
        await send_error_alert_async(
            origin="Bot Ticket Panel View",
            error=error,
            traceback_str=tb_str,
            context_info=ctx,
        )
        try:
            msg = "An error occurred while handling this ticket action."
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            pass

class TicketNoteModal(disnake.ui.Modal):
    def __init__(self, ticket_id: int, current_note: str = ""):
        self.ticket_id = ticket_id
        components = [
            disnake.ui.TextInput(
                label="Admin Note",
                custom_id="ticket_note_text",
                style=disnake.TextInputStyle.paragraph,
                placeholder="Enter official developer / administrator note...",
                value=current_note[:2000] if current_note else None,
                required=False,
                max_length=2000,
            )
        ]
        title = f"Edit Note: Ticket #{ticket_id}" if current_note else f"Add Note: Ticket #{ticket_id}"
        super().__init__(
            title=title[:45],
            custom_id=f"ticket_note_modal:{ticket_id}",
            components=components,
        )

    async def callback(self, inter: disnake.ModalInteraction):
        await handle_ticket_note_submission(inter, self.ticket_id)

    async def on_error(self, error: Exception, interaction: disnake.ModalInteraction) -> None:
        log.error(f"[TicketNoteModal] Modal submission error for ticket #{self.ticket_id}: {error}", exc_info=error)
        tb_str = "".join(traceback.format_exception(type(error), error, error.__traceback__)) if error and getattr(error, "__traceback__", None) else traceback.format_exc()
        ctx = {
            "Modal": "TicketNoteModal",
            "Ticket ID": str(self.ticket_id),
            "User": f"{interaction.author.name} (ID: {interaction.author.id})",
            "Channel": f"#{getattr(interaction.channel, 'name', 'unknown')} (ID: {interaction.channel_id})",
        }
        await send_error_alert_async(
            origin="Bot Ticket Note Modal",
            error=error,
            traceback_str=tb_str,
            context_info=ctx,
        )
        try:
            msg = "An error occurred while saving the note."
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            pass

_handled_interaction_ids: set[int] = set()

def _check_and_mark_interaction(inter_id: int) -> bool:
    """Returns True if this interaction has already been processed, preventing duplicate executions."""
    if inter_id in _handled_interaction_ids:
        return True
    _handled_interaction_ids.add(inter_id)
    if len(_handled_interaction_ids) > 1000:
        excess = len(_handled_interaction_ids) - 500
        for _ in range(excess):
            _handled_interaction_ids.pop()
    return False

def is_inter_admin(inter: disnake.Interaction) -> bool:
    """
    Checks if an interaction author is an authorized administrator,
    either via Discord guild administrator permissions or through website admin config.
    """
    sender_discord_id = str(inter.author.id)
    is_guild_admin = (
        inter.author.guild_permissions.administrator
        if (hasattr(inter.author, "guild_permissions") and isinstance(inter.author, disnake.Member))
        else False
    )
    is_web_admin = bool(ticket_bridge.is_website_admin and ticket_bridge.is_website_admin(sender_discord_id))
    return bool(is_guild_admin or is_web_admin)

def parse_embed_color(val: str | None) -> disnake.Color | None:
    if not val:
        return None
    val = val.strip().lower()
    color_map: dict[str, disnake.Color] = {
        "blurple": disnake.Color.blurple(),
        "blue": disnake.Color.blue(),
        "dark_blue": disnake.Color.dark_blue(),
        "red": disnake.Color.red(),
        "dark_red": disnake.Color.dark_red(),
        "green": disnake.Color.green(),
        "dark_green": disnake.Color.dark_green(),
        "gold": disnake.Color.gold(),
        "yellow": disnake.Color.yellow(),
        "orange": disnake.Color.orange(),
        "dark_orange": disnake.Color.dark_orange(),
        "purple": disnake.Color.purple(),
        "dark_purple": disnake.Color.dark_purple(),
        "magenta": disnake.Color.magenta(),
        "dark_theme": disnake.Color.dark_theme(),
        "dark": disnake.Color.dark_theme(),
        "teal": disnake.Color.teal(),
        "dark_teal": disnake.Color.dark_teal(),
        "cyan": disnake.Color.teal(),
        "grey": disnake.Color.greyple(),
        "gray": disnake.Color.greyple(),
    }
    if val in color_map:
        return color_map[val]
    clean_hex = val.lstrip("#").lstrip("0x")
    if len(clean_hex) == 3:
        clean_hex = "".join(c * 2 for c in clean_hex)
    try:
        hex_int = int(clean_hex, 16)
        return disnake.Color(hex_int)
    except ValueError:
        return None

def build_custom_embed(
    title: str | None = None,
    description: str | None = None,
    color: str | None = None,
    image_url: str | None = None,
    thumbnail_url: str | None = None,
    footer: str | None = None,
    footer_icon_url: str | None = None,
    author_name: str | None = None,
    author_icon_url: str | None = None,
    url: str | None = None,
    fields_str: str | None = None,
    json_data: str | None = None,
    include_timestamp: bool = True,
) -> disnake.Embed:
    if json_data:
        try:
            raw = json.loads(json_data.strip())
            if isinstance(raw, dict):
                embed_payload = raw.get("embed") or raw.get("embeds", [None])[0] or raw
                if isinstance(embed_payload, dict):
                    return disnake.Embed.from_dict(embed_payload)  # pyright: ignore[reportArgumentType]
            raise ValueError("JSON data must represent an embed dictionary object.")
        except json.JSONDecodeError as jde:
            raise ValueError(f"Invalid JSON syntax: {jde}")

    parsed_color = parse_embed_color(color) or disnake.Color(0x00D1FF)

    clean_title = title.replace(r"\n", "\n")[:256] if title else None
    clean_desc = description.replace(r"\n", "\n")[:4096] if description else None

    if not any([clean_title, clean_desc, image_url, thumbnail_url, fields_str, footer, author_name]):
        raise ValueError("Embed must contain at least one of: title, description, image, thumbnail, fields, or footer.")

    embed = disnake.Embed(
        title=clean_title,
        description=clean_desc,
        color=parsed_color,
        url=url or None,
    )

    if include_timestamp:
        embed.timestamp = datetime.now(timezone.utc)

    if footer:
        clean_footer = footer.replace(r"\n", "\n")[:2048]
        embed.set_footer(text=clean_footer, icon_url=footer_icon_url or None)

    if image_url:
        embed.set_image(url=image_url.strip())

    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url.strip())

    if author_name:
        clean_author = author_name.replace(r"\n", "\n")[:256]
        embed.set_author(name=clean_author, icon_url=author_icon_url or None)

    if fields_str:
        fields_str = fields_str.strip()
        if fields_str.startswith("[") and fields_str.endswith("]"):
            try:
                f_list = json.loads(fields_str)
                if isinstance(f_list, list):
                    for item in f_list:
                        if isinstance(item, dict) and "name" in item and "value" in item:
                            embed.add_field(
                                name=str(item["name"])[:256],
                                value=str(item["value"])[:1024],
                                inline=bool(item.get("inline", False)),
                            )
            except Exception as e:
                log.warning(f"[Embed Build] Failed to parse fields JSON: {e}")
        else:
            parts = fields_str.split("|")
            for part in parts:
                if ":" in part:
                    k, v = part.split(":", 1)
                    k_clean = k.strip().replace(r"\n", "\n")[:256]
                    v_clean = v.strip().replace(r"\n", "\n")[:1024]
                    if k_clean and v_clean:
                        embed.add_field(name=k_clean, value=v_clean, inline=False)

    return embed

class EmbedBuilderModal(disnake.ui.Modal):
    def __init__(self, target_channel_id: int):
        self.target_channel_id = target_channel_id
        components = [
            disnake.ui.TextInput(
                label="Embed Title",
                custom_id="embed_title",
                style=disnake.TextInputStyle.short,
                placeholder="Title text (optional)...",
                required=False,
                max_length=256,
            ),
            disnake.ui.TextInput(
                label="Embed Description",
                custom_id="embed_description",
                style=disnake.TextInputStyle.paragraph,
                placeholder="Enter description / body text...",
                required=True,
                max_length=4000,
            ),
            disnake.ui.TextInput(
                label="Color (Hex or Name)",
                custom_id="embed_color",
                style=disnake.TextInputStyle.short,
                placeholder="#00D1FF, blurple, red, green, gold...",
                required=False,
                max_length=32,
            ),
            disnake.ui.TextInput(
                label="Image URL",
                custom_id="embed_image_url",
                style=disnake.TextInputStyle.short,
                placeholder="https://example.com/image.png (optional)...",
                required=False,
                max_length=1024,
            ),
            disnake.ui.TextInput(
                label="Footer Text",
                custom_id="embed_footer",
                style=disnake.TextInputStyle.short,
                placeholder="Footer text (optional)...",
                required=False,
                max_length=2048,
            ),
        ]
        super().__init__(
            title="Create Custom Embed",
            custom_id=f"embed_builder_modal:{target_channel_id}",
            components=components,
        )

    async def callback(self, inter: disnake.ModalInteraction):
        await handle_embed_modal_submission(inter, self.target_channel_id)

    async def on_error(self, error: Exception, interaction: disnake.ModalInteraction) -> None:
        log.error(f"[EmbedBuilderModal] Modal submission error: {error}", exc_info=error)
        tb_str = "".join(traceback.format_exception(type(error), error, error.__traceback__)) if error and getattr(error, "__traceback__", None) else traceback.format_exc()
        ctx = {
            "Modal": "EmbedBuilderModal",
            "Target Channel ID": str(self.target_channel_id),
            "User": f"{interaction.author.name} (ID: {interaction.author.id})",
        }
        await send_error_alert_async(
            origin="Bot Embed Builder Modal",
            error=error,
            traceback_str=tb_str,
            context_info=ctx,
        )
        try:
            msg = "An error occurred while dispatching the embed."
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            pass

async def handle_embed_modal_submission(inter: disnake.ModalInteraction, target_channel_id: int):
    if _check_and_mark_interaction(inter.id) or inter.response.is_done():
        return

    if not is_inter_admin(inter):
        await inter.response.send_message("Only administrators can execute this command.", ephemeral=True)
        return

    await inter.response.defer(ephemeral=True)

    guild = inter.guild
    target_channel = None
    if guild:
        target_channel = guild.get_channel(target_channel_id)
        if not target_channel:
            try:
                target_channel = await guild.fetch_channel(target_channel_id)
            except Exception:
                target_channel = None

    if not target_channel or not hasattr(target_channel, "send") or not isinstance(target_channel, (disnake.TextChannel, disnake.Thread, disnake.VoiceChannel)):
        await inter.followup.send("Could not access target channel to send embed.", ephemeral=True)
        return

    title = inter.text_values.get("embed_title", "").strip() or None
    description = inter.text_values.get("embed_description", "").strip()
    color_str = inter.text_values.get("embed_color", "").strip() or None
    image_url = inter.text_values.get("embed_image_url", "").strip() or None
    footer = inter.text_values.get("embed_footer", "").strip() or None

    try:
        embed = build_custom_embed(
            title=title,
            description=description,
            color=color_str,
            image_url=image_url,
            footer=footer,
            include_timestamp=True,
        )
        sent_msg = await target_channel.send(embed=embed)
        log.info(
            f"[Embed Modal] Dispatched embed message {sent_msg.id} to #{getattr(target_channel, 'name', target_channel.id)} "
            f"by admin {inter.author.name} (ID: {inter.author.id})"
        )
        await inter.followup.send(
            f"Embed successfully dispatched to {target_channel.mention} (Message ID: `{sent_msg.id}`).",
            ephemeral=True,
        )
    except Exception as ex:
        log.error(f"[Embed Modal] Failed to send modal embed to channel {target_channel_id}: {ex}", exc_info=ex)
        await inter.followup.send(f"Failed to send embed: `{ex}`", ephemeral=True)

AUTOROLE_CONFIG_FILENAME = "autorole.json"

def get_autorole_config_path() -> str:
    bot_dir = os.path.dirname(os.path.abspath(__file__))
    server_data_dir = os.path.abspath(os.path.join(bot_dir, "..", "server", "data"))
    if os.path.isdir(server_data_dir):
        return os.path.join(server_data_dir, AUTOROLE_CONFIG_FILENAME)
    return os.path.join(bot_dir, AUTOROLE_CONFIG_FILENAME)

def load_autorole_config() -> dict[str, Any]:
    path = get_autorole_config_path()
    if not os.path.exists(path):
        return {"guilds": {}, "default_role_id": None, "default_role_name": None}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as ex:
        log.warning(f"[Autorole] Error loading config from {path}: {ex}")
    return {"guilds": {}, "default_role_id": None, "default_role_name": None}

def save_autorole_config(config: dict[str, Any]) -> bool:
    path = get_autorole_config_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as ex:
        log.error(f"[Autorole] Error saving config to {path}: {ex}")
        return False

def resolve_autorole_for_guild(guild: disnake.Guild) -> tuple[disnake.Role | None, str | None, bool]:
    config = load_autorole_config()
    guild_id_str = str(guild.id)
    guild_cfg = config.get("guilds", {}).get(guild_id_str, {})

    is_enabled = bool(guild_cfg.get("enabled", True))
    role_id = guild_cfg.get("role_id") or config.get("default_role_id") or os.getenv("DISCORD_AUTOROLE_ROLE_ID", "").strip() or None
    role_name = guild_cfg.get("role_name") or config.get("default_role_name") or os.getenv("DISCORD_AUTOROLE_ROLE_NAME", "").strip() or None

    role: disnake.Role | None = None
    source: str | None = None

    if role_id:
        try:
            role = guild.get_role(int(role_id))
            if role:
                source = f"Configured Role ID ({role_id})"
        except (ValueError, TypeError):
            pass

    if not role and role_name:
        role = disnake.utils.get(guild.roles, name=str(role_name))
        if role:
            source = f"Configured Role Name ('{role_name}')"

    if not role and not role_id and not role_name:
        for fallback_name in ("Member", "Members", "User", "Verified"):
            found = disnake.utils.get(guild.roles, name=fallback_name)
            if found:
                role = found
                source = f"Default Server Role ('{fallback_name}')"
                break

    return role, source, is_enabled

async def assign_autorole_to_member(member: disnake.Member) -> bool:
    if not member.guild:
        return False

    config = load_autorole_config()
    guild_cfg = config.get("guilds", {}).get(str(member.guild.id), {})
    include_bots = bool(guild_cfg.get("include_bots", False))

    if member.bot and not include_bots:
        log.info(f"[Autorole] Skipping bot member join: {member.name} (ID: {member.id}) in guild {member.guild.name}")
        return False

    target_role, source_desc, is_enabled = resolve_autorole_for_guild(member.guild)

    if not is_enabled:
        log.info(f"[Autorole] Autorole is currently disabled for guild {member.guild.name} ({member.guild.id})")
        return False

    if not target_role:
        log.info(f"[Autorole] No autorole configured or matched for guild {member.guild.name} ({member.guild.id})")
        return False

    if target_role in member.roles:
        log.debug(f"[Autorole] Member {member.name} ({member.id}) already possesses role '{target_role.name}'")
        return True

    me = member.guild.me
    if not me:
        try:
            me = await member.guild.fetch_member(member.guild.me.id if member.guild.me else member._state.self_id)  # pyright: ignore[reportArgumentType]
        except Exception:
            pass

    if me:
        if not me.guild_permissions.manage_roles:
            log.warning(f"[Autorole] Bot lacks 'Manage Roles' permission in guild {member.guild.name} ({member.guild.id})")
            await send_error_alert_async(
                origin="Bot Autorole (assign_autorole_to_member)",
                error=RuntimeError("Bot lacks Manage Roles permission"),
                context_info={
                    "Guild": f"{member.guild.name} ({member.guild.id})",
                    "Member": f"{member.name} ({member.id})",
                    "Target Role": f"{target_role.name} ({target_role.id})",
                    "Issue": "Manage Roles permission not granted to bot in Discord",
                },
            )
            return False

        if target_role >= me.top_role:
            log.warning(f"[Autorole] Target role '{target_role.name}' ({target_role.id}) is higher than or equal to bot's top role '{me.top_role.name}' ({me.top_role.id})")
            await send_error_alert_async(
                origin="Bot Autorole (assign_autorole_to_member)",
                error=RuntimeError("Role hierarchy conflict"),
                context_info={
                    "Guild": f"{member.guild.name} ({member.guild.id})",
                    "Member": f"{member.name} ({member.id})",
                    "Target Role": f"{target_role.name} ({target_role.id})",
                    "Bot Top Role": f"{me.top_role.name} ({me.top_role.id})",
                    "Issue": "Target role position must be below the bot role",
                },
            )
            return False

    try:
        await member.add_roles(target_role, reason="Autorole assignment on join")
        log.info(f"[Autorole] Assigned role '{target_role.name}' ({target_role.id}) to {member.name} ({member.id}) in {member.guild.name}")
        return True
    except disnake.Forbidden as fb:
        log.error(f"[Autorole] Forbidden: Failed to assign role '{target_role.name}' to {member.name}: {fb}")
        return False
    except Exception as ex:
        log.error(f"[Autorole] Unexpected error assigning role '{target_role.name}' to {member.name}: {ex}", exc_info=ex)
        await send_error_alert_async(
            origin="Bot Autorole (assign_autorole_to_member)",
            error=ex,
            context_info={
                "Guild": f"{member.guild.name} ({member.guild.id})",
                "Member": f"{member.name} ({member.id})",
                "Target Role": f"{target_role.name} ({target_role.id})",
            },
        )
        return False

def build_ticket_panel(
    ticket_id: int,
    ticket_type: str,
    current_status: str,
    admin_comment: str | None = None,
) -> tuple[disnake.Embed, disnake.ui.View]:
    is_bug = (ticket_type == "bug_report")
    status_clean = (current_status or ("open" if is_bug else "pending")).lower()

    panel_embed = disnake.Embed(
        title=f"Ticket Panel — {'Bug Report' if is_bug else 'Suggestion'} #{ticket_id}",
        description=(
            "**Admin Management Controls**\n"
            "• Use the dropdown menu below to change ticket state.\n"
            "• Click **Add Note** / **Edit Note** to attach an official administrator note.\n"
            "• Click **Open Discussions** to create a community thread and ping the author."
        ),
        color=disnake.Color.dark_theme() if hasattr(disnake.Color, "dark_theme") else disnake.Color.blurple(),
        timestamp=datetime.now(timezone.utc)
    )
    panel_embed.add_field(name="Current State", value=f"`{status_clean.upper()}`", inline=True)
    panel_embed.add_field(name="Ticket Type", value="Bug Report" if is_bug else "Feature Suggestion", inline=True)
    if admin_comment and admin_comment.strip():
        panel_embed.add_field(name="Admin Note", value=admin_comment.strip()[:1000], inline=False)
    panel_embed.set_footer(text=f"RBWR Utility • Admin Ticket Panel #{ticket_id}")

    has_note = bool(admin_comment and admin_comment.strip())
    view = TicketPanelView(ticket_id=ticket_id, ticket_type=ticket_type, current_status=status_clean, has_note=has_note)
    return panel_embed, view

def update_discussion_thread_status(
    ticket: dict[str, Any],
    new_status: str,
    changed_by: str | None = None,
    prev_status: str | None = None
) -> None:
    """
    Updates the embed in the discussion thread to reflect the new ticket status.
    Can be safely called from both the bot event loop and web server threads.
    """
    global disnake_bot, disnake_bot_loop
    if not disnake_bot or not disnake_bot.is_ready() or not disnake_bot_loop or not disnake_bot_loop.is_running():
        return

    thread_id_val = ticket.get("discussion_thread_id")
    if not thread_id_val:
        return

    bot_ref = disnake_bot

    async def _update_async():
        try:
            tid = int(thread_id_val)
            ch = bot_ref.get_channel(tid)
            if not ch or not isinstance(ch, disnake.Thread):
                try:
                    ch = await bot_ref.fetch_channel(tid)
                except Exception as ex:
                    log.warning(f"[Discussion Status Update] Could not fetch thread {tid}: {ex}")
                    return

            if not ch or not isinstance(ch, disnake.Thread):
                return

            msg = None
            msg_id_val = ticket.get("discussion_message_id")
            if msg_id_val:
                try:
                    msg = await ch.fetch_message(int(msg_id_val))
                except Exception:
                    msg = None

            if not msg:
                try:
                    msg = await ch.fetch_message(tid)
                except Exception:
                    msg = None

            if not msg and hasattr(ch, "history"):
                try:
                    async for m in ch.history(oldest_first=True, limit=5):
                        if bot_ref.user and m.author.id == bot_ref.user.id and m.embeds:
                            msg = m
                            break
                except Exception:
                    msg = None

            if not msg or not msg.embeds:
                return

            old_embed = msg.embeds[0]
            new_embed = disnake.Embed.from_dict(old_embed.to_dict())

            status_upper = str(new_status).upper()
            found_field = False
            for idx, field in enumerate(new_embed.fields):
                if field.name and field.name.strip().lower() == "status":
                    new_embed.set_field_at(idx, name="Status", value=f"`{status_upper}`", inline=True)
                    found_field = True
                    break

            if not found_field:
                new_embed.add_field(name="Status", value=f"`{status_upper}`", inline=True)

            if status_upper in ("FIXED", "RESOLVED", "IMPLEMENTED", "ACCEPTED"):
                new_embed.color = disnake.Color.green()
            elif status_upper in ("PLANNED", "CONFIRMED"):
                new_embed.color = disnake.Color.teal()
            elif status_upper in ("INVESTIGATING", "CONSIDERING"):
                new_embed.color = disnake.Color.blue()
            elif status_upper in ("INVALID", "DECLINED", "CLOSED"):
                new_embed.color = disnake.Color.red()

            admin_comment = (ticket.get("admin_comment") or "").strip()
            comment_by = ticket.get("comment_by") or "Administrator"
            note_idx = None
            for idx, field in enumerate(new_embed.fields):
                if field.name and field.name.strip().lower() in ("admin note", "developer note", "note"):
                    note_idx = idx
                    break

            if admin_comment:
                note_val = f"**[{comment_by}]**:\n{admin_comment}"
                if note_idx is not None:
                    new_embed.set_field_at(note_idx, name="Admin Note", value=note_val[:1024], inline=False)
                else:
                    new_embed.add_field(name="Admin Note", value=note_val[:1024], inline=False)
            elif note_idx is not None:
                new_embed.remove_field(note_idx)

            await msg.edit(embed=new_embed)
            log.info(f"[Discussion Status Update] Updated discussion embed for ticket #{ticket.get('id')} to {status_upper}")

            if prev_status and str(prev_status).strip().lower() != str(new_status).strip().lower():
                actor_str = changed_by or "Administrator"
                try:
                    await ch.send(f"Ticket #{ticket.get('id')} status updated to **`{status_upper}`** by {actor_str}.")
                except Exception as ex_post:
                    log.warning(f"[Discussion Status Update] Failed to post status message to thread: {ex_post}")
        except Exception as e:
            log.warning(f"[Discussion Status Update] Failed to update discussion thread message: {e}")

    try:
        asyncio.run_coroutine_threadsafe(_update_async(), disnake_bot_loop)
    except Exception as ex:
        log.warning(f"[Discussion Status Update] Failed to dispatch update task: {ex}")

def update_ticket_channel_message(
    ticket: dict[str, Any],
    changed_by: str | None = None,
    prev_status: str | None = None
) -> None:
    """
    Updates the Discord ticket channel messages (overview embed and panel view)
    to reflect changes in ticket state or admin note, and sends a status update
    notification message in the ticket channel when the state changes.
    Can be safely invoked from web server worker threads or the bot event loop.
    """
    global disnake_bot, disnake_bot_loop
    if not disnake_bot or not disnake_bot.is_ready() or not disnake_bot_loop or not disnake_bot_loop.is_running():
        return

    ticket_id = ticket.get("id")
    if not ticket_id:
        return

    channel_id_val = ticket.get("discord_channel_id")
    bot_ref = disnake_bot

    async def _update_async():
        ch = None
        if channel_id_val:
            try:
                ch = bot_ref.get_channel(int(channel_id_val))
                if not ch:
                    ch = await bot_ref.fetch_channel(int(channel_id_val))
            except Exception as ex:
                log.warning(f"[Ticket Channel Update] Could not fetch channel {channel_id_val}: {ex}")

        if not ch:
            cat_id = int(TICKETS_CATEGORY_ID) if TICKETS_CATEGORY_ID.isdigit() else None
            for g in bot_ref.guilds:
                for c in g.text_channels:
                    if cat_id and c.category_id != cat_id:
                        continue
                    name_lower = c.name.lower()
                    if (
                        name_lower == f"ticket-{ticket_id}"
                        or name_lower.startswith(f"ticket-{ticket_id}-")
                        or name_lower == f"suggestion-{ticket_id}"
                        or name_lower.startswith(f"suggestion-{ticket_id}-")
                        or name_lower == f"bug-{ticket_id}"
                        or name_lower.startswith(f"bug-{ticket_id}-")
                    ):
                        ch = c
                        break
                if ch:
                    break

        if not ch or not isinstance(ch, disnake.TextChannel):
            log.warning(f"[Ticket Channel Update] Text channel for ticket #{ticket_id} not found.")
            return

        is_bug = (ticket.get("type") == "bug_report")
        current_status = str(ticket.get("status") or ("open" if is_bug else "pending")).lower()
        admin_comment = (ticket.get("admin_comment") or "").strip()
        comment_by = ticket.get("comment_by") or "Administrator"

        overview_msg = None
        panel_msg = None

        overview_msg_id = ticket.get("discord_message_id")
        if overview_msg_id:
            try:
                overview_msg = await ch.fetch_message(int(overview_msg_id))
            except Exception:
                overview_msg = None

        panel_msg_id = ticket.get("panel_message_id")
        if panel_msg_id:
            try:
                panel_msg = await ch.fetch_message(int(panel_msg_id))
            except Exception:
                panel_msg = None

        if not overview_msg or not panel_msg:
            try:
                async for m in ch.history(oldest_first=True, limit=20):
                    if bot_ref.user and m.author.id == bot_ref.user.id and m.embeds:
                        emb = m.embeds[0]
                        title = emb.title or ""
                        if not overview_msg and ("Bug Report #" in title or "Feature Suggestion #" in title or f"#{ticket_id}" in title) and "Ticket Panel" not in title:
                            overview_msg = m
                        elif not panel_msg and ("Ticket Panel" in title or f"Admin Ticket Panel #{ticket_id}" in (getattr(emb.footer, "text", "") or "")):
                            panel_msg = m
            except Exception as h_err:
                log.warning(f"[Ticket Channel Update] Error scanning history: {h_err}")

        new_disc_id = str(overview_msg.id) if overview_msg else None
        new_panel_id = str(panel_msg.id) if panel_msg else None
        if (new_disc_id and new_disc_id != ticket.get("discord_message_id")) or (new_panel_id and new_panel_id != ticket.get("panel_message_id")):
            if ticket_bridge.load_suggestions and ticket_bridge.save_suggestions:
                try:
                    data = ticket_bridge.load_suggestions()
                    for s in data.get("suggestions", []):
                        if s.get("id") == ticket_id:
                            if new_disc_id:
                                s["discord_message_id"] = new_disc_id
                            if new_panel_id:
                                s["panel_message_id"] = new_panel_id
                            break
                    ticket_bridge.save_suggestions(data)
                except Exception as save_err:
                    log.warning(f"[Ticket Channel Update] Error saving message IDs: {save_err}")

        if overview_msg and overview_msg.embeds:
            try:
                old_emb = overview_msg.embeds[0]
                new_emb = disnake.Embed.from_dict(old_emb.to_dict())

                status_upper = current_status.upper()
                found_status = False
                for idx, fld in enumerate(new_emb.fields):
                    if fld.name and fld.name.strip().lower() == "status":
                        new_emb.set_field_at(idx, name="Status", value=f"`{status_upper}`", inline=True)
                        found_status = True
                        break
                if not found_status:
                    new_emb.add_field(name="Status", value=f"`{status_upper}`", inline=True)

                note_field_idx = None
                admin_replies_idx = None
                for idx, fld in enumerate(new_emb.fields):
                    if fld.name and fld.name.strip().lower() in ("admin note", "developer note", "note"):
                        note_field_idx = idx
                    elif fld.name and fld.name.strip().lower() == "admin replies":
                        admin_replies_idx = idx

                if admin_comment:
                    note_val = f"**[{comment_by}]**:\n{admin_comment}"
                    if note_field_idx is not None:
                        new_emb.set_field_at(note_field_idx, name="Admin Note", value=note_val[:1024], inline=False)
                    else:
                        if admin_replies_idx is not None:
                            new_emb.insert_field_at(admin_replies_idx, name="Admin Note", value=note_val[:1024], inline=False)
                        else:
                            new_emb.add_field(name="Admin Note", value=note_val[:1024], inline=False)
                else:
                    if note_field_idx is not None:
                        new_emb.remove_field(note_field_idx)

                if status_upper in ("FIXED", "RESOLVED", "IMPLEMENTED", "ACCEPTED"):
                    new_emb.color = disnake.Color.green()
                elif status_upper in ("PLANNED", "CONFIRMED"):
                    new_emb.color = disnake.Color.teal()
                elif status_upper in ("INVESTIGATING", "CONSIDERING"):
                    new_emb.color = disnake.Color.blue()
                elif status_upper in ("INVALID", "DECLINED", "CLOSED"):
                    new_emb.color = disnake.Color.red()
                else:
                    new_emb.color = disnake.Color.red() if is_bug else disnake.Color.blurple()

                await overview_msg.edit(embed=new_emb)
                log.info(f"[Ticket Channel Update] Updated overview message for ticket #{ticket_id}")
            except Exception as e:
                log.warning(f"[Ticket Channel Update] Failed to update overview message: {e}")

        panel_embed, panel_view = build_ticket_panel(
            ticket_id=ticket_id,
            ticket_type=ticket.get("type", "suggestion"),
            current_status=current_status,
            admin_comment=admin_comment
        )

        if panel_msg:
            try:
                await panel_msg.edit(embed=panel_embed, view=panel_view)
                log.info(f"[Ticket Channel Update] Updated panel message for ticket #{ticket_id}")
            except Exception as e:
                log.warning(f"[Ticket Channel Update] Failed to update panel message: {e}")
        else:
            try:
                sent_panel = await ch.send(embed=panel_embed, view=panel_view)
                if ticket_bridge.load_suggestions and ticket_bridge.save_suggestions:
                    try:
                        d = ticket_bridge.load_suggestions()
                        for s in d.get("suggestions", []):
                            if s.get("id") == ticket_id:
                                s["panel_message_id"] = str(sent_panel.id)
                                break
                        ticket_bridge.save_suggestions(d)
                    except Exception:
                        pass
                log.info(f"[Ticket Channel Update] Created panel message for ticket #{ticket_id}")
            except Exception as e:
                log.warning(f"[Ticket Channel Update] Failed to send new panel message: {e}")

        if prev_status and str(prev_status).strip().lower() != current_status.strip().lower():
            actor_str = changed_by or "Administrator"
            status_color = disnake.Color.gold()
            status_upper = current_status.upper()
            if status_upper in ("FIXED", "RESOLVED", "IMPLEMENTED", "ACCEPTED"):
                status_color = disnake.Color.green()
            elif status_upper in ("PLANNED", "CONFIRMED"):
                status_color = disnake.Color.teal()
            elif status_upper in ("INVESTIGATING", "CONSIDERING"):
                status_color = disnake.Color.blue()
            elif status_upper in ("INVALID", "DECLINED", "CLOSED"):
                status_color = disnake.Color.red()

            status_embed = disnake.Embed(
                title=f"Ticket #{ticket_id} State Updated",
                description=f"Status was changed from `{str(prev_status).upper()}` to **`{status_upper}`** by {actor_str}.",
                color=status_color,
                timestamp=datetime.now(timezone.utc)
            )
            status_embed.set_footer(text=f"RBWR Utility • Ticket #{ticket_id}")
            try:
                await ch.send(
                    content=f"Ticket #{ticket_id} status updated to **`{status_upper}`** by {actor_str}.",
                    embed=status_embed
                )
                log.info(f"[Ticket Channel Update] Sent status update message in #{getattr(ch, 'name', ch.id)} for ticket #{ticket_id}")
            except Exception as send_err:
                log.warning(f"[Ticket Channel Update] Failed to send status message in #{getattr(ch, 'name', ch.id)}: {send_err}")

    try:
        asyncio.run_coroutine_threadsafe(_update_async(), disnake_bot_loop)
    except Exception as ex:
        log.warning(f"[Ticket Channel Update] Failed to dispatch update task: {ex}")

def notify_ticket_deleted(ticket: dict[str, Any], deleted_by: str = "Administrator") -> None:
    """
    Sends a message in the ticket's Discord admin channel (and discussion thread if active)
    indicating that the ticket has been deleted.
    """
    global disnake_bot, disnake_bot_loop
    if not disnake_bot or not disnake_bot.is_ready() or not disnake_bot_loop or not disnake_bot_loop.is_running():
        return

    ticket_id = ticket.get("id")
    channel_id_val = ticket.get("discord_channel_id")
    discussion_thread_id_val = ticket.get("discussion_thread_id")

    bot_ref = disnake_bot

    async def _notify_async():
        ch = None
        if channel_id_val:
            try:
                ch = bot_ref.get_channel(int(channel_id_val))
                if not ch:
                    ch = await bot_ref.fetch_channel(int(channel_id_val))
            except Exception as ex:
                log.warning(f"[Ticket Deletion Notification] Could not fetch channel {channel_id_val}: {ex}")

        if not ch and ticket_id:
            try:
                cat_id = int(TICKETS_CATEGORY_ID) if TICKETS_CATEGORY_ID.isdigit() else None
                for g in bot_ref.guilds:
                    for c in g.text_channels:
                        if cat_id and c.category_id != cat_id:
                            continue
                        name_lower = c.name.lower()
                        if (
                            name_lower == f"ticket-{ticket_id}"
                            or name_lower.startswith(f"ticket-{ticket_id}-")
                            or name_lower == f"suggestion-{ticket_id}"
                            or name_lower.startswith(f"suggestion-{ticket_id}-")
                            or name_lower == f"bug-{ticket_id}"
                            or name_lower.startswith(f"bug-{ticket_id}-")
                        ):
                            ch = c
                            break
                    if ch:
                        break
            except Exception as ex:
                log.warning(f"[Ticket Deletion Notification] Fallback channel lookup failed: {ex}")

        if ch and hasattr(ch, "send") and isinstance(ch, disnake.TextChannel):
            try:
                title_txt = ticket.get("title") or (ticket.get("suggestion") or ticket.get("description") or "")[:80] or "No Title"
                t_type = str(ticket.get("type", "suggestion")).replace("_", " ").title()

                embed = disnake.Embed(
                    title=f"Ticket #{ticket_id} Deleted",
                    description=f"This ticket has been permanently deleted from the website by **{deleted_by}**.",
                    color=disnake.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="Title", value=title_txt[:250], inline=False)
                embed.add_field(name="Type", value=t_type, inline=True)
                embed.add_field(name="Author", value=ticket.get("name") or "Anonymous", inline=True)
                embed.add_field(name="Deleted By", value=deleted_by, inline=True)
                embed.set_footer(text=f"RBWR Utility • Ticket #{ticket_id} Deleted")

                await ch.send(content=f"**Ticket #{ticket_id} was deleted by {deleted_by}.**", embed=embed)
                log.info(f"[Ticket Deletion Notification] Successfully notified #{getattr(ch, 'name', ch.id)} of deletion of Ticket #{ticket_id}")
            except Exception as e:
                log.warning(f"[Ticket Deletion Notification] Failed to post deletion in ticket channel: {e}")

        if discussion_thread_id_val:
            try:
                dt_id = int(discussion_thread_id_val)
                dt_ch = bot_ref.get_channel(dt_id)
                if not dt_ch:
                    dt_ch = await bot_ref.fetch_channel(dt_id)
                if dt_ch and hasattr(dt_ch, "send") and isinstance(dt_ch, disnake.Thread):
                    await dt_ch.send(
                        content=f"**Notice:** The ticket for this discussion (#{ticket_id}) was deleted from the website by **{deleted_by}**."
                    )
            except Exception as e:
                log.warning(f"[Ticket Deletion Notification] Failed to notify discussion thread: {e}")

    try:
        asyncio.run_coroutine_threadsafe(_notify_async(), disnake_bot_loop)
    except Exception as ex:
        log.warning(f"[Ticket Deletion Notification] Failed to dispatch task: {ex}")

async def handle_ticket_edit_note_button(inter: disnake.MessageInteraction, ticket_id: int):
    sender_discord_id = str(inter.author.id)
    is_guild_admin = inter.author.guild_permissions.administrator if (hasattr(inter.author, "guild_permissions") and isinstance(inter.author, disnake.Member)) else None
    is_admin = (ticket_bridge.is_website_admin and ticket_bridge.is_website_admin(sender_discord_id)) or is_guild_admin

    if not is_admin:
        await inter.response.send_message("Only website administrators can edit ticket notes.", ephemeral=True)
        return

    if not ticket_bridge.load_suggestions:
        await inter.response.send_message("Ticket bridge is not configured.", ephemeral=True)
        return

    data = ticket_bridge.load_suggestions()
    suggestions = data.get("suggestions", [])
    target = next((s for s in suggestions if s.get("id") == ticket_id), None)
    if not target:
        await inter.response.send_message(f"Ticket #{ticket_id} not found in database.", ephemeral=True)
        return

    current_note = target.get("admin_comment") or ""
    await inter.response.send_modal(TicketNoteModal(ticket_id=ticket_id, current_note=current_note))

async def handle_ticket_note_submission(inter: disnake.ModalInteraction, ticket_id: int):
    if _check_and_mark_interaction(inter.id) or inter.response.is_done():
        return

    sender_discord_id = str(inter.author.id)
    is_guild_admin = inter.author.guild_permissions.administrator if (hasattr(inter.author, "guild_permissions") and isinstance(inter.author, disnake.Member)) else None
    is_admin = (ticket_bridge.is_website_admin and ticket_bridge.is_website_admin(sender_discord_id)) or is_guild_admin

    if not is_admin:
        await inter.response.send_message("Only website administrators can edit ticket notes.", ephemeral=True)
        return

    note_text = inter.text_values.get("ticket_note_text", "").strip()

    if not ticket_bridge.load_suggestions or not ticket_bridge.save_suggestions:
        await inter.response.send_message("Ticket bridge is not configured.", ephemeral=True)
        return

    data = ticket_bridge.load_suggestions()
    suggestions = data.get("suggestions", [])
    target = next((s for s in suggestions if s.get("id") == ticket_id), None)
    if not target:
        await inter.response.send_message(f"Ticket #{ticket_id} not found in database.", ephemeral=True)
        return

    prev_note = target.get("admin_comment") or ""
    author_name = inter.author.display_name

    target["admin_comment"] = note_text
    target["comment_by"] = author_name
    target["comment_timestamp"] = datetime.now(timezone.utc).isoformat()

    ticket_bridge.save_suggestions(data)

    if ticket_bridge.broadcast_dashboard:
        ticket_bridge.broadcast_dashboard()

    if ticket_bridge.broadcast_ticket_update:
        ticket_bridge.broadcast_ticket_update(
            ticket_id,
            None,
            target.get("messages", []),
            target.get("discord_id"),
            target.get("anonymous")
        )

    if note_text:
        notify_ticket_author_dm(
            ticket=target,
            event_type="note",
            details={
                "comment_by": author_name,
                "comment": note_text
            }
        )

    update_ticket_channel_message(target)
    update_discussion_thread_status(target, target.get("status") or "open")

    action_word = "updated" if prev_note else "added"
    if not note_text:
        action_word = "cleared"

    await inter.response.send_message(
        f"Admin note for Ticket #{ticket_id} has been {action_word} by {inter.author.mention}."
    )

async def handle_ticket_status_select(inter: disnake.MessageInteraction, ticket_id: int):
    if _check_and_mark_interaction(inter.id) or inter.response.is_done():
        return

    sender_discord_id = str(inter.author.id)
    is_guild_admin = inter.author.guild_permissions.administrator if (hasattr(inter.author, "guild_permissions") and isinstance(inter.author, disnake.Member)) else None
    is_admin = (ticket_bridge.is_website_admin and ticket_bridge.is_website_admin(sender_discord_id)) or is_guild_admin

    if not is_admin:
        await inter.response.send_message("Only website administrators can change ticket status.", ephemeral=True)
        return

    new_status = inter.values[0] if inter.values else None
    if not new_status:
        return

    if not ticket_bridge.load_suggestions or not ticket_bridge.save_suggestions:
        await inter.response.send_message("Ticket bridge is not configured.", ephemeral=True)
        return

    data = ticket_bridge.load_suggestions()
    suggestions = data.get("suggestions", [])
    target = next((s for s in suggestions if s.get("id") == ticket_id), None)
    if not target:
        await inter.response.send_message(f"Ticket #{ticket_id} not found in database.", ephemeral=True)
        return

    prev_status = str(target.get("status") or "pending").upper()
    target["status"] = new_status
    ticket_bridge.save_suggestions(data)

    if ticket_bridge.broadcast_dashboard:
        ticket_bridge.broadcast_dashboard()

    if ticket_bridge.broadcast_ticket_update:
        ticket_bridge.broadcast_ticket_update(
            ticket_id,
            None,
            target.get("messages", []),
            target.get("discord_id"),
            target.get("anonymous")
        )

    notify_ticket_author_dm(
        ticket=target,
        event_type="status",
        details={
            "changed_by": inter.author.display_name,
            "status": new_status
        }
    )

    update_discussion_thread_status(
        ticket=target,
        new_status=new_status,
        changed_by=inter.author.mention,
        prev_status=prev_status
    )

    update_ticket_channel_message(
        ticket=target,
        changed_by=inter.author.mention,
        prev_status=prev_status
    )

    if not inter.response.is_done():
        await inter.response.send_message(
            f"Ticket #{ticket_id} status updated from `{prev_status}` to **`{new_status.upper()}`**.",
            ephemeral=True
        )

async def handle_ticket_open_discussions(inter: disnake.MessageInteraction, ticket_id: int):
    if _check_and_mark_interaction(inter.id) or inter.response.is_done():
        return

    sender_discord_id = str(inter.author.id)
    is_guild_admin = inter.author.guild_permissions.administrator if (hasattr(inter.author, "guild_permissions") and isinstance(inter.author, disnake.Member)) else None
    is_admin = (ticket_bridge.is_website_admin and ticket_bridge.is_website_admin(sender_discord_id)) or is_guild_admin

    if not is_admin:
        await inter.response.send_message("Only administrators can open discussion threads.", ephemeral=True)
        return

    if not ticket_bridge.load_suggestions:
        await inter.response.send_message("Ticket bridge is not configured.", ephemeral=True)
        return

    data = ticket_bridge.load_suggestions()
    suggestions = data.get("suggestions", [])
    target = next((s for s in suggestions if s.get("id") == ticket_id), None)
    if not target:
        await inter.response.send_message(f"Ticket #{ticket_id} not found in database.", ephemeral=True)
        return

    existing_thread_id = target.get("discussion_thread_id")
    if existing_thread_id:
        await inter.response.send_message(
            f"A discussion thread has already been created for Ticket #{ticket_id}: <#{existing_thread_id}>",
            ephemeral=True
        )
        return

    await inter.response.defer(ephemeral=False)

    is_bug = (target.get("type") == "bug_report")
    target_channel_id = BUGS_DISCUSSION_CHANNEL_ID if is_bug else SUGGESTIONS_DISCUSSION_CHANNEL_ID

    bot_ref = inter.bot
    dest_ch = bot_ref.get_channel(target_channel_id)
    if not dest_ch:
        try:
            dest_ch = await bot_ref.fetch_channel(target_channel_id)
        except Exception as e:
            await inter.followup.send(f"Failed to access discussion channel <#{target_channel_id}>: `{e}`", ephemeral=True)
            return

    raw_title = target.get("title") or (target.get("suggestion") or target.get("description") or f"Ticket #{ticket_id}")[:60]
    thread_name = f"[{'Bug' if is_bug else 'Suggestion'} #{ticket_id}] {raw_title}"[:95]
    desc_content = target.get("suggestion") or target.get("description") or "No description provided."

    author_discord_id = target.get("discord_id")
    if author_discord_id and str(author_discord_id).isdigit():
        author_ping = f"<@{author_discord_id}>"
    else:
        author_ping = f"**{target.get('name', 'Anonymous')}**"

    embed = disnake.Embed(
        title=f"{'Bug Report' if is_bug else 'Feature Suggestion'} #{ticket_id}: {raw_title}",
        description=desc_content[:3500],
        color=disnake.Color.red() if is_bug else disnake.Color.blurple(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="Author", value=author_ping, inline=True)
    embed.add_field(name="Type", value="Bug Report" if is_bug else "Feature Suggestion", inline=True)
    embed.add_field(name="Status", value=(target.get("status") or ("open" if is_bug else "pending")).upper(), inline=True)
    embed.set_footer(text=f"RBWR Community Discussion • Ticket #{ticket_id}")

    init_msg = f"{author_ping} — Discussion thread opened for Ticket #{ticket_id}!"

    created_thread = None
    starter_msg = None
    try:
        if isinstance(dest_ch, disnake.ForumChannel):
            forum_post = await dest_ch.create_thread(
                name=thread_name,
                content=init_msg,
                embed=embed,
                allowed_mentions=disnake.AllowedMentions(users=True)
            )
            created_thread = forum_post.thread
            starter_msg = getattr(forum_post, "message", None)
        elif isinstance(dest_ch, disnake.TextChannel):
            created_thread = await dest_ch.create_thread(
                name=thread_name,
                type=disnake.ChannelType.public_thread
            )
            starter_msg = await created_thread.send(
                content=init_msg,
                embed=embed,
                allowed_mentions=disnake.AllowedMentions(users=True)
            )
        elif isinstance(dest_ch, disnake.Thread):
            starter_msg = await dest_ch.send(
                content=init_msg,
                embed=embed,
                allowed_mentions=disnake.AllowedMentions(users=True)
            )
            created_thread = dest_ch
        elif hasattr(dest_ch, "create_thread"):
            created_thread = await dest_ch.create_thread(name=thread_name)
            starter_msg = await created_thread.send(
                content=init_msg,
                embed=embed,
                allowed_mentions=disnake.AllowedMentions(users=True)
            )
    except Exception as ex:
        log.error(f"[Discussion Thread] Error creating thread in {dest_ch}: {ex}", exc_info=True)
        await inter.followup.send(f"Failed to create thread in {dest_ch.mention}: `{ex}`", ephemeral=True)
        return

    if created_thread:
        target["discussion_thread_id"] = str(created_thread.id)
        target["discussion_channel_id"] = str(target_channel_id)
        if starter_msg:
            target["discussion_message_id"] = str(starter_msg.id)
        if ticket_bridge.save_suggestions:
            ticket_bridge.save_suggestions(data)
        if ticket_bridge.broadcast_dashboard:
            ticket_bridge.broadcast_dashboard()

        await inter.followup.send(
            f"Discussion thread created for **Ticket #{ticket_id}** in {dest_ch.mention}: {created_thread.mention}!"
        )
    else:
        await inter.followup.send(
            f"Unable to create discussion thread in {dest_ch.mention}.",
            ephemeral=True
        )

ROBLOX_PLACE_ID = "11765852158"

def get_server_points_rate(server: dict[str, Any]) -> float | None:
    if not isinstance(server, dict):
        return None
    if "points_rate" in server and server["points_rate"] is not None:
        try:
            return float(server["points_rate"])
        except (ValueError, TypeError):
            pass
    st = server.get("state")
    if isinstance(st, dict):
        misc = st.get("Misc")
        if isinstance(misc, dict) and "Total points/second" in misc:
            val = misc.get("Total points/second")
            if val is not None:
                try:
                    return float(val)
                except (ValueError, TypeError):
                    pass
    return None

def get_server_top_score(server: dict[str, Any]) -> float:
    if not isinstance(server, dict):
        return 0.0
    for key in ("top_score", "topScore", "score", "TopScore"):
        val = server.get(key)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                pass
    st = server.get("state")
    if isinstance(st, dict):
        for key in ("top_score", "topScore", "score"):
            val = st.get(key)
            if val is not None:
                try:
                    return float(st[key])
                except (ValueError, TypeError):
                    pass
    if calculate_server_top_score and "snapshots" in server and isinstance(server["snapshots"], dict):
        try:
            return float(calculate_server_top_score(server["snapshots"]))
        except Exception:
            pass
    pts = get_server_points_rate(server)
    if pts is not None and pts > 0.0:
        return round(min(100.0, (pts / 2.9) * 100.0), 1)
    return 0.0

def get_unit_state(server: dict[str, Any], unit: int) -> dict[str, Any]:
    if not isinstance(server, dict):
        return {}
    st = server.get("state")
    if isinstance(st, dict):
        u = st.get(f"Unit{unit}")
        if isinstance(u, dict):
            return u
    return {}

def get_unit_aprm(u_state: dict[str, Any]) -> float:
    aprm = u_state.get("APRM")
    if aprm is not None:
        try:
            return float(aprm)
        except (ValueError, TypeError):
            pass
    return 0.0

def is_unit_running(u_state: dict[str, Any]) -> bool:
    return get_unit_aprm(u_state) > 5.0

def get_unit_status_badge(u_state: dict[str, Any]) -> str:
    aprm = get_unit_aprm(u_state)
    scram = u_state.get("SCRAMreason")
    if scram and str(scram).strip() not in ("None", "", "null"):
        return f"SCRAM: {str(scram).strip()} ({aprm:.1f}%)"
    if aprm > 5.0:
        return f"Running ({aprm:.1f}% APRM)"
    return f"Offline ({aprm:.1f}% APRM)"

def get_unit_output_mw(u_dict: dict[str, Any] | None) -> float:
    if not isinstance(u_dict, dict):
        return 0.0
    for k in ("Output (MW)", "PradDoSieci", "Output", "Power", "megawatts", "output_mw"):
        val = u_dict.get(k)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                continue
    return 0.0

def get_unit_demand(u_state: dict[str, Any] | None, s_state: dict[str, Any] | None = None, unit: int = 1) -> float | None:
    if isinstance(u_state, dict):
        for k in ("Demand", "Demand (MW)", "TargetDemand", "demand_mw"):
            v = u_state.get(k)
            if v is not None:
                try:
                    val = float(v)
                    if val > 0:
                        return val
                except (ValueError, TypeError):
                    pass
    if isinstance(s_state, dict):
        for k in (f"DemandU{unit}", f"NextDemandU{unit}", f"Demand{unit}", f"TargetDemand{unit}"):
            v = s_state.get(k)
            if v is not None:
                try:
                    val = float(v)
                    if val > 0:
                        return val
                except (ValueError, TypeError):
                    pass
    return None

def make_roblox_join_url(job_id: str) -> str:
    return f"https://www.roblox.com/games/start?placeId={ROBLOX_PLACE_ID}&gameInstanceId={job_id}"

def make_web_server_url(job_id: str) -> str:
    return f"{DEFAULT_SERVER_BASE_URL}/servers/{job_id}"

class ServerBrowserView(disnake.ui.View):
    PAGE_SIZE = 5

    def __init__(
        self,
        client: RBWRClient,
        author_id: int,
        all_servers: list[dict[str, Any]],
        query: str = "",
        sort_by: str = "points",
        filter_status: str = "all",
    ):
        super().__init__(timeout=300)
        self.client = client
        self.author_id = author_id
        self.raw_servers = all_servers
        self.query = (query or "").strip().lower()
        self.sort_by = sort_by
        self.filter_status = filter_status
        self.page = 0
        self.selected_server_job_id: str | None = None

        self.filtered_servers: list[dict[str, Any]] = []
        self._apply_filtering_and_sorting()
        self.rebuild_components()

    def _apply_filtering_and_sorting(self):
        max_public_score = 0.0
        best_server_tuple = None
        if self.filter_status in ("top_server", "top_servers", "top"):
            for s in self.raw_servers:
                if not is_server_public(s):
                    continue
                sc = get_server_top_score(s)
                if sc > max_public_score:
                    max_public_score = sc
                u1 = get_unit_state(s, 1)
                u2 = get_unit_state(s, 2)
                p = get_server_points_rate(s) or 0.0
                run_c = int(is_unit_running(u1)) + int(is_unit_running(u2))
                cand_tuple = (sc, p, run_c)
                if best_server_tuple is None or cand_tuple > best_server_tuple:
                    best_server_tuple = cand_tuple

        matched = []
        for s in self.raw_servers:
            if not is_server_public(s):
                continue

            jid = str(s.get("jobId", ""))
            short = self.client.short_id(jid).lower()
            u1 = get_unit_state(s, 1)
            u2 = get_unit_state(s, 2)
            u1_running = is_unit_running(u1)
            u2_running = is_unit_running(u2)
            pts = get_server_points_rate(s)
            u1_scram = str(u1.get("SCRAMreason", "None")).strip()
            u2_scram = str(u2.get("SCRAMreason", "None")).strip()
            has_scram = (u1_scram not in ("None", "", "null")) or (u2_scram not in ("None", "", "null"))
            top_score = get_server_top_score(s)

            if self.query:
                q = self.query.replace("-", "")
                norm_jid = jid.lower().replace("-", "")
                norm_short = short.replace("-", "")
                if (q not in norm_jid) and (q not in norm_short) and (q not in u1_scram.lower()) and (q not in u2_scram.lower()):
                    continue

            if self.filter_status == "top_server":
                cand_tuple = (top_score, pts or 0.0, int(u1_running) + int(u2_running))
                if best_server_tuple and cand_tuple < best_server_tuple:
                    continue
            elif self.filter_status in ("top_servers", "top"):
                if max_public_score >= 70.0:
                    if top_score < 70.0:
                        continue
                elif max_public_score >= 50.0:
                    if top_score < 50.0:
                        continue
                elif max_public_score > 0.0:
                    if top_score < max_public_score * 0.8:
                        continue
                else:
                    if (not (u1_running or u2_running)) or (pts is None or pts <= 0):
                        continue
            elif self.filter_status == "running":
                if not (u1_running or u2_running):
                    continue
            elif self.filter_status == "both":
                if not (u1_running and u2_running):
                    continue
            elif self.filter_status == "points":
                if pts is None or pts <= 0:
                    continue
            elif self.filter_status == "scrammed":
                if not has_scram:
                    continue

            matched.append(s)

        def sort_key_fn(s: dict[str, Any]):
            u1 = get_unit_state(s, 1)
            u2 = get_unit_state(s, 2)
            pts = get_server_points_rate(s)
            pts_val = pts if pts is not None else -1.0
            u1_aprm = get_unit_aprm(u1)
            u2_aprm = get_unit_aprm(u2)
            run_count = int(is_unit_running(u1)) + int(is_unit_running(u2))
            top_score = get_server_top_score(s)

            if self.sort_by in ("top_servers", "top", "top_score", "top_server"):
                return (top_score, pts_val, run_count, u1_aprm + u2_aprm)
            elif self.sort_by == "points":
                return (pts_val, top_score, run_count, u1_aprm + u2_aprm)
            elif self.sort_by == "active_reactors":
                return (run_count, top_score, u1_aprm + u2_aprm, pts_val)
            elif self.sort_by == "aprm_u1":
                return (u1_aprm, u2_aprm, top_score)
            elif self.sort_by == "aprm_u2":
                return (u2_aprm, u1_aprm, top_score)
            elif self.sort_by == "players":
                p_str = get_player_count(s)
                try:
                    p_num = int(p_str)
                except ValueError:
                    p_num = -1
                return (p_num, top_score, pts_val)
            elif self.sort_by == "id":
                return self.client.short_id(str(s.get("jobId", "")))
            return (top_score, pts_val)

        reverse = (self.sort_by != "id")
        matched.sort(key=sort_key_fn, reverse=reverse)
        self.filtered_servers = matched

        max_page = max(0, (len(self.filtered_servers) - 1) // self.PAGE_SIZE)
        if self.page > max_page:
            self.page = max_page

    def build_embed(self) -> disnake.Embed:
        if self.selected_server_job_id:
            selected = next((s for s in self.filtered_servers if str(s.get("jobId")) == self.selected_server_job_id), None)
            if not selected:
                selected = next((s for s in self.raw_servers if str(s.get("jobId")) == self.selected_server_job_id), None)
            if selected:
                return self._build_detail_embed(selected)

        total_matched = len(self.filtered_servers)
        total_pages = max(1, (total_matched + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        start_idx = self.page * self.PAGE_SIZE
        page_servers = self.filtered_servers[start_idx : start_idx + self.PAGE_SIZE]

        active_reactors = sum(
            int(is_unit_running(get_unit_state(s, 1))) + int(is_unit_running(get_unit_state(s, 2)))
            for s in self.filtered_servers
        )
        total_gen = sum(
            (get_server_points_rate(s) or 0.0)
            for s in self.filtered_servers
        )

        embed = disnake.Embed(
            title="RBWR Live Server Browser",
            color=disnake.Color.teal() if total_matched > 0 else disnake.Color.dark_grey(),
            timestamp=datetime.now(timezone.utc),
        )

        filter_names = {
            "all": "All Public",
            "top_servers": "Top Servers",
            "top_server": "Top Server",
            "top": "Top Servers",
            "running": "Running (≥ 1 Unit)",
            "both": "Dual Running",
            "points": "Points (> 0/s)",
            "scrammed": "Scrammed",
        }
        sort_names = {
            "top_servers": "Top Servers",
            "top": "Top Servers",
            "top_server": "Top Server",
            "points": "Points / sec",
            "active_reactors": "Active Units",
            "aprm_u1": "U1 APRM",
            "aprm_u2": "U2 APRM",
            "players": "Players",
            "id": "Server ID",
        }

        desc_lines = [
            f"**Filter:** `{filter_names.get(self.filter_status, self.filter_status)}` • **Sort:** `{sort_names.get(self.sort_by, self.sort_by)}`"
        ]
        if self.query:
            desc_lines.append(f"**Search Query:** `{self.query}`")

        desc_lines.append(
            f"**Matching:** `{total_matched}` • **Active Units:** `{active_reactors}` • **Total Gen:** `{total_gen:.2f} pts/s`\n"
        )

        if not page_servers:
            desc_lines.append("*No public servers matched your search / filter criteria.*")
            desc_lines.append("Try adjusting your filter or search query above.")
        else:
            for s in page_servers:
                jid = str(s.get("jobId", "unknown"))
                short = self.client.short_id(jid)
                u1 = get_unit_state(s, 1)
                u2 = get_unit_state(s, 2)
                u1_badge = get_unit_status_badge(u1)
                u2_badge = get_unit_status_badge(u2)
                pts = get_server_points_rate(s)
                pts_str = f"{pts:.2f} pts/s" if pts is not None else "N/A"
                top_score = get_server_top_score(s)
                score_str = f"{top_score:.1f}" if top_score > 0 else "0.0"
                players = get_player_count(s)
                p_display = f"{players}/12" if players != "?" else "?"
                web_url = make_web_server_url(jid)
                join_url = make_roblox_join_url(jid)

                desc_lines.append(
                    f"**[`{short}`]({web_url})** • [`Join Game`]({join_url})\n"
                    f"`Job ID:` `{jid}`\n"
                    f"• **Score:** `{score_str}/100` | **Points:** `{pts_str}` | **Players:** `{p_display}`\n"
                    f"• **U1:** {u1_badge} | **U2:** {u2_badge}\n"
                )

        embed.description = "\n".join(desc_lines)
        embed.set_footer(
            text=f"Page {self.page + 1}/{total_pages} • Total Public: {len(self.raw_servers)} • User App Ready"
        )
        return embed

    def _build_detail_embed(self, server: dict[str, Any]) -> disnake.Embed:
        jid = str(server.get("jobId", "unknown"))
        short = self.client.short_id(jid)
        u1 = get_unit_state(server, 1)
        u2 = get_unit_state(server, 2)
        pts = get_server_points_rate(server)
        pts_str = f"{pts:.4f}".rstrip("0").rstrip(".") + " pts/s" if pts is not None else "N/A"
        top_score = get_server_top_score(server)
        score_str = f"{top_score:.1f}/100" if top_score > 0 else "0.0/100"
        is_pub = is_server_public(server)
        vis_label = "Public" if is_pub else "Private"
        players = get_player_count(server)
        p_display = f"{players}/12" if (is_pub and players != "?") else ("Private" if not is_pub else "?")

        u1_running = is_unit_running(u1)
        u2_running = is_unit_running(u2)
        if u1_running and u2_running:
            color = disnake.Color.green()
        elif u1_running or u2_running:
            color = disnake.Color.gold()
        else:
            color = disnake.Color.dark_theme() if hasattr(disnake.Color, "dark_theme") else disnake.Color.greyple()

        embed = disnake.Embed(
            title=f"RBWR Server Metrics — {short}",
            description=(
                f"**Job ID:** `{jid}`\n"
                f"**Top Score:** `{score_str}`\n"
                f"**Points Generation:** `{pts_str}`\n"
                f"**Active Players:** `{p_display}`\n"
                f"**Visibility:** `{vis_label}`"
            ),
            color=color,
            timestamp=datetime.now(timezone.utc),
        )

        def unit_field(u_num: int, u_data: dict[str, Any]) -> str:
            scram = u_data.get("SCRAMreason")
            scram_text = f"**Last SCRAM:** {scram}\n" if (scram and str(scram).strip() not in ("None", "", "null")) else ""
            demand_left = u_data.get("Demand Time Left")
            demand_text = f"**Demand Timer:** `{demand_left}s`\n" if demand_left is not None else ""
            return (
                f"{scram_text}"
                f"**APRM:** `{fmt(u_data.get('APRM'))}%`\n"
                f"**RTP:** `{fmt(u_data.get('RTP'))}%`\n"
                f"**Reactor Temp:** `{fmt(u_data.get('Reactor Temp'))} °C`\n"
                f"**Output:** `{fmt(u_data.get('Output (MW)'))} MW`\n"
                f"**Turbine RPM:** `{fmt(u_data.get('Turbine RPM'))}`\n"
                f"**Points / sec:** `{fmt(u_data.get('PointsPerSecond'))}`\n"
                f"**Xenon:** `{fmt(u_data.get('Xenon'))}`\n"
                f"{demand_text}"
            )

        embed.add_field(name=f"Unit 1 ({get_unit_status_badge(u1)})", value=unit_field(1, u1), inline=True)
        embed.add_field(name=f"Unit 2 ({get_unit_status_badge(u2)})", value=unit_field(2, u2), inline=True)

        st = server.get("state") if isinstance(server, dict) else None
        misc = st.get("Misc") if isinstance(st, dict) else None
        if isinstance(misc, dict) and misc:
            misc_lines = []
            for k in ("Outside Temperature", "EDG Diesel Storage", "FSS Smoke Detected", "Evacuation Cooldown"):
                if k in misc:
                    misc_lines.append(f"**{k}:** `{misc[k]}`")
            if misc_lines:
                embed.add_field(name="Environmental / Facility", value="\n".join(misc_lines), inline=False)

        footer_vis = f" • {vis_label}" if not is_pub else ""
        embed.set_footer(text=f"RBWR Utility • Server ID: {short}{footer_vis}")
        return embed

    def rebuild_components(self):
        self.clear_items()

        if self.selected_server_job_id:
            jid = self.selected_server_job_id
            selected_server = next((s for s in self.raw_servers if str(s.get("jobId", "")) == jid), None)
            is_pub = is_server_public(selected_server) if selected_server else True
            if is_pub:
                self.add_item(disnake.ui.Button(
                    label="Join in Roblox",
                    url=make_roblox_join_url(jid),
                    row=0,
                ))
            self.add_item(disnake.ui.Button(
                label="Open Web View",
                url=make_web_server_url(jid),
                row=0,
            ))
            back_btn = disnake.ui.Button(
                label="Back to Server List",
                style=disnake.ButtonStyle.secondary,
                row=0,
            )
            back_btn.callback = self.on_back_to_list
            self.add_item(back_btn)
            return

        filter_options = [
            disnake.SelectOption(label="All Public Servers", value="all", description="Show all online public servers", default=(self.filter_status == "all")),
            disnake.SelectOption(label="Top Servers", value="top_servers", description="Highest scoring operational servers", default=(self.filter_status in ("top", "top_servers"))),
            disnake.SelectOption(label="Top Server", value="top_server", description="Show only the single #1 ranked server", default=(self.filter_status == "top_server")),
            disnake.SelectOption(label="Running Reactors", value="running", description="At least 1 unit running (>5% APRM)", default=(self.filter_status == "running")),
            disnake.SelectOption(label="Dual Running Reactors", value="both", description="Both units actively running", default=(self.filter_status == "both")),
            disnake.SelectOption(label="Earning Points", value="points", description="Points rate > 0 pts/sec", default=(self.filter_status == "points")),
            disnake.SelectOption(label="Scrammed Reactors", value="scrammed", description="Servers with an active reactor SCRAM", default=(self.filter_status == "scrammed")),
        ]
        filter_select = disnake.ui.StringSelect(
            custom_id="browser_filter_select",
            placeholder="Filter servers...",
            options=filter_options,
            row=0,
        )
        filter_select.callback = self.on_filter_change
        self.add_item(filter_select)

        sort_options = [
            disnake.SelectOption(label="Top Servers", value="top_servers", description="Sort by Top Score and points rate", default=(self.sort_by in ("top", "top_servers"))),
            disnake.SelectOption(label="Highest Points / sec", value="points", description="Sort by highest points generation rate", default=(self.sort_by == "points")),
            disnake.SelectOption(label="Most Running Reactors", value="active_reactors", description="Dual running > single running > offline", default=(self.sort_by == "active_reactors")),
            disnake.SelectOption(label="Highest Unit 1 APRM", value="aprm_u1", description="Sort by Unit 1 core power", default=(self.sort_by == "aprm_u1")),
            disnake.SelectOption(label="Highest Unit 2 APRM", value="aprm_u2", description="Sort by Unit 2 core power", default=(self.sort_by == "aprm_u2")),
            disnake.SelectOption(label="Most Players", value="players", description="Sort by player population", default=(self.sort_by == "players")),
            disnake.SelectOption(label="Server ID (A-Z)", value="id", description="Alphabetical sort by short ID", default=(self.sort_by == "id")),
        ]
        sort_select = disnake.ui.StringSelect(
            custom_id="browser_sort_select",
            placeholder="Sort by...",
            options=sort_options,
            row=1,
        )
        sort_select.callback = self.on_sort_change
        self.add_item(sort_select)

        start_idx = self.page * self.PAGE_SIZE
        page_servers = self.filtered_servers[start_idx : start_idx + self.PAGE_SIZE]
        if page_servers:
            inspect_options = []
            for s in page_servers:
                jid = str(s.get("jobId", ""))
                short = self.client.short_id(jid)
                u1 = get_unit_state(s, 1)
                u2 = get_unit_state(s, 2)
                pts = get_server_points_rate(s)
                pts_str = f"{pts:.2f} pts/s" if pts is not None else "N/A"
                top_score = get_server_top_score(s)
                score_badge = f"Score: {top_score:.1f}" if top_score > 0 else "Score: 0.0"
                label = f"{short} • {pts_str}"
                desc = f"{score_badge} | U1: {get_unit_aprm(u1):.0f}% | U2: {get_unit_aprm(u2):.0f}%"
                inspect_options.append(disnake.SelectOption(
                    label=label[:100],
                    value=jid,
                    description=desc[:100],
                ))
            inspect_select = disnake.ui.StringSelect(
                custom_id="browser_inspect_select",
                placeholder="Select a server to inspect full operational stats...",
                options=inspect_options,
                row=2,
            )
            inspect_select.callback = self.on_inspect_select
            self.add_item(inspect_select)

        total_matched = len(self.filtered_servers)
        total_pages = max(1, (total_matched + self.PAGE_SIZE - 1) // self.PAGE_SIZE)

        prev_btn = disnake.ui.Button(
            label="[<] Prev",
            style=disnake.ButtonStyle.primary,
            disabled=(self.page <= 0),
            row=3,
        )
        prev_btn.callback = self.on_prev
        self.add_item(prev_btn)

        page_indicator = disnake.ui.Button(
            label=f"Page {self.page + 1} / {total_pages}",
            style=disnake.ButtonStyle.secondary,
            disabled=True,
            row=3,
        )
        self.add_item(page_indicator)

        next_btn = disnake.ui.Button(
            label="Next [>]",
            style=disnake.ButtonStyle.primary,
            disabled=(self.page >= total_pages - 1),
            row=3,
        )
        next_btn.callback = self.on_next
        self.add_item(next_btn)

        refresh_btn = disnake.ui.Button(
            label="Refresh",
            style=disnake.ButtonStyle.success,
            row=3,
        )
        refresh_btn.callback = self.on_refresh
        self.add_item(refresh_btn)

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        if self.author_id and interaction.author.id != self.author_id:
            await interaction.response.send_message(
                "This server browser belongs to another session. Use `/servers` to open your own interactive browser!",
                ephemeral=True
            )
            return False
        return True

    async def on_prev(self, inter: disnake.MessageInteraction):
        if self.page > 0:
            self.page -= 1
        self.rebuild_components()
        await inter.response.edit_message(embed=self.build_embed(), view=self)

    async def on_next(self, inter: disnake.MessageInteraction):
        total_pages = max(1, (len(self.filtered_servers) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        if self.page < total_pages - 1:
            self.page += 1
        self.rebuild_components()
        await inter.response.edit_message(embed=self.build_embed(), view=self)

    async def on_filter_change(self, inter: disnake.MessageInteraction):
        self.filter_status = inter.values[0]  # pyright: ignore[reportOptionalSubscript]
        self.page = 0
        self.selected_server_job_id = None
        self._apply_filtering_and_sorting()
        self.rebuild_components()
        await inter.response.edit_message(embed=self.build_embed(), view=self)

    async def on_sort_change(self, inter: disnake.MessageInteraction):
        self.sort_by = inter.values[0]  # pyright: ignore[reportOptionalSubscript]
        self.page = 0
        self.selected_server_job_id = None
        self._apply_filtering_and_sorting()
        self.rebuild_components()
        await inter.response.edit_message(embed=self.build_embed(), view=self)

    async def on_inspect_select(self, inter: disnake.MessageInteraction):
        self.selected_server_job_id = inter.values[0]  # pyright: ignore[reportOptionalSubscript]
        self.rebuild_components()
        await inter.response.edit_message(embed=self.build_embed(), view=self)

    async def on_back_to_list(self, inter: disnake.MessageInteraction):
        self.selected_server_job_id = None
        self.rebuild_components()
        await inter.response.edit_message(embed=self.build_embed(), view=self)

    async def on_refresh(self, inter: disnake.MessageInteraction):
        await inter.response.defer()
        try:
            payload = await self.client.fetch(public_only=True)
            self.raw_servers = payload.get("data", {}).get("servers", [])
        except Exception:
            pass
        self._apply_filtering_and_sorting()
        self.rebuild_components()
        await inter.edit_original_response(embed=self.build_embed(), view=self)

    async def on_error(self, error: Exception, item: disnake.ui.Item, interaction: disnake.MessageInteraction) -> None:
        log.error(f"[ServerBrowserView] Interaction error on item {getattr(item, 'custom_id', item)}: {error}", exc_info=error)
        tb_str = "".join(traceback.format_exception(type(error), error, error.__traceback__)) if error and getattr(error, "__traceback__", None) else traceback.format_exc()
        ctx = {
            "View": "ServerBrowserView",
            "Component": str(getattr(item, "custom_id", item)),
            "User": f"{interaction.author.name} (ID: {interaction.author.id})",
            "Channel": f"#{getattr(interaction.channel, 'name', 'unknown')} (ID: {interaction.channel_id})",
        }
        await send_error_alert_async(
            origin="Bot Server Browser View",
            error=error,
            traceback_str=tb_str,
            context_info=ctx,
        )
        try:
            msg = "An error occurred while interacting with the server browser."
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            pass

def create_bot_instance(data_supplier: Callable[[bool], dict[str, Any]] | None = None) -> commands.InteractionBot:
    global disnake_bot
    intents = disnake.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.members = True

    new_bot = commands.InteractionBot(
        intents=intents,
        test_guilds=None,
        default_install_types=disnake.ApplicationInstallTypes.all(),
        default_contexts=disnake.InteractionContextTypes.all(),
    )
    new_bot.rbwr = RBWRClient(data_supplier=data_supplier)  # pyright: ignore[reportAttributeAccessIssue]

    register_bot_events_and_commands(new_bot)
    disnake_bot = new_bot
    return new_bot

def fmt(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)

def get_player_count(server: dict[str, Any]) -> str:
    if not is_server_public(server):
        return "?"
    for key in ("playerCount", "PlayerCount", "players", "Players", "player_count"):
        if key in server and server[key] is not None:
            return str(server[key])
    return "?"

def state_for(server: dict[str, Any], unit: int) -> dict[str, Any]:
    if not isinstance(server, dict):
        return {}
    st_root = server.get("state")
    st = st_root.get(f"Unit{unit}") if isinstance(st_root, dict) else None
    st = st if isinstance(st, dict) else {}
    if st.get("Output (MW)") is None:
        p_val = st.get("PradDoSieci")
        if p_val is None:
            p_val = st.get("Output") or st.get("Power") or st.get("megawatts")
        if p_val is not None:
            st["Output (MW)"] = p_val
    return st

def add_info(embed: disnake.Embed, server: dict[str, Any], unit: int, info: str):
    st = state_for(server, unit)

    if info == "all":
        lines = [
            f"**APRM:** {fmt(st.get('APRM'))}",
            f"**RTP:** {fmt(st.get('RTP'))}",
            f"**Xenon:** {fmt(st.get('Xenon'))}",
            f"**Reactor Temp:** {fmt(st.get('Reactor Temp'))}",
            f"**Output:** {fmt(st.get('Output (MW)'))} MW",
            f"**Turbine RPM:** {fmt(st.get('Turbine RPM'))}",
            f"**Points/s:** {fmt(st.get('PointsPerSecond'))}",
            f"**Demand time:** {fmt(st.get('Demand Time Left'))} s",
            f"**SCRAM:** {fmt(st.get('SCRAMreason'))}",
        ]
        embed.add_field(name=f"Unit {unit}", value="\n".join(lines), inline=True)
        return

    if info == "demand":
        key = "NextDemandU1" if unit == 1 else "NextDemandU2"
        label, value = "Next demand", st.get(key)
    else:
        key = INFO_ALIASES.get(info, info)
        label, value = key, st.get(key)

    embed.add_field(name=f"U{unit} — {label}", value=fmt(value), inline=True)

SORT_CHOICES = [
    disnake.OptionChoice(name="Top Servers (Top Score)", value="top_servers"),
    disnake.OptionChoice(name="Highest Points / sec", value="points"),
    disnake.OptionChoice(name="Most Running Reactors", value="active_reactors"),
    disnake.OptionChoice(name="Highest Unit 1 APRM", value="aprm_u1"),
    disnake.OptionChoice(name="Highest Unit 2 APRM", value="aprm_u2"),
    disnake.OptionChoice(name="Most Players", value="players"),
    disnake.OptionChoice(name="Server ID (A-Z)", value="id"),
]

FILTER_CHOICES = [
    disnake.OptionChoice(name="All Public Servers", value="all"),
    disnake.OptionChoice(name="Top Servers (High Score & Performance)", value="top_servers"),
    disnake.OptionChoice(name="Top Server (#1 Ranked Server)", value="top_server"),
    disnake.OptionChoice(name="Running Reactors (≥ 1 Unit)", value="running"),
    disnake.OptionChoice(name="Dual Running Reactors (Both Units)", value="both"),
    disnake.OptionChoice(name="Earning Points (> 0 pts/s)", value="points"),
    disnake.OptionChoice(name="Scrammed Reactors", value="scrammed"),
]

def register_bot_events_and_commands(b: commands.InteractionBot):
    @b.event
    async def on_ready():
        global disnake_bot, disnake_bot_loop
        disnake_bot = b
        try:
            disnake_bot_loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        log.info(f"[Disnake Bot] Connected and active as {b.user} (ID: {b.user.id if b.user else 'N/A'})")

    @b.event
    async def on_slash_command_error(inter: disnake.ApplicationCommandInteraction, error: Exception):
        log.error(f"[Disnake Bot] Slash command error in /{getattr(inter.data, 'name', 'unknown')}: {error}", exc_info=error)
        orig_err = getattr(error, "original", error)
        tb_str = "".join(traceback.format_exception(type(orig_err), orig_err, orig_err.__traceback__)) if orig_err and getattr(orig_err, "__traceback__", None) else traceback.format_exc()

        cmd_name = getattr(inter.data, "name", "unknown") if hasattr(inter, "data") else "unknown"
        ctx = {
            "Command": f"/{cmd_name}",
            "User": f"{inter.author.name} (ID: {inter.author.id})",
            "Channel": f"#{getattr(inter.channel, 'name', 'unknown')} (ID: {inter.channel_id})",
            "Guild": f"{inter.guild.name} (ID: {inter.guild.id})" if inter.guild else "Direct Message",
        }
        if hasattr(inter, "filled_options") and inter.filled_options:
            ctx["Options"] = str(inter.filled_options)[:500]

        await send_error_alert_async(
            origin=f"Bot Slash Command (/{cmd_name})",
            error=orig_err,
            traceback_str=tb_str,
            context_info=ctx,
        )

        try:
            msg = "An unexpected error occurred while processing this command."
            if inter.response.is_done():
                await inter.followup.send(msg, ephemeral=True)
            else:
                await inter.response.send_message(msg, ephemeral=True)
        except Exception:
            pass

    @b.event
    async def on_user_command_error(inter: disnake.ApplicationCommandInteraction, error: Exception):
        log.error(f"[Disnake Bot] User command error: {error}", exc_info=error)
        orig_err = getattr(error, "original", error)
        tb_str = "".join(traceback.format_exception(type(orig_err), orig_err, orig_err.__traceback__)) if orig_err and getattr(orig_err, "__traceback__", None) else traceback.format_exc()
        cmd_name = getattr(inter.data, "name", "unknown") if hasattr(inter, "data") else "unknown"
        ctx = {
            "Command": f"User Command: {cmd_name}",
            "User": f"{inter.author.name} (ID: {inter.author.id})",
            "Channel": f"#{getattr(inter.channel, 'name', 'unknown')} (ID: {inter.channel_id})",
        }
        await send_error_alert_async(
            origin="Bot User Command",
            error=orig_err,
            traceback_str=tb_str,
            context_info=ctx,
        )

    @b.event
    async def on_message_command_error(inter: disnake.ApplicationCommandInteraction, error: Exception):
        log.error(f"[Disnake Bot] Message command error: {error}", exc_info=error)
        orig_err = getattr(error, "original", error)
        tb_str = "".join(traceback.format_exception(type(orig_err), orig_err, orig_err.__traceback__)) if orig_err and getattr(orig_err, "__traceback__", None) else traceback.format_exc()
        cmd_name = getattr(inter.data, "name", "unknown") if hasattr(inter, "data") else "unknown"
        ctx = {
            "Command": f"Message Command: {cmd_name}",
            "User": f"{inter.author.name} (ID: {inter.author.id})",
            "Channel": f"#{getattr(inter.channel, 'name', 'unknown')} (ID: {inter.channel_id})",
        }
        await send_error_alert_async(
            origin="Bot Message Command",
            error=orig_err,
            traceback_str=tb_str,
            context_info=ctx,
        )

    @b.event
    async def on_error(event_method: str, *args, **kwargs):
        log.error(f"[Disnake Bot] Unhandled event error in {event_method}", exc_info=True)
        exc_type, exc_val, exc_tb = sys.exc_info()
        tb_str = "".join(traceback.format_exception(exc_type, exc_val, exc_tb)) if exc_val else traceback.format_exc()

        ctx = {"Event": event_method}
        if args and isinstance(args[0], disnake.Message):
            msg = args[0]
            ctx["Author"] = f"{msg.author.name} (ID: {msg.author.id})"
            ctx["Channel"] = f"#{getattr(msg.channel, 'name', 'unknown')} (ID: {msg.channel.id})"
            if msg.guild:
                ctx["Guild"] = f"{msg.guild.name} (ID: {msg.guild.id})"
            if msg.content:
                ctx["Message Preview"] = msg.content[:200]
        elif args and isinstance(args[0], disnake.Interaction):
            it = args[0]
            ctx["User"] = f"{it.author.name} (ID: {it.author.id})"
            ctx["Interaction Type"] = str(it.type)

        await send_error_alert_async(
            origin=f"Bot Event ({event_method})",
            error=exc_val or f"Error in event {event_method}",
            traceback_str=tb_str,
            context_info=ctx,
        )

    @b.slash_command(
        name="server",
        description="View real-time metrics and operational stats for an RBWR server",
        install_types=disnake.ApplicationInstallTypes.all(),
        contexts=disnake.InteractionContextTypes.all(),
    )
    async def server_command(
        inter: disnake.ApplicationCommandInteraction,
        id: str = commands.Param(description="Job ID or Server ID (e.g. 191f-49d5)"),
        info: str = commands.Param(
            default="all",
            description="Specific metric or ALL for complete inspection",
            choices=INFO_CHOICES,
        ),
    ):
        await inter.response.defer()

        client: RBWRClient = getattr(b, "rbwr", None) or RBWRClient()
        try:
            server = await client.find_server(id, allow_exact_private=True)
        except Exception as e:
            log.exception("RBWR API error")
            await inter.followup.send(f"Error fetching server data: `{e}`")
            return

        if not server:
            await inter.followup.send(f"Server `{id}` not found or is offline.")
            return

        job_id = str(server.get("jobId", id))
        short = client.short_id(job_id)
        info_val = getattr(info, "value", info)
        is_pub = is_server_public(server)

        view = disnake.ui.View(timeout=180)
        if is_pub:
            view.add_item(disnake.ui.Button(
                label="Join in Roblox",
                url=make_roblox_join_url(job_id),
            ))
        view.add_item(disnake.ui.Button(
            label="Open Web View",
            url=make_web_server_url(job_id),
        ))

        if info_val == "all":
            browser_view = ServerBrowserView(
                client=client,
                author_id=inter.author.id,
                all_servers=[server],
            )
            embed = browser_view._build_detail_embed(server)
            await inter.followup.send(embed=embed, view=view)
        else:
            players = get_player_count(server)
            vis_label = "Public" if is_pub else "Private"
            embed = disnake.Embed(
                title=f"RBWR Server — {short}",
                description=f"**Server ID:** `{short}`\n**Job ID:** `{job_id}`\n**Visibility:** `{vis_label}`",
                color=disnake.Color.teal(),
                timestamp=datetime.now(timezone.utc),
            )
            footer_text = f"Players: {players} • RBWR Metrics" if is_pub else "Private Server • RBWR Metrics"
            embed.set_footer(text=footer_text)
            add_info(embed, server, 1, info_val)
            add_info(embed, server, 2, info_val)
            await inter.followup.send(embed=embed, view=view)

    @server_command.autocomplete("id")
    async def server_id_autocomplete(inter: disnake.ApplicationCommandInteraction, user_input: str):
        client: RBWRClient = getattr(b, "rbwr", None) or RBWRClient()
        try:
            payload = await client.fetch(public_only=True)
            servers = payload.get("data", {}).get("servers", [])
        except Exception:
            return []

        clean_input = (user_input or "").strip().lower().replace("-", "")
        choices = []

        for s in servers:
            if not is_server_public(s):
                continue
            jid = str(s.get("jobId", ""))
            short = client.short_id(jid)
            u1 = get_unit_state(s, 1)
            u2 = get_unit_state(s, 2)
            pts = get_server_points_rate(s)
            pts_str = f"{pts:.2f} pts/s" if pts is not None else "N/A"
            u1_aprm = get_unit_aprm(u1)
            u2_aprm = get_unit_aprm(u2)

            norm_jid = jid.lower().replace("-", "")
            norm_short = short.lower().replace("-", "")

            if not clean_input or clean_input in norm_jid or clean_input in norm_short:
                label = f"{short} • U1: {u1_aprm:.0f}% | U2: {u2_aprm:.0f}% | {pts_str}"
                choices.append(disnake.OptionChoice(name=label[:100], value=short))
                if len(choices) >= 25:
                    break

        return choices

    @b.slash_command(
        name="servers",
        description="Interactive browser & search for active RBWR servers",
        install_types=disnake.ApplicationInstallTypes.all(),
        contexts=disnake.InteractionContextTypes.all(),
    )
    async def servers_command(
        inter: disnake.ApplicationCommandInteraction,
        query: str = commands.Param(default="", description="Search by Job ID, short ID, or SCRAM reason"),
        sort_by: str = commands.Param(default="top_servers", description="Sorting criteria", choices=SORT_CHOICES),
        filter: str = commands.Param(default="all", description="Filter criteria", choices=FILTER_CHOICES),
    ):
        await inter.response.defer()
        client: RBWRClient = getattr(b, "rbwr", None) or RBWRClient()
        try:
            payload = await client.fetch(public_only=True)
            servers = payload.get("data", {}).get("servers", [])
        except Exception as e:
            await inter.followup.send(f"Error fetching servers: `{e}`")
            return

        browser_view = ServerBrowserView(
            client=client,
            author_id=inter.author.id,
            all_servers=servers,
            query=query,
            sort_by=sort_by,
            filter_status=filter,
        )
        await inter.followup.send(embed=browser_view.build_embed(), view=browser_view)

    @b.slash_command(
        name="serverlist",
        description="Interactive browser & search for active RBWR servers",
        install_types=disnake.ApplicationInstallTypes.all(),
        contexts=disnake.InteractionContextTypes.all(),
    )
    async def serverlist_command(
        inter: disnake.ApplicationCommandInteraction,
        query: str = commands.Param(default="", description="Search by Job ID, short ID, or SCRAM reason"),
        sort_by: str = commands.Param(default="top_servers", description="Sorting criteria", choices=SORT_CHOICES),
        filter: str = commands.Param(default="all", description="Filter criteria", choices=FILTER_CHOICES),
    ):
        await servers_command(inter, query=query, sort_by=sort_by, filter=filter)

    @b.slash_command(
        name="score",
        description="Inspect 60-minute performance score breakdown for an RBWR server",
        install_types=disnake.ApplicationInstallTypes.all(),
        contexts=disnake.InteractionContextTypes.all(),
    )
    async def score_command(
        inter: disnake.ApplicationCommandInteraction,
        id: str = commands.Param(description="Job ID or Server ID (e.g. 191f-49d5)"),
        ephemeral: bool = commands.Param(default=False, description="Whether the response should be hidden from other users"),
    ):
        await inter.response.defer(ephemeral=ephemeral)
        client: RBWRClient = getattr(b, "rbwr", None) or RBWRClient()
        server = None
        try:
            server = await client.find_server(id, allow_exact_private=True)
        except Exception as ex:
            log.warning(f"[Score Command] find_server failed: {ex}")

        job_id = str(server.get("jobId", id)) if server else id
        short = client.short_id(job_id)

        score_res = None
        try:
            score_res = await client.fetch_score_breakdown(job_id)
        except Exception as ex:
            log.error(f"[Score Command] fetch_score_breakdown failed: {ex}", exc_info=True)

        if not score_res or not score_res.get("success"):
            if not server:
                await inter.followup.send(f"Server `{id}` not found in active or archived records.", ephemeral=ephemeral)
                return
            await inter.followup.send(f"Score breakdown data is currently unavailable for server `{short}` (`{job_id}`).", ephemeral=ephemeral)
            return

        breakdown = score_res.get("breakdown", {})
        final_score = float(score_res.get("score", breakdown.get("top_score", 0.0)))
        raw_score = float(breakdown.get("raw_score", 0.0))
        pre_penalty = float(breakdown.get("score_before_penalties", 0.0))
        eval_count = breakdown.get("evaluated_snapshots_count", 0)
        tot_count = breakdown.get("total_snapshots_count", 0)
        win_mins = breakdown.get("time_window_minutes", 60.0)

        point_gen = breakdown.get("point_generation", {})
        efficiency_pct = point_gen.get("efficiency_percent", 0.0)
        pps_weight = point_gen.get("point_generation_weight", 1.0)
        weighted_pps = point_gen.get("weighted_avg_pps", 0.0)
        pps_loss = point_gen.get("points_score_loss", 0.0)
        is_sustaining = point_gen.get("is_sustaining_max", False)

        synergy = breakdown.get("synergy", {})
        dual_active = synergy.get("dual_active_count", 0)
        single_active = synergy.get("single_active_count", 0)
        inactive_cnt = synergy.get("inactive_count", 0)
        avg_synergy = synergy.get("avg_synergy_multiplier", 1.0)

        penalties = breakdown.get("penalties", {})
        total_deduction = penalties.get("total_penalty_deduction", 0.0)
        u1_scrams = penalties.get("u1_scrams", 0)
        u2_scrams = penalties.get("u2_scrams", 0)
        u1_trips = penalties.get("u1_trips", 0)
        u2_trips = penalties.get("u2_trips", 0)

        u1 = breakdown.get("unit1_summary", {})
        u2 = breakdown.get("unit2_summary", {})

        is_pub = is_server_public(server) if server else True
        players = get_player_count(server) if server else "?"

        if final_score >= 80.0:
            score_color = disnake.Color.teal()
            grade_badge = "[RATING: OPTIMAL]"
        elif final_score >= 50.0:
            score_color = disnake.Color.gold()
            grade_badge = "[RATING: DEGRADED]"
        else:
            score_color = disnake.Color.red()
            grade_badge = "[RATING: CRITICAL]"

        embed = disnake.Embed(
            title=f"RBWR Performance Score — {short}",
            description=(
                f"**Server ID:** `{short}` • **Job ID:** `{job_id}`\n"
                f"**Window:** Rolling {win_mins:.0f} Minutes • **Half-Life:** 600s\n"
                f"**Overall Classification:** `{grade_badge}`"
            ),
            color=score_color,
            timestamp=datetime.now(timezone.utc),
        )

        embed.add_field(
            name="Performance Rating",
            value=(
                f"**Top Score:** `{final_score:.1f}` / 100.0\n"
                f"**Raw Score:** `{raw_score:.1f}` | **Pre-Penalty:** `{pre_penalty:.1f}`\n"
                f"**Evaluated Snapshots:** `{eval_count}` of `{tot_count}` in window"
            ),
            inline=False,
        )

        pps_status = "[SUSTAINING MAXIMUM 2.90 PTS/S]" if is_sustaining else f"[SUB-OPTIMAL: -{pps_loss:.1f} PTS]"
        embed.add_field(
            name="Point Generation Weight",
            value=(
                f"**Efficiency:** `{efficiency_pct:.1f}%` (Multiplier: `{pps_weight:.4f}`)\n"
                f"**Average PPS:** `{weighted_pps:.2f} pts/s` (Plant Max: `2.90 pts/s`)\n"
                f"**Status:** `{pps_status}`"
            ),
            inline=True,
        )

        embed.add_field(
            name="Multi-Unit Synergy",
            value=(
                f"**Dual Unit Active:** `{dual_active}` snapshots (+25%)\n"
                f"**Single Unit Active:** `{single_active}` snapshots (1.0x)\n"
                f"**Average Synergy:** `{avg_synergy:.2f}x` (Offline: `{inactive_cnt}`)"
            ),
            inline=True,
        )

        incident_summary = (
            f"**Total Deduction:** `-{total_deduction:.1f} pts` (Cap: `-25.0 pts`)\n"
            f"**SCRAMs:** `U1: {u1_scrams}` | `U2: {u2_scrams}`\n"
            f"**Turbine Trips:** `U1: {u1_trips}` | `U2: {u2_trips}`"
        )
        embed.add_field(name="Incident Deductions", value=incident_summary, inline=False)

        u1_text = (
            f"**Score:** `{u1.get('avg_score', 0.0):.1f} pts` (Active: `{u1.get('active_pct', 0.0):.1f}%`)\n"
            f"**Avg Output:** `{u1.get('avg_output_mw', 0.0):.1f} MW` (Latest: `{u1.get('latest_output_mw', 0.0):.1f} MW`)\n"
            f"**Deadband Compliance:** `[OK: {u1.get('demand_tolerance_count', 0)}]` `[DEVIATION: {u1.get('demand_extreme_count', 0)}]`\n"
            f"**Downtime / LOOP:** `[DOWNTIME: {u1.get('downtime_demand_count', 0)}]` `[LOOP: {u1.get('loop_count', 0)}]`"
        )
        embed.add_field(name="Unit 1 Performance", value=u1_text, inline=True)

        u2_refuel_min = u2.get("refuel_minutes_latest")
        refuel_state = f"`[REFUEL: {u2_refuel_min:.1f}m]`" if u2_refuel_min is not None else "`[ONLINE / NOMINAL]`"
        u2_text = (
            f"**Score:** `{u2.get('avg_score', 0.0):.1f} pts` (Active: `{u2.get('active_pct', 0.0):.1f}%`)\n"
            f"**Avg Output:** `{u2.get('avg_output_mw', 0.0):.1f} MW` (Latest: `{u2.get('latest_output_mw', 0.0):.1f} MW`)\n"
            f"**Deadband Compliance:** `[OK: {u2.get('demand_tolerance_count', 0)}]` `[DEVIATION: {u2.get('demand_extreme_count', 0)}]`\n"
            f"**Refuel Status:** {refuel_state}\n"
            f"**Downtime / LOOP:** `[DOWNTIME: {u2.get('downtime_demand_count', 0)}]` `[LOOP: {u2.get('loop_count', 0)}]`"
        )
        embed.add_field(name="Unit 2 Performance", value=u2_text, inline=True)

        footer_text = f"Players: {players} • RBWR Performance Scoring Engine" if is_pub else "Private Server • RBWR Performance Scoring Engine"
        embed.set_footer(text=footer_text)

        view = disnake.ui.View(timeout=180)
        if is_pub:
            view.add_item(disnake.ui.Button(label="Join in Roblox", url=make_roblox_join_url(job_id)))
        view.add_item(disnake.ui.Button(label="Open Score Breakdown", url=make_web_server_url(job_id)))

        await inter.followup.send(embed=embed, view=view, ephemeral=ephemeral)

    @score_command.autocomplete("id")
    async def score_id_autocomplete(inter: disnake.ApplicationCommandInteraction, user_input: str):
        return await server_id_autocomplete(inter, user_input)

    @b.slash_command(
        name="calc",
        description="Calculate RBWR reactor thermal power (APRM %), steam flow, and electrical generation",
        install_types=disnake.ApplicationInstallTypes.all(),
        contexts=disnake.InteractionContextTypes.all(),
    )
    async def calc_command(
        inter: disnake.ApplicationCommandInteraction,
        unit: int = commands.Param(default=1, description="Reactor Unit (1 or 2)", choices=[
            disnake.OptionChoice(name="Unit 1", value=1),
            disnake.OptionChoice(name="Unit 2", value=2),
        ]),
        demand: float | None = commands.Param(default=None, description="Target electrical generation demand in MWe (e.g. 1000)"),
        aprm: float | None = commands.Param(default=None, description="Reactor thermal power / APRM percentage (e.g. 100)"),
        recirc_override: float | None = commands.Param(default=None, description="Manual recirculation pump speed % (0-100)"),
        server: str | None = commands.Param(default=None, description="Optional active server to sync current live demand from"),
        ephemeral: bool = commands.Param(default=False, description="Whether the response should be hidden from other users"),
    ):
        await inter.response.defer(ephemeral=ephemeral)
        client: RBWRClient = getattr(b, "rbwr", None) or RBWRClient()

        synced_server = None
        synced_note = ""
        if server:
            try:
                synced_server = await client.find_server(server, allow_exact_private=True)
                if synced_server:
                    s_jid = str(synced_server.get("jobId", server))
                    short = client.short_id(s_jid)
                    u_state = get_unit_state(synced_server, unit)
                    s_state = synced_server.get("state", {})
                    if demand is None and aprm is None:
                        live_demand = get_unit_demand(u_state, s_state, unit)
                        if live_demand is not None and live_demand > 0:
                            demand = live_demand
                            synced_note = f"Synced with live server `{short}` (Demand: `{live_demand:.0f} MWe`)."
                        else:
                            live_aprm = get_unit_aprm(u_state)
                            if live_aprm > 0:
                                aprm = live_aprm
                                synced_note = f"Synced with live server `{short}` (APRM: `{live_aprm:.1f}%`)."
            except Exception as ex:
                log.warning(f"[Calc Command] Server sync error: {ex}")

        if demand is None and aprm is None:
            demand = 1000.0

        try:
            res = await client.calculate(
                unit=unit,
                demand=demand,
                thermal=aprm,
                recirc_override=recirc_override,
            )
        except Exception as ex:
            log.error(f"[Calc Command] Calculation failed: {ex}", exc_info=True)
            await inter.followup.send(f"Error calculating reactor operational parameters: `{ex}`", ephemeral=ephemeral)
            return

        if not res:
            await inter.followup.send("Failed to retrieve calculation results from API.", ephemeral=ephemeral)
            return

        thermal = float(res.get("thermal_percent", 0.0))
        flow = float(res.get("flow_kg_s", 0.0))
        gen_load = float(res.get("gen_load_mwe", 0.0))
        usage = float(res.get("station_usage_mwe", 0.0))
        net_demand = float(res.get("demand_mwe", 0.0))
        scram_risk = bool(res.get("scram_risk", False))
        scram_limit = float(res.get("scram_limit_percent", 108.0))

        color = disnake.Color.red() if scram_risk else disnake.Color.teal()

        desc_text = f""
        if synced_note:
            desc_text += f"\n{synced_note}"

        embed = disnake.Embed(
            title=f"RBWR Thermal Power Solver — Unit {unit}",
            description=desc_text,
            color=color,
            timestamp=datetime.now(timezone.utc),
        )

        embed.add_field(name="Generator Demand", value=f"`{net_demand:.1f} MWe`", inline=True)
        embed.add_field(name="Target APRM / RTP", value=f"`{thermal:.2f}%`", inline=True)
        embed.add_field(name="Steam Flow", value=f"`{flow:.1f} kg/s`", inline=True)
        embed.add_field(name="Gross Output", value=f"`{gen_load:.1f} MWe`", inline=True)
        embed.add_field(name="Station Load (Usage)", value=f"`{usage:.1f} MWe`", inline=True)

        reg_params = res.get("parameters", {})
        if reg_params:
            if unit == 1:
                tcv = reg_params.get("TCV")
                crp = reg_params.get("CRP")
                dio_in = reg_params.get("DIO Intake")
                dio_out = reg_params.get("DIO Output")
                lines = []
                if crp is not None:
                    lines.append(f"**Condenser Recirc Pump (CRP):** `{crp:.2f}%`")
                if tcv is not None:
                    lines.append(f"**Turbine Control Valve (TCV):** `{tcv:.2f}%`")
                if dio_in is not None and dio_out is not None:
                    lines.append(f"**Deaerator In / Out (DIO):** `{dio_in:.2f}%` / `{dio_out:.2f}%`")
                if lines:
                    embed.add_field(name="Estimated Plant Parameters (Regression)", value="\n".join(lines), inline=False)
            else:
                tcv = reg_params.get("TCV")
                crp = reg_params.get("CRP")
                sjae = reg_params.get("SJAE")
                dio_in = reg_params.get("DIO Intake")
                dio_out = reg_params.get("DIO Output")
                mss = reg_params.get("MSS")
                ocl = reg_params.get("OCL")
                ocv = reg_params.get("OCV")
                mcv = reg_params.get("MCV")
                lines = []
                if crp is not None and tcv is not None:
                    lines.append(f"**Condenser Recirc (CRP):** `{crp:.2f}%` • **Turbine Valve (TCV):** `{tcv:.2f}%`")
                if sjae is not None and mss is not None:
                    lines.append(f"**Air Ejector (SJAE):** `{sjae:.2f}%` • **Steam Sealing (MSS):** `{mss:.2f}%`")
                if dio_in is not None and dio_out is not None:
                    lines.append(f"**Deaerator In / Out (DIO):** `{dio_in:.2f}%` / `{dio_out:.2f}%`")
                if ocv is not None and mcv is not None and ocl is not None:
                    lines.append(f"**Oil Cooling (OCL):** `{ocl:.2f}%` • **Valves (OCV / MCV):** `{ocv:.2f}%` / `{mcv:.2f}%`")
                if lines:
                    embed.add_field(name="Estimated Plant Parameters (Regression)", value="\n".join(lines), inline=False)

        if scram_risk:
            embed.add_field(
                name="[WARNING] Overpower SCRAM Threshold Exceeded",
                value=(
                    f"Calculated thermal output `{thermal:.2f}%` exceeds the licensed reactor protection trip limit of `{scram_limit:.1f}%` APRM.\n"
                    "Immediate insertion of control rod patterns or reduction in recirculation pump speed is required to maintain core stability."
                ),
                inline=False,
            )

        embed.set_footer(text="RBWR Reactor Physics Solver")

        view = disnake.ui.View(timeout=180)
        view.add_item(disnake.ui.Button(label="Open Web Calculator", url=f"{DEFAULT_SERVER_BASE_URL}/calculator"))
        if synced_server and is_server_public(synced_server):
            s_jid = str(synced_server.get("jobId", ""))
            view.add_item(disnake.ui.Button(label="Join Synced Server", url=make_roblox_join_url(s_jid)))

        await inter.followup.send(embed=embed, view=view, ephemeral=ephemeral)

    @calc_command.autocomplete("server")
    async def calc_server_autocomplete(inter: disnake.ApplicationCommandInteraction, user_input: str):
        return await server_id_autocomplete(inter, user_input)

    @b.slash_command(
        name="download",
        description="Get download links and latest release information for RBWR APR Overlay",
        install_types=disnake.ApplicationInstallTypes.all(),
        contexts=disnake.InteractionContextTypes.all(),
    )
    async def download_command(
        inter: disnake.ApplicationCommandInteraction,
        ephemeral: bool = commands.Param(default=False, description="Whether the response should be hidden from other users"),
    ):
        await inter.response.defer(ephemeral=ephemeral)
        client: RBWRClient = getattr(b, "rbwr", None) or RBWRClient()

        rel = None
        try:
            rel = await client.fetch_latest_version()
        except Exception as ex:
            log.warning(f"[Download Command] Failed to fetch version info: {ex}")

        if not rel:
            await inter.followup.send("Failed to retrieve latest release information from version API.", ephemeral=ephemeral)
            return

        version = rel.get("version", "unknown")
        tag_name = rel.get("tag_name", f"v{version}")
        name = rel.get("name", f"Release {version}")
        rel_date = rel.get("release_date", "")
        html_url = rel.get("html_url", "https://github.com/Hotment/RBWR-Utility/releases/latest")
        download_url = rel.get("download_url", html_url)
        notes = rel.get("notes", "") or "No release notes available."

        if len(notes) > 850:
            notes = notes[:850].rsplit("\n", 1)[0] + "\n..."

        embed = disnake.Embed(
            title=f"RBWR APR Overlay — {name}",
            description=(
                "Official real-time reactor monitoring overlay client for RBWR.\n"
                "Engineered with Avalonia UI (.NET 8) for low-latency operational metrics and cross-platform desktop integration."
            ),
            color=disnake.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )

        embed.add_field(name="Version", value=f"`{tag_name}`", inline=True)
        if rel_date:
            embed.add_field(name="Release Date", value=f"`{rel_date}`", inline=True)
        embed.add_field(name="Supported Platforms", value="`Windows x64` / `Linux`", inline=True)

        embed.add_field(name="Release Notes", value=f"```markdown\n{notes}\n```", inline=False)

        assets = rel.get("assets", [])
        if assets:
            asset_lines = []
            for a in assets[:5]:
                a_name = a.get("name", "Asset")
                a_url = a.get("download_url") or html_url
                a_size = a.get("size")
                size_str = f" ({a_size // 1048576} MB)" if isinstance(a_size, int) and a_size > 0 else ""
                asset_lines.append(f"• [{a_name}]({a_url}){size_str}")
            embed.add_field(name="Package Downloads", value="\n".join(asset_lines), inline=False)

        embed.set_footer(text="RBWR APR Overlay Client • Verified Release Build")

        view = disnake.ui.View(timeout=180)
        view.add_item(disnake.ui.Button(label="Download Latest Release", url=download_url))
        view.add_item(disnake.ui.Button(label="View on GitHub", url=html_url))
        view.add_item(disnake.ui.Button(label="Web Portal", url=DEFAULT_SERVER_BASE_URL))

        await inter.followup.send(embed=embed, view=view, ephemeral=ephemeral)

    @b.slash_command(
        name="fleet",
        description="View fleet-wide power generation, active reactor units, and network stats",
        install_types=disnake.ApplicationInstallTypes.all(),
        contexts=disnake.InteractionContextTypes.all(),
    )
    async def fleet_command(
        inter: disnake.ApplicationCommandInteraction,
        ephemeral: bool = commands.Param(default=False, description="Whether the response should be hidden from other users"),
    ):
        await inter.response.defer(ephemeral=ephemeral)
        client: RBWRClient = getattr(b, "rbwr", None) or RBWRClient()

        try:
            payload = await client.fetch(public_only=True)
            servers = payload.get("data", {}).get("servers", [])
        except Exception as ex:
            await inter.followup.send(f"Error fetching fleet operational data: `{ex}`", ephemeral=ephemeral)
            return

        total_public = len(servers)
        if total_public == 0:
            embed = disnake.Embed(
                title="RBWR Reactor Fleet Overview",
                description="No public reactor instances are currently online or reporting snapshot data.",
                color=disnake.Color.dark_grey(),
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text="RBWR Fleet Network • All Cores Inactive")
            await inter.followup.send(embed=embed, ephemeral=ephemeral)
            return

        total_mw = 0.0
        total_pps = 0.0
        u1_running = 0
        u2_running = 0
        total_players = 0
        incident_count = 0

        top_server = None
        top_score = -1.0
        top_mw = -1.0

        for s in servers:
            u1 = get_unit_state(s, 1)
            u2 = get_unit_state(s, 2)

            u1_mw = get_unit_output_mw(u1)
            u2_mw = get_unit_output_mw(u2)
            s_mw = u1_mw + u2_mw
            total_mw += s_mw

            s_pps = get_server_points_rate(s) or 0.0
            total_pps += s_pps

            if is_unit_running(u1):
                u1_running += 1
            if is_unit_running(u2):
                u2_running += 1

            p_cnt = get_player_count(s)
            if isinstance(p_cnt, int):
                total_players += p_cnt

            for u in (u1, u2):
                scram = u.get("SCRAMreason")
                if scram and str(scram).strip() not in ("None", "", "null"):
                    incident_count += 1
                turb_stat = str(u.get("Turbine Status", "")).strip().lower()
                if "trip" in turb_stat:
                    incident_count += 1

            s_score = get_server_top_score(s)
            if s_score > top_score or (abs(s_score - top_score) < 0.1 and s_mw > top_mw):
                top_score = s_score
                top_mw = s_mw
                top_server = s

        total_reactors = u1_running + u2_running
        total_possible_reactors = total_public * 2
        capacity_pct = (total_reactors / total_possible_reactors * 100.0) if total_possible_reactors > 0 else 0.0

        embed = disnake.Embed(
            title="RBWR Reactor Fleet Overview",
            description=(
                f"**Active Public Instances:** `{total_public}`\n"
                f"**Fleet Core Utilization:** `{total_reactors}/{total_possible_reactors}` Cores Online (`{capacity_pct:.1f}%`)"
            ),
            color=disnake.Color.teal(),
            timestamp=datetime.now(timezone.utc),
        )

        embed.add_field(name="Fleet Power Generation", value=f"`{total_mw:,.1f} MWe`", inline=True)
        embed.add_field(name="Fleet Generation Rate", value=f"`{total_pps:.2f} pts/s`", inline=True)
        embed.add_field(name="Active Operators", value=f"`{total_players}` players online", inline=True)

        embed.add_field(
            name="Operational Core Units",
            value=f"**Unit 1 Active:** `{u1_running}`\n**Unit 2 Active:** `{u2_running}`",
            inline=True,
        )

        incident_status = f"`{incident_count}` active alerts" if incident_count > 0 else "`[NOMINAL - NO TRIPS]`"
        embed.add_field(
            name="Fleet Alerts / SCRAMs",
            value=incident_status,
            inline=True,
        )

        if top_server:
            top_jid = str(top_server.get("jobId", "unknown"))
            top_short = client.short_id(top_jid)
            top_u1 = get_unit_state(top_server, 1)
            top_u2 = get_unit_state(top_server, 2)
            top_pps = get_server_points_rate(top_server) or 0.0
            top_summary = (
                f"**Server ID:** `{top_short}` (`{top_jid}`)\n"
                f"**Performance Rating:** Top Score `{top_score:.1f}`\n"
                f"**Output:** `{top_mw:.1f} MWe` | **Rate:** `{top_pps:.2f} pts/s`\n"
                f"**Cores:** `[U1: {get_unit_aprm(top_u1):.0f}% APRM]` `[U2: {get_unit_aprm(top_u2):.0f}% APRM]`"
            )
            embed.add_field(name="Flagship Server (Top Performance)", value=top_summary, inline=False)

        embed.set_footer(text="RBWR Fleet Operations • Real-time Public Network Status")

        view = disnake.ui.View(timeout=180)
        view.add_item(disnake.ui.Button(label="Open Server Browser", url=f"{DEFAULT_SERVER_BASE_URL}/servers"))
        if top_server and is_server_public(top_server):
            top_jid = str(top_server.get("jobId", ""))
            view.add_item(disnake.ui.Button(label="Join Flagship Server", url=make_roblox_join_url(top_jid)))

        await inter.followup.send(embed=embed, view=view, ephemeral=ephemeral)

    @b.listen("on_interaction")
    async def global_ticket_interaction_listener(inter: disnake.Interaction):
        t_id: int | None = None
        if isinstance(inter, disnake.MessageInteraction):
            cid = str(getattr(inter.data, "custom_id", "") or "")
            if cid.startswith("ticket_status_select:"):
                try:
                    t_id = int(cid.split(":")[1])
                    await handle_ticket_status_select(inter, t_id)
                except Exception as ex:
                    log.error(f"[Component Handler] Status select error: {ex}", exc_info=True)
                    await send_error_alert_async(
                        origin="Bot Component Interaction (ticket_status_select)",
                        error=ex,
                        context_info={
                            "Ticket ID": t_id or "unknown",
                            "User": f"{inter.author.name} (ID: {inter.author.id})",
                            "Channel": f"#{getattr(inter.channel, 'name', 'unknown')} (ID: {inter.channel_id})",
                        },
                    )
            elif cid.startswith("ticket_edit_note:"):
                try:
                    t_id = int(cid.split(":")[1])
                    await handle_ticket_edit_note_button(inter, t_id)
                except Exception as ex:
                    log.error(f"[Component Handler] Edit note button error: {ex}", exc_info=True)
                    await send_error_alert_async(
                        origin="Bot Component Interaction (ticket_edit_note)",
                        error=ex,
                        context_info={
                            "Ticket ID": t_id or "unknown",
                            "User": f"{inter.author.name} (ID: {inter.author.id})",
                            "Channel": f"#{getattr(inter.channel, 'name', 'unknown')} (ID: {inter.channel_id})",
                        },
                    )
            elif cid.startswith("ticket_open_discussions:"):
                try:
                    t_id = int(cid.split(":")[1])
                    await handle_ticket_open_discussions(inter, t_id)
                except Exception as ex:
                    log.error(f"[Component Handler] Open discussions error: {ex}", exc_info=True)
                    await send_error_alert_async(
                        origin="Bot Component Interaction (ticket_open_discussions)",
                        error=ex,
                        context_info={
                            "Ticket ID": t_id or "unknown",
                            "User": f"{inter.author.name} (ID: {inter.author.id})",
                            "Channel": f"#{getattr(inter.channel, 'name', 'unknown')} (ID: {inter.channel_id})",
                        },
                    )
        elif isinstance(inter, disnake.ModalInteraction):
            cid = str(getattr(inter.data, "custom_id", "") or "")
            if cid.startswith("ticket_note_modal:"):
                try:
                    t_id = int(cid.split(":")[1])
                    await handle_ticket_note_submission(inter, t_id)
                except Exception as ex:
                    log.error(f"[Component Handler] Modal note error: {ex}", exc_info=True)
                    await send_error_alert_async(
                        origin="Bot Modal Interaction (ticket_note_modal)",
                        error=ex,
                        context_info={
                            "Ticket ID": t_id or "unknown",
                            "User": f"{inter.author.name} (ID: {inter.author.id})",
                            "Channel": f"#{getattr(inter.channel, 'name', 'unknown')} (ID: {inter.channel_id})",
                        },
                    )
            elif cid.startswith("embed_builder_modal:"):
                try:
                    ch_id = int(cid.split(":")[1])
                    await handle_embed_modal_submission(inter, ch_id)
                except Exception as ex:
                    log.error(f"[Component Handler] Embed modal error: {ex}", exc_info=True)
                    await send_error_alert_async(
                        origin="Bot Modal Interaction (embed_builder_modal)",
                        error=ex,
                        context_info={
                            "Channel ID": cid.split(":")[1] if ":" in cid else "unknown",
                            "User": f"{inter.author.name} (ID: {inter.author.id})",
                        },
                    )

    async def _show_panel_interactive(
        inter: disnake.ApplicationCommandInteraction,
        id: int | None = None
    ):
        await inter.response.defer(ephemeral=True)
        sender_discord_id = str(inter.author.id)
        is_guild_admin = inter.author.guild_permissions.administrator if (hasattr(inter.author, "guild_permissions") and isinstance(inter.author, disnake.Member)) else None
        is_admin = (ticket_bridge.is_website_admin and ticket_bridge.is_website_admin(sender_discord_id)) or is_guild_admin
        if not is_admin:
            await inter.followup.send("Only administrators can spawn ticket panels.", ephemeral=True)
            return

        if not ticket_bridge.load_suggestions:
            await inter.followup.send("Ticket bridge is not configured.", ephemeral=True)
            return

        data = ticket_bridge.load_suggestions()
        suggestions = data.get("suggestions", [])
        ch_id = str(inter.channel.id)

        target = None
        if id is not None:
            target = next((s for s in suggestions if s.get("id") == id), None)
        else:
            target = next((s for s in suggestions if str(s.get("discord_channel_id", "")) == ch_id), None)
            if not target:
                ch_name = getattr(inter.channel, "name", "")
                for s in suggestions:
                    if f"ticket-{s.get('id')}" in ch_name or f"bug-{s.get('id')}" in ch_name:
                        target = s
                        break

        if not target:
            await inter.followup.send("Could not match this channel to an active ticket. Please specify a ticket ID.", ephemeral=True)
            return

        t_id = target.get("id")
        t_type = target.get("type", "suggestion")
        st = target.get("status") or ("open" if t_type == "bug_report" else "pending")

        panel_embed, panel_view = build_ticket_panel(
            ticket_id=t_id,
            ticket_type=t_type,
            current_status=st,
            admin_comment=target.get("admin_comment")
        )
        sent_panel = await inter.channel.send(embed=panel_embed, view=panel_view)
        target["panel_message_id"] = str(sent_panel.id)
        if ticket_bridge.save_suggestions:
            ticket_bridge.save_suggestions(data)
        await inter.followup.send(f"Spawned Ticket Admin Panel for Ticket #{t_id}!", ephemeral=True)

    admin_guild_ids = [int(GUILD_ID)] if GUILD_ID.isdigit() else None
    guild_only_install = disnake.ApplicationInstallTypes(guild=True, user=False)
    guild_only_contexts = disnake.InteractionContextTypes(guild=True, bot_dm=False, private_channel=False)

    @b.slash_command(
        name="panel",
        description="Show the ticket admin panel here without needing to scroll up",
        guild_ids=admin_guild_ids,
        install_types=guild_only_install,
        contexts=guild_only_contexts,
    )
    async def panel_command(
        inter: disnake.ApplicationCommandInteraction,
        id: int | None = commands.Param(default=None, description="Optional ticket ID (defaults to current channel's ticket)"),
    ):
        await _show_panel_interactive(inter, id)

    @b.slash_command(
        name="ticket_panel",
        description="Display or refresh the Ticket Admin Panel in this channel",
        guild_ids=admin_guild_ids,
        install_types=guild_only_install,
        contexts=guild_only_contexts,
    )
    async def ticket_panel_command(
        inter: disnake.ApplicationCommandInteraction,
        id: int | None = commands.Param(default=None, description="Optional ticket ID (defaults to current channel's ticket)"),
    ):
        await _show_panel_interactive(inter, id)

    @b.event
    async def on_member_join(member: disnake.Member):
        try:
            await assign_autorole_to_member(member)
        except Exception as ex:
            log.error(f"[Disnake Bot] Error in on_member_join event for {member}: {ex}", exc_info=ex)

    @b.slash_command(
        name="embed",
        description="Force the bot to send an embed into a channel",
        default_member_permissions=disnake.Permissions(administrator=True),
        install_types=guild_only_install,
        contexts=guild_only_contexts,
    )
    async def embed_command(
        inter: disnake.ApplicationCommandInteraction,
        description: str | None = commands.Param(default=None, description="Body description text of the embed"),
        title: str | None = commands.Param(default=None, description="Title of the embed"),
        channel: disnake.TextChannel | None = commands.Param(default=None, description="Target channel to send the embed (defaults to current channel)"),
        color: str | None = commands.Param(default=None, description="Hex color (e.g. #00D1FF) or color name (e.g. blurple, red, green, gold)"),
        content: str | None = commands.Param(default=None, description="Optional text content outside the embed (e.g. mentions)"),
        image_url: str | None = commands.Param(default=None, description="Image URL to display inside the embed"),
        thumbnail_url: str | None = commands.Param(default=None, description="Thumbnail URL to display in upper-right corner"),
        footer: str | None = commands.Param(default=None, description="Footer text for the embed"),
        footer_icon_url: str | None = commands.Param(default=None, description="Footer icon URL"),
        author_name: str | None = commands.Param(default=None, description="Author header text"),
        author_icon_url: str | None = commands.Param(default=None, description="Author header icon URL"),
        url: str | None = commands.Param(default=None, description="Clickable URL link for the title"),
        fields: str | None = commands.Param(default=None, description="Custom fields ('Name: Value | Name2: Value2' or JSON array)"),
        json_data: str | None = commands.Param(default=None, description="Raw embed JSON dictionary"),
        timestamp: bool = commands.Param(default=True, description="Whether to include current timestamp on embed"),
    ):
        if not is_inter_admin(inter):
            await inter.response.send_message("Only administrators can execute this command.", ephemeral=True)
            return

        target_channel = channel or inter.channel
        if not target_channel or not hasattr(target_channel, "send") or not isinstance(target_channel, (disnake.TextChannel, disnake.Thread, disnake.VoiceChannel)):
            await inter.response.send_message("The specified or current channel does not support sending messages.", ephemeral=True)
            return

        has_any_content = any([description, title, image_url, thumbnail_url, json_data, fields, footer, author_name])
        if not has_any_content:
            await inter.response.send_modal(EmbedBuilderModal(target_channel_id=target_channel.id))
            return

        await inter.response.defer(ephemeral=True)

        try:
            embed = build_custom_embed(
                title=title,
                description=description,
                color=color,
                image_url=image_url,
                thumbnail_url=thumbnail_url,
                footer=footer,
                footer_icon_url=footer_icon_url,
                author_name=author_name,
                author_icon_url=author_icon_url,
                url=url,
                fields_str=fields,
                json_data=json_data,
                include_timestamp=timestamp,
            )
        except Exception as build_err:
            await inter.followup.send(f"Invalid embed specification: `{build_err}`", ephemeral=True)
            return

        if inter.guild and inter.guild.me:
            perms = target_channel.permissions_for(inter.guild.me)
            if not perms.send_messages or not perms.embed_links:
                await inter.followup.send(
                    f"Bot lacks permissions to send messages or embeds in {target_channel.mention}.",
                    ephemeral=True,
                )
                return

        try:
            sent_msg = await target_channel.send(content=content, embed=embed)
            log.info(
                f"[Embed Command] Sent embed message {sent_msg.id} in #{getattr(target_channel, 'name', target_channel.id)} "
                f"by admin {inter.author.name} (ID: {inter.author.id})"
            )
            await inter.followup.send(
                f"Embed successfully dispatched to {target_channel.mention} (Message ID: `{sent_msg.id}`).",
                ephemeral=True,
            )
        except Exception as send_err:
            log.error(f"[Embed Command] Error sending embed to {target_channel.id}: {send_err}", exc_info=send_err)
            await inter.followup.send(f"Failed to send embed: `{send_err}`", ephemeral=True)

    @b.slash_command(
        name="autorole",
        description="Manage automatic role assignment for new server members",
        default_member_permissions=disnake.Permissions(administrator=True),
        install_types=guild_only_install,
        contexts=guild_only_contexts,
    )
    async def autorole_group(inter: disnake.ApplicationCommandInteraction):
        pass

    @autorole_group.sub_command(
        name="set",
        description="Configure the role to automatically assign to new members upon joining",
    )
    async def autorole_set(
        inter: disnake.ApplicationCommandInteraction,
        role: disnake.Role = commands.Param(description="Role to automatically assign to joining members"),
        enabled: bool = commands.Param(default=True, description="Enable autorole assignment immediately"),
        include_bots: bool = commands.Param(default=False, description="Whether to also assign role to newly added bots"),
    ):
        if not is_inter_admin(inter):
            await inter.response.send_message("Only administrators can execute this command.", ephemeral=True)
            return

        if not inter.guild:
            await inter.response.send_message("This command must be run within a server.", ephemeral=True)
            return

        if role.is_default():
            await inter.response.send_message("Cannot use @everyone as an autorole.", ephemeral=True)
            return

        if role.managed:
            await inter.response.send_message("Cannot use a managed integration/bot role as an autorole.", ephemeral=True)
            return

        guild_id_str = str(inter.guild.id)
        config = load_autorole_config()
        if "guilds" not in config or not isinstance(config["guilds"], dict):
            config["guilds"] = {}

        config["guilds"][guild_id_str] = {
            "role_id": role.id,
            "role_name": role.name,
            "enabled": enabled,
            "include_bots": include_bots,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": str(inter.author.id),
        }
        save_autorole_config(config)

        warnings = []
        me = inter.guild.me
        if me:
            if not me.guild_permissions.manage_roles:
                warnings.append("[WARNING] Bot lacks 'Manage Roles' permission in this server.")
            if role >= me.top_role:
                warnings.append(f"[WARNING] Role '{role.name}' is higher than or equal to bot's highest role '{me.top_role.name}'. Move the bot's role above this role in Server Settings > Roles.")

        embed = disnake.Embed(
            title="Autorole Configuration Updated",
            color=disnake.Color.teal(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Target Role", value=f"{role.mention} (`{role.id}`)", inline=True)
        embed.add_field(name="Status", value="Enabled" if enabled else "Disabled", inline=True)
        embed.add_field(name="Include Bots", value="Yes" if include_bots else "No", inline=True)
        if warnings:
            embed.add_field(name="Advisory Warnings", value="\n".join(warnings), inline=False)
        else:
            embed.add_field(name="Verification", value="Role hierarchy and bot permissions verified. Ready for incoming members.", inline=False)
        embed.set_footer(text=f"Guild: {inter.guild.name} ({inter.guild.id})")

        await inter.response.send_message(embed=embed, ephemeral=True)

    @autorole_group.sub_command(
        name="view",
        description="View current autorole configuration and permissions for this server",
    )
    async def autorole_view(inter: disnake.ApplicationCommandInteraction):
        if not is_inter_admin(inter):
            await inter.response.send_message("Only administrators can execute this command.", ephemeral=True)
            return

        if not inter.guild:
            await inter.response.send_message("This command must be run within a server.", ephemeral=True)
            return

        target_role, source_desc, is_enabled = resolve_autorole_for_guild(inter.guild)
        config = load_autorole_config()
        guild_cfg = config.get("guilds", {}).get(str(inter.guild.id), {})

        embed = disnake.Embed(
            title="Autorole System Status",
            color=disnake.Color.teal() if is_enabled else disnake.Color.orange(),
            timestamp=datetime.now(timezone.utc),
        )
        status_str = "Enabled" if is_enabled else "Disabled"
        if not target_role:
            status_str = "Not Configured"
        embed.add_field(name="Status", value=status_str, inline=True)

        if target_role:
            embed.add_field(name="Target Role", value=f"{target_role.mention} (`{target_role.id}`)", inline=True)
            embed.add_field(name="Source", value=source_desc or "Configured", inline=True)
            embed.add_field(name="Include Bots", value="Yes" if guild_cfg.get("include_bots") else "No", inline=True)

            me = inter.guild.me
            can_assign = True
            hierarchy_msg = "Valid (Role is below bot role)"
            perm_msg = "Granted (Manage Roles)"

            if me:
                if not me.guild_permissions.manage_roles:
                    can_assign = False
                    perm_msg = "[MISSING] Bot lacks 'Manage Roles' permission"
                if target_role >= me.top_role:
                    can_assign = False
                    hierarchy_msg = f"[CONFLICT] Target role >= Bot top role ({me.top_role.name})"

            embed.add_field(name="Bot Permission", value=perm_msg, inline=False)
            embed.add_field(name="Role Hierarchy", value=hierarchy_msg, inline=False)
            embed.add_field(name="Operational Ready", value="Yes" if (can_assign and is_enabled) else "No", inline=False)
        else:
            embed.add_field(name="Target Role", value="None configured", inline=True)
            embed.add_field(name="Configuration Help", value="Use `/autorole set role:@YourRole` to configure automatic role assignment for incoming members.", inline=False)

        embed.set_footer(text=f"Guild: {inter.guild.name} ({inter.guild.id})")
        await inter.response.send_message(embed=embed, ephemeral=True)

    @autorole_group.sub_command(
        name="disable",
        description="Disable automatic role assignment for this server",
    )
    async def autorole_disable(inter: disnake.ApplicationCommandInteraction):
        if not is_inter_admin(inter):
            await inter.response.send_message("Only administrators can execute this command.", ephemeral=True)
            return

        if not inter.guild:
            await inter.response.send_message("This command must be run within a server.", ephemeral=True)
            return

        config = load_autorole_config()
        if "guilds" not in config or not isinstance(config["guilds"], dict):
            config["guilds"] = {}

        guild_id_str = str(inter.guild.id)
        if guild_id_str not in config["guilds"]:
            config["guilds"][guild_id_str] = {}

        config["guilds"][guild_id_str]["enabled"] = False
        config["guilds"][guild_id_str]["updated_at"] = datetime.now(timezone.utc).isoformat()
        config["guilds"][guild_id_str]["updated_by"] = str(inter.author.id)
        save_autorole_config(config)

        await inter.response.send_message("Autorole assignment has been disabled for this server.", ephemeral=True)

    @autorole_group.sub_command(
        name="enable",
        description="Enable automatic role assignment for this server",
    )
    async def autorole_enable(inter: disnake.ApplicationCommandInteraction):
        if not is_inter_admin(inter):
            await inter.response.send_message("Only administrators can execute this command.", ephemeral=True)
            return

        if not inter.guild:
            await inter.response.send_message("This command must be run within a server.", ephemeral=True)
            return

        config = load_autorole_config()
        if "guilds" not in config or not isinstance(config["guilds"], dict):
            config["guilds"] = {}

        guild_id_str = str(inter.guild.id)
        if guild_id_str not in config["guilds"]:
            config["guilds"][guild_id_str] = {}

        config["guilds"][guild_id_str]["enabled"] = True
        config["guilds"][guild_id_str]["updated_at"] = datetime.now(timezone.utc).isoformat()
        config["guilds"][guild_id_str]["updated_by"] = str(inter.author.id)
        save_autorole_config(config)

        await inter.response.send_message("Autorole assignment has been enabled for this server.", ephemeral=True)

    @autorole_group.sub_command(
        name="sync",
        description="Backfill autorole to existing members who do not currently have the role",
    )
    async def autorole_sync(
        inter: disnake.ApplicationCommandInteraction,
        include_bots: bool = commands.Param(default=False, description="Whether to also assign role to bots"),
    ):
        if not is_inter_admin(inter):
            await inter.response.send_message("Only administrators can execute this command.", ephemeral=True)
            return

        if not inter.guild:
            await inter.response.send_message("This command must be run within a server.", ephemeral=True)
            return

        target_role, _, is_enabled = resolve_autorole_for_guild(inter.guild)
        if not target_role:
            await inter.response.send_message("No autorole is configured for this server. Use `/autorole set` first.", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)

        me = inter.guild.me
        if me:
            if not me.guild_permissions.manage_roles:
                await inter.followup.send("Bot lacks 'Manage Roles' permission in this server.", ephemeral=True)
                return
            if target_role >= me.top_role:
                await inter.followup.send(f"Role '{target_role.name}' is higher than or equal to bot's highest role '{me.top_role.name}'.", ephemeral=True)
                return

        assigned_count = 0
        failed_count = 0
        total_members = inter.guild.members

        for member in total_members:
            if member.bot and not include_bots:
                continue
            if target_role not in member.roles:
                try:
                    await member.add_roles(target_role, reason=f"Autorole sync initiated by admin {inter.author.name}")
                    assigned_count += 1
                    await asyncio.sleep(0.3)
                except Exception as ex:
                    log.warning(f"[Autorole Sync] Failed to assign role to {member.name}: {ex}")
                    failed_count += 1

        await inter.followup.send(
            f"Autorole sync completed for role '{target_role.name}': {assigned_count} members updated, {failed_count} errors.",
            ephemeral=True,
        )

    @b.event
    async def on_message(message: disnake.Message):
        if not message.guild or message.author.bot:
            return
        if b.user and message.author.id == b.user.id:
            return

        if not ticket_bridge.is_configured():
            return

        cat_id = str(getattr(message.channel, "category_id", "") or "")
        target_cat_id = str(TICKETS_CATEGORY_ID).strip()
        ch_id = str(message.channel.id)

        assert ticket_bridge.load_suggestions is not None
        data = ticket_bridge.load_suggestions()
        suggestions = data.get("suggestions", [])

        target_ticket = None
        for s in suggestions:
            if str(s.get("discord_channel_id", "")) == ch_id or str(s.get("discussion_thread_id", "")) == ch_id:
                target_ticket = s
                break

        if not target_ticket:
            ch_name = getattr(message.channel, "name", "")
            for s in suggestions:
                tid = str(s.get("id"))
                if f"ticket-{tid}" in ch_name or f"bug-{tid}" in ch_name or f"#{tid}" in ch_name:
                    target_ticket = s
                    break

        if not target_ticket:
            return

        sender_discord_id = str(message.author.id)

        assert ticket_bridge.is_website_admin is not None
        if not ticket_bridge.is_website_admin(sender_discord_id):
            log.info(
                f"[Disnake Bot] Ignored message from non-website-admin {message.author} "
                f"(ID: {sender_discord_id}) in #{getattr(message.channel, 'name', ch_id)}: "
                f"author is not an administrator on the website."
            )
            return

        d_msg_id = str(message.id)
        messages = target_ticket.setdefault("messages", [])
        for m in messages:
            if str(m.get("discord_message_id", "")) == d_msg_id:
                return

        msg_content = (message.clean_content or message.content or "").strip()
        if not msg_content and message.attachments:
            msg_content = "\n".join(a.url for a in message.attachments)
        if not msg_content:
            return

        admin_entry = None
        if ticket_bridge.load_admins:
            admins_data = ticket_bridge.load_admins()
            admin_entry = admins_data.get("admins", {}).get(sender_discord_id)
            if not admin_entry:
                for k, v in admins_data.get("admins", {}).items():
                    if isinstance(v, dict) and str(v.get("discord_id", "")).strip() == sender_discord_id:
                        admin_entry = v
                        break

        configured_admin_name = admin_entry.get("username") if admin_entry else None
        sender_name = configured_admin_name or message.author.display_name or getattr(message.author, "global_name", None) or message.author.name or "Administrator"
        sender_avatar = str(message.author.display_avatar.url) if message.author.display_avatar else ""

        new_msg_id = (max([m.get("id", 0) for m in messages]) if messages else 0) + 1
        new_msg_obj = {
            "id": new_msg_id,
            "sender_type": "admin",
            "sender_name": sender_name,
            "sender_discord_id": sender_discord_id,
            "sender_avatar": sender_avatar,
            "message": msg_content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "discord_message_id": d_msg_id
        }
        messages.append(new_msg_obj)
        assert ticket_bridge.save_suggestions is not None
        ticket_bridge.save_suggestions(data)

        if ticket_bridge.broadcast_dashboard:
            ticket_bridge.broadcast_dashboard()

        log.info(f"[Disnake Bot] Ingested admin reply from #{getattr(message.channel, 'name', ch_id)} (Author: {sender_name}) for ticket #{target_ticket.get('id')}")

        if ticket_bridge.broadcast_ticket_update:
            ticket_bridge.broadcast_ticket_update(
                target_ticket.get("id"),
                new_msg_obj,
                messages,
                target_ticket.get("discord_id"),
                target_ticket.get("anonymous")
            )

        try:
            notify_ticket_author_dm(
                ticket=target_ticket,
                event_type="message",
                details={
                    "sender_name": sender_name,
                    "message": msg_content
                }
            )
        except Exception as dm_err:
            log.warning(f"[Disnake Bot] Failed to send author DM on Discord admin message: {dm_err}")

    @b.event
    async def on_message_edit(before: disnake.Message, after: disnake.Message):
        if not after.guild or after.author.bot:
            return
        if b.user and after.author.id == b.user.id:
            return
        if not ticket_bridge.is_configured():
            return

        ch_id = str(after.channel.id)
        assert ticket_bridge.load_suggestions is not None
        data = ticket_bridge.load_suggestions()
        suggestions = data.get("suggestions", [])

        target_ticket = None
        for s in suggestions:
            if str(s.get("discord_channel_id", "")) == ch_id or str(s.get("discussion_thread_id", "")) == ch_id:
                target_ticket = s
                break

        if not target_ticket:
            ch_name = getattr(after.channel, "name", "")
            for s in suggestions:
                tid = str(s.get("id"))
                if f"ticket-{tid}" in ch_name or f"bug-{tid}" in ch_name or f"#{tid}" in ch_name:
                    target_ticket = s
                    break

        if not target_ticket:
            return

        d_msg_id = str(after.id)
        messages = target_ticket.setdefault("messages", [])
        target_msg = next((m for m in messages if str(m.get("discord_message_id", "")) == d_msg_id), None)
        if not target_msg:
            return

        new_content = (after.clean_content or after.content or "").strip()
        if not new_content and after.attachments:
            new_content = "\n".join(a.url for a in after.attachments)
        if not new_content:
            return

        target_msg["message"] = new_content
        target_msg["edited"] = True
        target_msg["edited_at"] = datetime.now(timezone.utc).isoformat()

        assert ticket_bridge.save_suggestions is not None
        ticket_bridge.save_suggestions(data)

        if ticket_bridge.broadcast_dashboard:
            ticket_bridge.broadcast_dashboard()

        if ticket_bridge.broadcast_ticket_update:
            ticket_bridge.broadcast_ticket_update(
                target_ticket.get("id"),
                target_msg,
                messages,
                target_ticket.get("discord_id"),
                target_ticket.get("anonymous")
            )
        log.info(f"[Disnake Bot] Synchronized edited message {d_msg_id} for ticket #{target_ticket.get('id')}")

    @b.event
    async def on_message_delete(message: disnake.Message):
        if not message.guild:
            return
        if not ticket_bridge.is_configured():
            return

        ch_id = str(message.channel.id)
        assert ticket_bridge.load_suggestions is not None
        data = ticket_bridge.load_suggestions()
        suggestions = data.get("suggestions", [])

        target_ticket = None
        for s in suggestions:
            if str(s.get("discord_channel_id", "")) == ch_id or str(s.get("discussion_thread_id", "")) == ch_id:
                target_ticket = s
                break

        if not target_ticket:
            ch_name = getattr(message.channel, "name", "")
            for s in suggestions:
                tid = str(s.get("id"))
                if f"ticket-{tid}" in ch_name or f"bug-{tid}" in ch_name or f"#{tid}" in ch_name:
                    target_ticket = s
                    break

        if not target_ticket:
            return

        d_msg_id = str(message.id)
        messages = target_ticket.setdefault("messages", [])
        before_count = len(messages)
        messages[:] = [m for m in messages if str(m.get("discord_message_id", "")) != d_msg_id]
        if len(messages) == before_count:
            return

        assert ticket_bridge.save_suggestions is not None
        ticket_bridge.save_suggestions(data)

        if ticket_bridge.broadcast_dashboard:
            ticket_bridge.broadcast_dashboard()

        if ticket_bridge.broadcast_ticket_update:
            ticket_bridge.broadcast_ticket_update(
                target_ticket.get("id"),
                {"id": 0, "deleted": True, "discord_message_id": d_msg_id},
                messages,
                target_ticket.get("discord_id"),
                target_ticket.get("anonymous")
            )
        log.info(f"[Disnake Bot] Synchronized deleted message {d_msg_id} for ticket #{target_ticket.get('id')}")

def create_discord_ticket_channel(ticket: dict[str, Any]) -> str | None:
    global disnake_bot, disnake_bot_loop
    if not disnake_bot or not disnake_bot.is_ready() or not disnake_bot_loop or not disnake_bot_loop.is_running():
        log.warning("[Disnake Channel] Disnake bot is not ready; cannot create ticket channel.")
        return None

    ticket_id = ticket.get("id")
    ticket_type = ticket.get("type", "suggestion")
    raw_title = ticket.get("title") or ticket.get("suggestion") or ticket.get("description") or f"ticket-{ticket_id}"

    slug = "".join(c if c.isalnum() else "-" for c in raw_title.lower()).strip("-")
    slug = "-".join(part for part in slug.split("-") if part)[:25]
    prefix = "bug" if ticket_type == "bug_report" else "ticket"
    channel_name = f"{prefix}-{ticket_id}"
    if slug:
        channel_name += f"-{slug}"
    channel_name = channel_name[:95]

    author_name = ticket.get("name", "Anonymous")
    discord_id = ticket.get("discord_id")
    discord_username = ticket.get("discord_username")
    is_anon = bool(ticket.get("anonymous"))

    target_labels = {
        "overlay": "APRM Overlay",
        "point_graph": "Point History Graph",
        "server_checker": "Server Browser",
        "general": "General"
    }
    target = ticket.get("target") or "overlay"

    is_bug = (ticket_type == "bug_report")
    embed_color = disnake.Color.red() if is_bug else disnake.Color.blurple()
    author_display = f"{discord_username} (ID: `{discord_id}`)" if discord_id and not is_anon else author_name
    if is_anon and discord_id:
        author_display += " *(Submitted anonymously to public)*"

    bot_ref = disnake_bot

    async def _create_async():
        guild_id = int(GUILD_ID)
        guild = bot_ref.get_guild(guild_id)
        if not guild:
            guild = await bot_ref.fetch_guild(guild_id)

        cat_id = int(TICKETS_CATEGORY_ID)
        category = bot_ref.get_channel(cat_id)
        if not category:
            try:
                category = await bot_ref.fetch_channel(cat_id)
            except Exception:
                category = None

        cat_obj = category if isinstance(category, disnake.CategoryChannel) else None
        ch = await guild.create_text_channel(
            name=channel_name,
            category=cat_obj,
            topic=f"Ticket #{ticket_id} ({ticket_type.upper()}) | Author: {discord_username or author_name}"
        )

        embed = disnake.Embed(
            title=f"{'Bug Report' if is_bug else 'Feature Suggestion'} #{ticket_id}: {ticket.get('title') or (ticket.get('suggestion') or '')[:50]}",
            description=(ticket.get('suggestion') or ticket.get('description') or '')[:3500],
            color=embed_color,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Type", value="Bug Report" if is_bug else "Suggestion", inline=True)
        embed.add_field(name="Category", value=target_labels.get(target, target), inline=True)
        embed.add_field(name="Status", value=(ticket.get("status") or ("open" if is_bug else "pending")).upper(), inline=True)
        embed.add_field(name="Author", value=author_display, inline=True)
        if ticket.get("admin_comment"):
            comment_by = ticket.get("comment_by") or "Administrator"
            embed.add_field(name="Admin Note", value=f"**[{comment_by}]**:\n{ticket.get('admin_comment')}"[:1024], inline=False)
        embed.add_field(name="Admin Replies", value="Type any message in this channel to send a reply directly to the ticket author. When the author replies on the website, their message will appear here in real time.", inline=False)
        embed.set_footer(text=f"RBWR Utility Ticket #{ticket_id}")

        main_msg = await ch.send(embed=embed)
        panel_msg = None
        try:
            panel_embed, panel_view = build_ticket_panel(
                ticket_id=ticket_id,  # pyright: ignore[reportArgumentType]
                ticket_type=ticket_type,
                current_status=ticket.get("status") or ("open" if is_bug else "pending"),
                admin_comment=ticket.get("admin_comment")
            )
            panel_msg = await ch.send(embed=panel_embed, view=panel_view)
        except Exception as panel_err:
            log.warning(f"[Disnake Channel] Failed to send ticket panel: {panel_err}", exc_info=True)

        if ticket_bridge.load_suggestions and ticket_bridge.save_suggestions:
            try:
                data = ticket_bridge.load_suggestions()
                for s in data.get("suggestions", []):
                    if s.get("id") == ticket_id:
                        s["discord_channel_id"] = str(ch.id)
                        s["discord_message_id"] = str(main_msg.id)
                        if panel_msg:
                            s["panel_message_id"] = str(panel_msg.id)
                        break
                ticket_bridge.save_suggestions(data)
            except Exception as e:
                log.warning(f"[Disnake Channel] Failed to save message IDs to suggestions: {e}")

        return str(ch.id)

    try:
        future = asyncio.run_coroutine_threadsafe(_create_async(), disnake_bot_loop)
        channel_id = future.result(timeout=10)
        log.info(f"[Disnake Channel] Created Discord channel #{channel_name} ({channel_id}) for ticket #{ticket_id}")
        return channel_id
    except Exception as ex:
        log.error(f"[Disnake Channel] Error creating channel: {ex}", exc_info=True)
        report_error_to_discord("Ticket Bridge (create_discord_ticket_channel)", ex, context_info={"Ticket ID": ticket.get("id"), "Type": ticket.get("type")})
        return None

def forward_ticket_reply_to_discord(
    channel_id: str | list[str],
    message_text: str,
    sender_name: str,
    is_admin: bool,
) -> str | None:
    global disnake_bot, disnake_bot_loop
    if not disnake_bot or not disnake_bot.is_ready() or not disnake_bot_loop or not disnake_bot_loop.is_running():
        return None

    sender_label = "Administrator" if is_admin else "Ticket Author"
    content = f"**[{sender_label}] {sender_name}**:\n{message_text}"
    bot_ref = disnake_bot

    c_list = [channel_id] if isinstance(channel_id, str) else list(channel_id)
    c_list = [str(c) for c in c_list if c]

    async def _send_fwd_async():
        last_id = None
        for ch_id in c_list:
            try:
                ch = bot_ref.get_channel(int(ch_id))
                if not ch:
                    ch = await bot_ref.fetch_channel(int(ch_id))

                if not ch or not hasattr(ch, "send") or not isinstance(ch, disnake.TextChannel):
                    continue

                sent = await ch.send(content=content)
                last_id = str(sent.id)
            except Exception as e:
                log.warning(f"[Disnake Forward] Channel {ch_id} send failed: {e}")
        return last_id

    try:
        fut = asyncio.run_coroutine_threadsafe(_send_fwd_async(), disnake_bot_loop)
        return fut.result(timeout=8)
    except Exception as ex:
        log.warning(f"[Disnake Forward] Failed to forward message to Discord: {ex}")
        return None

def edit_ticket_reply_in_discord(
    channel_ids: str | list[str],
    discord_message_id: str,
    message_text: str,
    sender_name: str,
    is_admin: bool,
) -> bool:
    global disnake_bot, disnake_bot_loop
    if not disnake_bot or not disnake_bot.is_ready() or not disnake_bot_loop or not disnake_bot_loop.is_running():
        return False
    if not discord_message_id:
        return False

    c_list = [channel_ids] if isinstance(channel_ids, str) else list(channel_ids)
    c_list = [str(c) for c in c_list if c]

    sender_label = "Administrator" if is_admin else "Ticket Author"
    new_content = f"**[{sender_label}] {sender_name}**:\n{message_text}"
    bot_ref = disnake_bot
    msg_id_int = int(discord_message_id)

    async def _edit_fwd_async():
        edited_any = False
        for ch_id in c_list:
            try:
                ch = bot_ref.get_channel(int(ch_id))
                if not ch:
                    ch = await bot_ref.fetch_channel(int(ch_id))
                if not ch or not hasattr(ch, "fetch_message") or not isinstance(ch, disnake.TextChannel):
                    continue
                try:
                    target_msg = await ch.fetch_message(msg_id_int)
                    if target_msg and bot_ref.user and target_msg.author.id == bot_ref.user.id:
                        await target_msg.edit(content=new_content)
                        log.info(f"[Disnake Edit] Successfully edited bot message {discord_message_id} in channel {ch_id}")
                        edited_any = True
                except disnake.NotFound:
                    continue
                except Exception as msg_err:
                    log.warning(f"[Disnake Edit] Error editing message in {ch_id}: {msg_err}")
            except Exception as ch_err:
                log.warning(f"[Disnake Edit] Error accessing channel {ch_id}: {ch_err}")
        return edited_any

    try:
        fut = asyncio.run_coroutine_threadsafe(_edit_fwd_async(), disnake_bot_loop)
        return fut.result(timeout=8)
    except Exception as ex:
        log.warning(f"[Disnake Edit] Failed to edit message in Discord: {ex}")
        return False

def delete_ticket_reply_in_discord(
    channel_ids: str | list[str],
    discord_message_id: str,
) -> bool:
    global disnake_bot, disnake_bot_loop
    if not disnake_bot or not disnake_bot.is_ready() or not disnake_bot_loop or not disnake_bot_loop.is_running():
        return False
    if not discord_message_id:
        return False

    c_list = [channel_ids] if isinstance(channel_ids, str) else list(channel_ids)
    c_list = [str(c) for c in c_list if c]

    bot_ref = disnake_bot
    msg_id_int = int(discord_message_id)

    async def _delete_fwd_async():
        deleted_any = False
        for ch_id in c_list:
            try:
                ch = bot_ref.get_channel(int(ch_id))
                if not ch:
                    ch = await bot_ref.fetch_channel(int(ch_id))
                if not ch or not hasattr(ch, "fetch_message") or not isinstance(ch, disnake.TextChannel):
                    continue
                try:
                    target_msg = await ch.fetch_message(msg_id_int)
                    if target_msg:
                        await target_msg.delete()
                        log.info(f"[Disnake Delete] Successfully deleted message {discord_message_id} in channel {ch_id}")
                        deleted_any = True
                except disnake.NotFound:
                    continue
                except Exception as msg_err:
                    log.warning(f"[Disnake Delete] Error deleting message in {ch_id}: {msg_err}")
            except Exception as ch_err:
                log.warning(f"[Disnake Delete] Error accessing channel {ch_id}: {ch_err}")
        return deleted_any

    try:
        fut = asyncio.run_coroutine_threadsafe(_delete_fwd_async(), disnake_bot_loop)
        return fut.result(timeout=8)
    except Exception as ex:
        log.warning(f"[Disnake Delete] Failed to delete message in Discord: {ex}")
        return False

def start_bot_thread(
    load_suggestions: Callable[[], dict[str, Any]] | None = None,
    save_suggestions: Callable[[dict[str, Any]], None] | None = None,
    load_admins: Callable[[], dict[str, Any]] | None = None,
    is_website_admin: Callable[[str], bool] | None = None,
    broadcast_dashboard: Callable[[], None] | None = None,
    broadcast_ticket_update: Callable[..., None] | None = None,
    get_servers_data: Callable[[bool], dict[str, Any]] | None = None,
    token: str | None = None,
) -> threading.Thread | None:
    """
    Spawns the Disnake Discord bot in a background daemon thread, wiring the ticket bridge callbacks.
    """
    configure_ticket_bridge(
        load_suggestions=load_suggestions,
        save_suggestions=save_suggestions,
        load_admins=load_admins,
        is_website_admin=is_website_admin,
        broadcast_dashboard=broadcast_dashboard,
        broadcast_ticket_update=broadcast_ticket_update,
    )

    bot_token = token or TOKEN or os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if not bot_token:
        log.warning("[Disnake Bot] DISCORD_BOT_TOKEN is not configured; Disnake bot is disabled.")
        return None

    def _worker():
        global disnake_bot, disnake_bot_loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        disnake_bot_loop = loop

        bot = create_bot_instance(data_supplier=get_servers_data)
        disnake_bot = bot

        try:
            loop.run_until_complete(bot.start(bot_token))
        except disnake.errors.PrivilegedIntentsRequired:
            log.warning("[Disnake Bot] Privileged intents (Message Content / Server Members) are disabled in Discord Developer Portal. Retrying with basic intents...")
            try:
                intents = disnake.Intents.default()
                intents.message_content = False
                intents.guilds = True
                intents.members = False
                bot = commands.InteractionBot(
                    intents=intents,
                    test_guilds=None,
                    default_install_types=disnake.ApplicationInstallTypes.all(),
                    default_contexts=disnake.InteractionContextTypes.all(),
                )
                bot.rbwr = RBWRClient(data_supplier=get_servers_data)  # pyright: ignore[reportAttributeAccessIssue]
                register_bot_events_and_commands(bot)
                disnake_bot = bot
                loop.run_until_complete(bot.start(bot_token))
            except Exception as retry_err:
                log.error(f"[Disnake Bot] Fallback start failed: {retry_err}")
                report_error_to_discord("Bot Fallback Startup", retry_err, context_info={"Intents": "Basic fallback"})
        except Exception as e:
            log.error(f"[Disnake Bot] Bot encountered error: {e}", exc_info=True)
            report_error_to_discord("Bot Daemon Thread", e, context_info={"Thread": "DisnakeBotThread"})

    thread = threading.Thread(target=_worker, daemon=True, name="DisnakeBotThread")
    thread.start()
    return thread

if __name__ == "__main__":
    bot_token = TOKEN or os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if not bot_token:
        log.error("DISCORD_BOT_TOKEN is not set in environment or .env file.")
        exit(1)

    try:
        standalone_bot = create_bot_instance()
        disnake_bot = standalone_bot
        standalone_bot.run(bot_token)
    except Exception as e:
        log.critical(f"Bot terminated with fatal error: {e}", exc_info=True)
        report_error_to_discord("Bot Standalone Process", e)
        raise