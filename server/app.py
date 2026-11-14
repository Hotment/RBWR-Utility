from typing import Any, Optional
from flask import Flask, request, jsonify, send_from_directory, redirect, Response, render_template, session, has_request_context
from pydantic import BaseModel, Field, ValidationError
import os
import sys
import json
import gzip
import traceback
import re
from werkzeug.exceptions import HTTPException
orjson = None
try:
    import orjson
except ImportError:
    pass

try:
    from server.scoring import calculate_server_top_score
except ImportError:
    from scoring import calculate_server_top_score

try:
    from server.fuel import evaluate_server_fuel
except ImportError:
    from fuel import evaluate_server_fuel

def _json_dumps(obj):
    if orjson:
        try:
            return orjson.dumps(obj)
        except Exception:
            pass
    return json.dumps(obj).encode("utf-8")

def _json_loads(b):
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

from urllib.parse import quote, urlencode
import secrets
import requests
import hashlib
import binascii
from dotenv import load_dotenv
import time
import threading
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask_sock import Sock
from werkzeug.middleware.proxy_fix import ProxyFix

_workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _workspace_root not in sys.path:
    sys.path.insert(0, _workspace_root)
_current_dir = os.path.abspath(os.path.dirname(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

try:
    from bot.bot import (
        create_discord_ticket_channel,
        forward_ticket_reply_to_discord,
        edit_ticket_reply_in_discord,
        delete_ticket_reply_in_discord,
        start_bot_thread,
        is_user_in_guild,
        notify_ticket_author_dm,
        send_test_notification_dm,
        update_discussion_thread_status,
        update_ticket_channel_message,
        notify_ticket_deleted,
        report_error_to_discord,
        report_crash_to_discord,
    )
except Exception:
    from bot import (
        create_discord_ticket_channel,  # pyright: ignore[reportAttributeAccessIssue]
        forward_ticket_reply_to_discord,  # pyright: ignore[reportAttributeAccessIssue]
        edit_ticket_reply_in_discord,  # pyright: ignore[reportAttributeAccessIssue]
        delete_ticket_reply_in_discord,  # pyright: ignore[reportAttributeAccessIssue]
        start_bot_thread,  # pyright: ignore[reportAttributeAccessIssue]
        is_user_in_guild,  # pyright: ignore[reportAttributeAccessIssue]
        notify_ticket_author_dm,  # pyright: ignore[reportAttributeAccessIssue]
        send_test_notification_dm,  # pyright: ignore[reportAttributeAccessIssue]
        update_discussion_thread_status,  # pyright: ignore[reportAttributeAccessIssue]
        update_ticket_channel_message,  # pyright: ignore[reportAttributeAccessIssue]
        notify_ticket_deleted,  # pyright: ignore[reportAttributeAccessIssue]
        report_error_to_discord,  # pyright: ignore[reportAttributeAccessIssue]
        report_crash_to_discord,  # pyright: ignore[reportAttributeAccessIssue]
    )

try:
    send_test_notification_dm  # pyright: ignore[reportUnusedExpression]
except NameError:
    def send_test_notification_dm(user_id, message = None) -> tuple[bool, str]:
        return False, "Bot notification module is not loaded."

try:
    report_error_to_discord  # pyright: ignore[reportUnusedExpression]
except NameError:
    def report_error_to_discord(*args, **kwargs) -> bool:
        return False

try:
    report_crash_to_discord  # pyright: ignore[reportUnusedExpression]
except NameError:
    def report_crash_to_discord(*args, **kwargs) -> bool:
        return False

import atexit
import socket
import subprocess

try:
    from server import audit
except ImportError:
    import audit

try:
    from server import core
    from server.core import (
        load_suggestions,
        save_suggestions,
        load_persistent_servers,
        save_persistent_servers,
        safe_dict_items,
        safe_dict_keys,
        safe_float,
        format_demand_value,
        format_total_demand,
        get_server_visibility,
        get_server_player_count,
        ensure_unit_fuel_level,
        get_sc_data,
        build_server_metadata,
        is_exact_job_or_server_id_match,
        lookup_archive_server_date,
        get_archived_server_snapshots,
        format_file_size,
        get_all_archive_days_info,
        convert_ISO_to_secs,
        format_uptime_duration,
        get_server_uptime_seconds,
        is_server_historical,
        get_unit_output_mw,
        calculate_server_points_rate,
        get_historical_cards_base,
        sort_historical_cards,
        build_server_cards,
        build_chart_payload,
        build_global_chart_payload,
        get_public_servers_payload,
        get_github_latest_release,
    )
except ImportError:
    import core
    from core import (
        load_suggestions,
        save_suggestions,
        load_persistent_servers,
        save_persistent_servers,
        safe_dict_items,
        safe_dict_keys,
        safe_float,
        format_demand_value,
        format_total_demand,
        get_server_visibility,
        get_server_player_count,
        ensure_unit_fuel_level,
        get_sc_data,
        build_server_metadata,
        is_exact_job_or_server_id_match,
        lookup_archive_server_date,
        get_archived_server_snapshots,
        format_file_size,
        get_all_archive_days_info,
        convert_ISO_to_secs,
        format_uptime_duration,
        get_server_uptime_seconds,
        is_server_historical,
        get_unit_output_mw,
        calculate_server_points_rate,
        get_historical_cards_base,
        sort_historical_cards,
        build_server_cards,
        build_chart_payload,
        build_global_chart_payload,
        get_public_servers_payload,
        get_github_latest_release,
    )

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
ARCHIVES_DIR = os.path.join(DATA_DIR, "archives")
ARCHIVES_META_FILE = os.path.join(DATA_DIR, "archives_meta.json")
ARCHIVES_INDEX_FILE = os.path.join(DATA_DIR, "archives_index.json")
SUGGESTIONS_FILE = os.path.join(BASE_DIR, "suggestions.json")
CONTACT_MESSAGES_FILE = os.path.join(BASE_DIR, "contact_messages.json")
BANNED_FILE = os.path.join(BASE_DIR, "banned_ips.json")
CRASHES_FILE = os.path.join(BASE_DIR, "crashes.json")
ADMINS_FILE = os.path.join(BASE_DIR, "admins.json")
AUDIT_LOGS_FILE = os.path.join(DATA_DIR, "audit_logs.json")

def _on_audit_log_entry(entry):
    broadcast_update("audit_logs")

audit.register_audit_listener(_on_audit_log_entry)
ENV_FILE = os.path.join(BASE_DIR, ".env")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(ARCHIVES_DIR, exist_ok=True)
load_dotenv(ENV_FILE)
load_dotenv()

import sys
import logging
from logging.handlers import RotatingFileHandler
from logger import CustomConsoleFormatter, PlainTextFormatter

LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "server.log")

log_format = '[%(asctime)s | %(levelname)s | %(name)s]: %(message)s'

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(CustomConsoleFormatter(log_format))

file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=5 * 1024 * 1024,  # 5 MB limit per log file
    backupCount=5,              # 5 backup log files
    encoding='utf-8'
)
file_handler.setFormatter(PlainTextFormatter(log_format))
file_handler.setLevel(logging.INFO)

app = Flask(
    __name__,
    template_folder="templates"
)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.logger.handlers = [stream_handler, file_handler]
app.logger.propagate = False
app.logger.setLevel(logging.INFO)

gunicorn_error_logger = logging.getLogger('gunicorn.error')
if gunicorn_error_logger.handlers:
    gunicorn_error_logger.addHandler(file_handler)

werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.handlers = [stream_handler, file_handler]
werkzeug_logger.setLevel(logging.INFO)

logger = app.logger.getChild("main")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=2, x_proto=1, x_host=1, x_prefix=1)

@app.template_filter("hex_to_int")
def hex_to_int_filter(val, default=3900150):
    if val is None:
        return default
    if isinstance(val, int):
        return val
    try:
        s = str(val).strip().lstrip("#")
        return int(s, 16)
    except Exception:
        return default

@app.template_filter("fmt_score")
def fmt_score_filter(val):
    if val is None:
        return "0"
    try:
        s = f"{float(val):.1f}"
        return s[:-2] if s.endswith(".0") else s
    except Exception:
        return str(val)

def is_turnstile_enabled() -> bool:
    return bool(
        os.environ.get("TURNSTILE_SITE_KEY", "").strip()
        and os.environ.get("TURNSTILE_SECRET_KEY", "").strip()
    )

def is_session_authenticated() -> bool:
    return bool(session.get("admin_logged_in") or session.get("discord_user"))

def get_client_ip() -> str:
    ip = request.remote_addr or "unknown"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    return ip

def extract_turnstile_token(req_json=None) -> str:
    if isinstance(req_json, dict):
        tok = req_json.get("cf-turnstile-response") or req_json.get("turnstile_token")
        if tok:
            return str(tok).strip()
    form_tok = request.form.get("cf-turnstile-response") or request.form.get("turnstile_token")
    if form_tok:
        return str(form_tok).strip()
    hdr_tok = request.headers.get("X-Turnstile-Token")
    return str(hdr_tok).strip() if hdr_tok else ""

