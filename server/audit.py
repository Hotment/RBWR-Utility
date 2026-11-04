from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
AUDIT_LOGS_FILE = os.path.join(DATA_DIR, "audit_logs.json")
MAX_AUDIT_ENTRIES = 5000

_lock = threading.Lock()
_listeners: list[Callable[[dict[str, Any]], None]] = []


def register_audit_listener(callback: Callable[[dict[str, Any]], None]) -> None:
    """Registers a callback invoked whenever a new audit entry is recorded."""
    if callback not in _listeners:
        _listeners.append(callback)

def _notify_listeners(entry: dict[str, Any]) -> None:
    for listener in _listeners:
        try:
            listener(entry)
        except Exception:
            pass

def load_raw_audit_logs() -> list[dict[str, Any]]:
    """Loads all audit logs from disk (thread-safe)."""
    with _lock:
        if not os.path.exists(AUDIT_LOGS_FILE):
            return []
        try:
            with open(AUDIT_LOGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    return data.get("logs", [])
                return []
        except Exception:
            return []

def save_raw_audit_logs(logs: list[dict[str, Any]]) -> None:
    """Saves audit logs to disk (thread-safe)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with _lock:
        try:
            with open(AUDIT_LOGS_FILE, "w", encoding="utf-8") as f:
                json.dump({"logs": logs}, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

def record_audit_log(
    actor: dict[str, Any] | None,
    action: str,
    category: str,
    description: str,
    target: str | None = None,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    actor_info = {
        "username": str(actor.get("username", "System")) if actor else "System",
        "discord_id": str(actor.get("discord_id", "")) if actor else "",
        "display_name": str(actor.get("display_name") or actor.get("username", "System")) if actor else "System",
        "avatar_url": actor.get("avatar_url") if actor else None,
        "is_root": bool(actor.get("is_root", False)) if actor else False,
    }

    entry_id = f"aud_{uuid.uuid4().hex[:12]}"
    clean_ua = (user_agent or "").strip()
    if len(clean_ua) > 200:
        clean_ua = clean_ua[:197] + "..."

    entry: dict[str, Any] = {
        "id": entry_id,
        "timestamp": now_iso,
        "action": str(action).strip(),
        "category": str(category).strip().lower(),
        "actor": actor_info,
        "target": str(target or "").strip(),
        "description": str(description).strip(),
        "details": details or {},
        "ip": str(ip or "unknown").strip(),
        "user_agent": clean_ua,
    }

    logs = load_raw_audit_logs()
    logs.insert(0, entry)
    if len(logs) > MAX_AUDIT_ENTRIES:
        logs = logs[:MAX_AUDIT_ENTRIES]

    save_raw_audit_logs(logs)
    _notify_listeners(entry)
    return entry

def query_audit_logs(
    category: str | None = None,
    action: str | None = None,
    actor: str | None = None,
    query: str | None = None,
    page: int = 1,
    limit: int = 50,
) -> dict[str, Any]:
    logs = load_raw_audit_logs()

    total_stored = len(logs)
    all_categories: set[str] = set()
    all_actions: set[str] = set()
    unique_actors: set[str] = set()
    today_count = 0
    security_events_count = 0

    now_utc = datetime.now(timezone.utc)

    for item in logs:
        cat = item.get("category", "")
        if cat:
            all_categories.add(cat)
        act = item.get("action", "")
        if act:
            all_actions.add(act)

        actr = item.get("actor", {})
        if isinstance(actr, dict):
            identifier = actr.get("discord_id") or actr.get("username")
            if identifier:
                unique_actors.add(str(identifier))

        ts_str = item.get("timestamp")
        if ts_str:
            try:
                dt = datetime.fromisoformat(ts_str)
                if (now_utc - dt).total_seconds() <= 86400:
                    today_count += 1
            except Exception:
                pass

        if cat in ("auth", "bans", "accounts"):
            security_events_count += 1

    cat_filter = (category or "").strip().lower()
    act_filter = (action or "").strip().lower()
    actor_filter = (actor or "").strip().lower()
    q_filter = (query or "").strip().lower()

    filtered = logs
    if cat_filter and cat_filter != "all":
        filtered = [x for x in filtered if x.get("category", "").lower() == cat_filter]

    if act_filter and act_filter != "all":
        filtered = [x for x in filtered if act_filter in x.get("action", "").lower()]

    if actor_filter:
        def match_actor(entry: dict[str, Any]) -> bool:
            a = entry.get("actor") or {}
            u = str(a.get("username", "")).lower()
            dn = str(a.get("display_name", "")).lower()
            did = str(a.get("discord_id", "")).lower()
            return actor_filter in u or actor_filter in dn or actor_filter in did
        filtered = [x for x in filtered if match_actor(x)]

    if q_filter:
        def match_query(entry: dict[str, Any]) -> bool:
            desc = str(entry.get("description", "")).lower()
            tgt = str(entry.get("target", "")).lower()
            ip = str(entry.get("ip", "")).lower()
            act = str(entry.get("action", "")).lower()
            cat = str(entry.get("category", "")).lower()
            a = entry.get("actor") or {}
            u = str(a.get("username", "")).lower()
            dn = str(a.get("display_name", "")).lower()
            did = str(a.get("discord_id", "")).lower()
            det_str = json.dumps(entry.get("details", {})).lower()
            return (
                q_filter in desc
                or q_filter in tgt
                or q_filter in ip
                or q_filter in act
                or q_filter in cat
                or q_filter in u
                or q_filter in dn
                or q_filter in did
                or q_filter in det_str
            )
        filtered = [x for x in filtered if match_query(x)]

    total_filtered = len(filtered)
    limit = max(1, min(limit, 200))
    total_pages = max(1, (total_filtered + limit - 1) // limit)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    page_items = filtered[start_idx:end_idx]

    return {
        "logs": page_items,
        "total": total_filtered,
        "total_stored": total_stored,
        "page": page,
        "pages": total_pages,
        "limit": limit,
        "categories": sorted(all_categories),
        "actions": sorted(all_actions),
        "stats": {
            "total_stored": total_stored,
            "today_count": today_count,
            "unique_actors": len(unique_actors),
            "security_events": security_events_count,
        },
    }

def clear_audit_logs(
    actor: dict[str, Any] | None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    save_raw_audit_logs([])

    actor_name = actor.get("display_name") or actor.get("username") if actor else "Root Administrator"
    new_entry = record_audit_log(
        actor=actor,
        action="audit.purge",
        category="system",
        description=f"All prior administrative audit logs were cleared by {actor_name}",
        target="Audit Log Store",
        details={"purged_at": datetime.now(timezone.utc).isoformat()},
        ip=ip,
        user_agent=user_agent,
    )
    return new_entry

def get_audit_summary() -> dict[str, Any]:
    """Returns a quick summary payload for WebSockets / overview dashboard."""
    logs = load_raw_audit_logs()
    total = len(logs)
    recent = logs[:20]
    now_utc = datetime.now(timezone.utc)
    today_count = 0
    unique_actors: set[str] = set()

    for item in logs:
        ts_str = item.get("timestamp")
        if ts_str:
            try:
                dt = datetime.fromisoformat(ts_str)
                if (now_utc - dt).total_seconds() <= 86400:
                    today_count += 1
            except Exception:
                pass
        actr = item.get("actor", {})
        if isinstance(actr, dict):
            identifier = actr.get("discord_id") or actr.get("username")
            if identifier:
                unique_actors.add(str(identifier))

    return {
        "total": total,
        "today_count": today_count,
        "unique_actors": len(unique_actors),
        "recent_logs": recent,
    }