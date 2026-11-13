from __future__ import annotations

import gzip
import json
import logging
import os
import sys
import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

import requests
from dotenv import load_dotenv

try:
    import orjson
except ImportError:
    orjson = None

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_WORKSPACE_ROOT = os.path.abspath(os.path.join(_BASE_DIR, ".."))
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

try:
    from server.scoring import calculate_server_top_score
    from server.calculator import calculate_reactor_metrics
    from server.fuel import (
        approximate_fuel_from_snapshots,
        calculate_u1_fuel_level,
        calculate_u2_fuel_level,
        evaluate_server_fuel,
        resolve_unit_name,
    )
except ImportError:
    from scoring import calculate_server_top_score
    from calculator import calculate_reactor_metrics
    from fuel import (
        approximate_fuel_from_snapshots,
        calculate_u1_fuel_level,
        calculate_u2_fuel_level,
        evaluate_server_fuel,
        resolve_unit_name,
    )

BASE_DIR = _BASE_DIR
DATA_DIR = os.path.join(BASE_DIR, "data")
ARCHIVES_DIR = os.path.join(DATA_DIR, "archives")
ARCHIVES_META_FILE = os.path.join(DATA_DIR, "archives_meta.json")
ARCHIVES_INDEX_FILE = os.path.join(DATA_DIR, "archives_index.json")
PERSISTENT_SERVERS_FILE = os.path.join(DATA_DIR, "persistent_servers.json")
SUGGESTIONS_FILE = os.path.join(BASE_DIR, "suggestions.json")
LATEST_SERVERS_CACHE_FILE = "latest_servers.json"
PUBLIC_SERVERS_CACHE_FILE = "public_servers_cache.json"
ENV_FILE = os.path.join(BASE_DIR, ".env")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(ARCHIVES_DIR, exist_ok=True)
load_dotenv(ENV_FILE)
load_dotenv()

logger = logging.getLogger("rbwr.core")

SERVER_START_TIME = time.time()

def _json_dumps(obj: Any) -> bytes:
    if orjson:
        try:
            return orjson.dumps(obj)
        except Exception:
            pass
    return json.dumps(obj).encode("utf-8")

def _json_loads(b: Any) -> Any:
    if not b:
        return {}
    if isinstance(b, (bytes, bytearray)):
        if not b.strip():
            return {}
        if orjson:
            try:
                return orjson.loads(b)
            except Exception:
                pass
        try:
            return json.loads(b.decode("utf-8"))
        except Exception:
            return {}
    if isinstance(b, str):
        if not b.strip():
            return {}
        if orjson:
            try:
                return orjson.loads(b)
            except Exception:
                pass
        try:
            return json.loads(b)
        except Exception:
            return {}
    return {}

def format_uptime(seconds: float) -> str:
    secs = int(seconds)
    days, secs = divmod(secs, 86400)
    hours, secs = divmod(secs, 3600)
    mins, secs = divmod(secs, 60)
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0 or days > 0:
        parts.append(f"{hours}h")
    if mins > 0 or hours > 0 or days > 0:
        parts.append(f"{mins}m")
    parts.append(f"{secs}s")
    return " ".join(parts)

_github_version_cache: dict[str, Any] = {"data": None, "timestamp": 0.0}
_github_version_lock = threading.Lock()
GITHUB_RELEASE_CACHE_TTL = 300

def get_github_latest_release(force_refresh: bool = False) -> dict:
    """Fetch the latest RBWR-Utility release metadata from GitHub with caching."""
    now = time.time()
    with _github_version_lock:
        if not force_refresh and _github_version_cache["data"] and (now - _github_version_cache["timestamp"] < GITHUB_RELEASE_CACHE_TTL):
            return _github_version_cache["data"]

    headers = {"User-Agent": "RBWR-Utility-Server/2.0"}
    try:
        r = requests.get(
            "https://api.github.com/repos/Hotment/RBWR-Utility/releases/latest",
            headers=headers,
            timeout=5,
        )
        if r.status_code == 200:
            rel = r.json()
            tag_name = rel.get("tag_name", "")
            version = tag_name.lstrip("vV") if tag_name else "unknown"
            published_at = rel.get("published_at", "")
            release_date = published_at.split("T")[0] if published_at else datetime.now(timezone.utc).strftime("%Y-%m-%d")
            body_content = (rel.get("body", "") or "No release notes available.").replace("\r\n", "\n")
            html_url = rel.get("html_url", "https://github.com/Hotment/RBWR-Utility/releases/latest")

            assets = []
            download_url = html_url
            for a in rel.get("assets", []):
                assets.append({
                    "name": a.get("name"),
                    "size": a.get("size"),
                    "download_url": a.get("browser_download_url"),
                })

            for a in assets:
                aname = (a.get("name") or "").lower()
                if "win-x64" in aname and aname.endswith(".exe"):
                    download_url = a.get("download_url") or html_url
                    break
            if download_url == html_url:
                for a in assets:
                    aname = (a.get("name") or "").lower()
                    if aname.endswith((".exe", ".zip")):
                        download_url = a.get("download_url") or html_url
                        break

            result = {
                "version": version,
                "tag_name": tag_name,
                "name": rel.get("name", f"Release {version}"),
                "release_date": release_date,
                "published_at": published_at,
                "notes": body_content,
                "html_url": html_url,
                "download_url": download_url,
                "assets": assets,
            }
            with _github_version_lock:
                _github_version_cache["data"] = result
                _github_version_cache["timestamp"] = now
            return result
    except Exception as e:
        logger.warning(f"Error fetching latest release from GitHub: {e}")

    with _github_version_lock:
        if _github_version_cache["data"]:
            return _github_version_cache["data"]

    return {
        "version": "2.0.5",
        "tag_name": "v2.0.5",
        "name": "Version 2.0.5",
        "release_date": "2026-09-23",
        "published_at": "2026-09-23T23:15:33Z",
        "notes": "No release notes available.",
        "html_url": "https://github.com/Hotment/RBWR-Utility/releases/latest",
        "download_url": "https://github.com/Hotment/RBWR-Utility/releases/latest",
        "assets": [],
    }