def verify_turnstile_token(token: str, remote_ip: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Verify a Cloudflare Turnstile response token when Turnstile is configured."""
    if not is_turnstile_enabled():
        return True, None

    secret = os.environ.get("TURNSTILE_SECRET_KEY", "").strip()
    if not token:
        return False, "CAPTCHA verification required. Please complete the challenge."

    payload = {
        "secret": secret,
        "response": token,
    }
    if remote_ip and remote_ip != "unknown":
        payload["remoteip"] = remote_ip

    try:
        resp = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data=payload,
            timeout=5,
        )
        data = resp.json() if resp.ok else {}
        if data.get("success") is True:
            return True, None
        logger.warning(f"Turnstile verification failed: {data.get('error-codes')}")
        return False, "CAPTCHA verification failed. Please try again."
    except Exception as ex:
        logger.warning(f"Turnstile verification request error: {ex}")
        return False, "CAPTCHA verification service unavailable. Please try again."

@app.context_processor
def inject_turnstile_config():
    enabled = is_turnstile_enabled()
    site_key = os.environ.get("TURNSTILE_SITE_KEY", "").strip() if enabled else ""
    return {
        "turnstile_enabled": enabled,
        "turnstile_site_key": site_key,
        "is_authenticated_user": is_session_authenticated(),
    }

@app.template_filter("fmt_refreshed_date")
def fmt_refreshed_date_filter(val):
    if not val or val == "now":
        dt = datetime.now(timezone.utc)
    elif isinstance(val, (int, float)):
        dt = datetime.fromtimestamp(val, tz=timezone.utc)
    elif isinstance(val, datetime):
        dt = val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    else:
        try:
            s = str(val).strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if not dt.tzinfo:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            dt = datetime.now(timezone.utc)
    dt_utc = dt.astimezone(timezone.utc)
    unix = int(dt_utc.timestamp())
    utc_str = dt_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"{utc_str} (<t:{unix}:R>)"

def _global_threading_excepthook(args):
    try:
        exc_type = args.exc_type
        exc_val = args.exc_value
        exc_tb = args.exc_traceback
        thread_name = args.thread.name if args.thread else "UnknownThread"
        tb_str = "".join(traceback.format_exception(exc_type, exc_val, exc_tb)) if exc_val else ""
        logger.critical(f"[Thread Crash] Unhandled exception in thread {thread_name}: {exc_val}", exc_info=(exc_type, exc_val, exc_tb))
        report_error_to_discord(
            origin=f"Website Background Thread ({thread_name})",
            error=exc_val or "Thread crashed",
            traceback_str=tb_str,
            context_info={"Thread": thread_name},
        )
    except Exception:
        pass
    if _prev_threading_excepthook:
        try:
            _prev_threading_excepthook(args)
        except Exception:
            pass

_prev_threading_excepthook = getattr(threading, "excepthook", None)
if hasattr(threading, "excepthook"):
    threading.excepthook = _global_threading_excepthook

SERVER_START_TIME = time.time()

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

sock = Sock(app)
active_connections = set()

def get_dashboard_payload_data(username=None):
    perms = get_user_permissions(username) if username else {"suggestions": False, "crashes": False, "contact": False, "bans": False, "servers": False}
    
    suggestions = []
    if perms.get("suggestions", False):
        sug_data = load_suggestions()
        raw_sugs = sug_data.get("suggestions", [])
        for s in sorted(raw_sugs, key=lambda x: x.get("timestamp", ""), reverse=True):
            suggestions.append({
                "id": s.get("id"),
                "type": s.get("type", "suggestion"),
                "title": s.get("title", ""),
                "name": s.get("name", "Anonymous"),
                "suggestion": s.get("suggestion", ""),
                "description": s.get("description") or s.get("suggestion", ""),
                "ip": s.get("ip", ""),
                "timestamp": s.get("timestamp", ""),
                "status": s.get("status", "pending"),
                "admin_comment": s.get("admin_comment", ""),
                "comment_by": s.get("comment_by", ""),
                "comment_timestamp": s.get("comment_timestamp", ""),
                "target": s.get("target") or ("server_checker" if s.get("is_server_checker") else "overlay"),
                "is_server_checker": s.get("target") == "server_checker" or bool(s.get("is_server_checker")),
                "hidden": bool(s.get("hidden", False)),
                "anonymous": bool(s.get("anonymous", False)),
                "discord_id": s.get("discord_id") or "",
                "discord_username": s.get("discord_username") or "",
                "discord_avatar": s.get("discord_avatar") or "",
                "messages": s.get("messages", []),
                "messages_count": len(s.get("messages", []))
            })

    banned_ips = {}
    if perms.get("bans", False):
        ban_data = load_banned_ips()
        banned_ips = ban_data.get("banned", {})

    crashes = []
    if perms.get("crashes", False):
        crash_data = load_crashes()
        crashes = sorted(crash_data.get("crashes", []), key=lambda c: c.get("timestamp", ""), reverse=True)

    contact_messages = []
    if perms.get("contact", False):
        contact_data = load_contact_messages()
        contact_messages = sorted(contact_data.get("messages", []), key=lambda m: m.get("timestamp", ""), reverse=True)

    persistent_servers = {}
    server_cards = []
    if perms.get("servers", False):
        persistent_data = load_persistent_servers()
        persistent_servers = persistent_data.get("persistent", {})
        servers_data = get_sc_data("servers.json") or {}
        server_cards = build_server_cards(servers_data)

    active_count = len(server_cards)
    total_count = len(server_cards)
    persistent_count = len(persistent_servers)
    historical_count = 0

    return {
        "suggestions": suggestions,
        "banned_ips": banned_ips,
        "crashes": crashes,
        "contact_messages": contact_messages,
        "servers": server_cards,
        "persistent_servers": persistent_servers,
        "server_counts": {
            "total": total_count,
            "active": active_count,
            "historical": historical_count,
            "persistent": persistent_count
        }
    }

def get_accounts_payload_data():
    admins_data = load_admins()
    admins_list = []
    for admin_key, info in admins_data.get("admins", {}).items():
        discord_id = info.get("discord_id") or (admin_key if admin_key.isdigit() else "")
        admins_list.append({
            "key": admin_key,
            "discord_id": discord_id,
            "username": info.get("username") or admin_key,
            "created_at": info.get("created_at"),
            "permissions": normalize_permissions(info.get("permissions")),
            "notifier": info.get("notifier") or {
                "enabled": False,
                "categories": ["overlay", "point_graph", "server_checker", "general"]
            }
        })
    return {"admins": admins_list}

def get_audit_logs_payload_data():
    return audit.get_audit_summary()

def broadcast_update(data_type):
    for conn in list(active_connections):
        ws = conn[0] if isinstance(conn, tuple) else conn
        uname = conn[1] if isinstance(conn, tuple) else ""
        try:
            if data_type == "dashboard":
                payload = {
                    "type": "dashboard",
                    "data": get_dashboard_payload_data(uname)
                }
            elif data_type == "accounts":
                if uname and not is_root_user(uname):
                    continue
                payload = {
                    "type": "accounts",
                    "data": get_accounts_payload_data()
                }
            elif data_type == "audit_logs":
                if uname and not has_permission(uname, "audit_logs"):
                    continue
                payload = {
                    "type": "audit_logs",
                    "data": get_audit_logs_payload_data()
                }
            else:
                continue
            ws.send(json.dumps(payload))
        except Exception:
            active_connections.discard(conn)

active_ticket_connections = set()

def broadcast_ticket_update(ticket_id: int, new_message: dict, full_messages: list, ticket_discord_id: str|None = None, is_anonymous: bool = False):
    """
    Broadcasts real-time ticket messages to connected web users on tickets.html.
    """
    for conn in list(active_ticket_connections):
        ws = conn[0] if isinstance(conn, tuple) else conn
        user_d_id = conn[1] if isinstance(conn, tuple) else ""
        is_admin_user = conn[2] if isinstance(conn, tuple) else False
        
        can_view = is_admin_user or (user_d_id and ticket_discord_id and str(user_d_id) == str(ticket_discord_id) and not is_anonymous)
        if not can_view:
            continue
            
        try:
            payload = {
                "type": "ticket_message",
                "ticket_id": ticket_id,
                "new_message": new_message,
                "messages": full_messages
            }
            ws.send(json.dumps(payload))
        except Exception:
            active_ticket_connections.discard(conn)

@sock.route('/ws/tickets')
def tickets_ws(ws):
    discord_user = session.get("discord_user") or {}
    user_d_id = str(discord_user.get("id") or "")
    is_admin_user = bool(session.get("admin_logged_in"))
    
    conn_tuple = (ws, user_d_id, is_admin_user)
    active_ticket_connections.add(conn_tuple)
    
    try:
        ws.send(json.dumps({"type": "ready", "connected": True}))
        while True:
            msg = ws.receive()
            if msg is None:
                break
            try:
                data = json.loads(msg)
                if data.get("type") == "ping":
                    ws.send(json.dumps({"type": "pong"}))
            except Exception:
                pass
    except Exception:
        pass
    finally:
        active_ticket_connections.discard(conn_tuple)

@sock.route('/admin/ws')
def admin_ws(ws):
    username = session.get("username") or ""
    if not session.get("admin_logged_in"):
        ws.close(1008)
        return
        
    conn_tuple = (ws, username)
    active_connections.add(conn_tuple)
    
    try:
        initial_payload = {
            "type": "all",
            "dashboard": get_dashboard_payload_data(username),
            "accounts": get_accounts_payload_data() if is_root_user(username) else None,
            "audit_logs": get_audit_logs_payload_data() if has_permission(username, "audit_logs") else None
        }
        ws.send(json.dumps(initial_payload))
    except Exception:
        active_connections.discard(conn_tuple)
        return
        
    try:
        while True:
            message = ws.receive()
            if message is None:
                break
            try:
                data = json.loads(message)
                if data.get("type") == "ping":
                    ws.send(json.dumps({"type": "pong"}))
            except Exception:
                pass
    except Exception:
        pass
    finally:
        active_connections.discard(conn_tuple)

_secret_key = os.environ.get("FLASK_SECRET_KEY")
if not _secret_key:
    _secret_key = secrets.token_hex(32)
    try:
        with open(ENV_FILE, "a", encoding="utf-8") as env_f:
            env_f.write(f"\nFLASK_SECRET_KEY={_secret_key}\n")
        os.environ["FLASK_SECRET_KEY"] = _secret_key
    except Exception:
        pass

app.secret_key = _secret_key
app.permanent_session_lifetime = timedelta(days=30)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax"
)

CURRENT_SESSION_VERSION = 2

@app.before_request
def enforce_session_version():
    has_auth_session = (
        session.get("admin_logged_in")
        or session.get("discord_user")
        or session.get("username")
        or session.get("discord_id")
    )
    if has_auth_session and session.get("session_v") != CURRENT_SESSION_VERSION:
        session.clear()

@app.after_request
def add_security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    ip = request.remote_addr or "unknown"
    protocol = request.environ.get('SERVER_PROTOCOL', 'HTTP/1.1')
    logger.info(f'{ip} - - "{request.method} {request.path} {protocol}" {response.status_code}')
    
    return response

_generated_admin_user = secrets.token_hex(12)
_generated_admin_pass = secrets.token_hex(24)

if not os.environ.get("ADMIN_USERNAME") or not os.environ.get("ADMIN_PASSWORD"):
    import logging
    app.logger.warning(
        "Security Warning: ADMIN_USERNAME or ADMIN_PASSWORD is not set in the environment/dotenv. "
        "A random secure credential has been dynamically generated for this server session."
    )

DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_OAUTH_AUTHORIZE_URL = "https://discord.com/api/oauth2/authorize"
DISCORD_OAUTH_TOKEN_URL = "https://discord.com/api/v10/oauth2/token"

def get_discord_redirect_uri(req):
    custom_uri = os.environ.get("DISCORD_REDIRECT_URI", "").strip()
    if custom_uri:
        return custom_uri
    host_url = get_host_url(req)
    return f"{host_url}/auth/discord/callback"

def get_discord_avatar_url(user_id, avatar_hash):
    if not avatar_hash:
        try:
            default_idx = (int(user_id) >> 22) % 6
        except Exception:
            default_idx = 0
        return f"https://cdn.discordapp.com/embed/avatars/{default_idx}.png"
    ext = "gif" if str(avatar_hash).startswith("a_") else "png"
    return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{ext}"

def get_root_discord_ids() -> list[str]:
    root_env = os.environ.get("ROOT_DISCORD_ID", "").strip()
    if not root_env:
        return []
    return [x.strip() for x in root_env.replace(",", " ").split() if x.strip()]

def get_admin_credentials():
    username = os.environ.get("ADMIN_USERNAME")
    password = os.environ.get("ADMIN_PASSWORD")
    return username or _generated_admin_user, password or _generated_admin_pass

def safe_compare_digest(val_a: Any, val_b: Any) -> bool:
    if val_a is None or val_b is None:
        return False
    try:
        a_bytes = val_a.encode("utf-8") if isinstance(val_a, str) else bytes(val_a)
        b_bytes = val_b.encode("utf-8") if isinstance(val_b, str) else bytes(val_b)
        return secrets.compare_digest(a_bytes, b_bytes)
    except Exception:
        return False

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return f"{binascii.hexlify(salt).decode('utf-8')}:{binascii.hexlify(key).decode('utf-8')}"

def verify_password(stored_password_hash: str, password: str) -> bool:
    try:
        salt_hex, key_hex = stored_password_hash.split(':')
        salt = binascii.unhexlify(salt_hex)
        key = binascii.unhexlify(key_hex)
        new_key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        return safe_compare_digest(key, new_key)
    except Exception:
        return False

def load_admins():
    if not os.path.exists(ADMINS_FILE):
        return {"admins": {}}
    with open(ADMINS_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {"admins": {}}

def save_admins(data):
    with open(ADMINS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def is_root_user(user_identifier: str) -> bool:
    if not user_identifier:
        return False
    ident_str = str(user_identifier).strip()
    
    root_ids = get_root_discord_ids()
    if root_ids and ident_str in root_ids:
        return True
        
    root_user, _ = get_admin_credentials()
    if root_user and safe_compare_digest(ident_str, root_user):
        return True

    if has_request_context():
        try:
            if session.get("admin_logged_in") and session.get("is_root"):
                sess_user = str(session.get("username") or "")
                sess_discord = str(session.get("discord_id") or "")
                if (sess_user and safe_compare_digest(sess_user, ident_str)) or (sess_discord and sess_discord == ident_str):
                    return True
        except Exception:
            pass

    return False

def get_current_audit_actor(username: str | None = None) -> dict:
    uname = username or get_authenticated_user() or (session.get("username") if has_request_context() else None) or "System"
    d_id = (session.get("discord_id") if has_request_context() else None) or ""
    d_user = (session.get("discord_user") if has_request_context() else {}) or {}
    
    avatar_url = d_user.get("avatar_url")
    display_name = d_user.get("global_name") or uname
    
    if not avatar_url and d_id:
        try:
            admins_data = load_admins()
            admin_rec = admins_data.get("admins", {}).get(d_id, {})
            avatar_url = admin_rec.get("avatar_url")
            display_name = admin_rec.get("display_name") or admin_rec.get("username") or display_name
        except Exception:
            pass

    is_root = is_root_user(uname) or (bool(d_id) and is_root_user(d_id))
    return {
        "username": uname,
        "discord_id": d_id,
        "display_name": display_name,
        "avatar_url": avatar_url,
        "is_root": is_root,
    }

def get_client_ip_address() -> str:
    if not has_request_context():
        return "unknown"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"

def log_audit_event(
    action: str,
    category: str,
    description: str,
    target: str | None = None,
    details: dict | None = None,
    username: str | None = None,
    ip: str | None = None,
) -> dict:
    actor = get_current_audit_actor(username)
    client_ip = ip or get_client_ip_address()
    ua = request.headers.get("User-Agent", "") if has_request_context() else ""
    return audit.record_audit_log(
        actor=actor,
        action=action,
        category=category,
        description=description,
        target=target,
        details=details,
        ip=client_ip,
        user_agent=ua,
    )

def is_website_admin_discord_id(discord_id: str | int) -> bool:
    """
    Verifies whether a Discord ID belongs to an administrator registered on the website.
    Checks against ROOT_DISCORD_ID and entries in admins.json (ignoring Discord server roles).
    """
    if not discord_id:
        return False
    d_id = str(discord_id).strip()
    if not d_id:
        return False

    root_ids = get_root_discord_ids()
    if root_ids and d_id in root_ids:
        return True
    if is_root_user(d_id):
        return True

    admins_data = load_admins()
    admins_dict = admins_data.get("admins", {})
    if d_id in admins_dict:
        return True
    for k, v in admins_dict.items():
        if isinstance(v, dict) and str(v.get("discord_id", "")).strip() == d_id:
            return True

    return False

# sections an admin can be given access to in Accounts. All sections default to on when an
# admin account is created or has no saved value for a section; a root admin unticks what
# they don't want that admin to have. Clearing audit logs is a separate, hardcoded
# root-only action and is never gated by the "audit_logs" permission (see api_clear_audit_logs).
LEGACY_PERMISSION_SECTIONS = ["suggestions", "crashes", "contact", "bans", "servers"]
BOT_PERMISSION_SECTIONS = ["dms", "moderation", "automod", "embeds", "autorole", "welcome", "faq", "commands", "errors", "debug", "audit_logs"]
ALL_PERMISSION_SECTIONS = LEGACY_PERMISSION_SECTIONS + BOT_PERMISSION_SECTIONS


def default_permission(section: str) -> bool:
    return True

def normalize_permissions(perms: dict | None) -> dict:
    perms = perms or {}
    return {s: bool(perms.get(s, default_permission(s))) for s in ALL_PERMISSION_SECTIONS}

def get_user_permissions(user_identifier: str) -> dict:
    if not user_identifier:
        return {s: False for s in ALL_PERMISSION_SECTIONS}
    if is_root_user(user_identifier):
        return {s: True for s in ALL_PERMISSION_SECTIONS}
    
    admins_data = load_admins()
    admins_dict = admins_data.get("admins", {})
    admin_info = admins_dict.get(str(user_identifier))
    if not admin_info:
        for k, v in admins_dict.items():
            if v.get("username") == user_identifier or v.get("discord_id") == user_identifier:
                admin_info = v
                break
                
    if not admin_info:
        return {s: False for s in ALL_PERMISSION_SECTIONS}

    return normalize_permissions(admin_info.get("permissions"))

def has_permission(user_identifier: str, section: str) -> bool:
    if not user_identifier:
        return False
    if is_root_user(user_identifier):
        return True
    return bool(get_user_permissions(user_identifier).get(section, False))

def get_admin_notifier_config(user_identifier: str) -> dict:
    admins_data = load_admins()
    admin_info = admins_data.get("admins", {}).get(str(user_identifier))
    if not admin_info:
        for k, v in admins_data.get("admins", {}).items():
            if v.get("username") == user_identifier or v.get("discord_id") == user_identifier:
                admin_info = v
                break
    
    if admin_info and "notifier" in admin_info:
        return admin_info["notifier"]
    
    if is_root_user(user_identifier):
        root_cfg = admins_data.get("root_notifier", {})
        if root_cfg:
            return root_cfg
    
    return {
        "enabled": False,
        "categories": ["overlay", "point_graph", "server_checker", "general"]
    }

def save_admin_notifier_config(user_identifier: str, notifier_config: dict):
    admins_data = load_admins()
    saved = False
    
    admin_info = admins_data.get("admins", {}).get(str(user_identifier))
    if admin_info:
        admin_info["notifier"] = notifier_config
        saved = True
    else:
        for k, v in admins_data.get("admins", {}).items():
            if v.get("username") == user_identifier or v.get("discord_id") == user_identifier:
                v["notifier"] = notifier_config
                saved = True
                break
    
    if is_root_user(user_identifier) or not saved:
        admins_data["root_notifier"] = notifier_config
        discord_id = str(user_identifier)
        username_val = "Root"
        if has_request_context():
            try:
                discord_id = session.get("discord_id") or discord_id
                username_val = session.get("username") or username_val
            except Exception:
                pass
        if discord_id.isdigit():
            if discord_id in admins_data.get("admins", {}):
                admins_data["admins"][discord_id]["notifier"] = notifier_config
            else:
                admins_data.setdefault("admins", {})[discord_id] = {
                    "discord_id": discord_id,
                    "username": username_val,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "permissions": {"suggestions": True, "crashes": True, "contact": True, "bans": True, "servers": True},
                    "notifier": notifier_config
                }
    
    save_admins(admins_data)

def get_authenticated_user():
    if has_request_context():
        try:
            if session.get("admin_logged_in"):
                discord_id = session.get("discord_id")
                username = session.get("username")
                if discord_id and (discord_id in get_root_discord_ids() or is_root_user(discord_id)):
                    return username or discord_id
                if discord_id:
                    admins_data = load_admins()
                    if discord_id in admins_data.get("admins", {}):
                        return username or discord_id
                if username:
                    if is_root_user(username):
                        return username
                    admins_data = load_admins()
                    if username in admins_data.get("admins", {}):
                        return username
                    for k, v in admins_data.get("admins", {}).items():
                        if v.get("username") == username or v.get("discord_id") == username:
                            return username
        except Exception:
            pass

    auth = request.authorization if has_request_context() else None
    if auth and auth.username and auth.password:
        root_user, root_pass = get_admin_credentials()
        is_root_username = safe_compare_digest(auth.username, root_user)
        is_root_password = safe_compare_digest(auth.password, root_pass)
        if is_root_username and is_root_password:
            return auth.username
            
        admins_data = load_admins()
        admin_info = admins_data.get("admins", {}).get(auth.username)
        if admin_info:
            stored_hash = admin_info.get("password_hash")
            if stored_hash and verify_password(stored_hash, auth.password):
                return auth.username
            
    return None

def get_host_url(req):
    scheme = req.headers.get("X-Forwarded-Proto") or req.scheme
    host = req.headers.get("X-Forwarded-Host") or req.headers.get("Host") or req.host
    if scheme and host:
        return f"{scheme}://{host}".rstrip('/')
    return req.host_url.rstrip('/')

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        username = get_authenticated_user()
        if not username:
            if request.path.startswith("/admin/tickets/status") or \
               request.path.startswith("/admin/tickets/comment") or \
               request.path.startswith("/admin/tickets/delete") or \
               request.path.startswith("/admin/tickets/ban") or \
               request.path.startswith("/admin/tickets/unban"):
                return Response(
                    "Unauthorized access - Credentials required",
                    401,
                    {"WWW-Authenticate": 'Basic realm="Admin API Required"'}
                )
            return redirect(f"/admin/login?next={quote(request.path)}")
            
        if request.method in ["POST", "PUT", "DELETE"]:
            is_basic_auth = False
            auth = request.authorization
            if auth and auth.username and auth.password:
                correct_user, correct_pass = get_admin_credentials()
                is_correct_username = safe_compare_digest(auth.username, correct_user)
                is_correct_password = safe_compare_digest(auth.password, correct_pass)
                if is_correct_username and is_correct_password:
                    is_basic_auth = True

            if not is_basic_auth:
                origin = request.headers.get("Origin")
                referer = request.headers.get("Referer")
                host_url = get_host_url(request)
                
                origin_ok = True
                if origin:
                    origin_ok = (origin.rstrip('/') == host_url)
                elif referer:
                    origin_ok = referer.startswith(host_url)
                else:
                    origin_ok = False
                    
                if not origin_ok:
                    return jsonify({"detail": "CSRF verification failed - Same origin required"}), 403
                
        return f(username, *args, **kwargs)
    return decorated

def admin_panel_identity(username: str) -> dict:
    """Who is using the admin panel: shown in the panel and stored as the author of what they change."""
    discord_id = ""
    name = username
    picture = None
    if has_request_context():
        discord_id = str(session.get("discord_id") or "")
        discord_user = session.get("discord_user") or {}
        name = discord_user.get("global_name") or session.get("username") or username
        picture = discord_user.get("avatar_url")
    if discord_id and not picture:
        info = load_admins().get("admins", {}).get(discord_id) or {}
        picture = info.get("avatar_url")
        name = info.get("display_name") or name
    return {"id": discord_id or str(username), "discord_id": discord_id or None, "name": name, "picture": picture}

def get_next_ticket_id(data: dict) -> int:
    """
    Computes the next unique ticket ID ensuring IDs never overlap,
    even if tickets have been deleted.
    """
    used_ids = set()
    for s in data.get("suggestions", []):
        if isinstance(s.get("id"), int):
            used_ids.add(s["id"])

    for d in data.get("deleted_tickets", []):
        if isinstance(d, dict) and isinstance(d.get("id"), int):
            used_ids.add(d["id"])
        elif isinstance(d, int):
            used_ids.add(d)

    for d_id in data.get("deleted_ticket_ids", []):
        if isinstance(d_id, int):
            used_ids.add(d_id)

    last_id = data.get("last_ticket_id", 0)
    highest = max(used_ids) if used_ids else 0
    new_id = max(highest, last_id) + 1
    data["last_ticket_id"] = new_id
    return new_id

try:
    start_bot_thread(
        load_suggestions=load_suggestions,
        save_suggestions=save_suggestions,
        load_admins=load_admins,
        is_website_admin=is_website_admin_discord_id,
        broadcast_dashboard=lambda: broadcast_update("dashboard"),
        broadcast_ticket_update=broadcast_ticket_update,
        get_servers_data=lambda public_only=True: get_public_servers_payload(public_only=public_only),
    )
except Exception as e:
    logger.warning(f"[Discord Bot] Failed to initialize bot from bot.py: {e}")

try:
    import bot_features
    import admin_features

    bot_features.configure(
        is_admin=is_website_admin_discord_id,
        is_owner=lambda d_id: bool(d_id) and str(d_id) in get_root_discord_ids(),
        site_url=os.environ.get("SERVER_BASE_URL", "").strip() or None,
    )
    admin_features.init_app(
        app,
        get_user=get_authenticated_user,
        has_permission=has_permission,
        is_root=is_root_user,
        identity=admin_panel_identity,
        host_url=lambda: get_host_url(request),
        load_admins=load_admins,
        report_error=report_error_to_discord,
        alerts_configured=lambda: bool(os.environ.get("DISCORD_BOT_TOKEN", "").strip()),
        log_audit=lambda u, act, cat, desc, target=None, details=None: log_audit_event(
            action=act, category=cat, description=desc, target=target, details=details, username=u
        ),
    )
except Exception as e:
    logger.error(f"[Admin Panel] Failed to load the Discord bot sections: {e}", exc_info=True)

def load_contact_messages():
    if not os.path.exists(CONTACT_MESSAGES_FILE):
        return {"messages": []}
    with open(CONTACT_MESSAGES_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {"messages": []}

def save_contact_messages(data):
    with open(CONTACT_MESSAGES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def get_public_suggestions():
    return get_public_tickets()

def get_public_tickets():
    is_admin = False
    current_discord_id = None
    if has_request_context():
        try:
            is_admin = bool(session.get("admin_logged_in"))
            discord_user = session.get("discord_user") or {}
            current_discord_id = str(discord_user.get("id") or "")
        except Exception:
            pass
    return core.get_public_tickets(is_admin=is_admin, current_discord_id=current_discord_id)

def load_crashes():
    if not os.path.exists(CRASHES_FILE):
        return {"crashes": []}
    with open(CRASHES_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {"crashes": []}

def save_crashes(data):
    with open(CRASHES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def load_banned_ips():
    if not os.path.exists(BANNED_FILE):
        return {"banned": {}}
    with open(BANNED_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {"banned": {}}

def save_banned_ips(data):
    with open(BANNED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def is_ip_banned(ip: str) -> bool:
    if ip == "unknown":
        return False
    data = load_banned_ips()
    banned = data.get("banned", {})
    if ip not in banned:
        return False
    
    ban_info = banned[ip]
    expires_at_str = ban_info.get("expires_at")
    if expires_at_str is None:
        return True
    
    try:
        expires_at = datetime.fromisoformat(expires_at_str)
        if datetime.now(timezone.utc) > expires_at:
            del banned[ip]
            save_banned_ips(data)
            return False
        return True
    except Exception:
        return True

class SuggestionPayload(BaseModel):
    name: str = Field(default="", max_length=50)
    suggestion: str = Field(default="", max_length=4000)
    description: str = Field(default="", max_length=4000)
    title: str = Field(default="", max_length=150)
    type: str = Field(default="suggestion", max_length=50)
    anonymous: bool = Field(default=False)
    target: str = Field(default="overlay", max_length=50)
    is_server_checker: bool = Field(default=False)

class TicketPayload(BaseModel):
    type: str = Field(default="suggestion", max_length=50)
    title: str = Field(default="", max_length=150)
    suggestion: str = Field(default="", max_length=4000)
    description: str = Field(default="", max_length=4000)
    name: str = Field(default="", max_length=50)
    anonymous: bool = Field(default=False)
    target: str = Field(default="overlay", max_length=50)
    is_server_checker: bool = Field(default=False)

class TicketMessagePayload(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)

class CrashPayload(BaseModel):
    version: str = Field(..., max_length=20)
    traceback: str = Field(..., max_length=20000)
    log_data: str = Field(default="", max_length=50000)
    os_info: str = Field(default="Unknown OS", max_length=100)

class DeleteCrashPayload(BaseModel):
    id: int | None = None
    ids: list[int] | None = None

class CrashStatusPayload(BaseModel):
    id: int | None = None
    ids: list[int] | None = None
    status: str

class StatusUpdatePayload(BaseModel):
    id: int
    status: str

class CommentPayload(BaseModel):
    id: int
    comment: str = Field(default="", max_length=2000)

class DeleteSuggestionPayload(BaseModel):
    id: int

class BanPayload(BaseModel):
    ip: str
    duration_minutes: int | None = None  # None for permanent
    reason: str

class UnbanPayload(BaseModel):
    ip: str

class ServerPersistPayload(BaseModel):
    job_id: str
    persistent: bool
    note: str = ""

@app.route("/", methods=["GET"])
def root():
    release = get_github_latest_release()
    return render_template(
        "index.html",
        latest_version=release.get("version", "2.0.5"),
        release_date=release.get("release_date", "2026-09-23"),
        release_notes=release.get("notes", "No release notes available.")
    )

@app.route("/favicon.png")
def favicon_png():
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "favicon.png",
        mimetype="image/png"
    )

@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon"
    )

@app.route("/robots.txt", methods=["GET"])
def robots_txt():
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /api/admin/\n"
        "Disallow: /auth/\n\n"
        "User-agent: Googlebot\n"
        "Allow: /\n\n"
        "Sitemap: https://rbwr.hotment.dev/sitemap.xml\n"
    )
    return Response(body, mimetype="text/plain; charset=utf-8")

def _get_file_lastmod_iso(*paths: str) -> str:
    latest_mtime = 0.0
    for p in paths:
        if not p or not os.path.exists(p):
            continue
        try:
            if os.path.isdir(p):
                for entry in os.scandir(p):
                    if entry.is_file():
                        mt = entry.stat().st_mtime
                        if mt > latest_mtime:
                            latest_mtime = mt
            else:
                mt = os.path.getmtime(p)
                if mt > latest_mtime:
                    latest_mtime = mt
        except Exception:
            pass
    if latest_mtime > 0:
        return datetime.fromtimestamp(latest_mtime, tz=timezone.utc).strftime("%Y-%m-%d")
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

@app.route("/sitemap.xml", methods=["GET"])
def sitemap_xml():
    base_url = "https://rbwr.hotment.dev"

    pages = [
        {
            "loc": f"{base_url}/",
            "lastmod": _get_file_lastmod_iso(
                os.path.join(TEMPLATES_DIR, "index.html"),
                os.path.join(TEMPLATES_DIR, "base.html"),
            ),
        },
        {
            "loc": f"{base_url}/calculator",
            "lastmod": _get_file_lastmod_iso(os.path.join(TEMPLATES_DIR, "calculator.html")),
        },
        {
            "loc": f"{base_url}/points",
            "lastmod": _get_file_lastmod_iso(os.path.join(TEMPLATES_DIR, "points.html")),
        },
        {
            "loc": f"{base_url}/servers",
            "lastmod": _get_file_lastmod_iso(
                os.path.join(TEMPLATES_DIR, "servers.html"),
                os.path.join(DATA_DIR, "servers.json"),
            ),
        },
        {
            "loc": f"{base_url}/operator-tablet",
            "lastmod": _get_file_lastmod_iso(os.path.join(TEMPLATES_DIR, "operator_tablet.html")),
        },
        {
            "loc": f"{base_url}/points-graph",
            "lastmod": _get_file_lastmod_iso(os.path.join(TEMPLATES_DIR, "local_viewer.html")),
        },
        {
            "loc": f"{base_url}/archives",
            "lastmod": _get_file_lastmod_iso(
                os.path.join(TEMPLATES_DIR, "archives.html"),
                ARCHIVES_DIR,
            ),
        },
        {
            "loc": f"{base_url}/tickets",
            "lastmod": _get_file_lastmod_iso(
                os.path.join(TEMPLATES_DIR, "tickets.html"),
                SUGGESTIONS_FILE,
            ),
        },
        {
            "loc": f"{base_url}/contact",
            "lastmod": _get_file_lastmod_iso(os.path.join(TEMPLATES_DIR, "contact.html")),
        },
        {
            "loc": f"{base_url}/privacy",
            "lastmod": _get_file_lastmod_iso(os.path.join(TEMPLATES_DIR, "privacy.html")),
        },
        {
            "loc": f"{base_url}/credits",
            "lastmod": _get_file_lastmod_iso(os.path.join(TEMPLATES_DIR, "credits.html")),
        },
    ]

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for p in pages:
        xml_lines.append("  <url>")
        xml_lines.append(f"    <loc>{p['loc']}</loc>")
        xml_lines.append(f"    <lastmod>{p['lastmod']}</lastmod>")
        xml_lines.append("  </url>")
    xml_lines.append("</urlset>")

    xml_content = "\n".join(xml_lines).replace("\u00a0", " ")
    return Response(xml_content, mimetype="application/xml; charset=utf-8")

@app.route("/calculator", methods=["GET"])
def calculator_page():
    return render_template("calculator.html")

@app.route("/points", methods=["GET"])
def points_page():
    return render_template("points.html")

@app.route("/points-graph", methods=["GET"])
def local_viewer_page():
    return render_template("local_viewer.html")

@app.route("/operator-tablet", methods=["GET"])
def operator_tablet_page():
    return render_template("operator_tablet.html")

@app.route("/privacy", methods=["GET"])
def privacy_page():
    privacy_file = os.path.join(TEMPLATES_DIR, "privacy.html")
    if os.path.exists(privacy_file):
        mtime = os.path.getmtime(privacy_file)
        last_updated = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%B %d, %Y")
    else:
        last_updated = datetime.now(timezone.utc).strftime("%B %d, %Y")
    return render_template("privacy.html", last_updated=last_updated)

@app.route("/contact", methods=["GET"])
def contact_page():
    return render_template("contact.html")

@app.route("/credits", methods=["GET"])
def credits_page():
    return render_template("credits.html")

@app.errorhandler(404)
def page_not_found(e):
    if request.path.startswith("/api/") or request.headers.get("Accept") == "application/json":
        return jsonify({"detail": "Not found", "status": 404}), 404
    return render_template("404.html"), 404

@app.errorhandler(Exception)
def handle_unhandled_exception(e):
    if isinstance(e, HTTPException) and e.code and e.code < 500:
        return e

    req_method = getattr(request, "method", "UNKNOWN")
    req_path = getattr(request, "path", "UNKNOWN")
    req_url = getattr(request, "url", "UNKNOWN")

    client_ip = getattr(request, "remote_addr", "unknown") or "unknown"
    forwarded = request.headers.get("X-Forwarded-For") if hasattr(request, "headers") else None
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    user_info = "Anonymous"
    try:
        sess_discord = session.get("discord_user")
        sess_user = session.get("username") or session.get("user")
        if sess_discord and isinstance(sess_discord, dict):
            user_info = f"@{sess_discord.get('username', 'unknown')} (ID: {sess_discord.get('id', 'unknown')})"
        elif sess_user:
            user_info = f"Admin: {sess_user}"
    except Exception:
        pass

    context_info = {
        "Request": f"{req_method} {req_path}",
        "URL": req_url[:200],
        "Client IP": client_ip,
        "User": user_info,
        "User-Agent": request.headers.get("User-Agent", "Unknown")[:120] if hasattr(request, "headers") else "Unknown",
    }

    try:
        if hasattr(request, "args") and request.args:
            sanitized_args = {}
            for k, v in request.args.items():
                if any(s in k.lower() for s in ["pass", "token", "secret", "auth", "key", "cookie"]):
                    sanitized_args[k] = "[REDACTED]"
                else:
                    sanitized_args[k] = v[:100] if isinstance(v, str) else v
            context_info["Query Params"] = json.dumps(sanitized_args)[:300]
    except Exception:
        pass

    tb_str = traceback.format_exc()
    logger.error(f"[Website Exception] {req_method} {req_path} encountered unhandled exception: {e}", exc_info=True)

    try:
        report_error_to_discord(
            origin=f"Website ({req_method} {req_path})",
            error=e,
            traceback_str=tb_str,
            context_info=context_info,
        )
    except Exception as dispatch_err:
        logger.error(f"[Website Exception] Failed to send error alert to Discord: {dispatch_err}")

    if req_path.startswith("/api/") or (hasattr(request, "headers") and request.headers.get("Accept") == "application/json"):
        return jsonify({"detail": "Internal server error", "status": 500}), 500

    try:
        return render_template("500.html"), 500
    except Exception:
        return (
            "<!DOCTYPE html><html><head><title>500 Internal Server Error</title></head>"
            "<body style='font-family:sans-serif;background:#0f172a;color:#f8fafc;padding:40px;text-align:center;'>"
            "<h1>500 - Internal Server Error</h1><p>An unexpected error occurred. The incident has been recorded and reported.</p>"
            "<a href='/' style='color:#38bdf8;'>Return to Home</a></body></html>"
        ), 500

@app.route("/contact", methods=["POST"])
def submit_contact_message():
    ip = request.remote_addr or "unknown"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()

    if is_ip_banned(ip):
        return jsonify({"detail": "Access restricted. Your IP is banned."}), 403

    ip_hash = hashlib.sha256(ip.encode('utf-8')).hexdigest()
    ban_data = load_banned_ips()
    if ip_hash in ban_data.get("banned", {}):
        return jsonify({"detail": "Access restricted."}), 403

    payload = request.get_json() or {}
    if not isinstance(payload, dict):
        return jsonify({"detail": "Invalid request body."}), 400

    if not is_session_authenticated():
        captcha_ok, captcha_err = verify_turnstile_token(extract_turnstile_token(payload), ip)
        if not captcha_ok:
            return jsonify({"detail": captcha_err}), 400

    message_text = str(payload.get("message", "")).strip()
    if not message_text:
        return jsonify({"detail": "Message body cannot be empty."}), 400

    if len(message_text) > 2000:
        return jsonify({"detail": "Message text exceeds maximum length of 2000 characters."}), 400

    name = str(payload.get("name", "")).strip() or "Anonymous"
    contact_info = str(payload.get("contact_info", "")).strip() or "N/A"
    subject = str(payload.get("subject", "")).strip() or "General Inquiry"

    contact_data = load_contact_messages()
    messages = contact_data.get("messages", [])
    now_dt = datetime.now(timezone.utc)
    one_hour_ago = now_dt - timedelta(hours=1)
    
    recent_count = 0
    for m in messages:
        if m.get("ip_hash") == ip_hash:
            try:
                m_dt = datetime.fromisoformat(m.get("timestamp"))
                if m_dt > one_hour_ago:
                    recent_count += 1
            except Exception:
                pass
                
    if recent_count >= 5:
        return jsonify({"detail": "Rate limit exceeded. Please wait before sending another message."}), 429

    msg_id = secrets.token_hex(8)
    new_msg = {
        "id": msg_id,
        "timestamp": now_dt.isoformat(),
        "name": name[:60],
        "contact_info": contact_info[:100],
        "subject": subject[:50],
        "message": message_text,
        "ip_hash": ip_hash,
        "read": False
    }

    messages.append(new_msg)
    save_contact_messages({"messages": messages})
    broadcast_update("dashboard")

    return jsonify({"success": True, "id": msg_id})

# ==============================================================================
# RBWR Server Checker Background Worker (logic lives in server/core.py)
# ==============================================================================

def server_checker_worker():
    time.sleep(2)
    try:
        core.compress_finalized_archives()
    except Exception as e:
        logger.error(f"Error in initial archive compression: {e}")
    while True:
        try:
            core.pull_server_checker_data()
        except Exception as e:
            logger.error(f"Error in server_checker_worker: {e}")
        time.sleep(60)

_sc_worker_thread = None
_sc_worker_started = False
_sc_worker_lock = threading.Lock()

def start_server_checker_worker():
    global _sc_worker_started, _sc_worker_thread
    with _sc_worker_lock:
        if _sc_worker_started:
            return

        if os.environ.get("DISABLE_SC_WORKER") == "1":
            return
        if "unittest" in sys.modules:
            return

        is_reloader_active = os.environ.get("WERKZEUG_RUN_MAIN") is not None
        if is_reloader_active and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
            return

        _sc_worker_started = True
        _sc_worker_thread = threading.Thread(target=server_checker_worker, daemon=True, name="SCWorkerThread")
        _sc_worker_thread.start()
        logger.info("Started background server checker worker thread.")

@app.before_request
def ensure_server_checker_worker():
    if not _sc_worker_started:
        start_server_checker_worker()

@app.route("/servers", methods=["GET"])
def servers_page():
    query = (request.args.get("q") or request.args.get("search") or request.args.get("jobId") or "").strip()
    servers_data = get_sc_data("servers.json")
    global_data = get_sc_data("global.json")
    global_payload = build_global_chart_payload(global_data)
    server_cards = build_server_cards(servers_data, search_query=query)
    
    return render_template(
        "servers.html",
        servers=server_cards,
        charts=global_payload.get("charts", [])
    )

@app.route("/servers/", methods=["GET"])
def servers_trailing_slash_redirect():
    qs = f"?{request.query_string.decode('utf-8')}" if request.query_string else ""
    return redirect(f"/servers{qs}")

@app.route("/servers/<job_id>", methods=["GET"])
def server_detail_page(job_id):
    servers_data = get_sc_data("servers.json")
    snapshots = servers_data.get(job_id) if servers_data else None
    is_archived = False

    if snapshots is None:
        if core._sc_latest_data:
            for s in core._sc_latest_data.get('data', {}).get('servers', []):
                if s.get('jobId') == job_id:
                    snapshots = {s.get('lastHeartbeat', datetime.now(timezone.utc).isoformat()): s.get('state', {})}
                    break
                    
    if snapshots is None:
        matched_jid, archived_snaps = get_archived_server_snapshots(job_id)
        if matched_jid and archived_snaps:
            job_id = matched_jid
            snapshots = archived_snaps
            is_archived = True

    if snapshots is None:
        return redirect("/servers")

    try:
        payload = build_chart_payload(job_id, snapshots)
    except Exception as e:
        logger.error(f"Error building chart payload for {job_id}: {e}")
        return redirect("/servers")

    server = None
    if core._sc_latest_data and not is_archived:
        for s in core._sc_latest_data.get('data', {}).get('servers', []):
            if s.get('jobId') == job_id:
                server = s
                break

    persistent_data = load_persistent_servers()
    is_persistent = job_id in persistent_data.get("persistent", {})

    info = core._sc_public_servers_info.get(job_id, {})
    valid_detail_ts = [k for k in safe_dict_keys(snapshots) if not k.startswith('_')] if isinstance(snapshots, dict) else []
    latest_ts = max(valid_detail_ts) if valid_detail_ts else None
    latest_state = snapshots.get(latest_ts, {}) if latest_ts else {}
    age_sec = convert_ISO_to_secs(latest_ts) if latest_ts else 0

    is_private = get_server_visibility(job_id, snapshots, latest_state, is_active=(age_sec <= 600 and not is_archived))
    is_historical = is_server_historical(job_id, snapshots, latest_state, is_private=is_private, age_sec=age_sec) or is_archived

    meta = (snapshots.get("_meta") or core._sc_server_meta.get(job_id, {})) if isinstance(snapshots, dict) else (core._sc_server_meta.get(job_id, {}) or {})
    private_server_owner_id = (
        meta.get("privateServerOwnerId")
        or (latest_state.get("privateServerOwnerId") if isinstance(latest_state, dict) else None)
        or (server.get("privateServerOwnerId") if isinstance(server, dict) else None)
    ) if is_private else None

    if is_private:
        player_count = None
        max_players = None
    else:
        player_count = get_server_player_count(job_id, snapshots, latest_state, is_private=False)
        max_players = info.get("maxPlayers", 12) if info else 12
    is_admin = bool(get_authenticated_user())

    first_ts = min(valid_detail_ts) if valid_detail_ts else None
    uptime_sec = get_server_uptime_seconds(snapshots, is_historical, age_sec)
    uptime_str = format_uptime_duration(uptime_sec)
    server_top_score = calculate_server_top_score(snapshots)

    if not server:
        latest_st = latest_state if isinstance(latest_state, dict) else {}
        unit1_st = latest_st.get("Unit1", {})
        if not isinstance(unit1_st, dict):
            unit1_st = {}
        unit2_st = latest_st.get("Unit2", {})
        if not isinstance(unit2_st, dict):
            unit2_st = {}

        raw_u1_dem = unit1_st.get("DemandU1") if unit1_st.get("DemandU1") is not None else unit1_st.get("NextDemandU1")
        raw_u2_dem = unit2_st.get("DemandU2") if unit2_st.get("DemandU2") is not None else unit2_st.get("NextDemandU2")
        u1_dem = safe_float(raw_u1_dem, None)
        u2_dem = safe_float(raw_u2_dem, None)

        raw_next1 = unit1_st.get("NextDemandU1") if unit1_st.get("NextDemandU1") is not None else raw_u1_dem
        raw_next2 = unit2_st.get("NextDemandU2") if unit2_st.get("NextDemandU2") is not None else raw_u2_dem
        dmand_next1 = safe_float(raw_next1, None)
        dmand_next2 = safe_float(raw_next2, None)

        if dmand_next1 is not None and dmand_next2 is not None:
            next_demand = round(dmand_next1 + dmand_next2, 2)
        elif dmand_next1 is not None:
            next_demand = round(dmand_next1, 2)
        elif dmand_next2 is not None:
            next_demand = round(dmand_next2, 2)
        else:
            next_demand = None

        pts_info = calculate_server_points_rate(unit1_st, unit2_st, job_id=job_id, latest_state=latest_st)

        summary = {
            "is_private": is_private,
            "privateServerOwnerId": private_server_owner_id,
            "is_persistent": is_persistent,
            "is_historical": is_historical,
            "is_archived": is_archived,
            "is_admin": is_admin,
            "player_count": player_count,
            "max_players": max_players,
            "first_timestamp": first_ts,
            "uptime_seconds": uptime_sec,
            "uptime_str": uptime_str,
            "top_score": server_top_score,
            "time_to_next_demand": max(0.0, safe_float(unit1_st.get("Demand Time Left", 0), 0.0)),
            "next_demand": next_demand if next_demand is not None else "N/A",
            "next_demand_formatted": format_total_demand(raw_next1, raw_next2),
            "dmandU1": u1_dem if u1_dem is not None else "N/A",
            "dmandU2": u2_dem if u2_dem is not None else "N/A",
            "dmand_next1": dmand_next1 if dmand_next1 is not None else "N/A",
            "dmand_next2": dmand_next2 if dmand_next2 is not None else "N/A",
            "dmandU1_formatted": format_demand_value(raw_u1_dem),
            "dmandU2_formatted": format_demand_value(raw_u2_dem),
            "u1_running": pts_info["u1_running"],
            "u2_running": pts_info["u2_running"],
            "u1_aprm": pts_info["u1_aprm"],
            "u2_aprm": pts_info["u2_aprm"],
            "u1_output_mw": round(get_unit_output_mw(unit1_st), 1),
            "u2_output_mw": round(get_unit_output_mw(unit2_st), 1),
            "points_rate": pts_info["points_rate"],
            "points_rate_str": pts_info["points_rate_str"],
            "u1_rate": pts_info["u1_rate"],
            "u2_rate": pts_info["u2_rate"],
            "demand_rate": pts_info["demand_rate"],
            "last_refreshed": latest_ts or datetime.now(timezone.utc).isoformat(),
        }
        return render_template("server_detail.html", **payload, **summary)

    unit1_state = server.get('state', {}).get('Unit1', {})
    if not isinstance(unit1_state, dict):
        unit1_state = {}
    unit2_state = server.get('state', {}).get('Unit2', {})
    if not isinstance(unit2_state, dict):
        unit2_state = {}
    server_misc = (server.get('state', {}).get('Misc') or {}) if isinstance(server.get('state'), dict) else {}
    server_tot_pps = server_misc.get('Total points/second')
    pts_info = calculate_server_points_rate(unit1_state, unit2_state, job_id=job_id, total_pps=server_tot_pps, latest_state=server.get('state', {}))

    dmand_left_data = safe_float(unit1_state.get('Demand Time Left', 0), 0.0)
    raw_u1_live = unit1_state.get('DemandU1')
    raw_u2_live = unit2_state.get('DemandU2')
    u1_live_dem = safe_float(raw_u1_live, None)
    u2_live_dem = safe_float(raw_u2_live, None)

    raw_next1 = unit1_state.get('NextDemandU1') if unit1_state.get('NextDemandU1') is not None else raw_u1_live
    raw_next2 = unit2_state.get('NextDemandU2') if unit2_state.get('NextDemandU2') is not None else raw_u2_live
    dmand_next1 = safe_float(raw_next1, None)
    dmand_next2 = safe_float(raw_next2, None)

    if dmand_next1 is not None and dmand_next2 is not None:
        next_demand = round(dmand_next1 + dmand_next2, 2)
    elif dmand_next1 is not None:
        next_demand = round(dmand_next1, 2)
    elif dmand_next2 is not None:
        next_demand = round(dmand_next2, 2)
    else:
        next_demand = None

    try:
        hb_ts = server.get('lastHeartbeat', '')
        elapsed = time.time() - datetime.fromisoformat(hb_ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        elapsed = 0

    dmand_left = max(0.0, dmand_left_data - elapsed)

    summary = {
        "is_private": is_private,
        "privateServerOwnerId": private_server_owner_id,
        "is_persistent": is_persistent,
        "is_historical": is_historical,
        "is_archived": is_archived,
        "is_admin": is_admin,
        "player_count": player_count,
        "max_players": max_players,
        "first_timestamp": first_ts,
        "uptime_seconds": uptime_sec,
        "uptime_str": uptime_str,
        "top_score": server_top_score,
        "time_to_next_demand": dmand_left,
        "next_demand": next_demand if next_demand is not None else "N/A",
        "next_demand_formatted": format_total_demand(raw_next1, raw_next2),
        "dmandU1": u1_live_dem if u1_live_dem is not None else "N/A",
        "dmandU2": u2_live_dem if u2_live_dem is not None else "N/A",
        "dmand_next1": dmand_next1 if dmand_next1 is not None else "N/A",
        "dmand_next2": dmand_next2 if dmand_next2 is not None else "N/A",
        "dmandU1_formatted": format_demand_value(raw_u1_live),
        "dmandU2_formatted": format_demand_value(raw_u2_live),
        "u1_running": pts_info["u1_running"],
        "u2_running": pts_info["u2_running"],
        "u1_aprm": pts_info["u1_aprm"],
        "u2_aprm": pts_info["u2_aprm"],
        "u1_output_mw": round(get_unit_output_mw(unit1_state), 1),
        "u2_output_mw": round(get_unit_output_mw(unit2_state), 1),
        "points_rate": pts_info["points_rate"],
        "points_rate_str": pts_info["points_rate_str"],
        "u1_rate": pts_info["u1_rate"],
        "u2_rate": pts_info["u2_rate"],
        "demand_rate": pts_info["demand_rate"],
        "last_refreshed": server.get('lastHeartbeat') or latest_ts or datetime.now(timezone.utc).isoformat(),
    }

    return render_template("server_detail.html", **payload, **summary)

@app.route("/servers/cards/active", methods=["GET"])
def get_active_servers_cards():
    query = (request.args.get("q") or request.args.get("search") or request.args.get("jobId") or "").strip()
    servers_data = get_sc_data("servers.json") or {}
    global_data = get_sc_data("global.json") or {}
    global_payload = build_global_chart_payload(global_data)
    server_cards = build_server_cards(servers_data, search_query=query)

    cards_html = "".join(
        render_template("_server_card.html", server=c)
        for c in server_cards
    )

    return jsonify({
        "success": True,
        "total": len(server_cards),
        "cards_html": cards_html,
        "charts": global_payload.get("charts", [])
    })

@app.route("/servers/cards/lookup", methods=["GET"])
def lookup_server_card():
    query = (request.args.get("q") or request.args.get("search") or request.args.get("jobId") or "").strip()
    if not query:
        return jsonify({"success": True, "found": False, "message": "Query parameter 'q' is required."})

    servers_data = get_sc_data("servers.json") or {}
    matched_cards = build_server_cards(servers_data, search_query=query)
    target_card = None
    for card in matched_cards:
        if is_exact_job_or_server_id_match(query, card.get("job_id", "")):
            target_card = card
            break

    if not target_card:
        archived_jid, archived_snaps = get_archived_server_snapshots(query)
        if archived_jid and archived_snaps:
            archived_cards = build_server_cards({archived_jid: archived_snaps}, search_query=query, is_archived=True)
            if archived_cards:
                target_card = archived_cards[0]

    if not target_card:
        return jsonify({"success": True, "found": False})

    card_html = render_template("_server_card.html", server=target_card)
    return jsonify({
        "success": True,
        "found": True,
        "server": target_card,
        "card_html": card_html
    })

@app.route("/servers/cards/historical", methods=["GET"])
def get_historical_servers_cards():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 21, type=int)
    if per_page <= 0 or per_page > 100:
        per_page = 21
    if page <= 0:
        page = 1

    query = (request.args.get("q") or request.args.get("search") or request.args.get("jobId") or "").strip().lower()

    servers_data = get_sc_data("servers.json")
    if not servers_data:
        return jsonify({
            "success": True,
            "servers": [],
            "total": 0,
            "page": page,
            "per_page": per_page,
            "total_pages": 0,
            "cards_html": ""
        })

    persistent_data = load_persistent_servers()
    persistent_ids = set(persistent_data.get("persistent", {}).keys())

    base_cards = get_historical_cards_base(servers_data, persistent_ids)

    if query:
        clean_q = query.replace("-", "")
        historical_cards = []
        for c in base_cards:
            job_id = c.get("job_id", "")
            short_id = c.get("short_id", "")
            clean_jid = job_id.lower().replace("-", "")
            clean_sid = short_id.lower().replace("-", "")
            matches = (
                query in job_id.lower() or
                (short_id and query in short_id.lower()) or
                (clean_q and clean_q in clean_jid) or
                (clean_sid and clean_q in clean_sid) or
                is_exact_job_or_server_id_match(query, job_id)
            )
            if matches:
                historical_cards.append(c)
    else:
        historical_cards = list(base_cards)

    sort_option = request.args.get("sort", "top_servers").strip().lower()
    sort_historical_cards(historical_cards, sort_option)

    total = len(historical_cards)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    if page > total_pages:
        page = total_pages

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_cards = historical_cards[start_idx:end_idx]

    cards_html = "".join(
        render_template("_server_card.html", server=c)
        for c in page_cards
    )

    return jsonify({
        "success": True,
        "servers": page_cards,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "cards_html": cards_html
    })

@app.route("/archives", methods=["GET"])
def browse_archives_page():
    days_list, summary_stats = get_all_archive_days_info()
    return render_template("archives.html", days=days_list, stats=summary_stats)

@app.route("/archives/", methods=["GET"])
def archives_trailing_slash_redirect():
    qs = f"?{request.query_string.decode('utf-8')}" if request.query_string else ""
    return redirect(f"/archives{qs}")

@app.route("/archives/<date_str>", methods=["GET"])
def view_archive_day_page(date_str):
    date_str = date_str.strip()
    gz_path = os.path.join(ARCHIVES_DIR, f"servers_{date_str}.json.gz")
    json_path = os.path.join(ARCHIVES_DIR, f"servers_{date_str}.json")

    target_rel = None
    is_compressed = False
    filename = None

    if os.path.exists(gz_path):
        target_rel = os.path.join("archives", f"servers_{date_str}.json.gz")
        is_compressed = True
        filename = f"servers_{date_str}.json.gz"
    elif os.path.exists(json_path):
        target_rel = os.path.join("archives", f"servers_{date_str}.json")
        is_compressed = False
        filename = f"servers_{date_str}.json"
    else:
        return redirect("/archives")

    day_data = get_sc_data(target_rel)
    if not isinstance(day_data, dict):
        return redirect("/archives")

    full_path = os.path.join(ARCHIVES_DIR, filename)
    size_bytes = os.path.getsize(full_path) if os.path.exists(full_path) else 0

    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        date_formatted = dt.strftime("%B %d, %Y")
        day_of_week = dt.strftime("%A")
    except Exception:
        date_formatted = date_str
        day_of_week = ""

    server_cards = build_server_cards(day_data, is_archived=True, exact_search_only=False)
    total_snaps = sum(c.get("snapshot_count", 0) for c in server_cards)

    stats = {
        "date": date_str,
        "date_formatted": date_formatted,
        "day_of_week": day_of_week,
        "filename": filename,
        "is_compressed": is_compressed,
        "size_str": format_file_size(size_bytes),
        "total_servers": len(server_cards),
        "total_snapshots": total_snaps
    }

    return render_template(
        "archive_detail.html",
        date=date_str,
        date_formatted=date_formatted,
        day_of_week=day_of_week,
        servers=server_cards,
        stats=stats
    )

@app.route("/tickets", methods=["GET", "POST"])
def tickets_route():
    if request.method == "POST":
        return submit_ticket()
    
    if request.args.get("format") == "json" or request.headers.get("Accept") == "application/json":
        return jsonify({"tickets": get_public_tickets(), "suggestions": get_public_tickets()})
        
    return render_template(
        "tickets.html",
        tickets=get_public_tickets(),
        suggestions=get_public_tickets(),
        discord_user=session.get("discord_user"),
        discord_configured=bool(os.environ.get("DISCORD_CLIENT_ID", "").strip()),
        is_admin=bool(session.get("admin_logged_in"))
    )

@app.route("/tickets/<int:ticket_id>/messages", methods=["GET"])
def get_ticket_messages_api(ticket_id):
    data = load_suggestions()
    suggestions = data.get("suggestions", [])
    target_ticket = None
    for s in suggestions:
        if s.get("id") == ticket_id:
            target_ticket = s
            break

    if not target_ticket:
        return jsonify({"detail": f"Ticket #{ticket_id} not found."}), 404

    is_admin = bool(session.get("admin_logged_in"))
    discord_user = session.get("discord_user") or {}
    user_discord_id = str(discord_user.get("id") or "")
    ticket_discord_id = str(target_ticket.get("discord_id") or "")

    is_author = bool(user_discord_id and ticket_discord_id and user_discord_id == ticket_discord_id and not target_ticket.get("anonymous"))

    if not is_admin and not is_author:
        return jsonify({"detail": "Ticket discussions are private between the author and administrators."}), 403

    return jsonify({"ticket_id": ticket_id, "messages": target_ticket.get("messages", [])})


@app.route("/tickets/<int:ticket_id>/messages", methods=["POST"])
def add_ticket_message_api(ticket_id):
    ip = request.remote_addr or "unknown"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()

    if is_ip_banned(ip):
        return jsonify({"detail": "Your IP is banned from participating in ticket discussions."}), 403
    
    try:
        req_json = request.get_json() or {}
        if not isinstance(req_json, dict):
            return jsonify({"detail": "Invalid request body."}), 400
        payload = TicketMessagePayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400

    data = load_suggestions()
    suggestions = data.get("suggestions", [])
    target_ticket = None
    for s in suggestions:
        if s.get("id") == ticket_id:
            target_ticket = s
            break

    if not target_ticket:
        return jsonify({"detail": f"Ticket #{ticket_id} not found."}), 404

    is_admin = bool(session.get("admin_logged_in"))
    discord_user = session.get("discord_user") or {}
    user_discord_id = str(discord_user.get("id") or "")
    ticket_discord_id = str(target_ticket.get("discord_id") or "")

    is_author = bool(user_discord_id and ticket_discord_id and user_discord_id == ticket_discord_id and not target_ticket.get("anonymous"))

    if not is_admin and not is_author:
        return jsonify({"detail": "Only the ticket author and administrators can post messages in this discussion."}), 403

    msg_text = payload.message.strip()
    if not msg_text:
        return jsonify({"detail": "Message content cannot be empty."}), 400

    messages = target_ticket.setdefault("messages", [])
    new_msg_id = (max([m.get("id", 0) for m in messages]) if messages else 0) + 1

    if is_admin:
        admin_name = session.get("username") or "Administrator"
        admin_d_id = session.get("discord_id") or ""
        if not admin_d_id:
            if is_root_user(admin_name):
                r_ids = get_root_discord_ids()
                if r_ids:
                    admin_d_id = r_ids[0]
            if not admin_d_id:
                admins_data = load_admins()
                for k, v in admins_data.get("admins", {}).items():
                    if v.get("username") == admin_name or k == admin_name:
                        admin_d_id = v.get("discord_id") or (k if k.isdigit() else "")
                        break
        admin_avatar = discord_user.get("avatar_url") if discord_user else None
        msg_obj = {
            "id": new_msg_id,
            "sender_type": "admin",
            "sender_name": admin_name,
            "sender_discord_id": admin_d_id,
            "sender_avatar": admin_avatar,
            "message": msg_text,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        log_audit_event("tickets.reply", "tickets", f"Posted admin reply on ticket #{ticket_id}", target=f"Ticket #{ticket_id}", details={"ticket_id": ticket_id, "message_id": new_msg_id}, username=admin_name)
    else:
        author_name = discord_user.get("global_name") or discord_user.get("username") or "Author"
        msg_obj = {
            "id": new_msg_id,
            "sender_type": "author",
            "sender_name": author_name,
            "sender_discord_id": user_discord_id,
            "sender_avatar": discord_user.get("avatar_url"),
            "message": msg_text,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    messages.append(msg_obj)
    save_suggestions(data)
    broadcast_update("dashboard")

    broadcast_ticket_update(
        ticket_id,
        msg_obj,
        messages,
        target_ticket.get("discord_id"),
        target_ticket.get("anonymous")
    )

    if is_admin:
        try:
            notify_ticket_author_dm(
                target_ticket,
                "message",
                {
                    "sender_name": msg_obj.get("sender_name", "Administrator"),
                    "message": msg_text,
                }
            )
        except Exception as dm_err:
            logger.warning(f"[Ticket Message] Failed to notify author via DM: {dm_err}")

    discord_channel_id = target_ticket.get("discord_channel_id")
    discussion_thread_id = target_ticket.get("discussion_thread_id")
    channels_to_fwd = [c for c in [discord_channel_id, discussion_thread_id] if c]
    if channels_to_fwd:
        def _fwd_to_discord(chs, m_text, s_name, is_adm, current_msg_id):
            try:
                d_id = forward_ticket_reply_to_discord(
                    channel_id=chs,
                    message_text=m_text,
                    sender_name=s_name,
                    is_admin=is_adm,
                )
                if d_id:
                    d = load_suggestions()
                    for s in d.get("suggestions", []):
                        if s.get("id") == ticket_id:
                            for m in s.get("messages", []):
                                if m.get("id") == current_msg_id:
                                    m["discord_message_id"] = d_id
                                    break
                            break
                    save_suggestions(d)
            except Exception as ex:
                logger.warning(f"[Disnake Forward] Failed to forward message to Discord: {ex}")

        threading.Thread(
            target=_fwd_to_discord,
            args=(channels_to_fwd, msg_text, msg_obj.get("sender_name", "User"), is_admin, msg_obj.get("id")),
            daemon=True
        ).start()

    return jsonify({
        "message": "Reply posted successfully.",
        "ticket_id": ticket_id,
        "new_message": msg_obj,
        "messages": messages
    })

@app.route("/tickets/<int:ticket_id>/messages/<int:message_id>", methods=["PATCH", "PUT"])
def edit_ticket_message_api(ticket_id, message_id):
    if not session.get("admin_logged_in"):
        return jsonify({"detail": "Administrator authentication required."}), 403

    req_json = request.get_json() or {}
    new_text = str(req_json.get("message", "")).strip()
    if not new_text:
        return jsonify({"detail": "Message content cannot be empty."}), 400

    data = load_suggestions()
    suggestions = data.get("suggestions", [])
    target_ticket = None
    for s in suggestions:
        if s.get("id") == ticket_id:
            target_ticket = s
            break

    if not target_ticket:
        return jsonify({"detail": f"Ticket #{ticket_id} not found."}), 404

    messages = target_ticket.setdefault("messages", [])
    target_msg = next((m for m in messages if m.get("id") == message_id), None)
    if not target_msg:
        return jsonify({"detail": f"Message #{message_id} not found in Ticket #{ticket_id}."}), 404

    target_msg["message"] = new_text
    target_msg["edited"] = True
    target_msg["edited_at"] = datetime.now(timezone.utc).isoformat()

    save_suggestions(data)
    broadcast_update("dashboard")

    broadcast_ticket_update(
        ticket_id,
        target_msg,
        messages,
        target_ticket.get("discord_id"),
        target_ticket.get("anonymous")
    )

    d_msg_id = target_msg.get("discord_message_id")
    if d_msg_id:
        discord_channel_id = target_ticket.get("discord_channel_id")
        discussion_thread_id = target_ticket.get("discussion_thread_id")
        channels_to_sync = [c for c in [discord_channel_id, discussion_thread_id] if c]
        if channels_to_sync:
            def _edit_discord(chs, d_id, text, s_name):
                try:
                    edit_ticket_reply_in_discord(chs, d_id, text, s_name, True)
                except Exception as ex:
                    logger.warning(f"[Disnake Edit Forward] Failed to edit message in Discord: {ex}")

            threading.Thread(
                target=_edit_discord,
                args=(channels_to_sync, d_msg_id, new_text, target_msg.get("sender_name", "Administrator")),
                daemon=True
            ).start()

    return jsonify({
        "success": True,
        "message": "Reply updated successfully.",
        "ticket_id": ticket_id,
        "updated_message": target_msg,
        "messages": messages
    })

@app.route("/tickets/<int:ticket_id>/messages/<int:message_id>", methods=["DELETE"])
def delete_ticket_message_api(ticket_id, message_id):
    if not session.get("admin_logged_in"):
        return jsonify({"detail": "Administrator authentication required."}), 403

    data = load_suggestions()
    suggestions = data.get("suggestions", [])
    target_ticket = None
    for s in suggestions:
        if s.get("id") == ticket_id:
            target_ticket = s
            break

    if not target_ticket:
        return jsonify({"detail": f"Ticket #{ticket_id} not found."}), 404

    messages = target_ticket.setdefault("messages", [])
    target_msg = next((m for m in messages if m.get("id") == message_id), None)
    if not target_msg:
        return jsonify({"detail": f"Message #{message_id} not found in Ticket #{ticket_id}."}), 404

    d_msg_id = target_msg.get("discord_message_id")
    messages[:] = [m for m in messages if m.get("id") != message_id]

    save_suggestions(data)
    broadcast_update("dashboard")

    broadcast_ticket_update(
        ticket_id,
        {"id": message_id, "deleted": True, "discord_message_id": d_msg_id},
        messages,
        target_ticket.get("discord_id"),
        target_ticket.get("anonymous")
    )

    if d_msg_id:
        discord_channel_id = target_ticket.get("discord_channel_id")
        discussion_thread_id = target_ticket.get("discussion_thread_id")
        channels_to_sync = [c for c in [discord_channel_id, discussion_thread_id] if c]
        if channels_to_sync:
            def _delete_discord(chs, d_id):
                try:
                    delete_ticket_reply_in_discord(chs, d_id)
                except Exception as ex:
                    logger.warning(f"[Disnake Delete Forward] Failed to delete message in Discord: {ex}")

            threading.Thread(
                target=_delete_discord,
                args=(channels_to_sync, d_msg_id),
                daemon=True
            ).start()

    return jsonify({
        "success": True,
        "message": "Reply deleted successfully.",
        "ticket_id": ticket_id,
        "deleted_message_id": message_id,
        "messages": messages
    })

def submit_suggestion():
    return submit_ticket()

def submit_ticket():
    ip = request.remote_addr or "unknown"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()

    if is_ip_banned(ip):
        return jsonify({"detail": "Your IP is banned from submitting tickets."}), 403
    
    try:
        req_json = request.get_json() or {}
        if not isinstance(req_json, dict):
            return jsonify({"detail": "Invalid request body."}), 400
        if not is_session_authenticated():
            captcha_ok, captcha_err = verify_turnstile_token(extract_turnstile_token(req_json), ip)
            if not captcha_ok:
                return jsonify({"detail": captcha_err}), 400
        payload = TicketPayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400
    
    content = (payload.suggestion or payload.description or "").strip()
    if not content:
        return jsonify({"detail": "Ticket description/details cannot be empty."}), 400
    
    data = load_suggestions()
    suggestions = data.setdefault("suggestions", [])
    
    if ip != "unknown" and ip != "127.0.0.1":
        now = datetime.now(timezone.utc)
        limit_period = timedelta(minutes=15)
        for s in suggestions:
            if s.get("ip") == ip:
                try:
                    s_time = datetime.fromisoformat(s.get("timestamp"))
                    if now - s_time < limit_period:
                        time_left = limit_period - (now - s_time)
                        hours_left = int(time_left.total_seconds() // 3600)
                        mins_left = int((time_left.total_seconds() % 3600) // 60)
                        msg = f"Rate limit: Try again in {f'{hours_left}h ' if hours_left > 0 else ''}{mins_left}m."
                        return jsonify({"detail": msg}), 429
                except (ValueError, TypeError):
                    continue
    
    new_id = get_next_ticket_id(data)
        
    discord_user = session.get("discord_user") or {}
    discord_id = discord_user.get("id") or None
    discord_username = discord_user.get("username") or discord_user.get("global_name") or None
    discord_avatar = discord_user.get("avatar_url") or None
    
    if not discord_id:
        name = "Anonymous"
        is_anon = True
        discord_id = None
        discord_username = None
        discord_avatar = None
    else:
        is_anon = bool(payload.anonymous)
        if is_anon:
            name = "Anonymous"
        else:
            name = discord_username or "Discord User"
        
    if payload.target in ["point_graph", "points_graph", "point_history"]:
        target_val = "point_graph"
    elif payload.target == "server_checker" or payload.is_server_checker:
        target_val = "server_checker"
    elif payload.target == "general":
        target_val = "general"
    else:
        target_val = "overlay"
    
    ticket_type = "bug_report" if payload.type in ["bug_report", "bug", "issue"] else "suggestion"
    initial_status = "open" if ticket_type == "bug_report" else "pending"

    new_sug = {
        "id": new_id,
        "type": ticket_type,
        "title": payload.title.strip() if payload.title else "",
        "name": name,
        "suggestion": content,
        "description": content,
        "ip": ip,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": initial_status,
        "target": target_val,
        "is_server_checker": target_val == "server_checker",
        "anonymous": is_anon,
        "discord_id": str(discord_id) if discord_id else None,
        "discord_username": discord_username,
        "discord_avatar": discord_avatar,
        "hidden": False,
        "messages": [],
        "discord_channel_id": None
    }
    suggestions.append(new_sug)
    save_suggestions(data)
    broadcast_update("dashboard")

    def _create_channel_task(t_copy):
        ch_id = create_discord_ticket_channel(t_copy)
        if ch_id:
            d = load_suggestions()
            for s in d.get("suggestions", []):
                if s.get("id") == t_copy.get("id"):
                    s["discord_channel_id"] = ch_id
                    break
            save_suggestions(d)
            broadcast_update("dashboard")

    threading.Thread(target=_create_channel_task, args=(dict(new_sug),), daemon=True).start()

    in_guild = False
    is_logged_in_discord = bool(discord_id)
    if is_logged_in_discord:
        try:
            in_guild = is_user_in_guild(discord_id)
        except Exception as ex:
            logger.warning(f"Error checking guild membership for user {discord_id}: {ex}")
            in_guild = False

    return jsonify({
        "message": f"{'Bug report' if ticket_type == 'bug_report' else 'Suggestion'} submitted successfully.",
        "id": new_id,
        "type": ticket_type,
        "logged_in_discord": is_logged_in_discord,
        "in_guild": in_guild
    })

def sanitize_crash_text(text: str) -> str:
    if not text:
        return ""

    text = re.sub(r'(?i)[a-zA-Z]:[\\/]+Users[\\/]+[^\s\\/",\':;]+[\\/]+AppData[\\/]+Local[\\/]+Temp', '%temp%', text)
    text = re.sub(r'(?i)[a-zA-Z]:[\\/]+Users[\\/]+[^\s\\/",\':;]+[\\/]+AppData[\\/]+Roaming', '%appdata%', text)
    text = re.sub(r'(?i)[a-zA-Z]:[\\/]+Users[\\/]+[^\s\\/",\':;]+[\\/]+AppData[\\/]+Local', '%localappdata%', text)
    text = re.sub(r'(?i)[a-zA-Z]:[\\/]+Users[\\/]+[^\s\\/",\':;]+', '%userprofile%', text)

    text = re.sub(r'(?i)[\\/]+home[\\/]+[^\s\\/",\':;]+[\\/]+\.config', '$XDG_CONFIG_HOME', text)
    text = re.sub(r'(?i)[\\/]+home[\\/]+[^\s\\/",\':;]+', '$HOME', text)

    text = re.sub(r'(?i)[\\/]+Users[\\/]+[^\s\\/",\':;]+', '$HOME', text)

    return text

def normalize_traceback_signature(tb: str) -> str:
    if not tb:
        return ""

    s = re.sub(r'(?i)=== CRASH OCCURRED:[^\n\r]*===', '', tb)
    s = re.sub(r'\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?\b', '', s)
    s = re.sub(r'(?i)\bExecutable:[^\n\r]*', '', s)
    s = re.sub(r'(?i)\bBase Directory:[^\n\r]*', '', s)
    return s.strip()

@app.route("/crashes", methods=["POST"])
def submit_crash():
    ip = request.remote_addr or "unknown"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()

    if is_ip_banned(ip):
        return jsonify({"detail": "Your IP is banned."}), 403
    
    try:
        req_json = request.get_json() or {}
        if not isinstance(req_json, dict):
            return jsonify({"detail": "Invalid request body."}), 400
        payload = CrashPayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400
    
    data = load_crashes()
    crashes = data.setdefault("crashes", [])
    
    new_id = 1
    if crashes:
        new_id = max(c.get("id", 0) for c in crashes) + 1
        
    sanitized_traceback = sanitize_crash_text(payload.traceback.strip())
    sanitized_log = sanitize_crash_text(payload.log_data.strip())

    new_crash = {
        "id": new_id,
        "version": payload.version.strip(),
        "traceback": sanitized_traceback,
        "log_data": sanitized_log,
        "os_info": payload.os_info.strip(),
        "status": "OPEN",
        "ip": ip,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    crashes.append(new_crash)
    save_crashes(data)
    broadcast_update("dashboard")

    norm_sig = normalize_traceback_signature(sanitized_traceback)
    occurrence_count = sum(1 for c in crashes if normalize_traceback_signature(c.get("traceback", "")) == norm_sig)

    try:
        threading.Thread(
            target=report_crash_to_discord,
            args=(dict(new_crash), occurrence_count),
            daemon=True
        ).start()
    except Exception as ex:
        logger.warning(f"Failed to dispatch Discord crash notification: {ex}")

    return jsonify({"message": "Crash report submitted successfully.", "id": new_id, "occurrences": occurrence_count})

class VisibilitySuggestionPayload(BaseModel):
    id: int
    hidden: bool

class UpdateAdminPermissionsPayload(BaseModel):
    discord_id: str
    permissions: dict[str, bool]

@app.route("/admin/crashes/status", methods=["POST"])
@admin_required
def update_crash_status(username):
    if not has_permission(username, "crashes"):
        return jsonify({"detail": "Permission denied for crash logs section"}), 403
    try:
        req_json = request.get_json() or {}
        if not isinstance(req_json, dict):
            return jsonify({"detail": "Invalid request body."}), 400
        payload = CrashStatusPayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400

    target_ids = set()
    if payload.ids:
        target_ids.update(payload.ids)
    if payload.id is not None:
        target_ids.add(payload.id)

    if not target_ids:
        return jsonify({"detail": "No crash report IDs provided."}), 400

    data = load_crashes()
    crashes = data.get("crashes", [])
    updated = 0
    for c in crashes:
        if c.get("id") in target_ids:
            c["status"] = payload.status
            updated += 1

    if updated > 0:
        save_crashes(data)
        broadcast_update("dashboard")
        log_audit_event("crashes.status_update", "crashes", f"Updated {updated} crash report(s) status to '{payload.status}'", target=f"{updated} Crash Reports", details={"ids": sorted(list(target_ids)), "status": payload.status}, username=username)
        return jsonify({"message": f"{updated} crash report(s) updated to {payload.status}.", "status": payload.status, "count": updated})

    return jsonify({"detail": "No matching crash reports found."}), 404

@app.route("/admin/crashes/delete", methods=["POST"])
@admin_required
def delete_crash(username):
    if not has_permission(username, "crashes"):
        return jsonify({"detail": "Permission denied for crash logs section"}), 403
    try:
        req_json = request.get_json() or {}
        if not isinstance(req_json, dict):
            return jsonify({"detail": "Invalid request body."}), 400
        payload = DeleteCrashPayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400

    target_ids = set()
    if payload.ids:
        target_ids.update(payload.ids)
    if payload.id is not None:
        target_ids.add(payload.id)

    if not target_ids:
        return jsonify({"detail": "No crash report IDs provided."}), 400

    data = load_crashes()
    crashes = data.get("crashes", [])
    initial_len = len(crashes)
    data["crashes"] = [c for c in crashes if c.get("id") not in target_ids]
    deleted_count = initial_len - len(data["crashes"])

    if deleted_count > 0:
        save_crashes(data)
        broadcast_update("dashboard")
        log_audit_event("crashes.delete", "crashes", f"Deleted {deleted_count} crash report(s)", target=f"{deleted_count} Crash Reports", details={"ids": sorted(list(target_ids))}, username=username)
        return jsonify({"message": f"{deleted_count} crash report(s) deleted successfully.", "count": deleted_count})

    return jsonify({"detail": "No matching crash reports found."}), 404

@app.route("/admin/tickets/status", methods=["POST"])
@admin_required
def update_suggestion_status(username):
    if not has_permission(username, "suggestions"):
        return jsonify({"detail": "Permission denied for tickets section"}), 403
    try:
        req_json = request.get_json() or {}
        if not isinstance(req_json, dict):
            return jsonify({"detail": "Invalid request body."}), 400
        payload = StatusUpdatePayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400

    data = load_suggestions()
    suggestions = data.get("suggestions", [])
    for s in suggestions:
        if s.get("id") == payload.id:
            is_bug = (s.get("type") == "bug_report")
            ticket_type = "bug_report" if is_bug else "suggestion"
            norm_status = (payload.status or "").strip().lower()

            if is_bug:
                if norm_status == "resolved":
                    norm_status = "fixed"
                elif norm_status == "closed":
                    norm_status = "invalid"
            else:
                if norm_status == "accepted":
                    norm_status = "implemented"

            valid_statuses = (
                {"open", "investigating", "confirmed", "fixed", "invalid"}
                if is_bug
                else {"pending", "considering", "planned", "implemented", "declined"}
            )
            if norm_status not in valid_statuses:
                return jsonify({
                    "detail": f"Invalid status '{payload.status}' for {ticket_type}. Allowed: {sorted(valid_statuses)}"
                }), 400

            prev_status = str(s.get("status") or ("open" if is_bug else "pending"))
            s["status"] = norm_status
            save_suggestions(data)
            broadcast_update("dashboard")
            log_audit_event("tickets.status_update", "tickets", f"Updated status of {ticket_type} #{payload.id} to '{norm_status}'", target=f"Ticket #{payload.id}", details={"ticket_id": payload.id, "prev_status": prev_status, "new_status": norm_status}, username=username)
            try:
                notify_ticket_author_dm(
                    s,
                    "status",
                    {"changed_by": username, "status": norm_status}
                )
            except Exception as dm_err:
                logger.warning(f"Failed to notify author of status change via DM: {dm_err}")
            try:
                actor_label = f"{username} (via Website)"
                update_discussion_thread_status(s, norm_status, changed_by=actor_label, prev_status=prev_status)
            except Exception as dt_err:
                logger.warning(f"Failed to update discussion thread status: {dt_err}")
            try:
                actor_label = f"{username} (via Website)"
                update_ticket_channel_message(s, changed_by=actor_label, prev_status=prev_status)
            except Exception as tcm_err:
                logger.warning(f"Failed to update ticket channel message: {tcm_err}")
            return jsonify({"message": "Status updated successfully.", "id": payload.id, "status": norm_status})
    return jsonify({"detail": f"Ticket with ID {payload.id} not found."}), 404

@app.route("/admin/tickets/comment", methods=["POST"])
@admin_required
def update_suggestion_comment(username):
    if not has_permission(username, "suggestions"):
        return jsonify({"detail": "Permission denied for tickets section"}), 403
    try:
        req_json = request.get_json() or {}
        if not isinstance(req_json, dict):
            return jsonify({"detail": "Invalid request body."}), 400
        payload = CommentPayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400

    data = load_suggestions()
    suggestions = data.get("suggestions", [])
    for s in suggestions:
        if s.get("id") == payload.id:
            s["admin_comment"] = payload.comment.strip()
            s["comment_by"] = username
            s["comment_timestamp"] = datetime.now(timezone.utc).isoformat()
            save_suggestions(data)
            broadcast_update("dashboard")
            log_audit_event("tickets.comment", "tickets", f"Updated admin comment on ticket #{payload.id}", target=f"Ticket #{payload.id}", details={"ticket_id": payload.id, "comment": payload.comment.strip()}, username=username)
            try:
                notify_ticket_author_dm(
                    s,
                    "note",
                    {"comment_by": username, "comment": payload.comment.strip()}
                )
            except Exception as dm_err:
                logger.warning(f"Failed to notify author of note change via DM: {dm_err}")
            try:
                update_ticket_channel_message(s)
            except Exception as tcm_err:
                logger.warning(f"Failed to update ticket channel message: {tcm_err}")
            try:
                update_discussion_thread_status(s, s.get("status") or "open")
            except Exception as dt_err:
                logger.warning(f"Failed to update discussion thread note: {dt_err}")
            return jsonify({"message": "Admin comment saved successfully.", "id": payload.id, "comment": payload.comment.strip(), "comment_by": username})
    return jsonify({"detail": f"Ticket with ID {payload.id} not found."}), 404

@app.route("/admin/tickets/visibility", methods=["POST"])
@admin_required
def update_suggestion_visibility(username):
    if not has_permission(username, "suggestions"):
        return jsonify({"detail": "Permission denied for tickets section"}), 403
    try:
        req_json = request.get_json() or {}
        if not isinstance(req_json, dict):
            return jsonify({"detail": "Invalid request body."}), 400
        payload = VisibilitySuggestionPayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400

    data = load_suggestions()
    suggestions = data.get("suggestions", [])
    for s in suggestions:
        if s.get("id") == payload.id:
            s["hidden"] = payload.hidden
            save_suggestions(data)
            broadcast_update("dashboard")
            log_audit_event("tickets.visibility", "tickets", f"Set ticket #{payload.id} visibility to {'hidden' if payload.hidden else 'public'}", target=f"Ticket #{payload.id}", details={"ticket_id": payload.id, "hidden": payload.hidden}, username=username)
            return jsonify({"message": f"Ticket #{payload.id} visibility updated.", "id": payload.id, "hidden": payload.hidden})
    return jsonify({"detail": f"Ticket with ID {payload.id} not found."}), 404

@app.route("/admin/tickets/delete", methods=["POST"])
@admin_required
def delete_suggestion(username):
    if not has_permission(username, "suggestions"):
        return jsonify({"detail": "Permission denied for tickets section"}), 403
    try:
        req_json = request.get_json() or {}
        if not isinstance(req_json, dict):
            return jsonify({"detail": "Invalid request body."}), 400
        payload = DeleteSuggestionPayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400

    data = load_suggestions()
    suggestions = data.get("suggestions", [])
    target_ticket = None
    remaining_suggestions = []
    for s in suggestions:
        if s.get("id") == payload.id:
            target_ticket = s
        else:
            remaining_suggestions.append(s)

    if not target_ticket:
        return jsonify({"detail": f"Ticket with ID {payload.id} not found."}), 404

    data["suggestions"] = remaining_suggestions

    deleted_tickets = data.setdefault("deleted_tickets", [])
    deleted_record = {
        "id": payload.id,
        "title": target_ticket.get("title", ""),
        "type": target_ticket.get("type", "suggestion"),
        "name": target_ticket.get("name", "Anonymous"),
        "status": target_ticket.get("status", "pending"),
        "discord_id": target_ticket.get("discord_id"),
        "discord_channel_id": target_ticket.get("discord_channel_id"),
        "discussion_thread_id": target_ticket.get("discussion_thread_id"),
        "deleted_at": datetime.now(timezone.utc).isoformat(),
        "deleted_by": username,
        "content": target_ticket.get("suggestion") or target_ticket.get("description") or "",
    }
    deleted_tickets.append(deleted_record)
    data.setdefault("deleted_ticket_ids", []).append(payload.id)
    data["last_ticket_id"] = max(data.get("last_ticket_id", 0), payload.id)  # pyright: ignore[reportArgumentType]

    save_suggestions(data)
    broadcast_update("dashboard")
    log_audit_event("tickets.delete", "tickets", f"Deleted ticket #{payload.id} ('{target_ticket.get('title')}')", target=f"Ticket #{payload.id}", details={"ticket_id": payload.id, "title": target_ticket.get("title"), "type": target_ticket.get("type")}, username=username)

    try:
        notify_ticket_deleted(target_ticket, deleted_by=username)
    except Exception as del_err:
        logger.warning(f"Failed to send ticket deletion notice to Discord: {del_err}")

    return jsonify({"message": f"Ticket #{payload.id} deleted successfully.", "id": payload.id})

@app.route("/admin/tickets/ban", methods=["POST"])
@admin_required
def ban_ip(username):
    if not has_permission(username, "bans"):
        return jsonify({"detail": "Permission denied for bans section"}), 403
    try:
        req_json = request.get_json() or {}
        if not isinstance(req_json, dict):
            return jsonify({"detail": "Invalid request body."}), 400
        payload = BanPayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400

    ip_to_ban = payload.ip.strip()
    if not ip_to_ban or ip_to_ban == "unknown":
        return jsonify({"detail": "Invalid IP address."}), 400

    data = load_banned_ips()
    banned = data.setdefault("banned", {})
    
    expires_at = None
    if payload.duration_minutes is not None and payload.duration_minutes > 0:
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=payload.duration_minutes)).isoformat()

    banned[ip_to_ban] = {
        "banned_by": username,
        "banned_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at,
        "reason": payload.reason.strip() or "No reason provided"
    }
    save_banned_ips(data)
    broadcast_update("dashboard")
    log_audit_event("bans.ban_ip", "bans", f"Banned IP {ip_to_ban}: {payload.reason.strip() or 'No reason provided'}", target=f"IP {ip_to_ban}", details={"ip": ip_to_ban, "reason": payload.reason.strip(), "duration_minutes": payload.duration_minutes}, username=username)
    return jsonify({"message": f"IP {ip_to_ban} has been banned.", "ip": ip_to_ban})

@app.route("/admin/tickets/unban", methods=["POST"])
@admin_required
def unban_ip(username):
    if not has_permission(username, "bans"):
        return jsonify({"detail": "Permission denied for bans section"}), 403
    try:
        req_json = request.get_json() or {}
        if not isinstance(req_json, dict):
            return jsonify({"detail": "Invalid request body."}), 400
        payload = UnbanPayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400

    data = load_banned_ips()
    banned = data.get("banned", {})
    if payload.ip in banned:
        del banned[payload.ip]
        save_banned_ips(data)
        broadcast_update("dashboard")
        log_audit_event("bans.unban_ip", "bans", f"Unbanned IP {payload.ip}", target=f"IP {payload.ip}", details={"ip": payload.ip}, username=username)
        return jsonify({"message": f"IP {payload.ip} unbanned successfully.", "ip": payload.ip})
    return jsonify({"detail": f"IP {payload.ip} is not currently banned."}), 404

@app.route("/admin/tickets", methods=["GET"])
@admin_required
def view_suggestions_dashboard(username):
    if not has_permission(username, "suggestions"):
        return redirect("/admin")
    discord_id = session.get("discord_id") or username
    notifier_cfg = get_admin_notifier_config(discord_id)
    return render_template(
        "admin_panel.html",
        username=username,
        discord_id=session.get("discord_id") or "",
        active_view="suggestions",
        is_root=is_root_user(username),
        permissions=get_user_permissions(username),
        me=admin_panel_identity(username),
        notifier=notifier_cfg
    )

@app.route("/admin/crashes", methods=["GET"])
@admin_required
def view_crashes_dashboard(username):
    if not has_permission(username, "crashes"):
        return redirect("/admin")
    discord_id = session.get("discord_id") or username
    notifier_cfg = get_admin_notifier_config(discord_id)
    return render_template(
        "admin_panel.html",
        username=username,
        discord_id=session.get("discord_id") or "",
        active_view="crashes",
        is_root=is_root_user(username),
        permissions=get_user_permissions(username),
        me=admin_panel_identity(username),
        notifier=notifier_cfg
    )

@app.route("/admin/contact", methods=["GET"])
@admin_required
def view_contact_dashboard(username):
    if not has_permission(username, "contact"):
        return redirect("/admin")
    discord_id = session.get("discord_id") or username
    notifier_cfg = get_admin_notifier_config(discord_id)
    return render_template(
        "admin_panel.html",
        username=username,
        discord_id=session.get("discord_id") or "",
        active_view="contact",
        is_root=is_root_user(username),
        permissions=get_user_permissions(username),
        me=admin_panel_identity(username),
        notifier=notifier_cfg
    )

@app.route("/admin/bans", methods=["GET"])
@admin_required
def view_bans_dashboard(username):
    if not has_permission(username, "bans"):
        return redirect("/admin")
    discord_id = session.get("discord_id") or username
    notifier_cfg = get_admin_notifier_config(discord_id)
    return render_template(
        "admin_panel.html",
        username=username,
        discord_id=session.get("discord_id") or "",
        active_view="bans",
        is_root=is_root_user(username),
        permissions=get_user_permissions(username),
        me=admin_panel_identity(username),
        notifier=notifier_cfg
    )

@app.route("/admin", methods=["GET"])
@admin_required
def admin_root(username):
    discord_id = session.get("discord_id") or username
    notifier_cfg = get_admin_notifier_config(discord_id)
    return render_template(
        "admin_panel.html",
        username=username,
        discord_id=session.get("discord_id") or "",
        active_view="overview",
        is_root=is_root_user(username),
        permissions=get_user_permissions(username),
        me=admin_panel_identity(username),
        notifier=notifier_cfg
    )

@app.route("/admin/<any(dms, moderation, automod, embeds, autorole, welcome, faq, commands, errors):section>", methods=["GET"])
@admin_required
def view_bot_section_dashboard(username, section):
    if not has_permission(username, section):
        return redirect("/admin")
    discord_id = session.get("discord_id") or username
    return render_template(
        "admin_panel.html",
        username=username,
        discord_id=session.get("discord_id") or "",
        active_view=section,
        is_root=is_root_user(username),
        permissions=get_user_permissions(username),
        me=admin_panel_identity(username),
        notifier=get_admin_notifier_config(discord_id),
    )

@app.route("/admin/servers", methods=["GET"])
@admin_required
def view_servers_dashboard(username):
    if not has_permission(username, "servers"):
        return redirect("/admin")
    servers_data = get_sc_data("servers.json")
    server_cards = build_server_cards(servers_data)
    initial_tab = request.args.get("status") or request.args.get("tab") or "all"
    discord_id = session.get("discord_id") or username
    notifier_cfg = get_admin_notifier_config(discord_id)
    return render_template(
        "admin_panel.html",
        username=username,
        discord_id=session.get("discord_id") or "",
        active_view="servers",
        initial_server_tab=initial_tab,
        is_root=is_root_user(username),
        permissions=get_user_permissions(username),
        me=admin_panel_identity(username),
        servers=server_cards,
        notifier=notifier_cfg
    )

@app.route("/admin/servers/persist", methods=["POST"])
@admin_required
def toggle_server_persistence(username):
    if not has_permission(username, "servers"):
        return jsonify({"detail": "Permission denied for servers section"}), 403
    try:
        req_json = request.get_json() or {}
        if not isinstance(req_json, dict):
            return jsonify({"detail": "Invalid request body."}), 400
        payload = ServerPersistPayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400

    job_id = payload.job_id.strip()
    if not job_id:
        return jsonify({"detail": "job_id is required."}), 400

    data = load_persistent_servers()
    persistent = data.setdefault("persistent", {})

    if payload.persistent:
        persistent[job_id] = {
            "marked_by": username,
            "marked_at": datetime.now(timezone.utc).isoformat(),
            "note": payload.note.strip()
        }
        msg = f"Server {job_id} marked as persistent."
    else:
        if job_id in persistent:
            del persistent[job_id]
        msg = f"Server {job_id} persistence removed."

    save_persistent_servers(data)
    broadcast_update("dashboard")
    log_audit_event("servers.persist_toggle", "servers", f"{'Marked' if payload.persistent else 'Removed'} persistence for server {job_id}", target=f"Server {job_id}", details={"job_id": job_id, "persistent": payload.persistent, "note": payload.note}, username=username)
    return jsonify({"success": True, "message": msg, "job_id": job_id, "is_persistent": payload.persistent})

@app.route("/admin/audit-logs", methods=["GET"])
@admin_required
def view_audit_logs_dashboard(username):
    if not has_permission(username, "audit_logs"):
        return redirect("/admin")
    discord_id = session.get("discord_id") or username
    notifier_cfg = get_admin_notifier_config(discord_id)
    return render_template(
        "admin_panel.html",
        username=username,
        discord_id=session.get("discord_id") or "",
        active_view="audit-logs",
        is_root=is_root_user(username),
        permissions=get_user_permissions(username),
        me=admin_panel_identity(username),
        notifier=notifier_cfg,
    )

@app.route("/admin/audit-logs/data", methods=["GET"])
@admin_required
def api_get_audit_logs(username):
    if not has_permission(username, "audit_logs"):
        return jsonify({"detail": "Forbidden - Root privileges required"}), 403
    category = request.args.get("category")
    action = request.args.get("action")
    actor = request.args.get("actor")
    q = request.args.get("q")
    try:
        page = int(request.args.get("page", 1))
    except (ValueError, TypeError):
        page = 1
    try:
        limit = int(request.args.get("limit", 50))
    except (ValueError, TypeError):
        limit = 50
    data = audit.query_audit_logs(
        category=category,
        action=action,
        actor=actor,
        query=q,
        page=page,
        limit=limit,
    )
    return jsonify(data)

@app.route("/admin/audit-logs/export", methods=["GET"])
@admin_required
def api_export_audit_logs(username):
    if not has_permission(username, "audit_logs"):
        return jsonify({"detail": "Forbidden - Root privileges required"}), 403
    logs = audit.load_raw_audit_logs()
    filename = f"rbwr_audit_logs_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    response = Response(
        json.dumps({"audit_logs": logs, "exported_at": datetime.now(timezone.utc).isoformat(), "exported_by": username}, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
    log_audit_event("audit.export", "system", f"Exported {len(logs)} audit logs", target="Audit Logs", username=username)
    return response

@app.route("/admin/audit-logs/clear", methods=["POST"])
@admin_required
def api_clear_audit_logs(username):
    if not is_root_user(username):
        return jsonify({"detail": "Forbidden - Root privileges required"}), 403
    actor = get_current_audit_actor(username)
    ip = get_client_ip_address()
    ua = request.headers.get("User-Agent", "") if has_request_context() else ""
    audit.clear_audit_logs(actor, ip=ip, user_agent=ua)
    broadcast_update("audit_logs")
    return jsonify({"success": True, "message": "All prior audit logs have been purged."})

@app.route("/admin/accounts", methods=["GET"])
@admin_required
def view_accounts_dashboard(username):
    if not is_root_user(username):
        return redirect("/admin")
    discord_id = session.get("discord_id") or username
    notifier_cfg = get_admin_notifier_config(discord_id)
    return render_template(
        "admin_panel.html",
        username=username,
        discord_id=session.get("discord_id") or "",
        active_view="accounts",
        is_root=True,
        permissions=get_user_permissions(username),
        me=admin_panel_identity(username),
        notifier=notifier_cfg
    )

class CreateAdminPayload(BaseModel):
    discord_id: str = Field(..., min_length=15, max_length=25)
    username: str = Field(default="", max_length=50)

class DeleteAdminPayload(BaseModel):
    discord_id: str

@app.route("/admin/accounts/create", methods=["POST"])
@admin_required
def create_admin_account(username):
    if not is_root_user(username):
        return jsonify({"detail": "Forbidden - Root privileges required"}), 403
    try:
        req_json = request.get_json() or {}
        if not isinstance(req_json, dict):
            return jsonify({"detail": "Invalid request body."}), 400
        payload = CreateAdminPayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400

    discord_id = payload.discord_id.strip()
    if not discord_id.isdigit():
        return jsonify({"detail": "Invalid Discord ID: must be numeric digits (17-20 characters)."}), 400

    root_ids = get_root_discord_ids()
    if discord_id in root_ids:
        return jsonify({"detail": "This Discord ID is already configured as the Root Administrator."}), 400

    admins_data = load_admins()
    admins = admins_data.setdefault("admins", {})
    if discord_id in admins:
        return jsonify({"detail": f"Admin with Discord ID '{discord_id}' already exists."}), 400

    admin_label = payload.username.strip() or f"Admin ({discord_id})"
    admins[discord_id] = {
        "discord_id": discord_id,
        "username": admin_label,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "permissions": normalize_permissions(None),
        "notifier": {
            "enabled": False,
            "categories": ["overlay", "point_graph", "server_checker", "general"]
        }
    }
    save_admins(admins_data)
    broadcast_update("accounts")
    log_audit_event("accounts.create", "accounts", f"Authorized new administrator Discord ID: {discord_id} ('{admin_label}')", target=f"Admin {discord_id}", details={"discord_id": discord_id, "label": admin_label}, username=username)
    return jsonify({"message": f"Admin with Discord ID '{discord_id}' added successfully."})

@app.route("/admin/accounts/permissions", methods=["POST"])
@admin_required
def update_admin_permissions(username):
    if not is_root_user(username):
        return jsonify({"detail": "Forbidden - Root privileges required"}), 403
    try:
        req_json = request.get_json() or {}
        if not isinstance(req_json, dict):
            return jsonify({"detail": "Invalid request body."}), 400
        payload = UpdateAdminPermissionsPayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400

    target_id = payload.discord_id.strip()
    admins_data = load_admins()
    admins = admins_data.get("admins", {})
    
    admin_entry = admins.get(target_id)
    if not admin_entry:
        for k, v in admins.items():
            if k == target_id or v.get("username") == target_id or v.get("discord_id") == target_id:
                admin_entry = v
                break
                
    if not admin_entry:
        return jsonify({"detail": f"Admin account '{target_id}' not found."}), 404

    admin_entry["permissions"] = normalize_permissions({**(admin_entry.get("permissions") or {}), **payload.permissions})
    save_admins(admins_data)
    broadcast_update("accounts")
    broadcast_update("dashboard")
    log_audit_event("accounts.permissions_update", "accounts", f"Updated permissions for admin '{target_id}'", target=f"Admin {target_id}", details={"target_id": target_id, "permissions": payload.permissions}, username=username)
    return jsonify({"message": f"Permissions for admin '{target_id}' updated successfully."})

@app.route("/admin/accounts/delete", methods=["POST"])
@admin_required
def delete_admin_account(username):
    if not is_root_user(username):
        return jsonify({"detail": "Forbidden - Root privileges required"}), 403
    try:
        req_json = request.get_json() or {}
        if not isinstance(req_json, dict):
            return jsonify({"detail": "Invalid request body."}), 400
        payload = DeleteAdminPayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400

    target_id = payload.discord_id.strip()
    admins_data = load_admins()
    admins = admins_data.get("admins", {})
    
    key_to_delete = None
    if target_id in admins:
        key_to_delete = target_id
    else:
        for k, v in admins.items():
            if k == target_id or v.get("username") == target_id or v.get("discord_id") == target_id:
                key_to_delete = k
                break
                
    if key_to_delete:
        del admins[key_to_delete]
        save_admins(admins_data)
        broadcast_update("accounts")
        log_audit_event("accounts.delete", "accounts", f"Removed administrator account '{target_id}'", target=f"Admin {target_id}", details={"target_id": target_id, "key": key_to_delete}, username=username)
        return jsonify({"message": f"Admin account '{target_id}' removed successfully."})
    return jsonify({"detail": f"Admin account '{target_id}' not found."}), 404

def analyze_server_state_anomalies(snapshots: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(snapshots, dict):
        return {
            "total_snapshots": 0,
            "anomalous_snapshots_count": 0,
            "total_anomalies": 1,
            "has_dict_demand": False,
            "anomalies": [{
                "timestamp": "N/A",
                "unit": "Root",
                "field": "snapshots",
                "type": type(snapshots).__name__,
                "severity": "CRITICAL",
                "keys": [],
                "raw_value": str(snapshots),
                "message": f"Snapshots root is of type '{type(snapshots).__name__}', expected dictionary."
            }],
            "snapshots_summary": []
        }

    sorted_ts = sorted([k for k in snapshots.keys() if not k.startswith('_')])
    anomalies: list[dict[str, Any]] = []
    snapshots_summary: list[dict[str, Any]] = []
    anomalous_snapshots_set = set()

    for ts in sorted_ts:
        st = snapshots.get(ts)
        snap_anomalies = []
        if not isinstance(st, dict):
            anom = {
                "timestamp": ts,
                "unit": "Root",
                "field": "state",
                "type": type(st).__name__,
                "severity": "CRITICAL",
                "keys": [],
                "raw_value": str(st),
                "message": f"Snapshot state is of type '{type(st).__name__}' instead of a dictionary."
            }
            anomalies.append(anom)
            snap_anomalies.append(anom)
            anomalous_snapshots_set.add(ts)
            continue

        for unit_key in ("Unit1", "Unit2"):
            ust = st.get(unit_key)
            if ust is None:
                continue
            if not isinstance(ust, dict):
                anom = {
                    "timestamp": ts,
                    "unit": unit_key,
                    "field": unit_key,
                    "type": type(ust).__name__,
                    "severity": "CRITICAL",
                    "keys": [],
                    "raw_value": str(ust),
                    "message": f"{unit_key} state is of type '{type(ust).__name__}' instead of a dictionary."
                }
                anomalies.append(anom)
                snap_anomalies.append(anom)
                anomalous_snapshots_set.add(ts)
                continue

            fields_to_check = [
                ("DemandU1" if unit_key == "Unit1" else "DemandU2", "Active electrical demand setpoint"),
                ("NextDemandU1" if unit_key == "Unit1" else "NextDemandU2", "Next scheduled demand setpoint"),
                ("Demand", "Legacy demand setpoint"),
                ("Demand Time Left", "Countdown timer to next demand update"),
                ("PointsPerSecond", "Points generation rate per second"),
                ("APRM", "Average Power Range Monitor percentage"),
                ("Output", "Generator electrical output"),
                ("ElectricOutputMW", "Grid electrical output (MW)"),
                ("PradDoSieci", "Unit 2 grid electrical power (MW)"),
                ("Reactor Temp", "Reactor core temperature"),
            ]

            for field_name, field_desc in fields_to_check:
                if field_name not in ust:
                    continue
                val = ust[field_name]
                if isinstance(val, dict):
                    is_roblox_nan = (
                        (val.get("t") == "numeric" and str(val.get("v")).lower() == "nan")
                        or (str(val.get("v")).lower() == "nan")
                    )
                    is_typed_num = "t" in val and "v" in val

                    if is_roblox_nan:
                        subtype = "roblox_nan_dict"
                        message = (
                            f"{unit_key}.{field_name} received Roblox serialized NaN float {json.dumps(val)} "
                            f"(typed numeric object representing 'nan' from division by zero or uninitialized float). "
                            f"Passing this dictionary into float() triggers TypeError: float() argument must be a string or a real number, not 'dict'. "
                            f"The application safely handles this as non-numeric (N/A) without attempting dictionary extraction."
                        )
                    elif is_typed_num:
                        subtype = "typed_numeric_dict"
                        message = (
                            f"{unit_key}.{field_name} received typed numeric dictionary {json.dumps(val)}. "
                            f"Passing this dictionary into float() triggers TypeError. "
                            f"The application safely handles this as non-numeric (N/A) without attempting dictionary extraction."
                        )
                    else:
                        subtype = "dict"
                        message = (
                            f"{unit_key}.{field_name} received a dictionary object {json.dumps(val)} "
                            f"(keys: {list(val.keys())}) instead of a numeric value. "
                            f"This caused float({unit_key}.{field_name}) to raise TypeError."
                        )

                    anom = {
                        "timestamp": ts,
                        "unit": unit_key,
                        "field": field_name,
                        "field_desc": field_desc,
                        "type": "dict",
                        "subtype": subtype,
                        "is_roblox_nan": is_roblox_nan,
                        "severity": "CRITICAL",
                        "keys": list(val.keys()),
                        "raw_value": val,
                        "message": message
                    }
                    anomalies.append(anom)
                    snap_anomalies.append(anom)
                    anomalous_snapshots_set.add(ts)
                elif isinstance(val, list):
                    anom = {
                        "timestamp": ts,
                        "unit": unit_key,
                        "field": field_name,
                        "field_desc": field_desc,
                        "type": "list",
                        "severity": "CRITICAL",
                        "keys": [],
                        "raw_value": val,
                        "message": f"{unit_key}.{field_name} received a list instead of a numeric value."
                    }
                    anomalies.append(anom)
                    snap_anomalies.append(anom)
                    anomalous_snapshots_set.add(ts)
                elif isinstance(val, str):
                    try:
                        float(val)
                    except ValueError:
                        anom = {
                            "timestamp": ts,
                            "unit": unit_key,
                            "field": field_name,
                            "field_desc": field_desc,
                            "type": "str",
                            "severity": "WARNING",
                            "keys": [],
                            "raw_value": val,
                            "message": f"{unit_key}.{field_name} is an unparseable non-numeric string '{val}'."
                        }
                        anomalies.append(anom)
                        snap_anomalies.append(anom)
                        anomalous_snapshots_set.add(ts)

        for rf_name, rf_desc in [("Demand", "Root legacy demand setpoint"), ("Total points/second", "Plant points/sec rate"), ("PlayerCount", "Player count")]:
            if rf_name in st:
                rval = st[rf_name]
                if isinstance(rval, dict):
                    is_roblox_nan = (
                        (rval.get("t") == "numeric" and str(rval.get("v")).lower() == "nan")
                        or (str(rval.get("v")).lower() == "nan")
                    )
                    anom = {
                        "timestamp": ts,
                        "unit": "Root",
                        "field": rf_name,
                        "field_desc": rf_desc,
                        "type": "dict",
                        "subtype": "roblox_nan_dict" if is_roblox_nan else "dict",
                        "is_roblox_nan": is_roblox_nan,
                        "severity": "CRITICAL",
                        "keys": list(rval.keys()),
                        "raw_value": rval,
                        "message": f"Root.{rf_name} received dictionary object {json.dumps(rval)} instead of a numeric value."
                    }
                    anomalies.append(anom)
                    snap_anomalies.append(anom)
                    anomalous_snapshots_set.add(ts)

        u1_st = st.get("Unit1", {}) if isinstance(st.get("Unit1"), dict) else {}
        u2_st = st.get("Unit2", {}) if isinstance(st.get("Unit2"), dict) else {}
        u1_dem_val = u1_st.get("DemandU1") if "DemandU1" in u1_st else u1_st.get("Demand")
        u2_dem_val = u2_st.get("DemandU2") if "DemandU2" in u2_st else u2_st.get("Demand")
        ensure_unit_fuel_level("Unit1", u1_st)
        ensure_unit_fuel_level("Unit2", u2_st)

        snapshots_summary.append({
            "timestamp": ts,
            "has_anomaly": len(snap_anomalies) > 0,
            "anomaly_count": len(snap_anomalies),
            "anomalies": snap_anomalies,
            "has_dict_demand": any(a["type"] == "dict" and "Demand" in a["field"] for a in snap_anomalies),
            "is_roblox_nan": any(a.get("is_roblox_nan") for a in snap_anomalies),
            "u1_demand_type": type(u1_dem_val).__name__ if u1_dem_val is not None else "None",
            "u1_demand_val": str(u1_dem_val) if not isinstance(u1_dem_val, (dict, list)) else json.dumps(u1_dem_val),
            "u2_demand_type": type(u2_dem_val).__name__ if u2_dem_val is not None else "None",
            "u2_demand_val": str(u2_dem_val) if not isinstance(u2_dem_val, (dict, list)) else json.dumps(u2_dem_val),
            "u1_aprm": u1_st.get("APRM", "N/A"),
            "u2_aprm": u2_st.get("APRM", "N/A"),
            "u1_out": u1_st.get("Output", u1_st.get("ElectricOutputMW", "N/A")),
            "u2_out": u2_st.get("Output", u2_st.get("ElectricOutputMW", "N/A")),
            "u1_fuel": u1_st.get("EstimatedFuel"),
            "u2_fuel": u2_st.get("EstimatedFuel"),
        })

    first_anom_snap = None
    if anomalous_snapshots_set:
        sorted_anom_ts = sorted(list(anomalous_snapshots_set))
        first_anom_snap = {
            "timestamp": sorted_anom_ts[0],
            "state": snapshots.get(sorted_anom_ts[0])
        }

    return {
        "total_snapshots": len(sorted_ts),
        "anomalous_snapshots_count": len(anomalous_snapshots_set),
        "total_anomalies": len(anomalies),
        "has_dict_demand": any(a["type"] == "dict" and "Demand" in a["field"] for a in anomalies),
        "anomalies": anomalies,
        "first_anomaly": anomalies[0] if anomalies else None,
        "first_anomalous_snapshot": first_anom_snap,
        "earliest_timestamp": sorted_ts[0] if sorted_ts else None,
        "latest_timestamp": sorted_ts[-1] if sorted_ts else None,
        "earliest_state": snapshots.get(sorted_ts[0]) if sorted_ts else None,
        "latest_state": snapshots.get(sorted_ts[-1]) if sorted_ts else None,
        "snapshots_summary": snapshots_summary,
    }

def diagnose_server_snapshots(job_id_query: str) -> dict[str, Any]:
    query = (job_id_query or "").strip()
    if not query:
        return {"found": False, "error": "No Server Job ID provided."}

    clean_q = query.lower()
    matched_job_id = None
    snapshots: dict[str, Any] = {}
    source_location = ""
    is_live = False

    if core._sc_latest_data and isinstance(core._sc_latest_data, dict):
        for s in core._sc_latest_data.get('data', {}).get('servers', []):
            jid = str(s.get('jobId') or "")
            if jid.lower() == clean_q or jid.lower().startswith(clean_q) or clean_q in jid.lower():
                matched_job_id = jid
                hb = s.get('lastHeartbeat') or datetime.now(timezone.utc).isoformat()
                snapshots[hb] = s.get('state') or {}
                source_location = "Live Memory Cache (core._sc_latest_data)"
                is_live = True
                break

    servers_data = get_sc_data("servers.json") or {}
    if not snapshots and isinstance(servers_data, dict):
        if query in servers_data:
            matched_job_id = query
            snapshots = dict(servers_data[query])
            source_location = "servers.json (active cache)"
        else:
            for jid, snaps in safe_dict_items(servers_data):
                if jid.lower() == clean_q or jid.lower().startswith(clean_q) or clean_q in jid.lower():
                    matched_job_id = jid
                    snapshots = dict(snaps)
                    source_location = "servers.json (active cache)"
                    break

    if not snapshots:
        idx_jid, date_str = lookup_archive_server_date(query)
        if idx_jid and date_str:
            matched_job_id = idx_jid
            for ext in (".json.gz", ".json"):
                target_rel = os.path.join("archives", f"servers_{date_str}{ext}")
                full_path = os.path.join(ARCHIVES_DIR, f"servers_{date_str}{ext}")
                if os.path.exists(full_path):
                    day_data = get_sc_data(target_rel)
                    if isinstance(day_data, dict) and idx_jid in day_data:
                        snapshots = dict(day_data[idx_jid])
                        source_location = f"data/archives/servers_{date_str}{ext} (via index)"
                        break

    if not snapshots and os.path.exists(ARCHIVES_DIR):
        try:
            archive_files = sorted(os.listdir(ARCHIVES_DIR), reverse=True)
            for fname in archive_files:
                if not (fname.endswith(".json") or fname.endswith(".json.gz")):
                    continue
                fpath = os.path.join(ARCHIVES_DIR, fname)
                try:
                    if fname.endswith(".gz"):
                        with gzip.open(fpath, "rt", encoding="utf-8") as gf:
                            day_data = json.load(gf)
                    else:
                        with open(fpath, "r", encoding="utf-8") as jf:
                            day_data = json.load(jf)
                    if isinstance(day_data, dict):
                        target_id = None
                        if query in day_data:
                            target_id = query
                        else:
                            for jid in day_data.keys():
                                if jid.lower() == clean_q or jid.lower().startswith(clean_q) or clean_q in jid.lower():
                                    target_id = jid
                                    break
                        if target_id and isinstance(day_data[target_id], dict):
                            matched_job_id = target_id
                            snapshots = dict(day_data[target_id])
                            source_location = f"data/archives/{fname} (archive file scan)"
                            break
                except Exception as arc_ex:
                    logger.debug(f"Error reading archive file {fname} during debug scan: {arc_ex}")
        except Exception as scan_ex:
            logger.warning(f"Error during deep archive scan for {query}: {scan_ex}")

    matching_errors = []
    try:
        errors_path = os.path.join(DATA_DIR, "errors.json")
        if os.path.exists(errors_path):
            with open(errors_path, "r", encoding="utf-8") as ef:
                err_content = json.load(ef)
                for err in err_content.get("errors", []):
                    err_str = json.dumps(err).lower()
                    if clean_q in err_str or (matched_job_id and matched_job_id.lower() in err_str):
                        matching_errors.append(err)
    except Exception:
        pass

    if not snapshots or not matched_job_id:
        return {
            "found": False,
            "query": query,
            "searched_locations": [
                "Memory Cache (core._sc_latest_data)",
                "servers.json",
                f"archives_index.json ({len(core._sc_archive_server_index)} index entries)",
                f"data/archives/ ({len(os.listdir(ARCHIVES_DIR)) if os.path.exists(ARCHIVES_DIR) else 0} archive files)",
            ],
            "matching_errors": matching_errors,
            "message": f"Server '{query}' was not located in any active storage tiers or archive files."
        }

    analysis = analyze_server_state_anomalies(snapshots)
    persistent_data = load_persistent_servers()
    is_persistent = matched_job_id in persistent_data.get("persistent", {})
    meta = snapshots.get("_meta") or core._sc_server_meta.get(matched_job_id, {})
    if not meta or not meta.get("snapshot_count"):
        meta = build_server_metadata(matched_job_id, snapshots, existing_meta=meta)
        core._sc_server_meta[matched_job_id] = meta
    clean_snapshots = {k: v for k, v in snapshots.items() if not str(k).startswith('_')}
    fuel_eval = evaluate_server_fuel(clean_snapshots)

    return {
        "found": True,
        "job_id": matched_job_id,
        "query": query,
        "source": source_location,
        "is_live": is_live,
        "is_persistent": is_persistent,
        "meta": meta,
        "snapshots": clean_snapshots,
        "fuel_assessment": fuel_eval.to_dict(),
        **analysis,
        "matching_errors": matching_errors,
    }

@app.route("/admin/debug", methods=["GET"])
@admin_required
def view_debug_dashboard(username):
    if not has_permission(username, "debug"):
        return redirect("/admin")
    discord_id = session.get("discord_id") or username
    notifier_cfg = get_admin_notifier_config(discord_id)
    initial_job_id = request.args.get("job_id") or request.args.get("server") or request.args.get("q") or ""
    return render_template(
        "admin_panel.html",
        username=username,
        discord_id=session.get("discord_id") or "",
        active_view="debug",
        is_root=is_root_user(username),
        permissions=get_user_permissions(username),
        me=admin_panel_identity(username),
        notifier=notifier_cfg,
        initial_debug_job_id=initial_job_id,
    )

@app.route("/admin/debug/server/<path:job_id>", methods=["GET"])
@admin_required
def api_debug_server(username, job_id):
    if not has_permission(username, "debug"):
        return jsonify({"detail": "Forbidden - Root privileges required"}), 403
    result = diagnose_server_snapshots(job_id)
    return jsonify(result)

@app.route("/admin/debug/analyze_payload", methods=["POST"])
@admin_required
def api_debug_analyze_payload(username):
    if not has_permission(username, "debug"):
        return jsonify({"detail": "Forbidden - Root privileges required"}), 403
    try:
        req_json = request.get_json(silent=True) or {}
    except Exception as e:
        return jsonify({"error": f"Invalid JSON body: {e}"}), 400

    payload = req_json.get("payload") if isinstance(req_json, dict) and "payload" in req_json else req_json
    server_raw = None
    if isinstance(payload, dict):
        if "state" in payload and isinstance(payload["state"], dict):
            server_raw = payload
            server_state = dict(payload["state"])
            hb = payload.get("lastHeartbeat") or datetime.now(timezone.utc).isoformat()
            snapshots = {hb: server_state}
            matched_job_id = str(payload.get("jobId") or payload.get("id") or req_json.get("job_id", "Custom Payload"))
        elif "Unit1" in payload or "Unit2" in payload:
            now_ts = datetime.now(timezone.utc).isoformat()
            snapshots = {now_ts: payload}
            matched_job_id = str(req_json.get("job_id", "Custom Payload")) if isinstance(req_json, dict) else "Custom Payload"
        else:
            snapshots = payload
            matched_job_id = str(req_json.get("job_id", "Custom Payload")) if isinstance(req_json, dict) else "Custom Payload"
    else:
        snapshots = {}
        matched_job_id = "Custom Payload"

    analysis = analyze_server_state_anomalies(snapshots)
    meta = build_server_metadata(matched_job_id, snapshots, server_raw=server_raw)
    return jsonify({
        "found": True,
        "job_id": matched_job_id,
        "source": "Custom Injected State Payload",
        "is_live": False,
        "is_persistent": False,
        "meta": meta,
        "snapshots": {k: v for k, v in snapshots.items() if not str(k).startswith('_')},
        **analysis,
        "matching_errors": []
    })

@app.route("/auth/discord/login", methods=["GET"])
def discord_login():
    client_id = os.environ.get("DISCORD_CLIENT_ID", "").strip()
    next_url = request.args.get("next") or request.referrer or "/tickets"
    if not next_url.startswith("/") or next_url.startswith("//") or next_url.startswith("/\\"):
        next_url = "/tickets"
        
    if not client_id:
        if next_url.startswith("/admin"):
            return render_template("admin_login.html", error="Discord OAuth2 is not configured on the server yet (DISCORD_CLIENT_ID missing in .env).", next_url=next_url), 500
        return render_template("tickets.html", tickets=get_public_tickets(), error="Discord OAuth2 is not configured on the server yet (DISCORD_CLIENT_ID missing in .env)."), 500

    state = secrets.token_hex(16)
    session["oauth_state"] = state
    session["oauth_next"] = next_url
    
    redirect_uri = get_discord_redirect_uri(request)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "identify applications.commands",
        "integration_type": "1",
        "state": state,
        "prompt": "consent"
    }
    auth_url = f"{DISCORD_OAUTH_AUTHORIZE_URL}?{urlencode(params)}"
    return redirect(auth_url)

@app.route("/auth/discord/callback", methods=["GET"])
def discord_callback():
    error_code = request.args.get("error")
    if error_code:
        err_desc = request.args.get("error_description") or "Authorization was cancelled or denied by Discord."
        next_dest = session.pop("oauth_next", None) or "/tickets"
        if next_dest.startswith("/admin"):
            return redirect(f"/admin/login?error={quote(err_desc)}")
        return redirect(f"/tickets?error={quote(err_desc)}")

    state = request.args.get("state")
    saved_state = session.pop("oauth_state", None)
    if not state or state != saved_state:
        next_dest = session.pop("oauth_next", None) or "/tickets"
        if next_dest.startswith("/admin"):
            return redirect(f"/admin/login?error={quote('OAuth state verification failed. Please try logging in again.')}")
        return redirect(f"/tickets?error={quote('OAuth state verification failed. Please try logging in again.')}")

    code = request.args.get("code")
    if not code:
        next_dest = session.pop("oauth_next", None) or "/tickets"
        return redirect(f"{next_dest}?error={quote('Missing authorization code from Discord.')}")

    client_id = os.environ.get("DISCORD_CLIENT_ID", "").strip()
    client_secret = os.environ.get("DISCORD_CLIENT_SECRET", "").strip()
    redirect_uri = get_discord_redirect_uri(request)

    if not client_id or not client_secret:
        return "Discord OAuth2 configuration incomplete on server.", 500

    token_payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        token_res = requests.post(DISCORD_OAUTH_TOKEN_URL, data=token_payload, headers=headers, timeout=10)
        if token_res.status_code != 200:
            logger.warning(f"[Discord OAuth] Token exchange failed: {token_res.status_code} {token_res.text}")
            next_dest = session.pop("oauth_next", None) or "/tickets"
            if next_dest.startswith("/admin"):
                return redirect(f"/admin/login?error={quote('Discord token exchange failed. Please verify credentials in .env.')}")
            return redirect(f"/tickets?error={quote('Failed to authenticate with Discord.')}")

        token_data = token_res.json()
        access_token = token_data.get("access_token")
        if not access_token:
            next_dest = session.pop("oauth_next", None) or "/tickets"
            return redirect(f"{next_dest}?error={quote('No access token received from Discord.')}")

        user_res = requests.get(
            f"{DISCORD_API_BASE}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )
        if user_res.status_code != 200:
            next_dest = session.pop("oauth_next", None) or "/tickets"
            return redirect(f"{next_dest}?error={quote('Failed to fetch Discord user profile.')}")

        user_data = user_res.json()
        d_id = str(user_data.get("id"))
        d_username = user_data.get("username", "")
        d_global_name = user_data.get("global_name") or d_username
        d_avatar = user_data.get("avatar")
        d_avatar_url = get_discord_avatar_url(d_id, d_avatar)

        discord_user_obj = {
            "id": d_id,
            "username": d_username,
            "global_name": d_global_name,
            "avatar": d_avatar,
            "avatar_url": d_avatar_url
        }
        session["session_v"] = CURRENT_SESSION_VERSION
        session["discord_user"] = discord_user_obj

        next_dest = session.pop("oauth_next", None) or "/tickets"
        if not next_dest.startswith("/") or next_dest.startswith("//") or next_dest.startswith("/\\"):
            next_dest = "/tickets"

        root_ids = get_root_discord_ids()
        is_root = (d_id in root_ids)
        admins_data = load_admins()
        is_admin = is_root or (d_id in admins_data.get("admins", {}))

        auth_username = d_username or d_id
        if next_dest.startswith("/admin"):
            if is_admin:
                session.permanent = True
                session["admin_logged_in"] = True
                session["discord_id"] = d_id
                session["username"] = auth_username
                session["is_root"] = is_root
                if d_id in admins_data.get("admins", {}):
                    admins_data["admins"][d_id]["username"] = auth_username
                    admins_data["admins"][d_id]["display_name"] = d_global_name or auth_username
                    admins_data["admins"][d_id]["avatar_url"] = d_avatar_url
                    save_admins(admins_data)
                log_audit_event("auth.discord_login", "auth", f"Administrator logged in via Discord OAuth: @{auth_username} (ID: {d_id})", target=f"@{auth_username}", username=auth_username)
                return redirect(next_dest)
            else:
                log_audit_event("auth.discord_denied", "auth", f"Unauthorized Discord user attempted admin login: @{auth_username} (ID: {d_id})", target=f"@{auth_username}", username=auth_username)
                return redirect(f"/admin/login?error={quote(f'Access Denied: Discord user @{auth_username} (ID: {d_id}) is not an authorized administrator. Please contact Root.')}")

        if is_admin:
            session.permanent = True
            session["admin_logged_in"] = True
            session["discord_id"] = d_id
            session["username"] = auth_username
            session["is_root"] = is_root

        return redirect(next_dest)

    except Exception as e:
        logger.error(f"[Discord OAuth] Exception during callback: {e}", exc_info=True)
        next_dest = session.pop("oauth_next", None) or "/tickets"
        return redirect(f"{next_dest}?error={quote(f'Internal OAuth error: {str(e)}')}")

@app.route("/auth/discord/logout", methods=["GET"])
def discord_logout():
    session.clear()
    next_url = request.args.get("next") or request.referrer or "/tickets"
    if not next_url.startswith("/") or next_url.startswith("//") or next_url.startswith("/\\"):
        next_url = "/tickets"
    return redirect(next_url)

@app.route("/admin/contact/delete/<msg_id>", methods=["POST"])
@admin_required
def delete_contact_message(username, msg_id):
    if not has_permission(username, "contact"):
        return jsonify({"detail": "Permission denied for contact messages section"}), 403
    contact_data = load_contact_messages()
    messages = contact_data.get("messages", [])
    filtered = [m for m in messages if m.get("id") != msg_id]
    if len(filtered) == len(messages):
        return jsonify({"detail": "Message not found"}), 404
    save_contact_messages({"messages": filtered})
    broadcast_update("dashboard")
    log_audit_event("contact.delete", "contact", f"Deleted contact message #{msg_id}", target=f"Message #{msg_id}", details={"msg_id": msg_id}, username=username)
    return jsonify({"success": True})

@app.route("/admin/contact/read/<msg_id>", methods=["POST"])
@admin_required
def toggle_read_contact_message(username, msg_id):
    if not has_permission(username, "contact"):
        return jsonify({"detail": "Permission denied for contact messages section"}), 403
    contact_data = load_contact_messages()
    messages = contact_data.get("messages", [])
    found = False
    for m in messages:
        if m.get("id") == msg_id:
            m["read"] = not m.get("read", False)
            found = True
            break
    if not found:
        return jsonify({"detail": "Message not found"}), 404
    save_contact_messages({"messages": messages})
    broadcast_update("dashboard")
    log_audit_event("contact.mark_read", "contact", f"Toggled read state for contact message #{msg_id}", target=f"Message #{msg_id}", details={"msg_id": msg_id}, username=username)
    return jsonify({"success": True})

_login_attempts = {}

def is_login_rate_limited(ip: str) -> bool:
    if ip == "unknown":
        return False
    now = datetime.now(timezone.utc)
    attempts = _login_attempts.setdefault(ip, [])
    attempts[:] = [t for t in attempts if now - t < timedelta(minutes=1)]
    return len(attempts) >= 5

def record_login_attempt(ip: str):
    if ip != "unknown":
        _login_attempts.setdefault(ip, []).append(datetime.now(timezone.utc))

def clear_login_attempts(ip: str):
    if ip in _login_attempts:
        del _login_attempts[ip]

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = request.args.get("error")
    next_url = request.args.get("next") or request.form.get("next") or "/admin"
    
    ip = request.remote_addr or "unknown"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
        
    if is_ip_banned(ip):
        return render_template("admin_login.html", error="Your IP is banned.", next_url=next_url), 403
        
    discord_client_id = os.environ.get("DISCORD_CLIENT_ID", "").strip()
    discord_login_url = f"/auth/discord/login?next={quote(next_url)}"
    
    if request.method == "POST":
        origin = request.headers.get("Origin")
        referer = request.headers.get("Referer")
        host_url = get_host_url(request)
        
        origin_ok = True
        if origin:
            origin_ok = (origin.rstrip('/') == host_url)
        elif referer:
            origin_ok = referer.startswith(host_url)
        else:
            origin_ok = False
            
        if not origin_ok:
            return render_template("admin_login.html", error="CSRF verification failed - Same origin required.", next_url=next_url, discord_login_url=discord_login_url, discord_configured=bool(discord_client_id)), 403
            
        if is_login_rate_limited(ip):
            return render_template("admin_login.html", error="Too many login attempts. Please try again in 1 minute.", next_url=next_url, discord_login_url=discord_login_url, discord_configured=bool(discord_client_id)), 429

        captcha_ok, captcha_err = verify_turnstile_token(extract_turnstile_token(), ip)
        if not captcha_ok:
            return render_template("admin_login.html", error=captcha_err, next_url=next_url, discord_login_url=discord_login_url, discord_configured=bool(discord_client_id)), 400

        username = request.form.get("username", "")
        password = request.form.get("password", "")
        
        root_user, root_pass = get_admin_credentials()
        is_root_username = safe_compare_digest(username, root_user)
        is_root_password = safe_compare_digest(password, root_pass)
        
        authenticated = False
        if is_root_username and is_root_password:
            authenticated = True
        else:
            admins_data = load_admins()
            admin_info = admins_data.get("admins", {}).get(username)
            if admin_info:
                stored_hash = admin_info.get("password_hash")
                if stored_hash and verify_password(stored_hash, password):
                    authenticated = True
                    
        if authenticated:
            clear_login_attempts(ip)
            
            session.clear()
            session.permanent = True
            session["session_v"] = CURRENT_SESSION_VERSION
            session["admin_logged_in"] = True
            session["username"] = username
            session["is_root"] = is_root_user(username)
            log_audit_event("auth.login", "auth", f"Administrator logged in via username/password: {username}", target=username, username=username, ip=ip)
            
            if not next_url.startswith("/") or next_url.startswith("//") or next_url.startswith("/\\"):
                next_url = "/admin"
            return redirect(next_url)
        else:
            record_login_attempt(ip)
            log_audit_event("auth.login_failed", "auth", f"Failed admin login attempt for user: '{username}'", target=username, username=username, ip=ip)
            error = "Invalid username or secret key credentials. Note: Admins are required to authenticate with Discord."
            
    return render_template(
        "admin_login.html",
        error=error,
        next_url=next_url,
        discord_login_url=discord_login_url,
        discord_configured=bool(discord_client_id)
    )

@app.route("/admin/logout", methods=["GET"])
def admin_logout():
    uname = session.get("username") or "Administrator"
    log_audit_event("auth.logout", "auth", f"Administrator logged out: {uname}", target=uname, username=uname)
    session.clear()
    return redirect("/admin/login")

_singleton_socket = None

def close_singleton_socket():
    global _singleton_socket
    if _singleton_socket:
        try:
            _singleton_socket.close()
        except Exception:
            pass
        _singleton_socket = None

def is_singleton():
    global _singleton_socket
    if _singleton_socket is not None:
        return True
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('127.0.0.1', 8405))
        s.listen(1)
        _singleton_socket = s
        return True
    except Exception:
        return False

def start_console_handler():
    if not is_singleton():
        return
        
    try:
        from cli_ih import InputHandler, safe_print
        import subprocess
        import signal
        import sys
        import time
        
        handler = InputHandler(logger=app.logger)
        
        @handler.command(name="update", description="Updates the web server and pulls latest code from origin.")
        def update_cmd():
            safe_print("Updating the web server and pulling changes...")
            try:
                if os.path.exists(".git"):
                    safe_print("Git repository found, pulling changes...")
                    subprocess.run("git config core.sparseCheckout true", shell=True, check=False)
                    sparse_file = os.path.join(".git", "info", "sparse-checkout")
                    os.makedirs(os.path.dirname(sparse_file), exist_ok=True)
                    with open(sparse_file, "w", encoding="utf-8") as f:
                        f.write("server/*\nbot/*\n")
                    
                    subprocess.run("git fetch origin main", shell=True, check=False)
                    subprocess.run("git checkout origin/main -- server bot", shell=True, check=False)
                    subprocess.run("git pull origin main", shell=True, check=False)
                
                if os.path.exists("server"):
                    safe_print("Copying server files...")
                    subprocess.run("cp -a server/. . && rm -rf server", shell=True, check=False)
                if os.path.exists("bot"):
                    safe_print("Bot directory ready.")
                    if os.path.exists(os.path.join("bot", "bot.py")):
                        subprocess.run("cp -a bot/bot.py .", shell=True, check=False)
            except Exception as e:
                safe_print(f"Error during git pull/copy: {e}")
                
            try:
                is_gunicorn = "gunicorn" in os.environ.get("SERVER_SOFTWARE", "").lower()
                close_singleton_socket()
                if is_gunicorn:
                    safe_print("Sending SIGHUP to Gunicorn master process...")
                    os.kill(os.getppid(), signal.SIGHUP)
                else:
                    safe_print("Restarting local Flask server via execv...")
                    time.sleep(0.2)
                    os.execv(sys.executable, [sys.executable] + sys.argv)
            except Exception as e:
                safe_print(f"Error restarting server: {e}")

        @handler.command(name="test_notification", description="Sends a test notification DM to a user: test_notification <user_id> [message]")
        @handler.command(name="test_notify", description="Alias for test_notification: test_notify <user_id> [message]")
        @handler.command(name="notify", description="Alias for test_notification: notify <user_id> [message]")
        def test_notification_cmd(user_id: str = "", *args):
            user_id = user_id.strip()
            if not user_id:
                safe_print("Usage: test_notification <user_id> [optional message]")
                return

            custom_msg = " ".join(args).strip() if args else None
            safe_print(f"Sending test notification to Discord user {user_id}...")

            try:
                success, info = send_test_notification_dm(user_id, custom_msg)
                if success:
                    safe_print(f"[SUCCESS] {info}")
                else:
                    safe_print(f"[ERROR] {info}")
            except Exception as ex:
                safe_print(f"[ERROR] Failed to execute test notification: {ex}")

        @handler.command(name="api_status", description="Shows status, PID, port, and live health of the FastAPI subservice.")
        def api_status_cmd():
            st = get_api_subservice_status(probe_http=True)
            mode = "managed" if st["managed_process_running"] else ("external" if st["port_open"] else "stopped")
            safe_print(
                f"[API] mode={mode} | port={st['port']} (open={st['port_open']}) | "
                f"pid={st['pid']} | supervisor={st['supervisor_active']} | disabled={st['disabled']}"
            )
            if st["health"]:
                h = st["health"]
                safe_print(
                    f"[API] health={h.get('status')} | version={h.get('version')} | uptime={h.get('uptime')}"
                )
            elif st["health_error"]:
                safe_print(f"[API] health_error={st['health_error']}")

        @handler.command(name="api_health", description="Probes /api/status, /api/grid/summary, and /api/openapi.json with latency.")
        def api_health_cmd():
            port = _get_api_port()
            for ep in ("/api/status", "/api/grid/summary", "/api/openapi.json"):
                t0 = time.perf_counter()
                try:
                    resp = requests.get(f"http://127.0.0.1:{port}{ep}", timeout=3.0)
                    ms = round((time.perf_counter() - t0) * 1000, 1)
                    safe_print(f"[API] GET {ep} -> HTTP {resp.status_code} ({ms} ms)")
                except Exception as ex:
                    ms = round((time.perf_counter() - t0) * 1000, 1)
                    safe_print(f"[API] GET {ep} -> ERROR ({ms} ms): {ex}")

        @handler.command(name="api_start", description="Starts the managed FastAPI subservice if not already running.")
        def api_start_cmd():
            ok, msg = start_api_subservice()
            safe_print(f"[{'OK' if ok else 'WARN'}] {msg}")

        @handler.command(name="api_stop", description="Stops the managed FastAPI subservice and pauses auto-restart.")
        def api_stop_cmd():
            ok, msg = stop_api_subservice()
            safe_print(f"[{'OK' if ok else 'WARN'}] {msg}")

        @handler.command(name="api_restart", description="Restarts the managed FastAPI subservice.")
        def api_restart_cmd():
            ok, msg = restart_api_subservice()
            safe_print(f"[{'OK' if ok else 'WARN'}] {msg}")

        @handler.command(name="api_refresh", description="Triggers POST /api/servers/refresh using API_REFRESH_KEY.")
        def api_refresh_cmd():
            port = _get_api_port()
            key = (os.environ.get("API_REFRESH_KEY") or os.environ.get("RBWR_API_KEY") or "").strip()
            if not key:
                safe_print("[ERROR] API_REFRESH_KEY is not configured in environment.")
                return
            try:
                resp = requests.post(
                    f"http://127.0.0.1:{port}/api/servers/refresh",
                    headers={"X-API-Key": key},
                    timeout=15.0,
                )
                safe_print(f"[API] POST /api/servers/refresh -> HTTP {resp.status_code}: {resp.text[:200]}")
            except Exception as ex:
                safe_print(f"[ERROR] Failed to reach API refresh endpoint: {ex}")

        handler.start()
    except Exception:
        pass

# ==============================================================================
# Standalone FastAPI REST Service Supervisor & /api/* Reverse Proxy
# ==============================================================================

API_SCRIPT_PATH = os.path.join(BASE_DIR, "api.py")
_api_process = None
_api_supervisor_thread = None
_api_supervisor_started = False
_api_shutting_down = False
_api_immediate_restart = False
_api_supervisor_lock = threading.Lock()
_HOP_BY_HOP_HEADERS = frozenset({
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-encoding",
    "content-length",
})

def _get_api_port() -> int:
    try:
        return int(os.environ.get("API_PORT", "8401"))
    except ValueError:
        return 8401

def _is_local_port_open(port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False

def _stop_api_subprocess():
    global _api_shutting_down, _api_process
    _api_shutting_down = True
    proc = _api_process
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    _api_process = None

atexit.register(_stop_api_subprocess)

def _api_supervisor_loop():
    global _api_process, _api_immediate_restart, _api_supervisor_started
    backoff = 1.0
    spawned_once = False
    while not _api_shutting_down:
        if not os.path.exists(API_SCRIPT_PATH):
            break
        api_host = os.environ.get("API_HOST", "0.0.0.0")
        api_port = _get_api_port()
        if not spawned_once:
            if _is_local_port_open(api_port):
                logger.info(f"[REST API] Detected existing listener on 127.0.0.1:{api_port}; proxying /api/* to it.")
                break
        else:
            close_deadline = time.time() + 2.0
            while _is_local_port_open(api_port, timeout=0.1) and time.time() < close_deadline:
                time.sleep(0.1)

        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "api:app",
            "--host",
            api_host,
            "--port",
            str(api_port),
            "--log-level",
            "warning",
        ]
        try:
            proc = subprocess.Popen(cmd, cwd=BASE_DIR)
            _api_process = proc
            spawned_once = True
            logger.info(f"[REST API] Started api.py Uvicorn subprocess (PID {proc.pid}) on {api_host}:{api_port}")
            backoff = 1.0
            exit_code = proc.wait()
            if _api_shutting_down:
                break
            if _api_immediate_restart:
                _api_immediate_restart = False
                logger.info("[REST API] Restarting api.py Uvicorn subprocess...")
                continue
            logger.warning(f"[REST API] Uvicorn subprocess exited with code {exit_code}; restarting in {backoff:.0f}s.")
        except Exception as e:
            logger.error(f"[REST API] Failed to launch api.py subprocess: {e}")

        time.sleep(backoff)
        backoff = min(backoff * 2, 15.0)
    with _api_supervisor_lock:
        _api_supervisor_started = False


def get_api_subservice_status(probe_http: bool = True) -> dict:
    port = _get_api_port()
    proc = _api_process
    pid = proc.pid if proc is not None else None
    running = proc is not None and proc.poll() is None
    returncode = None if proc is None else proc.poll()
    port_open = _is_local_port_open(port, timeout=0.3)

    info = {
        "host": os.environ.get("API_HOST", "0.0.0.0"),
        "port": port,
        "script_exists": os.path.exists(API_SCRIPT_PATH),
        "disabled": os.environ.get("DISABLE_API_PROCESS") == "1",
        "supervisor_active": bool(_api_supervisor_started and _api_supervisor_thread and _api_supervisor_thread.is_alive()),
        "shutting_down": _api_shutting_down,
        "managed_process_running": running,
        "pid": pid,
        "returncode": returncode,
        "port_open": port_open,
        "health": None,
        "health_error": None,
    }
    if probe_http and port_open:
        try:
            resp = requests.get(f"http://127.0.0.1:{port}/api/status", timeout=2.0)
            if resp.status_code == 200:
                info["health"] = resp.json()
            else:
                info["health_error"] = f"HTTP {resp.status_code}"
        except Exception as e:
            info["health_error"] = str(e)
    return info


def start_api_subservice() -> tuple[bool, str]:
    global _api_shutting_down, _api_supervisor_started
    if os.environ.get("DISABLE_API_PROCESS") == "1":
        return False, "API subprocess is disabled via DISABLE_API_PROCESS=1."
    if not os.path.exists(API_SCRIPT_PATH):
        return False, f"api.py not found at {API_SCRIPT_PATH}."
    port = _get_api_port()
    with _api_supervisor_lock:
        _api_shutting_down = False
        if _api_process is not None and _api_process.poll() is None:
            return True, f"API subservice is already running (PID {_api_process.pid}, port {port})."
        if _is_local_port_open(port, timeout=0.25):
            return True, f"External API listener already active on 127.0.0.1:{port}."
        if _api_supervisor_thread is None or not _api_supervisor_thread.is_alive():
            _api_supervisor_started = False

    start_api_subprocess()
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if _is_local_port_open(port, timeout=0.2):
            pid = _api_process.pid if _api_process else None
            return True, f"API subservice started (PID {pid}, port {port})."
        time.sleep(0.15)
    return False, f"API subservice launch requested, but 127.0.0.1:{port} did not open within 5s."


def stop_api_subservice() -> tuple[bool, str]:
    proc = _api_process
    pid = proc.pid if proc is not None else None
    was_running = proc is not None and proc.poll() is None
    _stop_api_subprocess()
    if was_running:
        return True, f"Stopped managed API subservice (PID {pid})."
    port = _get_api_port()
    if _is_local_port_open(port, timeout=0.2):
        return False, f"No managed API subprocess was running, but an external process is still listening on 127.0.0.1:{port}."
    return True, "API subservice is already stopped."


def restart_api_subservice() -> tuple[bool, str]:
    global _api_immediate_restart, _api_shutting_down
    if os.environ.get("DISABLE_API_PROCESS") == "1":
        return False, "API subprocess is disabled via DISABLE_API_PROCESS=1."
    port = _get_api_port()
    proc = _api_process
    if proc is not None and proc.poll() is None and _api_supervisor_thread is not None and _api_supervisor_thread.is_alive():
        _api_shutting_down = False
        _api_immediate_restart = True
        old_pid = proc.pid
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        deadline = time.time() + 5.0
        while time.time() < deadline:
            new_proc = _api_process
            if new_proc is not None and new_proc.pid != old_pid and new_proc.poll() is None and _is_local_port_open(port, timeout=0.2):
                return True, f"Restarted API subservice (old PID {old_pid} -> new PID {new_proc.pid}, port {port})."
            time.sleep(0.15)
        return False, f"Terminated old API process (PID {old_pid}), waiting for port {port} to reopen."

    return start_api_subservice()

def start_api_subprocess():
    global _api_supervisor_started, _api_supervisor_thread
    with _api_supervisor_lock:
        if _api_supervisor_started:
            return
        if os.environ.get("DISABLE_API_PROCESS") == "1":
            return
        if "unittest" in sys.modules:
            return
        if not os.path.exists(API_SCRIPT_PATH):
            return
        is_reloader_active = os.environ.get("WERKZEUG_RUN_MAIN") is not None
        if is_reloader_active and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
            return

        _api_supervisor_started = True
        _api_supervisor_thread = threading.Thread(
            target=_api_supervisor_loop,
            daemon=True,
            name="APISupervisorThread",
        )
        _api_supervisor_thread.start()

@app.before_request
def ensure_api_subprocess():
    if not _api_supervisor_started:
        start_api_subprocess()

@app.route("/api", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
@app.route("/api/<path:subpath>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
def proxy_api_request(subpath: str = ""):
    if not _api_supervisor_started:
        start_api_subprocess()

    api_port = _get_api_port()
    if _api_supervisor_started and not _is_local_port_open(api_port, timeout=0.15):
        deadline = time.time() + 4.0
        while time.time() < deadline:
            if _is_local_port_open(api_port, timeout=0.2):
                break
            time.sleep(0.1)

    target_path = f"/api/{subpath}" if subpath else "/api"
    qs = request.query_string.decode("utf-8", errors="replace") if request.query_string else ""
    upstream_url = f"http://127.0.0.1:{api_port}{target_path}"
    if qs:
        upstream_url = f"{upstream_url}?{qs}"

    fwd_headers = {}
    for k, v in request.headers.items():
        lk = k.lower()
        if lk in _HOP_BY_HOP_HEADERS or lk in ("host", "accept-encoding"):
            continue
        fwd_headers[k] = v

    client_ip = get_client_ip()
    existing_xff = request.headers.get("X-Forwarded-For", "").strip()
    if existing_xff:
        fwd_headers["X-Forwarded-For"] = existing_xff
    elif client_ip:
        fwd_headers["X-Forwarded-For"] = client_ip
    fwd_headers["X-Forwarded-Host"] = request.host
    fwd_headers["X-Forwarded-Proto"] = request.scheme
    fwd_headers["Accept-Encoding"] = "identity"

    try:
        upstream_resp = requests.request(
            method=request.method,
            url=upstream_url,
            headers=fwd_headers,
            data=request.get_data(),
            stream=True,
            allow_redirects=False,
            timeout=(5, 60),
        )
    except requests.RequestException as e:
        logger.warning(f"[REST API Proxy] Failed reaching 127.0.0.1:{api_port}{target_path}: {e}")
        return jsonify({
            "success": False,
            "detail": "REST API service is currently unavailable.",
        }), 503

    resp_headers = [
        (k, v)
        for k, v in upstream_resp.headers.items()
        if k.lower() not in _HOP_BY_HOP_HEADERS
    ]

    content_type = upstream_resp.headers.get("Content-Type", "")
    is_sse = "text/event-stream" in content_type.lower()

    if is_sse:
        def _stream_sse():
            try:
                for chunk in upstream_resp.iter_content(chunk_size=1):
                    if chunk:
                        yield chunk
            finally:
                upstream_resp.close()

        return Response(
            _stream_sse(),
            status=upstream_resp.status_code,
            headers=resp_headers,
            direct_passthrough=True,
        )

    def _stream_body():
        try:
            for chunk in upstream_resp.iter_content(chunk_size=65536):
                if chunk:
                    yield chunk
        finally:
            upstream_resp.close()

    return Response(
        _stream_body(),
        status=upstream_resp.status_code,
        headers=resp_headers,
    )

start_console_handler()

if __name__ == "__main__":
    import sys
    
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    host = os.environ.get("HOST", "0.0.0.0")
    try:
        port = int(os.environ.get("SERVER_PORT", "8400"))
    except ValueError:
        port = 8400
        
    start_server_checker_worker()
    start_api_subprocess()
    app.run(host=host, port=port, debug=False)