def load_suggestions() -> dict:
    if not os.path.exists(SUGGESTIONS_FILE):
        return {"suggestions": []}
    with open(SUGGESTIONS_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {"suggestions": []}

def save_suggestions(data: dict) -> None:
    with open(SUGGESTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def get_public_tickets(is_admin: bool = False, current_discord_id: Optional[str] = None) -> list[dict]:
    data = load_suggestions()
    suggestions = data.get("suggestions", [])
    public_list = []

    for s in sorted(suggestions, key=lambda x: x.get("timestamp", ""), reverse=True):
        if s.get("hidden"):
            continue
        is_anon = bool(s.get("anonymous")) or (s.get("name") or "").lower() == "anonymous"
        pub_name = "Anonymous" if is_anon else (s.get("name") or "Anonymous")
        pub_avatar = None if is_anon else s.get("discord_avatar")
        raw_text = s.get("suggestion") or s.get("description", "")

        ticket_discord_id = str(s.get("discord_id") or "")
        is_author = bool(current_discord_id and ticket_discord_id and str(current_discord_id) == ticket_discord_id and not is_anon)

        can_view_conversation = is_admin or is_author
        ticket_messages = s.get("messages", []) if can_view_conversation else []
        messages_count = len(s.get("messages", [])) if can_view_conversation else 0

        public_list.append({
            "id": s.get("id"),
            "type": s.get("type", "suggestion"),
            "title": s.get("title", ""),
            "name": pub_name,
            "suggestion": raw_text,
            "description": raw_text,
            "timestamp": s.get("timestamp", ""),
            "status": s.get("status", "pending"),
            "admin_comment": s.get("admin_comment", ""),
            "comment_by": s.get("comment_by", ""),
            "comment_timestamp": s.get("comment_timestamp", ""),
            "target": s.get("target") or ("server_checker" if s.get("is_server_checker") else "overlay"),
            "is_server_checker": s.get("target") == "server_checker" or bool(s.get("is_server_checker")),
            "anonymous": is_anon,
            "discord_avatar": pub_avatar,
            "discord_id": None if is_anon else (s.get("discord_id") or ""),
            "discord_username": None if is_anon else (s.get("discord_username") or ""),
            "is_discord_user": bool(s.get("discord_id")) and not is_anon,
            "can_view_conversation": can_view_conversation,
            "is_author": is_author,
            "messages": ticket_messages,
            "messages_count": messages_count,
        })
    return public_list

SERVER_CHECKER_PURGE_KEYS = [
    "APRM Setpoint",
    "AutoPressure",
    "BusA",
    "BusB",
    "BypassTurbineAutoTrip",
    "DCBus",
    "Demand Time Left",
    "DieselRPM",
    "DoAutoScramU1",
    "DiffPressure",
    "Disk Ruptured",
    "DoAutoScramU2",
    "Fuel Burn (default 0.54)",
    "NextDemandU1",
    "NextDemandU2",
    "RPS Trip State B",
    "RPS Trip State A",
    "Reactor Scram State",
    "SCRAMreason",
    "Startup XFMR",
    "StartupUnit1",
    "StartupUnit2",
    "TRIPreason",
    "TotalPowerGenerated",
    "Turbine RPM",
    "TurbineTrip",
    "Vibrations",
]

SERVER_CHECKER_FIELD_PRECISION = {
    "APRM": None,
    "RTP": None,
    "Xenon": None,
    "Iodine": None,
    "FWP1 Temp": 4,
    "FWP2 Temp": 4,
    "Recirc1": 3,
    "Recirc2": 3,
    "CasingTemperature": 4,
    "PradDoSieci": 0,
    "Output (MW)": 0,
    "Reactor Temp": 4,
    "EstimatedFuel": 2,
}

def load_persistent_servers() -> dict:
    if not os.path.exists(PERSISTENT_SERVERS_FILE):
        return {"persistent": {}}
    try:
        with open(PERSISTENT_SERVERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"persistent": {}}

def save_persistent_servers(data: dict) -> None:
    os.makedirs(os.path.dirname(PERSISTENT_SERVERS_FILE), exist_ok=True)
    with open(PERSISTENT_SERVERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

_sc_lock = threading.RLock()
_sc_public_server_ids: list[str] = []
_sc_public_servers_info: dict[str, dict] = {}
_sc_server_ids: list[str] = []
_sc_latest_data: dict[str, Any] = {}
_sc_server_meta: dict[str, dict] = {}

def safe_dict_items(d: Any, max_retries: int = 3) -> list[tuple[Any, Any]]:
    if not isinstance(d, dict):
        return []
    for attempt in range(max_retries):
        try:
            return list(d.items())
        except RuntimeError:
            if attempt == max_retries - 1:
                try:
                    keys = list(d.keys())
                    return [(k, d[k]) for k in keys if k in d]
                except Exception:
                    return []
            time.sleep(0.005)
    return []

def safe_dict_keys(d: Any, max_retries: int = 3) -> list[Any]:
    if not isinstance(d, dict):
        return []
    for attempt in range(max_retries):
        try:
            return list(d.keys())
        except RuntimeError:
            if attempt == max_retries - 1:
                return []
            time.sleep(0.005)
    return []

def safe_dict_values(d: Any, max_retries: int = 3) -> list[Any]:
    if not isinstance(d, dict):
        return []
    for attempt in range(max_retries):
        try:
            return list(d.values())
        except RuntimeError:
            if attempt == max_retries - 1:
                return []
            time.sleep(0.005)
    return []

def safe_float(val: Any, default: Any = 0.0) -> Any:
    if val is None or isinstance(val, (bool, dict, list, tuple, set)):
        return default
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def safe_demand_numeric(val: Any) -> float | None:
    if val is None or isinstance(val, (bool, dict, list, tuple, set)):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None

def format_demand_value(val: Any) -> str:
    if val is None or isinstance(val, (bool, dict, list, tuple, set)):
        return "N/A"
    try:
        v = float(val)
    except (ValueError, TypeError):
        return "N/A"

    if v == -4:
        return "Evac"
    if v == -3:
        return "RST"
    if v == -2:
        return "LOOP"
    if v == -1:
        return "Maint"
    if v.is_integer():
        return f"{int(v)} MW"
    return f"{v:.2f} MW"

def format_total_demand(u1: Any, u2: Any) -> str:
    v1 = safe_demand_numeric(u1)
    v2 = safe_demand_numeric(u2)

    if v1 is None and v2 is None:
        return "N/A"
    if v1 is None:
        return format_demand_value(v2)
    if v2 is None:
        return format_demand_value(v1)

    is_u1_special = v1 < 0
    is_u2_special = v2 < 0

    if is_u1_special and is_u2_special:
        lbl1 = format_demand_value(v1)
        lbl2 = format_demand_value(v2)
        return lbl1 if lbl1 == lbl2 else f"{lbl1} / {lbl2}"
    if is_u1_special or is_u2_special:
        return f"{format_demand_value(v1)} (U1) | {format_demand_value(v2)} (U2)"
    total = v1 + v2
    return f"{int(total)} MW" if total.is_integer() else f"{total:.2f} MW"

def sync_cross_process_caches() -> None:
    """Refresh in-memory public server info and server_meta from disk when modified by another process."""
    global _sc_public_server_ids, _sc_public_servers_info, _sc_server_meta
    pub_cache = get_sc_data(PUBLIC_SERVERS_CACHE_FILE)
    if isinstance(pub_cache, dict) and pub_cache:
        ids = pub_cache.get("ids")
        info = pub_cache.get("info")
        if isinstance(ids, list) and isinstance(info, dict):
            _sc_public_server_ids = ids
            _sc_public_servers_info = info
    meta_disk = get_sc_data("server_meta.json")
    if isinstance(meta_disk, dict) and meta_disk and len(meta_disk) != len(_sc_server_meta):
        _sc_server_meta = dict(meta_disk)

def get_latest_servers_data() -> dict[str, Any]:
    """Return latest raw upstream payload, falling back to the shared disk cache across processes."""
    global _sc_latest_data
    disk_latest = get_sc_data(LATEST_SERVERS_CACHE_FILE)
    if isinstance(disk_latest, dict) and disk_latest.get("data", {}).get("servers"):
        _sc_latest_data = disk_latest
    return _sc_latest_data

def get_server_visibility(job_id: str, snapshots: Any = None, latest_state: Any = None, is_active: bool = False) -> bool:
    if job_id in _sc_public_server_ids:
        return False
    meta = _sc_server_meta.get(job_id)
    if meta is not None and "is_private" in meta:
        return bool(meta["is_private"])
    if latest_state and "IsPrivate" in latest_state:
        return bool(latest_state["IsPrivate"])
    if snapshots:
        for snap in safe_dict_values(snapshots):
            if isinstance(snap, dict) and "IsPrivate" in snap:
                return bool(snap["IsPrivate"])
    if is_active and _sc_public_server_ids:
        return job_id not in _sc_public_server_ids
    return False

def get_server_player_count(job_id: str, snapshots: Any = None, latest_state: Any = None, is_private: Optional[bool] = None) -> Optional[int]:
    if is_private is True:
        return None
    if is_private is None and get_server_visibility(job_id, snapshots, latest_state):
        return None
    if job_id in _sc_public_servers_info:
        return int(_sc_public_servers_info[job_id].get("playing", 0))
    if latest_state and latest_state.get("PlayerCount", 0) > 0:
        return int(latest_state["PlayerCount"])
    meta = _sc_server_meta.get(job_id)
    if meta and meta.get("last_player_count", 0) > 0:
        return int(meta["last_player_count"])
    if snapshots:
        valid_ts = [k for k in safe_dict_keys(snapshots) if not k.startswith("_")]
        for ts in sorted(valid_ts, reverse=True):
            snap = snapshots.get(ts)
            if isinstance(snap, dict):
                p = snap.get("PlayerCount", 0)
                if p > 0:
                    return int(p)
    return 0

_sc_file_cache: dict[str, tuple[float, Any]] = {}
_sc_archive_cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
_sc_max_archive_cache_entries = 2
_sc_cache_lock = threading.Lock()
_sc_file_io_lock = threading.RLock()

def is_archive_filename(filename: str) -> bool:
    normalized = filename.replace("\\", "/").strip()
    return normalized.startswith("archives/") or "servers_" in normalized

def _update_sc_cache(filename: str, mtime: float, data: dict) -> None:
    with _sc_cache_lock:
        if is_archive_filename(filename):
            _sc_archive_cache[filename] = (mtime, data)
            _sc_archive_cache.move_to_end(filename)
            while len(_sc_archive_cache) > _sc_max_archive_cache_entries:
                _sc_archive_cache.popitem(last=False)
            _sc_file_cache.pop(filename, None)
        else:
            _sc_file_cache[filename] = (mtime, data)

def _invalidate_sc_cache(filename: str) -> None:
    with _sc_cache_lock:
        _sc_file_cache.pop(filename, None)
        _sc_archive_cache.pop(filename, None)

_sc_historical_cards_base = None
_sc_historical_cards_key = None
_sc_historical_lock = threading.Lock()

_sc_active_cards_base = None
_sc_active_cards_key = None
_sc_active_lock = threading.Lock()

def invalidate_historical_cards_cache() -> None:
    global _sc_historical_cards_base, _sc_historical_cards_key
    global _sc_active_cards_base, _sc_active_cards_key
    with _sc_historical_lock:
        _sc_historical_cards_base = None
        _sc_historical_cards_key = None
    with _sc_active_lock:
        _sc_active_cards_base = None
        _sc_active_cards_key = None

def ensure_unit_output_mw(unit_dict: Any) -> Any:
    if not isinstance(unit_dict, dict):
        return unit_dict
    if unit_dict.get("Output (MW)") is None:
        val = unit_dict.get("PradDoSieci")
        if val is None:
            val = unit_dict.get("Output") or unit_dict.get("Power") or unit_dict.get("megawatts")
        if val is not None:
            try:
                prec = SERVER_CHECKER_FIELD_PRECISION.get("Output (MW)", 0)
                unit_dict["Output (MW)"] = round(float(val), prec) if prec is not None else float(val)
            except (ValueError, TypeError):
                unit_dict["Output (MW)"] = val
    return unit_dict

def ensure_unit_fuel_level(unit_name: str, unit_dict: Any) -> Any:
    if not isinstance(unit_dict, dict):
        return unit_dict
    raw_val = unit_dict.get("EstimatedFuel")
    if raw_val is None:
        try:
            clean_u = resolve_unit_name(unit_name)
            if clean_u == "Unit2":
                fuel_val = calculate_u2_fuel_level(unit_dict)
            else:
                fuel_val = calculate_u1_fuel_level(unit_dict)
            if fuel_val is not None:
                fuel_val = round(min(100.0, max(0.0, float(fuel_val))), 2)
            unit_dict["EstimatedFuel"] = fuel_val
        except Exception:
            pass
    else:
        try:
            f_val = float(raw_val)
            if f_val > 100.0 or f_val < 0.0:
                unit_dict["EstimatedFuel"] = round(min(100.0, max(0.0, f_val)), 2)
        except (ValueError, TypeError):
            pass
    return unit_dict

def get_card_unit_fuel_stats(snapshots: Any, unit_name: str, unit_dict: Any) -> Dict[str, Optional[float]]:
    kalman_val = None
    projected_val = None
    median_val = None
    weighted_val = None
    mean_val = None
    instant_val = None
    uncertainty_val = None

    if isinstance(snapshots, dict) and snapshots:
        try:
            assessment = approximate_fuel_from_snapshots(snapshots, unit_name)
            if assessment.kalman_fuel is not None and assessment.kalman_fuel > 0.0:
                kalman_val = round(min(100.0, max(0.0, float(assessment.kalman_fuel))), 1)
            if assessment.projected_fuel is not None and assessment.projected_fuel > 0.0:
                projected_val = round(min(100.0, max(0.0, float(assessment.projected_fuel))), 1)
            if assessment.median_fuel is not None and assessment.median_fuel > 0.0:
                median_val = round(min(100.0, max(0.0, float(assessment.median_fuel))), 1)
            if assessment.weighted_fuel is not None and assessment.weighted_fuel > 0.0:
                weighted_val = round(min(100.0, max(0.0, float(assessment.weighted_fuel))), 1)
            if assessment.mean_fuel is not None and assessment.mean_fuel > 0.0:
                mean_val = round(min(100.0, max(0.0, float(assessment.mean_fuel))), 1)
            if assessment.latest_instantaneous and assessment.latest_instantaneous > 0.0:
                instant_val = round(min(100.0, max(0.0, float(assessment.latest_instantaneous))), 1)
            uncertainty_val = assessment.uncertainty
        except Exception:
            pass

    if instant_val is None and isinstance(unit_dict, dict):
        ensure_unit_fuel_level(unit_name, unit_dict)
        raw_fuel = unit_dict.get("EstimatedFuel")
        if raw_fuel is not None:
            try:
                f_val = float(raw_fuel)
                if f_val > 0.0:
                    instant_val = round(min(100.0, max(0.0, f_val)), 1)
            except (ValueError, TypeError):
                pass

    primary_fuel = kalman_val if kalman_val is not None else (
        projected_val if projected_val is not None else (
            median_val if median_val is not None else (
                weighted_val if weighted_val is not None else (
                    mean_val if mean_val is not None else instant_val
                )
            )
        )
    )

    return {
        "estimated_fuel": primary_fuel,
        "kalman_fuel": kalman_val,
        "uncertainty": uncertainty_val,
        "projected_fuel": projected_val,
        "median_fuel": median_val,
        "weighted_fuel": weighted_val,
        "mean_fuel": mean_val,
        "instantaneous_fuel": instant_val,
    }

def normalize_snapshots_power(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    for _job_id, snaps in safe_dict_items(data):
        if isinstance(snaps, dict):
            for _ts, state in safe_dict_items(snaps):
                if isinstance(state, dict):
                    if isinstance(state.get("Unit2"), dict):
                        ensure_unit_output_mw(state["Unit2"])
                        ensure_unit_fuel_level("Unit2", state["Unit2"])
                    if isinstance(state.get("Unit1"), dict):
                        ensure_unit_output_mw(state["Unit1"])
                        ensure_unit_fuel_level("Unit1", state["Unit1"])
    return data

def get_sc_data(filename: str, max_retries: int = 8) -> dict:
    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath):
        return {}

    try:
        current_mtime = os.path.getmtime(filepath)
    except OSError:
        current_mtime = None

    is_archive = is_archive_filename(filename)

    if current_mtime is not None:
        with _sc_cache_lock:
            if is_archive:
                cached_entry = _sc_archive_cache.get(filename)
                if cached_entry and cached_entry[0] == current_mtime:
                    _sc_archive_cache.move_to_end(filename)
                    return cached_entry[1]
            else:
                cached_entry = _sc_file_cache.get(filename)
                if cached_entry and cached_entry[0] == current_mtime:
                    return cached_entry[1]

    for attempt in range(max_retries):
        try:
            with _sc_file_io_lock:
                if not os.path.exists(filepath):
                    time.sleep(0.05 * (attempt + 1))
                    continue
                with open(filepath, "rb") as f:
                    raw_bytes = f.read()

            if not raw_bytes or not raw_bytes.strip():
                if attempt < max_retries - 1:
                    time.sleep(0.05 * (attempt + 1))
                    continue
                with _sc_cache_lock:
                    target_cache = _sc_archive_cache if is_archive else _sc_file_cache
                    if filename in target_cache:
                        return target_cache[filename][1]
                return {}

            if filename.endswith(".gz") or filepath.endswith(".gz"):
                try:
                    raw_bytes = gzip.decompress(raw_bytes)
                except Exception:
                    if attempt < max_retries - 1:
                        time.sleep(0.05 * (attempt + 1))
                        continue
                    raise

            data = _json_loads(raw_bytes)
            if not isinstance(data, dict):
                data = {}
            else:
                if filename.startswith("servers") or filename.startswith("archives"):
                    normalize_snapshots_power(data)

            try:
                mtime_after = os.path.getmtime(filepath)
            except OSError:
                mtime_after = current_mtime

            _update_sc_cache(filename, mtime_after or 0.0, data)
            return data
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(0.05 * (attempt + 1))
            else:
                with _sc_cache_lock:
                    target_cache = _sc_archive_cache if is_archive else _sc_file_cache
                    if filename in target_cache:
                        return target_cache[filename][1]
                logger.error(f"Error loading sc data from {filename}: {e}")

    with _sc_cache_lock:
        target_cache = _sc_archive_cache if is_archive else _sc_file_cache
        if filename in target_cache:
            return target_cache[filename][1]
    return {}

def save_sc_data(data: Any, filename: str, max_retries: int = 10) -> bool:
    if isinstance(data, dict) and (filename.startswith("servers") or filename.startswith("archives")):
        normalize_snapshots_power(data)
    filepath = os.path.join(DATA_DIR, filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    unique_id = f"{os.getpid()}_{threading.get_ident()}_{time.time_ns()}"
    temp_path = f"{filepath}.{unique_id}.tmp"

    try:
        raw_bytes = _json_dumps(data)
        if filename.endswith(".gz") or filepath.endswith(".gz"):
            raw_bytes = gzip.compress(raw_bytes, compresslevel=9)
        with open(temp_path, "wb") as f:
            f.write(raw_bytes)
            f.flush()

        for attempt in range(max_retries):
            try:
                with _sc_file_io_lock:
                    os.replace(temp_path, filepath)
                try:
                    new_mtime = os.path.getmtime(filepath)
                except OSError:
                    new_mtime = time.time()
                _update_sc_cache(filename, new_mtime, data)
                if filename in ("servers.json", "persistent_servers.json", "server_meta.json"):
                    invalidate_historical_cards_cache()
                return True
            except PermissionError:
                if attempt < max_retries - 1:
                    time.sleep(0.05 * (attempt + 1))
                else:
                    try:
                        with _sc_file_io_lock:
                            with open(filepath, "wb") as f:
                                f.write(raw_bytes)
                        try:
                            new_mtime = os.path.getmtime(filepath)
                        except OSError:
                            new_mtime = time.time()
                        _update_sc_cache(filename, new_mtime, data)
                        if filename in ("servers.json", "persistent_servers.json", "server_meta.json"):
                            invalidate_historical_cards_cache()
                        return True
                    except Exception as fallback_err:
                        logger.error(f"Error in direct save fallback for {filename}: {fallback_err}")
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(0.05 * (attempt + 1))
                else:
                    logger.error(f"Error replacing {temp_path} to {filepath}: {e}")
    except Exception as e:
        logger.error(f"Error saving server checker data to {filename}: {e}")
        return False
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
    return False

def load_server_meta() -> dict[str, dict]:
    global _sc_server_meta
    data = get_sc_data("server_meta.json")
    if isinstance(data, dict):
        _sc_server_meta = dict(data)
    return _sc_server_meta

def save_server_meta() -> None:
    save_sc_data(_sc_server_meta, "server_meta.json")

def build_server_metadata(
    job_id: str,
    snapshots: dict[str, Any] | None,
    server_raw: dict[str, Any] | None = None,
    existing_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    existing = dict(existing_meta) if isinstance(existing_meta, dict) else {}
    server_info = dict(server_raw) if isinstance(server_raw, dict) else {}
    snaps = dict(snapshots) if isinstance(snapshots, dict) else {}

    valid_ts = sorted([k for k in safe_dict_keys(snaps) if not str(k).startswith("_")])
    snapshot_count = len(valid_ts)

    raw_owner_id = server_info.get("privateServerOwnerId")
    if raw_owner_id in (None, "", 0, "0", "None", "null", False):
        raw_owner_id = None
    else:
        raw_owner_id = str(raw_owner_id).strip()

    if raw_owner_id is None and existing:
        raw_owner_id = existing.get("privateServerOwnerId")
        if raw_owner_id in (None, "", 0, "0", "None", "null", False):
            raw_owner_id = None
        else:
            raw_owner_id = str(raw_owner_id).strip()

    if raw_owner_id is None and snaps:
        for ts_k in reversed(valid_ts[-5:]):
            st = snaps.get(ts_k)
            if isinstance(st, dict):
                snap_owner = st.get("privateServerOwnerId")
                if snap_owner not in (None, "", 0, "0", "None", "null", False):
                    raw_owner_id = str(snap_owner).strip()
                    break

    is_priv = False
    if raw_owner_id is not None:
        is_priv = True
    elif _sc_public_server_ids and job_id in _sc_public_server_ids:
        is_priv = False
    elif existing.get("is_private") is True:
        is_priv = True
    elif _sc_public_server_ids and job_id not in _sc_public_server_ids:
        is_priv = True
    else:
        found_in_snaps = False
        for ts_k in reversed(valid_ts[-5:]):
            st = snaps.get(ts_k)
            if isinstance(st, dict) and "IsPrivate" in st:
                is_priv = bool(st["IsPrivate"])
                found_in_snaps = True
                break
        if not found_in_snaps:
            is_priv = bool(existing.get("is_private"))

    if is_priv:
        is_private_val = True
        owner_id_val = raw_owner_id or existing.get("privateServerOwnerId")
        owner_str_val = str(owner_id_val).strip() if owner_id_val not in (None, "", "None", "null") else "private"
        server_type_str = "Private Server"
        player_count_val = None
        max_players_val = None
    else:
        is_private_val = None
        owner_str_val = None
        server_type_str = "Public Server"
        pub_info = _sc_public_servers_info.get(job_id, {})
        player_count_val = server_info.get("playerCount", pub_info.get("playing", existing.get("player_count", existing.get("last_player_count", 0))))
        max_players_val = server_info.get("maxPlayers", pub_info.get("maxPlayers", existing.get("max_players", 50)))

    place_id = server_info.get("placeId") or existing.get("place_id") or 11765852158
    fps = server_info.get("fps", existing.get("fps"))
    ping = server_info.get("ping", existing.get("ping"))

    now_utc_str = datetime.now(timezone.utc).isoformat()
    start_ts = existing.get("start_timestamp") or (valid_ts[0] if valid_ts else server_info.get("lastHeartbeat", now_utc_str))
    last_hb = (valid_ts[-1] if valid_ts else None) or server_info.get("lastHeartbeat") or now_utc_str

    uptime_sec = 0.0
    try:
        dt_start = datetime.fromisoformat(str(start_ts).replace("Z", "+00:00"))
        dt_hb = datetime.fromisoformat(str(last_hb).replace("Z", "+00:00"))
        uptime_sec = max(0.0, (dt_hb - dt_start).total_seconds())
    except Exception:
        pass

    hours = int(uptime_sec // 3600)
    mins = int((uptime_sec % 3600) // 60)
    uptime_fmt = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"

    has_dict_demand = False
    has_anomalies = False
    anomaly_count = 0

    for ts_k in valid_ts:
        st = snaps.get(ts_k)
        if not isinstance(st, dict):
            has_anomalies = True
            anomaly_count += 1
            continue
        for uk in ("Unit1", "Unit2"):
            ust = st.get(uk)
            if not isinstance(ust, dict):
                continue
            for dk in ("DemandU1", "DemandU2", "Demand", "NextDemandU1", "NextDemandU2"):
                if dk in ust:
                    val = ust[dk]
                    if isinstance(val, dict):
                        has_dict_demand = True
                        has_anomalies = True
                        anomaly_count += 1
                    elif isinstance(val, (list, tuple)):
                        has_anomalies = True
                        anomaly_count += 1

    latest_summary = {}
    if valid_ts:
        last_snap = snaps.get(valid_ts[-1], {})
        if isinstance(last_snap, dict):
            u1 = last_snap.get("Unit1", {}) if isinstance(last_snap.get("Unit1"), dict) else {}
            u2 = last_snap.get("Unit2", {}) if isinstance(last_snap.get("Unit2"), dict) else {}
            u1_mw = safe_float(u1.get("Output", u1.get("ElectricOutputMW", u1.get("Output (MW)"))), 0.0)
            u2_mw = safe_float(u2.get("Output", u2.get("ElectricOutputMW", u2.get("PradDoSieci"))), 0.0)
            u1_dem = format_demand_value(u1.get("DemandU1", u1.get("Demand")))
            u2_dem = format_demand_value(u2.get("DemandU2", u2.get("Demand")))
            latest_summary = {
                "u1_mw": round(u1_mw, 1),
                "u2_mw": round(u2_mw, 1),
                "total_mw": round(u1_mw + u2_mw, 1),
                "u1_aprm": safe_float(u1.get("APRM"), 0.0),
                "u2_aprm": safe_float(u2.get("APRM"), 0.0),
                "u1_demand": u1_dem,
                "u2_demand": u2_dem,
                "pps": safe_float(last_snap.get("Total points/second", 0.0), 0.0),
            }

    return {
        "job_id": job_id,
        "jobId": job_id,
        "id": server_info.get("id") or existing.get("id"),
        "server_id": server_info.get("id") or existing.get("id"),
        "snapshot_count": snapshot_count,
        "is_private": is_private_val,
        "privateServerOwnerId": owner_str_val if is_priv else None,
        "server_type": server_type_str,
        "place_id": place_id,
        "player_count": player_count_val,
        "max_players": max_players_val,
        "fps": fps,
        "ping": ping,
        "start_timestamp": start_ts,
        "first_seen_timestamp": existing.get("first_seen_timestamp", start_ts),
        "last_heartbeat": last_hb,
        "last_seen_timestamp": last_hb,
        "uptime_seconds": round(uptime_sec, 1),
        "uptime_formatted": uptime_fmt,
        "last_archived_ts": existing.get("last_archived_ts", ""),
        "has_dict_demand": has_dict_demand,
        "has_anomalies": has_anomalies,
        "anomaly_count": anomaly_count,
        "latest_state_summary": latest_summary,
        "updated_at": now_utc_str,
    }

_sc_archives_meta_cache: dict[str, tuple[float, int, int, int]] = {}
_sc_archive_server_index: dict[str, str] = {}

def load_archives_meta() -> None:
    global _sc_archives_meta_cache
    if os.path.exists(ARCHIVES_META_FILE):
        try:
            with open(ARCHIVES_META_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                _sc_archives_meta_cache = {
                    k: (float(v[0]), int(v[1]), int(v[2]), int(v[3]))
                    for k, v in data.items()
                    if isinstance(v, (list, tuple)) and len(v) >= 4
                }
        except Exception as e:
            logger.error(f"Error loading archives meta cache from {ARCHIVES_META_FILE}: {e}")

def save_archives_meta() -> None:
    try:
        data = {k: list(v) for k, v in safe_dict_items(_sc_archives_meta_cache)}
        temp_path = f"{ARCHIVES_META_FILE}.{os.getpid()}_{time.time_ns()}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(temp_path, ARCHIVES_META_FILE)
    except Exception as e:
        logger.error(f"Error saving archives meta cache to {ARCHIVES_META_FILE}: {e}")

def save_archive_server_index() -> None:
    try:
        temp_path = f"{ARCHIVES_INDEX_FILE}.{os.getpid()}_{time.time_ns()}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(_sc_archive_server_index, f)
        os.replace(temp_path, ARCHIVES_INDEX_FILE)
    except Exception as e:
        logger.error(f"Error saving archive server index to {ARCHIVES_INDEX_FILE}: {e}")

def rebuild_archive_server_index() -> None:
    global _sc_archive_server_index
    if not os.path.exists(ARCHIVES_DIR):
        return
    logger.info("Rebuilding archive server index from archives directory...")
    new_index = {}
    try:
        for fname in sorted(os.listdir(ARCHIVES_DIR)):
            if not fname.startswith("servers_"):
                continue
            is_gz = fname.endswith(".json.gz")
            is_json = fname.endswith(".json") and not is_gz
            if not (is_gz or is_json):
                continue
            date_str = fname[len("servers_"):-len(".json.gz")] if is_gz else fname[len("servers_"):-len(".json")]
            rel_path = os.path.join("archives", fname)
            day_data = get_sc_data(rel_path)
            if isinstance(day_data, dict):
                for jid in day_data.keys():
                    new_index[jid] = date_str
        _sc_archive_server_index = new_index
        save_archive_server_index()
        logger.info(f"Rebuilt archive server index: {len(_sc_archive_server_index)} servers indexed.")
    except Exception as e:
        logger.error(f"Error during archive server index rebuild: {e}")

def load_archive_server_index() -> None:
    global _sc_archive_server_index
    if os.path.exists(ARCHIVES_INDEX_FILE):
        try:
            with open(ARCHIVES_INDEX_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data:
                _sc_archive_server_index = data
                return
        except Exception as e:
            logger.error(f"Error loading archive server index from {ARCHIVES_INDEX_FILE}: {e}")
    rebuild_archive_server_index()

def is_exact_job_or_server_id_match(query: str, job_id: str) -> bool:
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
    if len(clean_q) == 32 and clean_q == clean_jid:
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

def lookup_archive_server_date(query: str) -> tuple[str | None, str | None]:
    if not query:
        return None, None

    clean_q = query.strip()
    clean_q_lower = clean_q.lower()

    if clean_q in _sc_archive_server_index:
        return clean_q, _sc_archive_server_index[clean_q]
    if clean_q_lower in _sc_archive_server_index:
        return clean_q_lower, _sc_archive_server_index[clean_q_lower]

    meta = _sc_server_meta.get(clean_q) or _sc_server_meta.get(clean_q_lower)
    if meta and isinstance(meta, dict):
        st = meta.get("start_timestamp")
        if st and len(st) >= 10 and st[4] == "-" and st[7] == "-":
            return clean_q, st[:10]

    for jid, date_str in safe_dict_items(_sc_archive_server_index):
        if is_exact_job_or_server_id_match(clean_q, jid):
            return jid, date_str

    for jid, meta_entry in safe_dict_items(_sc_server_meta):
        if is_exact_job_or_server_id_match(clean_q, jid):
            st = meta_entry.get("start_timestamp") if isinstance(meta_entry, dict) else None
            if st and len(st) >= 10 and st[4] == "-" and st[7] == "-":
                return jid, st[:10]

    return None, None

def get_server_start_date(job_id: str, snaps: dict | None = None) -> str:
    if not job_id:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    meta = _sc_server_meta.get(job_id, {})
    st_ts = meta.get("start_timestamp")
    if st_ts and len(st_ts) >= 10 and st_ts[4] == "-" and st_ts[7] == "-":
        return st_ts[:10]

    if snaps and isinstance(snaps, dict):
        valid_ts = [k for k in safe_dict_keys(snaps) if not k.startswith("_")]
        if valid_ts:
            earliest_ts = min(valid_ts)
            if len(earliest_ts) >= 10 and earliest_ts[4] == "-" and earliest_ts[7] == "-":
                if job_id not in _sc_server_meta:
                    _sc_server_meta[job_id] = {}
                _sc_server_meta[job_id]["start_timestamp"] = earliest_ts
                return earliest_ts[:10]

    if job_id in _sc_archive_server_index:
        date_str = _sc_archive_server_index[job_id]
        if job_id not in _sc_server_meta:
            _sc_server_meta[job_id] = {}
        _sc_server_meta[job_id]["start_timestamp"] = f"{date_str}T00:00:00Z"
        return date_str

    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def get_active_server_start_dates(current_data: dict | None = None) -> set:
    active_dates = set()
    if current_data is None:
        current_data = get_sc_data("servers.json")
    if not isinstance(current_data, dict):
        return active_dates

    now_utc = datetime.now(timezone.utc)
    for s_id, snaps in safe_dict_items(current_data):
        if not snaps or not isinstance(snaps, dict):
            continue
        valid_ts_keys = [k for k in safe_dict_keys(snaps) if not k.startswith("_")]
        if not valid_ts_keys:
            continue
        latest_ts = max(valid_ts_keys)
        latest_state = snaps.get(latest_ts, {})
        age_sec = convert_ISO_to_secs(latest_ts, now=now_utc)
        if not is_server_historical(s_id, snaps, latest_state=latest_state, age_sec=age_sec):
            start_date = get_server_start_date(s_id, snaps)
            if start_date:
                active_dates.add(start_date)
    return active_dates

def archive_expired_server_data(expired_by_date: dict, current_data: dict | None = None) -> None:
    if not expired_by_date:
        return

    os.makedirs(ARCHIVES_DIR, exist_ok=True)
    active_dates = get_active_server_start_dates(current_data)

    for date_str, servers_dict in expired_by_date.items():
        if not servers_dict:
            continue

        base_name = f"servers_{date_str}"
        json_filename = f"{base_name}.json"
        gz_filename = f"{base_name}.json.gz"
        json_rel = os.path.join("archives", json_filename)
        gz_rel = os.path.join("archives", gz_filename)
        json_full = os.path.join(ARCHIVES_DIR, json_filename)
        gz_full = os.path.join(ARCHIVES_DIR, gz_filename)

        existing_archive: dict = {}
        if os.path.exists(gz_full):
            existing_archive = get_sc_data(gz_rel)
        elif os.path.exists(json_full):
            existing_archive = get_sc_data(json_rel)

        existing_archive = dict(existing_archive) if isinstance(existing_archive, dict) else {}

        for job_id, snaps in servers_dict.items():
            if job_id not in existing_archive:
                existing_archive[job_id] = {}
            else:
                existing_archive[job_id] = dict(existing_archive[job_id])
            existing_archive[job_id].update(snaps)
            if job_id in _sc_server_meta:
                existing_archive[job_id]["_meta"] = _sc_server_meta[job_id]
            elif isinstance(snaps, dict) and "_meta" in snaps:
                existing_archive[job_id]["_meta"] = snaps["_meta"]
            _sc_archive_server_index[job_id] = date_str

        day_has_active_servers = date_str in active_dates
        target_full = json_full if day_has_active_servers else gz_full
        target_fname = json_filename if day_has_active_servers else gz_filename
        alt_fname = gz_filename if day_has_active_servers else json_filename

        if day_has_active_servers:
            save_sc_data(existing_archive, json_rel)
            if os.path.exists(gz_full):
                try:
                    os.remove(gz_full)
                    _invalidate_sc_cache(gz_rel)
                except Exception:
                    pass
        else:
            save_sc_data(existing_archive, gz_rel)
            if os.path.exists(json_full):
                try:
                    os.remove(json_full)
                    _invalidate_sc_cache(json_rel)
                except Exception:
                    pass

        try:
            mtime = os.path.getmtime(target_full)
            size_b = os.path.getsize(target_full)
            s_cnt = len(existing_archive)
            snap_cnt = sum(len(snaps) for snaps in safe_dict_values(existing_archive) if isinstance(snaps, dict))
            _sc_archives_meta_cache[target_fname] = (mtime, size_b, s_cnt, snap_cnt)
            _sc_archives_meta_cache.pop(alt_fname, None)
        except Exception:
            pass

    save_archive_server_index()
    save_archives_meta()

def get_archived_server_snapshots(query: str) -> tuple[str | None, dict | None]:
    if not query or not os.path.exists(ARCHIVES_DIR):
        return None, None

    matched_job_id, date_str = lookup_archive_server_date(query.strip())
    if matched_job_id and date_str:
        gz_path = os.path.join(ARCHIVES_DIR, f"servers_{date_str}.json.gz")
        json_path = os.path.join(ARCHIVES_DIR, f"servers_{date_str}.json")
        target_rel = None
        if os.path.exists(gz_path):
            target_rel = os.path.join("archives", f"servers_{date_str}.json.gz")
        elif os.path.exists(json_path):
            target_rel = os.path.join("archives", f"servers_{date_str}.json")

        if target_rel:
            day_data = get_sc_data(target_rel)
            if isinstance(day_data, dict) and matched_job_id in day_data:
                snaps = day_data[matched_job_id]
                if isinstance(snaps, dict):
                    return matched_job_id, snaps

    return None, None

def format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.2f} MB"

def get_all_archive_days_info(progress_callback: Optional[Callable[[int, int, str, int], None]] = None) -> tuple[list[dict], dict]:
    if not os.path.exists(ARCHIVES_DIR):
        return [], {"total_days": 0, "total_servers": 0, "total_snapshots": 0, "total_size_bytes": 0, "total_size_str": "0 B"}

    archive_map: dict[str, dict] = {}
    try:
        raw_filenames = sorted(os.listdir(ARCHIVES_DIR), reverse=True)
    except Exception:
        raw_filenames = []

    valid_filenames = [
        fname for fname in raw_filenames
        if fname.startswith("servers_") and (fname.endswith(".json.gz") or fname.endswith(".json"))
    ]

    meta_dirty = False
    total_files = len(valid_filenames)
    for idx, fname in enumerate(valid_filenames, 1):
        is_gz = fname.endswith(".json.gz")
        date_part = fname[len("servers_"):]
        date_str = date_part[:-len(".json.gz")] if is_gz else date_part[:-len(".json")]

        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            date_formatted = dt.strftime("%B %d, %Y")
            day_of_week = dt.strftime("%A")
        except Exception:
            date_formatted = date_str
            day_of_week = ""

        full_path = os.path.join(ARCHIVES_DIR, fname)
        size_bytes = os.path.getsize(full_path) if os.path.exists(full_path) else 0
        try:
            mtime = os.path.getmtime(full_path)
        except OSError:
            mtime = 0

        cached = _sc_archives_meta_cache.get(fname)
        if cached and cached[0] == mtime and cached[1] == size_bytes:
            s_count, snap_count = cached[2], cached[3]
        else:
            rel_path = os.path.join("archives", fname)
            day_data = get_sc_data(rel_path)
            if isinstance(day_data, dict):
                s_count = len(day_data)
                snap_count = sum(len(snaps) for snaps in safe_dict_values(day_data) if isinstance(snaps, dict))
                for jid in day_data.keys():
                    _sc_archive_server_index[jid] = date_str
            else:
                s_count = 0
                snap_count = 0
            _sc_archives_meta_cache[fname] = (mtime, size_bytes, s_count, snap_count)
            meta_dirty = True

        if progress_callback:
            pct = int((idx / total_files) * 100) if total_files > 0 else 100
            try:
                progress_callback(idx, total_files, fname, pct)
            except Exception:
                pass

        if date_str in archive_map and not is_gz:
            continue

        archive_map[date_str] = {
            "date": date_str,
            "date_formatted": date_formatted,
            "day_of_week": day_of_week,
            "filename": fname,
            "is_compressed": is_gz,
            "size_bytes": size_bytes,
            "size_str": format_file_size(size_bytes),
            "server_count": s_count,
            "snapshot_count": snap_count,
            "rel_path": os.path.join("archives", fname),
        }

    if meta_dirty:
        save_archives_meta()
        save_archive_server_index()

    days_list = sorted(archive_map.values(), key=lambda d: d["date"], reverse=True)
    total_size_bytes = sum(d["size_bytes"] for d in days_list)
    summary_stats = {
        "total_days": len(days_list),
        "total_servers": sum(d["server_count"] for d in days_list),
        "total_snapshots": sum(d["snapshot_count"] for d in days_list),
        "total_size_bytes": total_size_bytes,
        "total_size_str": format_file_size(total_size_bytes),
    }
    return days_list, summary_stats

def compress_finalized_archives(current_data: dict | None = None) -> None:
    if not os.path.exists(ARCHIVES_DIR):
        return

    active_start_dates = get_active_server_start_dates(current_data)

    try:
        for fname in os.listdir(ARCHIVES_DIR):
            if not fname.startswith("servers_") or not fname.endswith(".json"):
                continue

            date_part = fname[len("servers_"):-len(".json")]
            if len(date_part) != 10 or date_part[4] != "-" or date_part[7] != "-":
                continue
            if date_part in active_start_dates:
                continue

            uncompressed_path = os.path.join(ARCHIVES_DIR, fname)
            gz_filename = f"{fname}.gz"
            gz_path = os.path.join(ARCHIVES_DIR, gz_filename)
            json_rel = os.path.join("archives", fname)
            gz_rel = os.path.join("archives", gz_filename)

            try:
                if os.path.exists(gz_path):
                    day_json = get_sc_data(json_rel)
                    day_gz = get_sc_data(gz_rel)
                    if isinstance(day_json, dict) and isinstance(day_gz, dict):
                        merged_gz = {jid: dict(snaps) for jid, snaps in safe_dict_items(day_gz)}
                        for j_id, snaps in safe_dict_items(day_json):
                            if j_id not in merged_gz:
                                merged_gz[j_id] = {}
                            else:
                                merged_gz[j_id] = dict(merged_gz[j_id])
                            merged_gz[j_id].update(snaps)
                        save_sc_data(merged_gz, gz_rel)
                    try:
                        os.remove(uncompressed_path)
                    except Exception:
                        pass
                else:
                    data = get_sc_data(json_rel)
                    if isinstance(data, dict) and data:
                        save_sc_data(data, gz_rel)
                    else:
                        with open(uncompressed_path, "rb") as f_in:
                            raw_data = f_in.read()
                        compressed_data = gzip.compress(raw_data, compresslevel=9)
                        temp_gz_path = f"{gz_path}.{os.getpid()}_{time.time_ns()}.tmp"
                        with open(temp_gz_path, "wb") as f_out:
                            f_out.write(compressed_data)
                            f_out.flush()
                        os.replace(temp_gz_path, gz_path)
                    try:
                        os.remove(uncompressed_path)
                    except Exception:
                        pass

                _invalidate_sc_cache(json_rel)
                _sc_archives_meta_cache.pop(fname, None)
                try:
                    gz_mtime = os.path.getmtime(gz_path)
                    gz_size = os.path.getsize(gz_path)
                    day_gz = get_sc_data(gz_rel)
                    s_cnt = len(day_gz) if isinstance(day_gz, dict) else 0
                    snap_cnt = sum(len(snaps) for snaps in safe_dict_values(day_gz) if isinstance(snaps, dict)) if isinstance(day_gz, dict) else 0
                    _sc_archives_meta_cache[gz_filename] = (gz_mtime, gz_size, s_cnt, snap_cnt)
                    save_archives_meta()
                except Exception as comp_meta_err:
                    logger.error(f"Error updating meta cache after compression of {gz_filename}: {comp_meta_err}")

                logger.info(f"Compressed finalized archive {fname} -> {gz_filename}")
            except Exception as comp_err:
                logger.error(f"Failed to compress archive {fname}: {comp_err}")
    except Exception as e:
        logger.error(f"Error checking archives for compression: {e}")

def prune_and_archive_servers_data(current_data: dict, persistent_ids: set) -> bool:
    if not current_data or not isinstance(current_data, dict):
        return False

    now_utc = datetime.now(timezone.utc)
    cutoff_dt = now_utc - timedelta(hours=48)
    cutoff_iso = cutoff_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:23] + "Z"

    servers_dirty = False
    meta_dirty = False
    archived_data_by_date: dict[str, dict] = {}

    def record_expired_snapshot(s_id: str, ts: str, s_data: Any, server_start_date: str) -> None:
        date_str = server_start_date or (ts[:10] if (ts and len(ts) >= 10 and ts[4] == "-" and ts[7] == "-") else now_utc.strftime("%Y-%m-%d"))
        archived_data_by_date.setdefault(date_str, {}).setdefault(s_id, {})[ts] = s_data

    for s_id in list(current_data.keys()):
        if s_id in persistent_ids:
            snaps = current_data.get(s_id, {})
            if snaps and isinstance(snaps, dict):
                server_start_date = get_server_start_date(s_id, snaps)
                valid_ts_keys = [k for k in snaps.keys() if not k.startswith("_")]
                if valid_ts_keys:
                    meta = _sc_server_meta.setdefault(s_id, {})
                    last_archived_ts = meta.get("last_archived_ts", "")
                    if not last_archived_ts and server_start_date:
                        gz_path = os.path.join(ARCHIVES_DIR, f"servers_{server_start_date}.json.gz")
                        json_path = os.path.join(ARCHIVES_DIR, f"servers_{server_start_date}.json")
                        target_rel = None
                        if os.path.exists(gz_path):
                            target_rel = os.path.join("archives", f"servers_{server_start_date}.json.gz")
                        elif os.path.exists(json_path):
                            target_rel = os.path.join("archives", f"servers_{server_start_date}.json")
                        if target_rel:
                            arch_data = get_sc_data(target_rel)
                            if isinstance(arch_data, dict) and s_id in arch_data:
                                arch_snaps = arch_data[s_id]
                                if isinstance(arch_snaps, dict) and arch_snaps:
                                    valid_arch_keys = [k for k in arch_snaps.keys() if not k.startswith("_")]
                                    if valid_arch_keys:
                                        last_archived_ts = max(valid_arch_keys)
                                        meta["last_archived_ts"] = last_archived_ts
                                        meta_dirty = True

                    unarchived_keys = [ts for ts in valid_ts_keys if ts > last_archived_ts]
                    if unarchived_keys:
                        for ts in unarchived_keys:
                            record_expired_snapshot(s_id, ts, snaps[ts], server_start_date)
                        meta["last_archived_ts"] = max(unarchived_keys)
                        meta_dirty = True
            continue

        snaps = current_data.get(s_id, {})
        if not snaps:
            del current_data[s_id]
            servers_dirty = True
            continue

        valid_ts_keys = [k for k in snaps.keys() if not k.startswith("_")]
        if not valid_ts_keys:
            del current_data[s_id]
            servers_dirty = True
            continue

        latest_ts = max(valid_ts_keys)
        latest_state = snaps.get(latest_ts, {})
        age_sec = convert_ISO_to_secs(latest_ts, now=now_utc)
        server_start_date = get_server_start_date(s_id, snaps)

        meta = _sc_server_meta.setdefault(s_id, {})
        last_archived_ts = meta.get("last_archived_ts", "")
        if not last_archived_ts and server_start_date:
            gz_path = os.path.join(ARCHIVES_DIR, f"servers_{server_start_date}.json.gz")
            json_path = os.path.join(ARCHIVES_DIR, f"servers_{server_start_date}.json")
            target_rel = None
            if os.path.exists(gz_path):
                target_rel = os.path.join("archives", f"servers_{server_start_date}.json.gz")
            elif os.path.exists(json_path):
                target_rel = os.path.join("archives", f"servers_{server_start_date}.json")
            if target_rel:
                arch_data = get_sc_data(target_rel)
                if isinstance(arch_data, dict) and s_id in arch_data:
                    arch_snaps = arch_data[s_id]
                    if isinstance(arch_snaps, dict) and arch_snaps:
                        valid_arch_keys = [k for k in arch_snaps.keys() if not k.startswith("_")]
                        if valid_arch_keys:
                            last_archived_ts = max(valid_arch_keys)
                            meta["last_archived_ts"] = last_archived_ts
                            meta_dirty = True

        if is_server_historical(s_id, snaps, latest_state=latest_state, age_sec=age_sec):
            unarchived_keys = [ts for ts in valid_ts_keys if ts > last_archived_ts]
            if unarchived_keys:
                for ts in unarchived_keys:
                    record_expired_snapshot(s_id, ts, snaps[ts], server_start_date)
                meta["last_archived_ts"] = max(unarchived_keys)
                meta_dirty = True

            if latest_ts < cutoff_iso:
                del current_data[s_id]
                _sc_server_meta.pop(s_id, None)
                servers_dirty = True
                meta_dirty = True
                logger.info(f"Purged expired historical server {s_id} (>48h inactive) from servers.json")
            continue

        earliest_ts = min(valid_ts_keys)
        if earliest_ts < cutoff_iso:
            expired_keys = [ts for ts in valid_ts_keys if ts < cutoff_iso]
            if expired_keys:
                for ts in expired_keys:
                    record_expired_snapshot(s_id, ts, snaps[ts], server_start_date)
                    del snaps[ts]
                meta["last_archived_ts"] = max(meta.get("last_archived_ts", ""), max(expired_keys))
                servers_dirty = True
                meta_dirty = True

    if archived_data_by_date:
        archive_expired_server_data(archived_data_by_date, current_data)
    if meta_dirty:
        save_server_meta()
    compress_finalized_archives(current_data)
    return servers_dirty

def update_public_roblox_servers() -> bool:
    base_url = "https://games.roblox.com/v1/games/11765852158/servers/Public?limit=100"
    cursor = ""
    public_ids: list[str] = []
    public_info: dict[str, dict] = {}

    try:
        for _ in range(5):
            url = f"{base_url}&cursor={cursor}" if cursor else base_url
            response = requests.get(url, headers={"User-Agent": "RBWR-Server-Checker/1.0 (RBWR Utilities)"}, timeout=10)
            if response.status_code != 200:
                break
            data = response.json()
            for server in data.get("data", []):
                s_id = server.get("id")
                if s_id:
                    public_ids.append(s_id)
                    public_info[s_id] = {
                        "playing": int(server.get("playing", 0)),
                        "maxPlayers": int(server.get("maxPlayers", 12)),
                    }
            cursor = data.get("nextPageCursor")
            if not cursor:
                break

        if public_ids or public_info:
            with _sc_lock:
                global _sc_public_server_ids, _sc_public_servers_info
                _sc_public_server_ids = list(public_ids)
                _sc_public_servers_info = dict(public_info)
                save_sc_data({"ids": _sc_public_server_ids, "info": _sc_public_servers_info}, PUBLIC_SERVERS_CACHE_FILE)

                meta_dirty = False
                for s_id in public_ids:
                    if s_id not in _sc_server_meta or _sc_server_meta[s_id].get("is_private") is not False:
                        _sc_server_meta.setdefault(s_id, {})["is_private"] = False
                        meta_dirty = True
                    p_num = public_info.get(s_id, {}).get("playing", 0)
                    if p_num > 0:
                        _sc_server_meta.setdefault(s_id, {})["last_player_count"] = p_num
                        meta_dirty = True
                if meta_dirty:
                    save_server_meta()
            return True
        return False
    except Exception as e:
        logger.error(f"Error updating public Roblox servers: {e}")
        return False

def pull_server_checker_data() -> bool:
    urls = [
        "https://hydrogen.realisticbwr.org/api/public/servers",
        "https://realisticbwr.org/api/public/servers",
    ]
    response = None
    for url in urls:
        try:
            resp = requests.get(url, headers={"User-Agent": "RBWR-Server-Checker/1.0 (RBWR Utilities)"}, timeout=60)
            if resp.status_code == 200:
                response = resp
                break
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            continue

    if not response or response.status_code != 200:
        logger.warning("All server endpoints failed or timed out.")
        return False

    try:
        resp_json = response.json()
    except Exception as e:
        logger.error(f"Failed to decode server response JSON: {e}")
        return False

    update_public_roblox_servers()

    with _sc_lock:
        raw_current = get_sc_data("servers.json") or {}
        current_data = {jid: dict(snaps) for jid, snaps in safe_dict_items(raw_current)}
        servers_list = resp_json.get("data", {}).get("servers", [])

        for server in servers_list:
            job_id = server.get("jobId")
            if job_id and job_id not in _sc_server_ids:
                _sc_server_ids.append(job_id)

        global _sc_latest_data
        _sc_latest_data = resp_json
        for s in _sc_latest_data.get("data", {}).get("servers", []):
            st = s.get("state")
            if isinstance(st, dict):
                if isinstance(st.get("Unit2"), dict):
                    ensure_unit_output_mw(st["Unit2"])
                    ensure_unit_fuel_level("Unit2", st["Unit2"])
                if isinstance(st.get("Unit1"), dict):
                    ensure_unit_output_mw(st["Unit1"])
                    ensure_unit_fuel_level("Unit1", st["Unit1"])
        save_sc_data(_sc_latest_data, LATEST_SERVERS_CACHE_FILE)

        persistent_data = load_persistent_servers()
        persistent_ids = set(persistent_data.get("persistent", {}).keys())
        meta_dirty = False

        for server in servers_list:
            job_id = server.get("jobId")
            if not job_id:
                continue
            if job_id not in current_data:
                current_data[job_id] = {}

            raw_state = server.get("state")
            if not isinstance(raw_state, dict):
                continue

            state = raw_state.copy()
            misc_data = state.get("Misc")
            if isinstance(misc_data, dict):
                tot_pps = misc_data.get("Total points/second")
                if tot_pps is not None:
                    state["Total points/second"] = tot_pps
            state.pop("Misc", None)

            owner_id = server.get("privateServerOwnerId")
            owner_id = str(owner_id).strip() if owner_id not in (None, "", 0, "0", "None", "null", False) else None

            if owner_id is not None:
                state["IsPrivate"] = True
                state["privateServerOwnerId"] = owner_id
                if server.get("id"):
                    state["ServerId"] = server.get("id")
                if job_id not in _sc_server_meta or _sc_server_meta[job_id].get("is_private") is not True or _sc_server_meta[job_id].get("privateServerOwnerId") != owner_id:
                    _sc_server_meta.setdefault(job_id, {})["is_private"] = True
                    _sc_server_meta[job_id]["privateServerOwnerId"] = owner_id
                    if server.get("id"):
                        _sc_server_meta[job_id]["id"] = server.get("id")
                    meta_dirty = True
            elif _sc_public_server_ids:
                is_priv = job_id not in _sc_public_server_ids
                state["IsPrivate"] = is_priv
                state["privateServerOwnerId"] = (_sc_server_meta.get(job_id, {}).get("privateServerOwnerId") or "private") if is_priv else None
                if job_id not in _sc_server_meta or _sc_server_meta[job_id].get("is_private") != (is_priv if is_priv else None):
                    _sc_server_meta.setdefault(job_id, {})["is_private"] = is_priv if is_priv else None
                    if not is_priv:
                        _sc_server_meta[job_id]["privateServerOwnerId"] = None
                    if server.get("id"):
                        _sc_server_meta[job_id]["id"] = server.get("id")
                    meta_dirty = True
            elif job_id in _sc_server_meta and "is_private" in _sc_server_meta[job_id]:
                is_priv = bool(_sc_server_meta[job_id]["is_private"])
                state["IsPrivate"] = is_priv
                state["privateServerOwnerId"] = (_sc_server_meta[job_id].get("privateServerOwnerId") or "private") if is_priv else None
            else:
                is_priv = False
                state["IsPrivate"] = False
                state["privateServerOwnerId"] = None

            info = _sc_public_servers_info.get(job_id, {})
            if state["IsPrivate"]:
                state.pop("PlayerCount", None)
            else:
                player_count = info.get("playing", 0) if job_id in _sc_public_servers_info else 0
                state["PlayerCount"] = player_count
                if player_count > 0:
                    _sc_server_meta.setdefault(job_id, {})["last_player_count"] = player_count
                    meta_dirty = True

            for unit in ("Unit1", "Unit2"):
                unit_state = state.get(unit)
                if isinstance(unit_state, dict):
                    unit_dict = {}
                    for k, v in unit_state.items():
                        if k in SERVER_CHECKER_PURGE_KEYS:
                            continue
                        if isinstance(v, (int, float)) and not isinstance(v, bool):
                            prec = SERVER_CHECKER_FIELD_PRECISION.get(k, 2)
                            unit_dict[k] = round(v, prec) if prec is not None else v
                        else:
                            unit_dict[k] = v
                    ensure_unit_output_mw(unit_dict)
                    ensure_unit_fuel_level(unit, unit_dict)
                    state[unit] = unit_dict
                else:
                    state[unit] = {}

            heartbeat = server.get("lastHeartbeat", datetime.now(timezone.utc).isoformat())
            _sc_server_meta.setdefault(job_id, {}).setdefault("start_timestamp", heartbeat)
            current_data[job_id][heartbeat] = state

            meta_record = build_server_metadata(
                job_id=job_id,
                snapshots=current_data[job_id],
                server_raw=server,
                existing_meta=_sc_server_meta.get(job_id),
            )
            current_data[job_id]["_meta"] = meta_record
            _sc_server_meta[job_id] = meta_record
            meta_dirty = True

        for s_id, s_snaps in current_data.items():
            if isinstance(s_snaps, dict) and "_meta" not in s_snaps:
                m_rec = build_server_metadata(s_id, s_snaps, existing_meta=_sc_server_meta.get(s_id))
                s_snaps["_meta"] = m_rec
                _sc_server_meta[s_id] = m_rec
                meta_dirty = True

        servers_dirty = bool(servers_list)
        if prune_and_archive_servers_data(current_data, persistent_ids):
            servers_dirty = True

        if servers_dirty:
            save_sc_data(current_data, "servers.json")
        if meta_dirty:
            save_server_meta()

        raw_global = get_sc_data("global.json") or {}
        global_data = dict(raw_global)
        stats_payload = resp_json.get("data", {}).get("stats", {})
        if stats_payload:
            global_data[str(datetime.now(timezone.utc).isoformat())] = stats_payload
            save_sc_data(global_data, "global.json")

        return True

def convert_ISO_to_secs(timestamp_str: str, now: Optional[datetime] = None) -> int:
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        if now is None:
            now = datetime.now(timezone.utc)
        age_seconds = (now - dt).total_seconds()
        return max(0, round(age_seconds))
    except Exception:
        return 0

def format_uptime_duration(seconds: float) -> str:
    s = max(0, int(round(seconds)))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        m = s // 60
        rem_s = s % 60
        return f"{m}m {rem_s}s" if rem_s > 0 else f"{m}m"
    h = s // 3600
    rem_m = (s % 3600) // 60
    return f"{h}h {rem_m}m" if rem_m > 0 else f"{h}h"

def format_heartbeat_age(seconds: Any) -> str:
    if seconds is None:
        return "N/A"
    try:
        s = max(0, int(round(float(seconds))))
    except (ValueError, TypeError):
        return "N/A"

    if s < 60:
        return f"{s}s ago"
    if s < 3600:
        m = s // 60
        rem_s = s % 60
        return f"{m}m {rem_s}s ago" if rem_s > 0 else f"{m}m ago"
    if s < 86400:
        h = s // 3600
        rem_m = (s % 3600) // 60
        return f"{h}h {rem_m}m ago" if rem_m > 0 else f"{h}h ago"
    if s < 604800:
        d = s // 86400
        rem_h = (s % 86400) // 3600
        return f"{d}d {rem_h}h ago" if rem_h > 0 else f"{d}d ago"
    if s < 2592000:
        w = s // 604800
        rem_d = (s % 604800) // 86400
        return f"{w}w {rem_d}d ago" if rem_d > 0 else f"{w}w ago"
    if s < 31536000:
        mo = s // 2592000
        rem_d = (s % 2592000) // 86400
        rem_w = rem_d // 7
        return f"{mo}mo {rem_w}w ago" if rem_w > 0 else (f"{mo}mo {rem_d}d ago" if rem_d > 0 else f"{mo}mo ago")
    y = s // 31536000
    rem_mo = (s % 31536000) // 2592000
    return f"{y}y {rem_mo}mo ago" if rem_mo > 0 else f"{y}y ago"

def get_server_uptime_seconds(snapshots: Any, is_historical: bool, age_sec: Optional[float] = None) -> int:
    if not snapshots or not isinstance(snapshots, dict):
        return 0
    try:
        valid_ts_keys = [k for k in safe_dict_keys(snapshots) if not k.startswith("_")]
        if not valid_ts_keys:
            return 0
        first_ts = min(valid_ts_keys)
        latest_ts = max(valid_ts_keys)
        first_sec_ago = convert_ISO_to_secs(first_ts)
        latest_sec_ago = convert_ISO_to_secs(latest_ts) if age_sec is None else age_sec
        if is_historical:
            return max(0, int(first_sec_ago - latest_sec_ago))
        return max(0, int(first_sec_ago))
    except Exception:
        return 0

def is_server_historical(job_id: str, snapshots: Any = None, latest_state: Any = None, is_private: Optional[bool] = None, age_sec: Optional[float] = None) -> bool:
    if age_sec is None:
        if snapshots and isinstance(snapshots, dict):
            valid_ts = [k for k in safe_dict_keys(snapshots) if not k.startswith("_")]
            age_sec = convert_ISO_to_secs(max(valid_ts)) if valid_ts else 0
        else:
            age_sec = 0

    if latest_state is None and snapshots and isinstance(snapshots, dict):
        valid_ts = [k for k in safe_dict_keys(snapshots) if not k.startswith("_")]
        if valid_ts:
            latest_state = snapshots.get(max(valid_ts), {})
    if latest_state is None:
        latest_state = {}

    if is_private is None:
        is_private = get_server_visibility(job_id, snapshots, latest_state, is_active=(age_sec <= 600))

    if is_private:
        return age_sec > 600

    info = _sc_public_servers_info.get(job_id)
    if _sc_public_server_ids:
        if info is None or job_id not in _sc_public_servers_info:
            return True
        return info.get("playing", 0) == 0 or age_sec > 600

    return (age_sec > 600) or (latest_state.get("PlayerCount", 0) == 0)

def get_sc_latest_pps_map() -> dict[str, float]:
    pps_map: dict[str, float] = {}
    latest = get_latest_servers_data()
    if latest and isinstance(latest, dict):
        try:
            for s in latest.get("data", {}).get("servers", []):
                jid = s.get("jobId")
                if jid:
                    st = s.get("state") or {}
                    misc = st.get("Misc") or {}
                    pps = misc.get("Total points/second")
                    if pps is not None:
                        try:
                            pps_map[jid] = float(pps)
                        except (ValueError, TypeError):
                            pass
        except Exception:
            pass
    return pps_map

def get_unit_output_mw(unit_dict: Any) -> float:
    if not isinstance(unit_dict, dict):
        return 0.0
    for k in ("Output (MW)", "PradDoSieci", "Output", "Power", "megawatts", "output_mw"):
        v = unit_dict.get(k)
        if v is not None:
            try:
                return float(v)
            except (ValueError, TypeError):
                continue
    return 0.0

def calculate_server_points_rate(
    unit1: Any,
    unit2: Any,
    job_id: Optional[str] = None,
    total_pps: Any = None,
    latest_state: Any = None,
    pps_map: Optional[dict[str, float]] = None,
) -> dict[str, Any]:
    if not isinstance(unit1, dict):
        unit1 = {}
    if not isinstance(unit2, dict):
        unit2 = {}

    u1_aprm = safe_float(unit1.get("APRM", 0), 0.0)
    u2_aprm = safe_float(unit2.get("APRM", 0), 0.0)
    u1_running = u1_aprm > 5.0
    u2_running = u2_aprm > 5.0

    resolved_total_pps = safe_demand_numeric(total_pps)
    if resolved_total_pps is None and pps_map and job_id and job_id in pps_map:
        resolved_total_pps = pps_map[job_id]

    if resolved_total_pps is None and job_id:
        latest = get_latest_servers_data()
        if latest and isinstance(latest, dict):
            try:
                for s in latest.get("data", {}).get("servers", []):
                    if s.get("jobId") == job_id:
                        st = s.get("state") or {}
                        misc = st.get("Misc") or {}
                        pps_val = misc.get("Total points/second")
                        if pps_val is not None:
                            resolved_total_pps = float(pps_val)
                        break
            except Exception:
                pass

    if resolved_total_pps is None and isinstance(latest_state, dict):
        pps_val = latest_state.get("Total points/second")
        if pps_val is None and isinstance(latest_state.get("Misc"), dict):
            pps_val = latest_state["Misc"].get("Total points/second")
        if pps_val is not None:
            resolved_total_pps = safe_demand_numeric(pps_val)

    u1_rate = safe_float(unit1.get("PointsPerSecond", 0), 0.0)
    u2_rate = safe_float(unit2.get("PointsPerSecond", 0), 0.0)

    if resolved_total_pps is None and (u1_rate > 0 or u2_rate > 0):
        resolved_total_pps = u1_rate + u2_rate

    if resolved_total_pps is not None:
        total_rate = max(0.0, resolved_total_pps)
        demand_rate = max(0.0, total_rate - (u1_rate + u2_rate))
        points_rate = round(total_rate, 2)
        points_rate_str = f"{total_rate:.2f} pts/s"
    else:
        demand_rate = None
        points_rate = None
        points_rate_str = "N/A"

    return {
        "u1_running": u1_running,
        "u2_running": u2_running,
        "u1_aprm": u1_aprm,
        "u2_aprm": u2_aprm,
        "u1_rate": u1_rate,
        "u2_rate": u2_rate,
        "demand_rate": demand_rate,
        "points_rate": points_rate,
        "points_rate_str": points_rate_str,
    }

def _build_unit_card_summary(snapshots: dict, unit_key: str, unit_dict: dict, is_running: bool, unit_rate: float) -> dict:
    demand_key = "DemandU1" if unit_key == "Unit1" else "DemandU2"
    stats = get_card_unit_fuel_stats(snapshots, unit_key, unit_dict)
    return {
        "demand": safe_demand_numeric(unit_dict.get(demand_key) if unit_dict.get(demand_key) is not None else unit_dict.get("Demand")),
        "demand_time_left": safe_float(unit_dict.get("Demand Time Left", 0), 0.0),
        "aprm": safe_float(unit_dict.get("APRM", 0), 0.0),
        "reactor_temp": safe_float(unit_dict.get("Reactor Temp", 0), 0.0),
        "output_mw": round(get_unit_output_mw(unit_dict), 1),
        "is_running": is_running,
        "points_rate": unit_rate,
        **stats,
    }

def get_active_cards_base(servers_data: dict, persistent_ids: set) -> list[dict]:
    global _sc_active_cards_base, _sc_active_cards_key
    sync_cross_process_caches()
    cache_key = (id(servers_data), len(servers_data), len(persistent_ids), len(_sc_public_server_ids))
    with _sc_active_lock:
        if _sc_active_cards_base is not None and _sc_active_cards_key == cache_key:
            return _sc_active_cards_base

    now_utc = datetime.now(timezone.utc)
    pps_map = get_sc_latest_pps_map()
    cards = []
    server_items = safe_dict_items(servers_data)
    server_items.sort(key=lambda x: str(x[0]))
    for job_id, snapshots in server_items:
        if not snapshots or not isinstance(snapshots, dict):
            continue
        valid_ts_keys = [k for k in safe_dict_keys(snapshots) if not k.startswith("_")]
        if not valid_ts_keys:
            continue
        latest_timestamp = max(valid_ts_keys)
        latest_state = snapshots.get(latest_timestamp)
        if not latest_state or not isinstance(latest_state, dict):
            continue
        info = _sc_public_servers_info.get(job_id, {})
        age_sec = convert_ISO_to_secs(latest_timestamp, now=now_utc)
        is_persistent = job_id in persistent_ids
        is_private = get_server_visibility(job_id, snapshots, latest_state, is_active=(age_sec <= 600))
        is_historical = is_server_historical(job_id, snapshots, latest_state, is_private=is_private, age_sec=age_sec)

        meta = (snapshots.get("_meta") or _sc_server_meta.get(job_id, {})) if isinstance(snapshots, dict) else (_sc_server_meta.get(job_id, {}) or {})
        card_owner_id = (
            meta.get("privateServerOwnerId")
            or (latest_state.get("privateServerOwnerId") if isinstance(latest_state, dict) else None)
        ) if is_private else None

        if is_historical and not is_persistent:
            continue

        if is_private:
            player_count = None
            max_players = None
        else:
            player_count = get_server_player_count(job_id, snapshots, latest_state, is_private=False)
            max_players = info.get("maxPlayers", 12) if info else 12

        first_timestamp = min(valid_ts_keys)
        uptime_sec = get_server_uptime_seconds(snapshots, is_historical, age_sec)
        j_parts = [p for p in job_id.split("-") if p]
        short_id = f"{j_parts[1]}-{j_parts[2]}" if len(j_parts) >= 3 else ""

        unit1 = latest_state.get("Unit1", {})
        unit2 = latest_state.get("Unit2", {})
        pts_info = calculate_server_points_rate(unit1, unit2, job_id=job_id, latest_state=latest_state, pps_map=pps_map)
        top_score = calculate_server_top_score(snapshots, now_utc=now_utc)

        cards.append({
            "job_id": job_id,
            "short_id": short_id,
            "is_private": is_private,
            "privateServerOwnerId": card_owner_id,
            "is_persistent": is_persistent,
            "is_historical": is_historical,
            "is_archived": False,
            "player_count": player_count,
            "max_players": max_players,
            "raw_timestamp": latest_timestamp,
            "first_timestamp": first_timestamp,
            "age_seconds": age_sec,
            "latest_timestamp": format_heartbeat_age(age_sec),
            "uptime_seconds": uptime_sec,
            "uptime_str": format_uptime_duration(uptime_sec),
            "snapshot_count": len(valid_ts_keys),
            "points_rate": pts_info["points_rate"],
            "points_rate_str": pts_info["points_rate_str"],
            "top_score": top_score,
            "u1_running": pts_info["u1_running"],
            "u2_running": pts_info["u2_running"],
            "unit1": _build_unit_card_summary(snapshots, "Unit1", unit1, pts_info["u1_running"], pts_info["u1_rate"]),
            "unit2": _build_unit_card_summary(snapshots, "Unit2", unit2, pts_info["u2_running"], pts_info["u2_rate"]),
        })

    with _sc_active_lock:
        _sc_active_cards_base = cards
        _sc_active_cards_key = cache_key

    return cards

def get_historical_cards_base(servers_data: dict, persistent_ids: set) -> list[dict]:
    global _sc_historical_cards_base, _sc_historical_cards_key
    sync_cross_process_caches()
    cache_key = (id(servers_data), len(servers_data), len(persistent_ids), len(_sc_public_server_ids))
    with _sc_historical_lock:
        if _sc_historical_cards_base is not None and _sc_historical_cards_key == cache_key:
            return _sc_historical_cards_base

    now_utc = datetime.now(timezone.utc)
    pps_map = get_sc_latest_pps_map()
    base_cards = []
    for job_id, snapshots in safe_dict_items(servers_data):
        if not snapshots or not isinstance(snapshots, dict):
            continue
        valid_ts_keys = [k for k in safe_dict_keys(snapshots) if not k.startswith("_")]
        if not valid_ts_keys:
            continue
        latest_timestamp = max(valid_ts_keys)
        latest_state = snapshots.get(latest_timestamp)
        if not latest_state or not isinstance(latest_state, dict):
            continue
        age_sec = convert_ISO_to_secs(latest_timestamp, now=now_utc)

        info = _sc_public_servers_info.get(job_id, {})
        is_persistent = job_id in persistent_ids
        is_private = get_server_visibility(job_id, snapshots, latest_state, is_active=(age_sec <= 600))
        is_historical = is_server_historical(job_id, snapshots, latest_state, is_private=is_private, age_sec=age_sec)
        if not is_historical:
            continue

        if is_private:
            player_count = None
            max_players = None
        else:
            player_count = get_server_player_count(job_id, snapshots, latest_state, is_private=False)
            max_players = info.get("maxPlayers", 12) if info else 12

        j_parts = [p for p in job_id.split("-") if p]
        short_id = f"{j_parts[1]}-{j_parts[2]}" if len(j_parts) >= 3 else ""

        first_timestamp = min(valid_ts_keys)
        uptime_sec = get_server_uptime_seconds(snapshots, is_historical, age_sec)
        unit1 = latest_state.get("Unit1", {})
        unit2 = latest_state.get("Unit2", {})
        pts_info = calculate_server_points_rate(unit1, unit2, job_id=job_id, latest_state=latest_state, pps_map=pps_map)
        top_score = calculate_server_top_score(snapshots, now_utc=now_utc)

        base_cards.append({
            "job_id": job_id,
            "short_id": short_id,
            "is_private": is_private,
            "is_persistent": is_persistent,
            "is_historical": True,
            "is_archived": False,
            "player_count": player_count,
            "max_players": max_players,
            "raw_timestamp": latest_timestamp,
            "first_timestamp": first_timestamp,
            "age_seconds": age_sec,
            "latest_timestamp": format_heartbeat_age(age_sec),
            "uptime_seconds": uptime_sec,
            "uptime_str": format_uptime_duration(uptime_sec),
            "snapshot_count": len(valid_ts_keys),
            "points_rate": pts_info["points_rate"],
            "points_rate_str": pts_info["points_rate_str"],
            "top_score": top_score,
            "u1_running": pts_info["u1_running"],
            "u2_running": pts_info["u2_running"],
            "unit1": _build_unit_card_summary(snapshots, "Unit1", unit1, pts_info["u1_running"], pts_info["u1_rate"]),
            "unit2": _build_unit_card_summary(snapshots, "Unit2", unit2, pts_info["u2_running"], pts_info["u2_rate"]),
        })

    with _sc_historical_lock:
        _sc_historical_cards_base = base_cards
        _sc_historical_cards_key = cache_key

    return base_cards

def sort_historical_cards(cards: list[dict], sort_option: str = "top_servers") -> list[dict]:
    s = (sort_option or "top_servers").strip().lower()
    out = list(cards)
    if s == "players_desc":
        out.sort(key=lambda c: (c.get("player_count") or 0, c.get("snapshot_count", 0)), reverse=True)
    elif s == "players_asc":
        out.sort(key=lambda c: (c.get("player_count") or 0, c.get("snapshot_count", 0)))
    elif s == "snapshots_desc":
        out.sort(key=lambda c: (c.get("snapshot_count", 0), c.get("player_count") or 0), reverse=True)
    elif s == "snapshots_asc":
        out.sort(key=lambda c: (c.get("snapshot_count", 0), c.get("player_count") or 0))
    elif s == "points_desc":
        out.sort(key=lambda c: (c.get("points_rate") or 0.0, c.get("uptime_seconds", 0)), reverse=True)
    elif s == "running_first":
        out.sort(key=lambda c: (1 if (c.get("u1_running") or c.get("u2_running")) else 0, c.get("points_rate") or 0.0), reverse=True)
    elif s == "oldest":
        out.sort(key=lambda c: (c.get("uptime_seconds", 0), c.get("player_count") or 0), reverse=True)
    elif s == "newest":
        out.sort(key=lambda c: (c.get("uptime_seconds", 0), -(c.get("player_count") or 0)))
    elif s == "public_first":
        out.sort(key=lambda c: (1 if c.get("is_private") else 0, -c.get("uptime_seconds", 0)))
    elif s == "private_first":
        out.sort(key=lambda c: (0 if c.get("is_private") else 1, -c.get("uptime_seconds", 0)))
    else:
        out.sort(key=lambda c: (c.get("top_score") or 0.0, c.get("points_rate") or 0.0, c.get("uptime_seconds", 0)), reverse=True)
    return out

def build_server_cards(data: dict, search_query: Optional[str] = None, is_archived: bool = False, exact_search_only: bool = True) -> list[dict]:
    if not data:
        return []
    sync_cross_process_caches()
    persistent_data = load_persistent_servers()
    persistent_ids = set(persistent_data.get("persistent", {}).keys())
    clean_query = (search_query or "").strip()

    if not clean_query and not is_archived:
        return list(get_active_cards_base(data, persistent_ids))

    cards = []
    now_utc = datetime.now(timezone.utc)
    pps_map = get_sc_latest_pps_map()
    data_items = safe_dict_items(data)
    data_items.sort(key=lambda x: str(x[0]))
    for job_id, snapshots in data_items:
        if not snapshots or not isinstance(snapshots, dict):
            continue
        valid_ts_keys = [k for k in safe_dict_keys(snapshots) if not k.startswith("_")]
        if not valid_ts_keys:
            continue
        latest_timestamp = max(valid_ts_keys)
        latest_state = snapshots.get(latest_timestamp)
        if not latest_state or not isinstance(latest_state, dict):
            continue
        unit1 = latest_state.get("Unit1", {})
        unit2 = latest_state.get("Unit2", {})

        info = _sc_public_servers_info.get(job_id, {})
        age_sec = convert_ISO_to_secs(latest_timestamp, now=now_utc)
        is_persistent = job_id in persistent_ids
        is_private = get_server_visibility(job_id, snapshots, latest_state, is_active=(age_sec <= 600))

        meta = (snapshots.get("_meta") or _sc_server_meta.get(job_id, {})) if isinstance(snapshots, dict) else (_sc_server_meta.get(job_id, {}) or {})
        card_owner_id = (
            meta.get("privateServerOwnerId")
            or (latest_state.get("privateServerOwnerId") if isinstance(latest_state, dict) else None)
        ) if is_private else None

        server_is_archived = is_archived or (isinstance(snapshots, dict) and bool(snapshots.get("_is_archived", False)))
        is_historical = is_server_historical(job_id, snapshots, latest_state, is_private=is_private, age_sec=age_sec) or server_is_archived
        if is_private:
            player_count = None
            max_players = None
        else:
            player_count = get_server_player_count(job_id, snapshots, latest_state, is_private=False)
            max_players = info.get("maxPlayers", 12) if info else 12

        if (is_historical or server_is_archived) and not is_persistent:
            if exact_search_only:
                if not is_exact_job_or_server_id_match(clean_query, job_id):
                    continue
            elif clean_query:
                j_parts = [p for p in job_id.split("-") if p]
                short_id = f"{j_parts[1]}-{j_parts[2]}" if len(j_parts) >= 3 else ""
                clean_q_lower = clean_query.lower()
                matches = (
                    is_exact_job_or_server_id_match(clean_query, job_id)
                    or clean_q_lower in job_id.lower()
                    or (short_id and clean_q_lower in short_id.lower())
                )
                if not matches:
                    continue

        first_timestamp = min(valid_ts_keys)
        uptime_sec = get_server_uptime_seconds(snapshots, is_historical, age_sec)
        j_parts = [p for p in job_id.split("-") if p]
        short_id = f"{j_parts[1]}-{j_parts[2]}" if len(j_parts) >= 3 else ""
        pts_info = calculate_server_points_rate(unit1, unit2, job_id=job_id, latest_state=latest_state, pps_map=pps_map)
        top_score = calculate_server_top_score(snapshots, now_utc=now_utc)

        cards.append({
            "job_id": job_id,
            "short_id": short_id,
            "is_private": is_private,
            "privateServerOwnerId": card_owner_id,
            "is_persistent": is_persistent,
            "is_historical": is_historical,
            "is_archived": server_is_archived,
            "player_count": player_count,
            "max_players": max_players,
            "raw_timestamp": latest_timestamp,
            "first_timestamp": first_timestamp,
            "age_seconds": age_sec,
            "latest_timestamp": format_heartbeat_age(age_sec),
            "uptime_seconds": uptime_sec,
            "uptime_str": format_uptime_duration(uptime_sec),
            "snapshot_count": len(valid_ts_keys),
            "points_rate": pts_info["points_rate"],
            "points_rate_str": pts_info["points_rate_str"],
            "top_score": top_score,
            "u1_running": pts_info["u1_running"],
            "u2_running": pts_info["u2_running"],
            "unit1": _build_unit_card_summary(snapshots, "Unit1", unit1, pts_info["u1_running"], pts_info["u1_rate"]),
            "unit2": _build_unit_card_summary(snapshots, "Unit2", unit2, pts_info["u2_running"], pts_info["u2_rate"]),
        })
    return cards

def resolve_server_snapshots(query: str) -> tuple[Optional[str], Optional[dict]]:
    sync_cross_process_caches()
    query = (query or "").strip()
    if not query:
        return None, None

    servers_data = get_sc_data("servers.json") or {}
    snapshots = servers_data.get(query)
    matched_job_id = query

    if not snapshots:
        for jid, snaps in safe_dict_items(servers_data):
            if is_exact_job_or_server_id_match(query, jid):
                matched_job_id = jid
                snapshots = snaps
                break

    latest = get_latest_servers_data()
    if not snapshots and latest:
        for s in latest.get("data", {}).get("servers", []):
            s_jid = s.get("jobId", "")
            if is_exact_job_or_server_id_match(query, s_jid):
                matched_job_id = s_jid
                snapshots = {s.get("lastHeartbeat", datetime.now(timezone.utc).isoformat()): s.get("state", {})}
                break

    if not snapshots:
        archived_jid, archived_snaps = get_archived_server_snapshots(query)
        if archived_jid and archived_snaps:
            matched_job_id = archived_jid
            snapshots = archived_snaps

    return matched_job_id, snapshots

def lttb_indices(points: list[tuple[float, float]], threshold: int = 600) -> set[int]:
    n = len(points)
    if n <= threshold or threshold <= 2:
        return set(range(n))

    sampled = {0, n - 1}
    bucket_size = (n - 2) / (threshold - 2)
    a = 0

    for i in range(threshold - 2):
        c_start = int((i + 1) * bucket_size) + 1
        c_end = min(int((i + 2) * bucket_size) + 1, n)
        if c_end <= c_start:
            c_x, c_y = points[min(c_start, n - 1)]
        else:
            c_x = sum(points[k][0] for k in range(c_start, c_end)) / (c_end - c_start)
            c_y = sum(points[k][1] for k in range(c_start, c_end)) / (c_end - c_start)

        b_start = int(i * bucket_size) + 1
        b_end = min(int((i + 1) * bucket_size) + 1, n)
        ax, ay = points[a]

        max_area = -1.0
        max_idx = b_start
        for j in range(b_start, b_end):
            bx, by = points[j]
            area = abs((ax - c_x) * (by - ay) - (ax - bx) * (c_y - ay))
            if area > max_area:
                max_area = area
                max_idx = j

        sampled.add(max_idx)
        a = max_idx

    return sampled

def compress_flat_stretches(points: list[tuple[float, float]], precision: Optional[int] = 2) -> list[tuple[float, float]]:
    n = len(points)
    if n <= 2:
        return list(points)
    result = [points[0]]
    for i in range(1, n - 1):
        y_prev = round(points[i - 1][1], precision) if precision is not None else points[i - 1][1]
        y_curr = round(points[i][1], precision) if precision is not None else points[i][1]
        y_next = round(points[i + 1][1], precision) if precision is not None else points[i + 1][1]
        if y_prev == y_curr == y_next:
            continue
        result.append(points[i])
    result.append(points[-1])
    return result

MAX_CHART_POINTS = 600

def compress_points(points: list[tuple[float, float]], precision: Optional[int] = 2, max_points: int = MAX_CHART_POINTS) -> list[dict]:
    if not points:
        return []
    cleaned = compress_flat_stretches(points, precision=precision)
    if len(cleaned) > max_points:
        indices = lttb_indices(cleaned, threshold=max_points)
        cleaned = [cleaned[i] for i in sorted(indices)]
    return [
        {"x": round(x, 1), "y": (round(y, precision) if precision is not None else y)}
        for x, y in cleaned
    ]

def compress_paired_points(
    u1_points: list[tuple[float, float]],
    u2_points: list[tuple[float, float]],
    precision: Optional[int] = 2,
    max_points: int = MAX_CHART_POINTS,
) -> tuple[list[dict], list[dict]]:
    if not u1_points and not u2_points:
        return [], []
    if not u1_points:
        return [], compress_points(u2_points, precision=precision, max_points=max_points)
    if not u2_points:
        return compress_points(u1_points, precision=precision, max_points=max_points), []

    c_u1 = compress_flat_stretches(u1_points, precision=precision)
    c_u2 = compress_flat_stretches(u2_points, precision=precision)

    if len(c_u1) > max_points or len(c_u2) > max_points:
        idx1 = lttb_indices(c_u1, threshold=max_points)
        idx2 = lttb_indices(c_u2, threshold=max_points)
        kept_x = {round(c_u1[i][0], 1) for i in idx1} | {round(c_u2[i][0], 1) for i in idx2}
    else:
        kept_x = {round(x, 1) for x, _ in c_u1} | {round(x, 1) for x, _ in c_u2}

    res_u1 = [{"x": round(x, 1), "y": (round(y, precision) if precision is not None else y)} for x, y in u1_points if round(x, 1) in kept_x]
    res_u2 = [{"x": round(x, 1), "y": (round(y, precision) if precision is not None else y)} for x, y in u2_points if round(x, 1) in kept_x]
    return res_u1, res_u2

def build_chart_payload(job_id: str, snapshots: Any) -> dict:
    metrics: dict[str, tuple[Any, ...]] = {
        "Demand": ("3", "Electrical Demand (MW)", ["Demand", "DemandU1", "DemandU2"], 2),
        "Output (MW)": ("3", "Electrical Output (MW)", ["Output (MW)", "PradDoSieci", "Output", "Power"], 2),
        "APRM": ("3", "APRM (%)", ["APRM"], 4),
        "RTP": ("2", "RTP (%)", ["RTP"], 4),
        "Xenon": ("3", "Xenon (%)", ["Xenon"], 6, 100.0),
        "Iodine": ("3", "Iodine (%)", ["Iodine"], 6, 100.0),
        "Pressure": ("3", "Reactor Pressure (kPa)", ["Pressure"], 2),
        "Reactor Temp": ("3", "Reactor Temperature (°C)", ["Reactor Temp"], 2),
        "ReactorLevel": ("3", "Reactor Water Level (m)", ["ReactorLevel"], 2),
        "Deareator Level": ("3", "Deaerator Level (m)", ["Deareator Level", "Deaerator Level"], 2),
        "Hotwell Level": ("3", "Hotwell Level (m)", ["Hotwell Level"], 2),
        "TurbineHealth": ("2", "Turbine Health (%)", ["TurbineHealth", "Turbine Health"], 2),
        "GeneratorTemperature": ("2", "Generator Temperature (°C)", ["GeneratorTemperature", "Generator Temperature"], 2),
        "CasingTemperature": ("2", "Casing Temperature (°C)", ["CasingTemperature", "Casing Temperature"], 4),
    }
    chart_payload = []
    ordered_snapshots = []

    if not snapshots:
        return {"job_id": job_id, "last_heartbeat_age": 0, "snapshots": [], "charts": []}

    valid_items = safe_dict_items(snapshots)
    valid_items.sort(key=lambda x: str(x[0]))
    for timestamp, state in valid_items:
        if str(timestamp).startswith("_") or not isinstance(state, dict):
            continue
        sec_ago = convert_ISO_to_secs(timestamp)
        ordered_snapshots.append({
            "timestamp": timestamp,
            "seconds_ago": sec_ago,
            "display_time": f"{sec_ago} seconds ago",
            "state": state,
        })

    is_private = get_server_visibility(job_id, snapshots)

    if not is_private:
        player_points = []
        for entry in ordered_snapshots:
            sec_ago = entry["seconds_ago"]
            st = entry["state"]
            p_val = st.get("PlayerCount")
            if p_val is None:
                p_val = st.get("Players")
            if p_val is None:
                p_val = st.get("playing")
            if p_val is not None and isinstance(p_val, (int, float)):
                player_points.append((sec_ago, float(p_val)))

        if not player_points and ordered_snapshots:
            cur_p = _sc_public_servers_info.get(job_id, {}).get("playing", 0)
            player_points.append((ordered_snapshots[-1]["seconds_ago"], float(cur_p)))

        if player_points:
            chart_payload.append({
                "metric": "Player Count",
                "datasets": [{
                    "label": "Players",
                    "data": compress_points(player_points, precision=0),
                    "borderColor": "#10b981",
                    "backgroundColor": "rgba(16, 185, 129, 0.08)",
                }],
                "total_points": len(player_points),
            })

    for metric_key, metric_cfg in metrics.items():
        unit_type = metric_cfg[0]
        metric_title = metric_cfg[1]
        field_aliases = metric_cfg[2]
        precision = metric_cfg[3] if len(metric_cfg) > 3 else 2
        scale_factor = metric_cfg[4] if len(metric_cfg) > 4 else 1.0
        u1_points = []
        u2_points = []

        for entry in ordered_snapshots:
            sec_ago = entry["seconds_ago"]
            u1_state = entry["state"].get("Unit1", {}) if isinstance(entry["state"].get("Unit1"), dict) else {}
            u2_state = entry["state"].get("Unit2", {}) if isinstance(entry["state"].get("Unit2"), dict) else {}

            if unit_type in ("1", "3"):
                v1 = None
                if metric_key == "Demand":
                    v1 = u1_state.get("DemandU1") if u1_state.get("DemandU1") is not None else u1_state.get("Demand")
                else:
                    for alias in field_aliases:
                        if alias in u1_state and u1_state[alias] is not None:
                            v1 = u1_state[alias]
                            break
                if v1 is not None and isinstance(v1, (int, float)):
                    u1_points.append((sec_ago, float(v1) * scale_factor))

            if unit_type in ("2", "3"):
                v2 = None
                if metric_key == "Demand":
                    v2 = u2_state.get("DemandU2") if u2_state.get("DemandU2") is not None else u2_state.get("Demand")
                else:
                    for alias in field_aliases:
                        if alias in u2_state and u2_state[alias] is not None:
                            v2 = u2_state[alias]
                            break
                if v2 is not None and isinstance(v2, (int, float)):
                    u2_points.append((sec_ago, float(v2) * scale_factor))

        datasets = []
        if u1_points and u2_points and unit_type == "3":
            c_u1, c_u2 = compress_paired_points(u1_points, u2_points, precision=precision)
            datasets.append({"label": "Unit 1", "data": c_u1, "borderColor": "#3b82f6", "backgroundColor": "rgba(59, 130, 246, 0.08)"})
            datasets.append({"label": "Unit 2", "data": c_u2, "borderColor": "#f59e0b", "backgroundColor": "rgba(245, 158, 11, 0.08)"})
        else:
            if u1_points and unit_type in ("1", "3"):
                datasets.append({"label": "Unit 1", "data": compress_points(u1_points, precision=precision), "borderColor": "#3b82f6", "backgroundColor": "rgba(59, 130, 246, 0.08)"})
            if u2_points and unit_type in ("2", "3"):
                datasets.append({"label": "Unit 2", "data": compress_points(u2_points, precision=precision), "borderColor": "#f59e0b", "backgroundColor": "rgba(245, 158, 11, 0.08)"})

        chart_payload.append({
            "metric": metric_title,
            "datasets": datasets,
            "total_points": max(len(u1_points), len(u2_points)) if (u1_points or u2_points) else 0,
        })

    last_heartbeat_age = ordered_snapshots[-1]["seconds_ago"] if ordered_snapshots else 0
    return {
        "job_id": job_id,
        "last_heartbeat_age": last_heartbeat_age,
        "snapshots": ordered_snapshots,
        "charts": chart_payload,
    }

def build_global_chart_payload(snapshots: dict, max_history_seconds: Optional[int] = 7 * 24 * 3600) -> dict:
    if not snapshots:
        return {"snapshots": [], "charts": []}

    u1_points = []
    u2_points = []

    valid_ts_list = sorted([k for k in safe_dict_keys(snapshots) if not k.startswith("_")])
    for timestamp in valid_ts_list:
        sec_ago = convert_ISO_to_secs(timestamp)
        if max_history_seconds is not None and sec_ago > max_history_seconds:
            continue
        data_entry = snapshots.get(timestamp) or {}
        v1 = data_entry.get("unit1", {}).get("megawatts")
        v2 = data_entry.get("unit2", {}).get("megawatts")
        if v1 is not None and isinstance(v1, (int, float)) and v1 > 0:
            u1_points.append((sec_ago, float(v1)))
        if v2 is not None and isinstance(v2, (int, float)) and v2 > 0:
            u2_points.append((sec_ago, float(v2)))

    datasets = []
    if u1_points and u2_points:
        c_u1, c_u2 = compress_paired_points(u1_points, u2_points, precision=2)
        datasets.append({"label": "Unit 1", "data": c_u1, "borderColor": "#3b82f6", "backgroundColor": "rgba(59, 130, 246, 0.08)"})
        datasets.append({"label": "Unit 2", "data": c_u2, "borderColor": "#f59e0b", "backgroundColor": "rgba(245, 158, 11, 0.08)"})
    elif u1_points:
        datasets.append({"label": "Unit 1", "data": compress_points(u1_points, precision=2), "borderColor": "#3b82f6", "backgroundColor": "rgba(59, 130, 246, 0.08)"})
    elif u2_points:
        datasets.append({"label": "Unit 2", "data": compress_points(u2_points, precision=2), "borderColor": "#f59e0b", "backgroundColor": "rgba(245, 158, 11, 0.08)"})

    return {
        "snapshots": [],
        "charts": [{"metric": "Global Power Output (MW)", "datasets": datasets}],
    }

_servers_cache: dict[str, Any] = {"data": None, "timestamp": 0, "content_type": "application/json", "status_code": 200}
_cache_lock = threading.Lock()

def get_public_servers_payload(public_only: bool = False) -> dict:
    sync_cross_process_caches()

    def _enrich_and_filter(raw_list: list[Any]) -> list[dict]:
        enriched = []
        for s in raw_list:
            if not isinstance(s, dict):
                continue
            jid = s.get("jobId")
            if not jid:
                continue
            is_priv = get_server_visibility(jid, is_active=True)
            owner_id = s.get("privateServerOwnerId")
            if not is_priv and owner_id not in (None, "", 0, "0", "None", "null", False):
                is_priv = True
            s_copy = dict(s)
            if is_priv:
                s_copy["is_private"] = True
                clean_oid = str(owner_id).strip() if owner_id not in (None, "", 0, "0", "None", "null", False) else (_sc_server_meta.get(jid, {}).get("privateServerOwnerId") or "private")
                s_copy["privateServerOwnerId"] = clean_oid
            else:
                s_copy["is_private"] = None
                s_copy["privateServerOwnerId"] = None
            if not is_priv:
                p_count = get_server_player_count(jid, is_private=False)
                if p_count is not None:
                    s_copy["playerCount"] = p_count
            if "top_score" not in s_copy:
                score = None
                if _sc_active_cards_base:
                    for card in _sc_active_cards_base:
                        if card.get("job_id") == jid and "top_score" in card:
                            score = card["top_score"]
                            break
                if score is not None:
                    s_copy["top_score"] = score
            st = s_copy.get("state")
            if isinstance(st, dict):
                if isinstance(st.get("Unit2"), dict):
                    ensure_unit_output_mw(st["Unit2"])
                    ensure_unit_fuel_level("Unit2", st["Unit2"])
                if isinstance(st.get("Unit1"), dict):
                    ensure_unit_output_mw(st["Unit1"])
                    ensure_unit_fuel_level("Unit1", st["Unit1"])
            if public_only and is_priv:
                continue
            enriched.append(s_copy)
        return enriched

    latest = get_latest_servers_data()
    if latest:
        res_json = dict(latest)
        if "success" not in res_json:
            res_json["success"] = True
        raw_servers = res_json.get("data", {}).get("servers", [])
        res_json["data"] = dict(res_json.get("data", {}), servers=_enrich_and_filter(raw_servers))
        return res_json

    with _cache_lock:
        if _servers_cache["data"] is not None:
            try:
                cached_json = _json_loads(_servers_cache["data"])
                if isinstance(cached_json, dict) and "data" in cached_json:
                    cached_json["data"] = dict(cached_json.get("data", {}), servers=_enrich_and_filter(cached_json.get("data", {}).get("servers", [])))
                    return cached_json
            except Exception:
                pass

    return {"success": True, "data": {"servers": []}}

def fetch_or_get_public_servers(public_only: bool = False) -> tuple[dict, int]:
    payload = get_public_servers_payload(public_only=public_only)
    if payload.get("data", {}).get("servers"):
        return payload, 200

    for url in (
        "https://hydrogen.realisticbwr.org/api/public/servers",
        "https://realisticbwr.org/api/public/servers",
    ):
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": "RBWR-Operator-Tablet/1.0 (RBWR Thermal Calculator Utility)"},
                timeout=10,
            )
            if resp.status_code == 200:
                try:
                    res_json = resp.json()
                    if isinstance(res_json, dict) and "success" not in res_json:
                        res_json["success"] = True
                    content = json.dumps(res_json).encode("utf-8")
                    save_sc_data(res_json, LATEST_SERVERS_CACHE_FILE)
                except Exception:
                    content = resp.content

                with _cache_lock:
                    _servers_cache["data"] = content
                    _servers_cache["timestamp"] = time.time()
                    _servers_cache["content_type"] = "application/json"
                    _servers_cache["status_code"] = 200

                return get_public_servers_payload(public_only=public_only), 200
        except Exception as e:
            logger.warning(f"Error fetching from {url}: {e}")

    with _cache_lock:
        if _servers_cache["data"] is not None:
            cached = _json_loads(_servers_cache["data"])
            if isinstance(cached, dict):
                return cached, _servers_cache["status_code"]

    return {"success": False, "error": "Unable to reach game API"}, 500

load_server_meta()
load_archives_meta()
load_archive_server_index()