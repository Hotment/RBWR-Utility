from flask import Flask, request, jsonify, send_from_directory, redirect, Response, render_template, session, has_request_context
from pydantic import BaseModel, Field, ValidationError
import os
import json
import gzip
orjson = None
try:
    import orjson
except ImportError:
    pass

def _json_dumps(obj):
    if orjson: 
        return orjson.dumps(obj)
    return json.dumps(obj).encode("utf-8")

def _json_loads(b):
    if orjson:
        return orjson.loads(b)
    if isinstance(b, (bytes, bytearray)):
        return json.loads(b.decode("utf-8"))
    return json.loads(b)

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
import asyncio
import disnake
from disnake.ext import commands
from flask_sock import Sock
from werkzeug.middleware.proxy_fix import ProxyFix

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILES_DIR = os.path.join(BASE_DIR, "files")
DATA_DIR = os.path.join(BASE_DIR, "data")
ARCHIVES_DIR = os.path.join(DATA_DIR, "archives")
VERSIONS_FILE = os.path.join(BASE_DIR, "versions.json")
SUGGESTIONS_FILE = os.path.join(BASE_DIR, "suggestions.json")
CONTACT_MESSAGES_FILE = os.path.join(BASE_DIR, "contact_messages.json")
BANNED_FILE = os.path.join(BASE_DIR, "banned_ips.json")
CRASHES_FILE = os.path.join(BASE_DIR, "crashes.json")
ADMINS_FILE = os.path.join(BASE_DIR, "admins.json")
ENV_FILE = os.path.join(BASE_DIR, ".env")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

os.makedirs(FILES_DIR, exist_ok=True)
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
            "permissions": info.get("permissions") or {
                "suggestions": True,
                "crashes": True,
                "contact": True,
                "bans": True,
                "servers": True
            },
            "notifier": info.get("notifier") or {
                "enabled": False,
                "categories": ["overlay", "point_graph", "server_checker", "general"]
            }
        })
    return {"admins": admins_list}

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
            "accounts": get_accounts_payload_data() if is_root_user(username) else None
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
        "[SECURITY] ADMIN_USERNAME or ADMIN_PASSWORD is not set in the environment/dotenv. "
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
        return secrets.compare_digest(key, new_key)
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
    if root_user and secrets.compare_digest(ident_str, root_user):
        return True

    if has_request_context():
        try:
            if session.get("admin_logged_in") and session.get("is_root"):
                sess_user = str(session.get("username") or "")
                sess_discord = str(session.get("discord_id") or "")
                if (sess_user and secrets.compare_digest(sess_user, ident_str)) or (sess_discord and sess_discord == ident_str):
                    return True
        except Exception:
            pass

    return False

def get_user_permissions(user_identifier: str) -> dict:
    if not user_identifier:
        return {"suggestions": False, "crashes": False, "contact": False, "bans": False, "servers": False}
    if is_root_user(user_identifier):
        return {"suggestions": True, "crashes": True, "contact": True, "bans": True, "servers": True}
    
    admins_data = load_admins()
    admins_dict = admins_data.get("admins", {})
    admin_info = admins_dict.get(str(user_identifier))
    if not admin_info:
        for k, v in admins_dict.items():
            if v.get("username") == user_identifier or v.get("discord_id") == user_identifier:
                admin_info = v
                break
                
    if not admin_info:
        return {"suggestions": False, "crashes": False, "contact": False, "bans": False, "servers": False}
        
    perms = admin_info.get("permissions")
    if perms is None:
        return {"suggestions": True, "crashes": True, "contact": True, "bans": True, "servers": True}
    return {
        "suggestions": bool(perms.get("suggestions", True)),
        "crashes": bool(perms.get("crashes", True)),
        "contact": bool(perms.get("contact", True)),
        "bans": bool(perms.get("bans", True)),
        "servers": bool(perms.get("servers", True))
    }

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

disnake_bot: commands.Bot | None = None
disnake_bot_loop: asyncio.AbstractEventLoop | None = None

DISCORD_TICKETS_CATEGORY_ID = os.environ.get("DISCORD_TICKETS_CATEGORY_ID", "1547529007334162432").strip()
DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "1547514559097733141").strip()

def create_discord_ticket_channel(ticket: dict) -> str | None:
    if not disnake_bot or not disnake_bot.is_ready() or not disnake_bot_loop or not disnake_bot_loop.is_running():
        logger.warning("[Disnake Channel] Disnake bot is not ready; cannot create ticket channel.")
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

    async def _create_async():
        if not disnake_bot:
            return None
            
        guild_id = int(DISCORD_GUILD_ID)
        guild = disnake_bot.get_guild(guild_id)
        if not guild:
            guild = await disnake_bot.fetch_guild(guild_id)
        
        cat_id = int(DISCORD_TICKETS_CATEGORY_ID)
        category = disnake_bot.get_channel(cat_id)
        if not category:
            try:
                category = await disnake_bot.fetch_channel(cat_id)
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
        embed.add_field(name="Admin Replies", value="Type any message in this channel to send a reply directly to the ticket author. When the author replies on the website, their message will appear here in real time.", inline=False)
        embed.set_footer(text=f"RBWR Utility Ticket #{ticket_id}")

        await ch.send(embed=embed)
        return str(ch.id)

    try:
        future = asyncio.run_coroutine_threadsafe(_create_async(), disnake_bot_loop)
        channel_id = future.result(timeout=10)
        logger.info(f"[Disnake Channel] Created Discord channel #{channel_name} ({channel_id}) for ticket #{ticket_id}")
        return channel_id
    except Exception as ex:
        logger.error(f"[Disnake Channel] Error creating channel: {ex}", exc_info=True)
        return None

def run_disnake_bot():
    """
    Runs the Disnake Discord Bot inside an asyncio event loop in a dedicated background daemon thread.
    Handles real-time gateway events (on_message) for sub-second admin reply ingestion from ticket channels.
    """
    global disnake_bot, disnake_bot_loop
    bot_token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not bot_token:
        logger.warning("[Disnake Bot] DISCORD_BOT_TOKEN is not configured; Disnake bot is disabled.")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    disnake_bot_loop = loop

    intents = disnake.Intents.default()
    intents.message_content = True
    intents.guilds = True

    bot = commands.Bot(command_prefix=commands.when_mentioned_or("!"), intents=intents)
    disnake_bot = bot

    @bot.event
    async def on_ready():
        logger.info(f"[Disnake Bot] Connected and active as {bot.user} (ID: {bot.user.id})")

    @bot.event
    async def on_message(message: disnake.Message):
        if not message.guild or message.author.bot:
            return
        if bot.user and message.author.id == bot.user.id:
            return

        cat_id = str(getattr(message.channel, "category_id", "") or "")
        target_cat_id = str(DISCORD_TICKETS_CATEGORY_ID).strip()
        ch_id = str(message.channel.id)

        data = load_suggestions()
        suggestions = data.get("suggestions", [])
        
        target_ticket = None
        for s in suggestions:
            if str(s.get("discord_channel_id", "")) == ch_id:
                target_ticket = s
                break

        if not target_ticket and cat_id != target_cat_id:
            return

        if not target_ticket and cat_id == target_cat_id:
            ch_name = getattr(message.channel, "name", "")
            for s in suggestions:
                if f"ticket-{s.get('id')}" in ch_name or f"bug-{s.get('id')}" in ch_name:
                    target_ticket = s
                    target_ticket["discord_channel_id"] = ch_id
                    break

        if not target_ticket:
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

        sender_name = message.author.display_name or getattr(message.author, "global_name", None) or message.author.name or "Administrator"
        sender_discord_id = str(message.author.id)
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
        save_suggestions(data)
        broadcast_update("dashboard")

        logger.info(f"[Disnake Bot] Ingested admin reply from #{getattr(message.channel, 'name', ch_id)} (Author: {sender_name}) for ticket #{target_ticket.get('id')}")

        try:
            await message.add_reaction("📨")
        except Exception:
            pass

        broadcast_ticket_update(
            target_ticket.get("id"),
            new_msg_obj,
            messages,
            target_ticket.get("discord_id"),
            target_ticket.get("anonymous")
        )

    try:
        loop.run_until_complete(bot.start(bot_token))
    except disnake.errors.PrivilegedIntentsRequired:
        logger.warning("[Disnake Bot] Privileged Message Content Intent is disabled in Discord Developer Portal. Retrying with basic intents...")
        try:
            intents.message_content = False
            bot = commands.Bot(command_prefix=commands.when_mentioned_or("!"), intents=intents)
            disnake_bot = bot
            loop.run_until_complete(bot.start(bot_token))
        except Exception as retry_err:
            logger.error(f"[Disnake Bot] Fallback start failed: {retry_err}")
    except Exception as e:
        logger.error(f"[Disnake Bot] Bot encountered error: {e}", exc_info=True)

threading.Thread(target=run_disnake_bot, daemon=True, name="DisnakeBotThread").start()

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
        is_root_username = secrets.compare_digest(auth.username, root_user)
        is_root_password = secrets.compare_digest(auth.password, root_pass)
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
            if request.path.startswith("/admin/suggestions/status") or \
               request.path.startswith("/admin/suggestions/comment") or \
               request.path.startswith("/admin/suggestions/delete") or \
               request.path.startswith("/admin/suggestions/ban") or \
               request.path.startswith("/admin/suggestions/unban"):
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
                is_correct_username = secrets.compare_digest(auth.username, correct_user)
                is_correct_password = secrets.compare_digest(auth.password, correct_pass)
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

def load_versions():
    if not os.path.exists(VERSIONS_FILE):
        default_data = {
            "latest": "1.4.1",
            "versions": {
                "1.4.1": {
                    "version": "1.4.1",
                    "filename": "rbwr_overlay_v1.4.1.exe",
                    "release_date": "2026-06-04",
                    "notes": "Dynamic facility usage integration and UI enhancements."
                }
            }
        }
        with open(VERSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=4)
        return default_data
    
    with open(VERSIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def load_suggestions():
    if not os.path.exists(SUGGESTIONS_FILE):
        return {"suggestions": []}
    with open(SUGGESTIONS_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {"suggestions": []}

def save_suggestions(data):
    with open(SUGGESTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

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
    data = load_suggestions()
    suggestions = data.get("suggestions", [])
    public_list = []
    
    is_admin = False
    current_discord_id = None
    if has_request_context():
        try:
            is_admin = bool(session.get("admin_logged_in"))
            discord_user = session.get("discord_user") or {}
            current_discord_id = str(discord_user.get("id") or "")
        except Exception:
            pass

    for s in sorted(suggestions, key=lambda x: x.get("timestamp", ""), reverse=True):
        if s.get("hidden"):
            continue
        is_anon = bool(s.get("anonymous")) or (s.get("name") or "").lower() == "anonymous"
        pub_name = "Anonymous" if is_anon else (s.get("name") or "Anonymous")
        pub_avatar = None if is_anon else s.get("discord_avatar")
        raw_text = s.get("suggestion") or s.get("description", "")
        
        ticket_discord_id = str(s.get("discord_id") or "")
        is_author = bool(current_discord_id and ticket_discord_id and current_discord_id == ticket_discord_id and not is_anon)
        
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
            "messages_count": messages_count
        })
    return public_list


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
    id: int

class CrashStatusPayload(BaseModel):
    id: int
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
    data = load_versions()
    latest_ver = data.get("latest", "1.5.5")
    latest_meta = data.get("versions", {}).get(latest_ver, {})
    release_date = latest_meta.get("release_date", "2026-06-12")
    release_notes = latest_meta.get("notes", "No release notes available.")
    
    headers = {"User-Agent": "RBWR-Overlay-Server"}
    try:
        r = requests.get(
            "https://api.github.com/repos/Hotment/RBWR-Utility/releases/latest",
            headers=headers,
            timeout=3
        )
        if r.status_code == 200:
            release_data = r.json()
            tag_name = release_data.get("tag_name", "")
            if tag_name:
                latest_ver = tag_name.lstrip('v')
                published_at = release_data.get("published_at", "")
                if published_at:
                    release_date = published_at.split('T')[0]
            body_content = release_data.get("body", "No release notes available.")
            if body_content:
                release_notes = body_content.replace("\\r\\n", "\n").replace("\r\n", "\n")
    except Exception:
        pass

    return render_template(
        "index.html",
        latest_version=latest_ver,
        release_date=release_date,
        release_notes=release_notes
    )

@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon"
    )

@app.route("/api/status", methods=["GET", "HEAD"])
def status_check():
    uptime_sec = max(0.0, round(time.time() - SERVER_START_TIME, 2))
    try:
        ver_data = load_versions()
        version = ver_data.get("latest", "unknown")
    except Exception:
        version = "unknown"

    payload = {
        "status": "ok",
        "service": "RBWR Utility Server",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": uptime_sec,
        "uptime": format_uptime(uptime_sec),
        "version": version
    }
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response, 200

@app.route("/calculator", methods=["GET"])
def calculator_page():
    return render_template("calculator.html")

@app.route("/points", methods=["GET"])
def points_page():
    return render_template("points.html")

@app.route("/points-graph", methods=["GET"])
def local_viewer_page():
    return render_template("local_viewer.html")

@app.route("/tablet", methods=["GET"])
@app.route("/operator-tablet", methods=["GET"])
def operator_tablet_page():
    return render_template("operator_tablet.html")

@app.route("/privacy", methods=["GET"])
@app.route("/privacy-policy", methods=["GET"])
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
@app.route("/acknowledgements", methods=["GET"])
def credits_page():
    return render_template("credits.html")

@app.errorhandler(404)
def page_not_found(e):
    if request.path.startswith("/api/") or request.headers.get("Accept") == "application/json":
        return jsonify({"detail": "Not found", "status": 404}), 404
    return render_template("404.html"), 404

@app.route("/api/contact", methods=["POST"])
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
    message_text = payload.get("message", "").strip()
    if not message_text:
        return jsonify({"detail": "Message body cannot be empty."}), 400

    if len(message_text) > 2000:
        return jsonify({"detail": "Message text exceeds maximum length of 2000 characters."}), 400

    name = payload.get("name", "").strip() or "Anonymous"
    contact_info = payload.get("contact_info", "").strip() or "N/A"
    subject = payload.get("subject", "").strip() or "General Inquiry"

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
# RBWR Server Checker Engine
# Original implementation & architecture by felixq (https://github.com/felixqx1/RBWR-Server-checker)
# Licensed under GNU General Public License v2.0 (GPL-2.0)
# ==============================================================================

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
    "Offsite Power",
    "PointsPerSecond",
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
}

PERSISTENT_SERVERS_FILE = os.path.join(DATA_DIR, "persistent_servers.json")

def load_persistent_servers():
    if not os.path.exists(PERSISTENT_SERVERS_FILE):
        return {"persistent": {}}
    try:
        with open(PERSISTENT_SERVERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"persistent": {}}

def save_persistent_servers(data):
    os.makedirs(os.path.dirname(PERSISTENT_SERVERS_FILE), exist_ok=True)
    with open(PERSISTENT_SERVERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

_sc_lock = threading.RLock()
_sc_public_server_ids = []
_sc_public_servers_info = {}
_sc_server_ids = []
_sc_latest_data = {}
_sc_server_meta = {}

def load_server_meta():
    global _sc_server_meta
    data = get_sc_data("server_meta.json")
    if isinstance(data, dict):
        _sc_server_meta.clear()
        _sc_server_meta.update(data)
    return _sc_server_meta

def save_server_meta():
    save_sc_data(_sc_server_meta, "server_meta.json")

def get_server_visibility(job_id, snapshots=None, latest_state=None, is_active=False):
    if job_id in _sc_public_server_ids:
        return False
    meta = _sc_server_meta.get(job_id)
    if meta is not None and "is_private" in meta:
        return bool(meta["is_private"])
    if latest_state and "IsPrivate" in latest_state:
        return bool(latest_state["IsPrivate"])
    if snapshots:
        for snap in snapshots.values():
            if isinstance(snap, dict) and "IsPrivate" in snap:
                return bool(snap["IsPrivate"])
    if is_active and _sc_public_server_ids:
        return job_id not in _sc_public_server_ids
    return False

def get_server_player_count(job_id, snapshots=None, latest_state=None, is_private=None):
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
        for ts in sorted(snapshots.keys(), reverse=True):
            p = snapshots[ts].get("PlayerCount", 0)
            if p > 0:
                return int(p)
    return 0

_sc_file_cache = {}
_sc_cache_lock = threading.Lock()

_sc_historical_cards_base = None
_sc_historical_cards_key = None
_sc_historical_lock = threading.Lock()

_sc_active_cards_base = None
_sc_active_cards_key = None
_sc_active_lock = threading.Lock()

def invalidate_historical_cards_cache():
    global _sc_historical_cards_base, _sc_historical_cards_key
    global _sc_active_cards_base, _sc_active_cards_key
    with _sc_historical_lock:
        _sc_historical_cards_base = None
        _sc_historical_cards_key = None
    with _sc_active_lock:
        _sc_active_cards_base = None
        _sc_active_cards_key = None

def get_sc_data(filename: str, max_retries: int = 6):
    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath):
        return {}

    try:
        current_mtime = os.path.getmtime(filepath)
    except OSError:
        current_mtime = None

    if current_mtime is not None:
        with _sc_cache_lock:
            cached_entry = _sc_file_cache.get(filename)
            if cached_entry and cached_entry[0] == current_mtime:
                return cached_entry[1]

    for attempt in range(max_retries):
        try:
            with open(filepath, "rb") as f:
                raw_bytes = f.read()
            if filename.endswith(".gz") or filepath.endswith(".gz"):
                raw_bytes = gzip.decompress(raw_bytes)
            data = _json_loads(raw_bytes)
            try:
                mtime_after = os.path.getmtime(filepath)
            except OSError:
                mtime_after = current_mtime
            with _sc_cache_lock:
                _sc_file_cache[filename] = (mtime_after, data)
            return data
        except (PermissionError, Exception) as e:
            if attempt < max_retries - 1:
                time.sleep(0.04 * (attempt + 1))
            else:
                logger.error(f"Error loading sc data from {filename}: {e}")
    return {}

def save_sc_data(data, filename: str, max_retries: int = 10):
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
                os.replace(temp_path, filepath)
                try:
                    new_mtime = os.path.getmtime(filepath)
                except OSError:
                    new_mtime = time.time()
                with _sc_cache_lock:
                    _sc_file_cache[filename] = (new_mtime, data)
                if filename in ("servers.json", "persistent_servers.json", "server_meta.json"):
                    invalidate_historical_cards_cache()
                return True
            except PermissionError:
                if attempt < max_retries - 1:
                    time.sleep(0.04 * (attempt + 1))
                else:
                    try:
                        with open(filepath, "wb") as f:
                            f.write(raw_bytes)
                        try:
                            new_mtime = os.path.getmtime(filepath)
                        except OSError:
                            new_mtime = time.time()
                        with _sc_cache_lock:
                            _sc_file_cache[filename] = (new_mtime, data)
                        if filename in ("servers.json", "persistent_servers.json", "server_meta.json"):
                            invalidate_historical_cards_cache()
                        return True
                    except Exception as fallback_err:
                        logger.error(f"Error in direct save fallback for {filename}: {fallback_err}")
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(0.04 * (attempt + 1))
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

def get_server_start_date(job_id: str, snaps: dict | None = None) -> str:
    """
    Returns the YYYY-MM-DD date when this server first started.
    Checks server_meta, then earliest snapshot in snaps, then archives, then today.
    """
    if not job_id:
        return datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
    meta = _sc_server_meta.get(job_id, {})
    st_ts = meta.get("start_timestamp")
    if st_ts and len(st_ts) >= 10 and st_ts[4] == '-' and st_ts[7] == '-':
        return st_ts[:10]
        
    if snaps:
        earliest_ts = min(snaps.keys())
        if earliest_ts and len(earliest_ts) >= 10 and earliest_ts[4] == '-' and earliest_ts[7] == '-':
            if job_id not in _sc_server_meta:
                _sc_server_meta[job_id] = {}
            _sc_server_meta[job_id]["start_timestamp"] = earliest_ts
            return earliest_ts[:10]
            
    if os.path.exists(ARCHIVES_DIR):
        try:
            for fname in sorted(os.listdir(ARCHIVES_DIR)):
                if fname.startswith("servers_") and (fname.endswith(".json") or fname.endswith(".json.gz")):
                    date_str = fname[len("servers_"):len("servers_")+10]
                    day_data = get_sc_data(os.path.join("archives", fname))
                    if isinstance(day_data, dict) and job_id in day_data:
                        if job_id not in _sc_server_meta:
                            _sc_server_meta[job_id] = {}
                        first_ts = min(day_data[job_id].keys()) if day_data[job_id] else None
                        _sc_server_meta[job_id]["start_timestamp"] = first_ts or f"{date_str}T00:00:00Z"
                        return date_str
        except Exception:
            pass

    return datetime.now(timezone.utc).strftime('%Y-%m-%d')

def get_active_server_start_dates(current_data: dict | None = None) -> set:
    """
    Returns the set of start dates (YYYY-MM-DD) for servers currently in current_data
    that are still ACTIVE (i.e. not historical).
    """
    active_dates = set()
    if not current_data:
        return active_dates

    now_utc = datetime.now(timezone.utc)
    for s_id, snaps in current_data.items():
        if not snaps:
            continue
        valid_ts_keys = [k for k in snaps.keys() if not k.startswith('_')]
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

def archive_expired_server_data(expired_by_date: dict, current_data: dict | None = None):
    """
    Saves/merges historical server snapshots into archive files in ARCHIVES_DIR.
    - If a day still has active servers running in current_data, it is saved as uncompressed .json.
    - If all servers from that day are historical (no active servers left), it is saved directly as .json.gz.
    expired_by_date format:
    {
        "YYYY-MM-DD": {
            "job_id": {
                "timestamp_iso": { ... state ... },
                ...
            },
            ...
        }
    }
    """
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
        
        existing_archive = {}
        
        if os.path.exists(gz_full):
            existing_archive = get_sc_data(gz_rel)
        elif os.path.exists(json_full):
            existing_archive = get_sc_data(json_rel)
            
        if not isinstance(existing_archive, dict):
            existing_archive = {}
        else:
            existing_archive = dict(existing_archive)
                
        for job_id, snaps in servers_dict.items():
            if job_id not in existing_archive:
                existing_archive[job_id] = {}
            else:
                existing_archive[job_id] = dict(existing_archive[job_id])
            existing_archive[job_id].update(snaps)
            
        day_has_active_servers = (date_str in active_dates)
        
        if day_has_active_servers:
            save_sc_data(existing_archive, json_rel)
            if os.path.exists(gz_full):
                try:
                    os.remove(gz_full)
                    with _sc_cache_lock:
                        _sc_file_cache.pop(gz_rel, None)
                except Exception:
                    pass
            logger.info(f"Archived {sum(len(s) for s in servers_dict.values())} snapshot(s) for {date_str} to {json_rel} (active day, uncompressed)")
        else:
            save_sc_data(existing_archive, gz_rel)
            if os.path.exists(json_full):
                try:
                    os.remove(json_full)
                    with _sc_cache_lock:
                        _sc_file_cache.pop(json_rel, None)
                except Exception:
                    pass
            logger.info(f"Archived {sum(len(s) for s in servers_dict.values())} snapshot(s) for {date_str} to {gz_rel} (finalized, compressed)")

def get_archived_server_snapshots(query: str) -> tuple[str | None, dict | None]:
    """
    Looks up snapshots for a given job_id or short in-game ID across archive files in ARCHIVES_DIR.
    Returns (matched_job_id, merged_snapshots) or (None, None).
    """
    if not query or not os.path.exists(ARCHIVES_DIR):
        return None, None

    clean_q = query.strip()
    merged_snapshots = {}
    matched_job_id = None

    try:
        archive_files = sorted(os.listdir(ARCHIVES_DIR), reverse=True)
        for fname in archive_files:
            if not (fname.startswith("servers_") and (fname.endswith(".json") or fname.endswith(".json.gz"))):
                continue
            day_data = get_sc_data(os.path.join("archives", fname))
            if not isinstance(day_data, dict):
                continue

            if clean_q in day_data:
                matched_job_id = clean_q
                snaps = day_data[clean_q]
                if isinstance(snaps, dict):
                    merged_snapshots.update(snaps)
            else:
                for j_id, snaps in day_data.items():
                    if is_exact_job_or_server_id_match(clean_q, j_id):
                        matched_job_id = j_id
                        if isinstance(snaps, dict):
                            merged_snapshots.update(snaps)
                        break

        if matched_job_id:
            for fname in archive_files:
                if not (fname.startswith("servers_") and (fname.endswith(".json") or fname.endswith(".json.gz"))):
                    continue
                day_data = get_sc_data(os.path.join("archives", fname))
                if isinstance(day_data, dict) and matched_job_id in day_data:
                    snaps = day_data[matched_job_id]
                    if isinstance(snaps, dict):
                        merged_snapshots.update(snaps)
            return matched_job_id, merged_snapshots
    except Exception as e:
        logger.error(f"Error querying archived snapshots for {query}: {e}")

    return None, None

def format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"

def get_all_archive_days_info() -> tuple[list[dict], dict]:
    """
    Returns (days_list, summary_stats) for all archived days in ARCHIVES_DIR.
    """
    if not os.path.exists(ARCHIVES_DIR):
        return [], {"total_days": 0, "total_servers": 0, "total_snapshots": 0, "total_size_bytes": 0, "total_size_str": "0 B"}

    archive_map = {}
    try:
        filenames = sorted(os.listdir(ARCHIVES_DIR), reverse=True)
    except Exception:
        filenames = []

    for fname in filenames:
        if not fname.startswith("servers_"):
            continue
        is_gz = fname.endswith(".json.gz")
        is_json = fname.endswith(".json") and not is_gz
        if not (is_gz or is_json):
            continue

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

        rel_path = os.path.join("archives", fname)
        day_data = get_sc_data(rel_path)
        if isinstance(day_data, dict):
            s_count = len(day_data)
            snap_count = sum(len(snaps) for snaps in day_data.values() if isinstance(snaps, dict))
        else:
            s_count = 0
            snap_count = 0

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
            "rel_path": rel_path
        }

    days_list = sorted(archive_map.values(), key=lambda d: d["date"], reverse=True)
    total_days = len(days_list)
    total_servers = sum(d["server_count"] for d in days_list)
    total_snapshots = sum(d["snapshot_count"] for d in days_list)
    total_size_bytes = sum(d["size_bytes"] for d in days_list)

    summary_stats = {
        "total_days": total_days,
        "total_servers": total_servers,
        "total_snapshots": total_snapshots,
        "total_size_bytes": total_size_bytes,
        "total_size_str": format_file_size(total_size_bytes)
    }

    return days_list, summary_stats

def compress_finalized_archives(current_data: dict | None = None):
    """
    Compresses archive JSON files into .json.gz once all servers started that day are historical.
    Scans ARCHIVES_DIR for servers_YYYY-MM-DD.json files:
    If no active servers from that date exist in current_data, it compresses the archive to .json.gz
    and removes the uncompressed .json file.
    """
    if not os.path.exists(ARCHIVES_DIR):
        return

    active_start_dates = get_active_server_start_dates(current_data)

    try:
        for fname in os.listdir(ARCHIVES_DIR):
            if not fname.startswith("servers_") or not fname.endswith(".json"):
                continue
            
            date_part = fname[len("servers_"):-len(".json")]
            if len(date_part) != 10 or date_part[4] != '-' or date_part[7] != '-':
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
                        for j_id, snaps in day_json.items():
                            if j_id not in day_gz:
                                day_gz[j_id] = {}
                            else:
                                day_gz[j_id] = dict(day_gz[j_id])
                            day_gz[j_id].update(snaps)
                        save_sc_data(day_gz, gz_rel)
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

                with _sc_cache_lock:
                    _sc_file_cache.pop(json_rel, None)
                    
                logger.info(f"Compressed finalized archive {fname} -> {gz_filename} (all servers for {date_part} are historical)")
            except Exception as comp_err:
                logger.error(f"Failed to compress archive {fname}: {comp_err}")
    except Exception as e:
        logger.error(f"Error checking archives for compression: {e}")

def prune_and_archive_servers_data(current_data: dict, persistent_ids: set) -> bool:
    """
    Archives servers as soon as they become historical into files based on their start date (data/archives/servers_YYYY-MM-DD.json),
    and removes non-persistent historical servers from current_data (servers.json).
    Also compresses a day's archive into .json.gz once all servers that started that day are historical.
    Returns True if current_data was modified (dirty), False otherwise.
    """
    now_utc = datetime.now(timezone.utc)
    cutoff_dt = now_utc - timedelta(hours=48)
    cutoff_iso = cutoff_dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:23] + 'Z'

    servers_dirty = False
    archived_data_by_date = {}

    def record_expired_snapshot(s_id, ts, s_data, server_start_date):
        date_str = server_start_date or (ts[:10] if (ts and len(ts) >= 10 and ts[4] == '-' and ts[7] == '-') else now_utc.strftime('%Y-%m-%d'))
        if date_str not in archived_data_by_date:
            archived_data_by_date[date_str] = {}
        if s_id not in archived_data_by_date[date_str]:
            archived_data_by_date[date_str][s_id] = {}
        archived_data_by_date[date_str][s_id][ts] = s_data

    for s_id in list(current_data.keys()):
        if s_id in persistent_ids:
            snaps = current_data.get(s_id, {})
            if snaps:
                server_start_date = get_server_start_date(s_id, snaps)
                valid_ts_keys = [k for k in snaps.keys() if not k.startswith('_')]
                expired_keys = [ts for ts in valid_ts_keys if ts < cutoff_iso]
                if expired_keys:
                    for ts in expired_keys:
                        record_expired_snapshot(s_id, ts, snaps[ts], server_start_date)
                        del snaps[ts]
                    servers_dirty = True
            continue

        snaps = current_data.get(s_id, {})
        if not snaps:
            del current_data[s_id]
            servers_dirty = True
            continue

        valid_ts_keys = [k for k in snaps.keys() if not k.startswith('_')]
        if not valid_ts_keys:
            del current_data[s_id]
            servers_dirty = True
            continue

        latest_ts = max(valid_ts_keys)
        latest_state = snaps.get(latest_ts, {})
        age_sec = convert_ISO_to_secs(latest_ts, now=now_utc)
        server_start_date = get_server_start_date(s_id, snaps)

        if is_server_historical(s_id, snaps, latest_state=latest_state, age_sec=age_sec):
            for ts in valid_ts_keys:
                record_expired_snapshot(s_id, ts, snaps[ts], server_start_date)
            if latest_ts < cutoff_iso:
                del current_data[s_id]
                servers_dirty = True
                logger.info(f"Purged expired historical server {s_id} (>48h inactive, started: {server_start_date}) from servers.json")
            continue

        earliest_ts = min(valid_ts_keys)
        if earliest_ts < cutoff_iso:
            expired_keys = [ts for ts in valid_ts_keys if ts < cutoff_iso]
            if expired_keys:
                for ts in expired_keys:
                    record_expired_snapshot(s_id, ts, snaps[ts], server_start_date)
                    del snaps[ts]
                servers_dirty = True

    if archived_data_by_date:
        archive_expired_server_data(archived_data_by_date, current_data)

    compress_finalized_archives(current_data)

    return servers_dirty

def update_public_roblox_servers():
    base_url = "https://games.roblox.com/v1/games/11765852158/servers/Public?limit=100"
    cursor = ""
    public_ids = []
    public_info = {}
    
    try:
        for _ in range(5):
            url = f"{base_url}&cursor={cursor}" if cursor else base_url
            response = requests.get(url, headers={"User-Agent": "RBWR-Server-Checker/1.0 (RBWR Utilities)"}, timeout=10)
            if response.status_code != 200:
                break
            data = response.json()
            for server in data.get('data', []):
                s_id = server.get('id')
                if s_id:
                    public_ids.append(s_id)
                    public_info[s_id] = {
                        "playing": int(server.get("playing", 0)),
                        "maxPlayers": int(server.get("maxPlayers", 12))
                    }
            cursor = data.get('nextPageCursor')
            if not cursor:
                break

        if public_ids or public_info:
            with _sc_lock:
                _sc_public_server_ids.clear()
                _sc_public_server_ids.extend(public_ids)
                _sc_public_servers_info.clear()
                _sc_public_servers_info.update(public_info)

                meta_dirty = False
                for s_id in public_ids:
                    if s_id not in _sc_server_meta or _sc_server_meta[s_id].get("is_private") is not False:
                        if s_id not in _sc_server_meta:
                            _sc_server_meta[s_id] = {}
                        _sc_server_meta[s_id]["is_private"] = False
                        meta_dirty = True
                    p_num = public_info.get(s_id, {}).get("playing", 0)
                    if p_num > 0:
                        if s_id not in _sc_server_meta:
                            _sc_server_meta[s_id] = {}
                        _sc_server_meta[s_id]["last_player_count"] = p_num
                        meta_dirty = True
                if meta_dirty:
                    save_server_meta()
            return True
        return False
    except Exception as e:
        logger.error(f"Error updating public Roblox servers: {e}")
        return False

def pull_server_checker_data():
    urls = [
        "https://hydrogen.realisticbwr.org/api/public/servers",
        "https://realisticbwr.org/api/public/servers"
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

    with _sc_lock:
        current_data = get_sc_data("servers.json")
        found_new_server = False
        servers_list = resp_json.get('data', {}).get('servers', [])

        for server in servers_list:
            job_id = server.get('jobId')
            if job_id and job_id not in _sc_server_ids:
                _sc_server_ids.append(job_id)
                found_new_server = True
        
        success_public = update_public_roblox_servers()

        _sc_latest_data.clear()
        _sc_latest_data.update(resp_json)

        persistent_data = load_persistent_servers()
        persistent_ids = set(persistent_data.get("persistent", {}).keys())
        meta_dirty = False

        for server in servers_list:
            job_id = server.get('jobId')
            if not job_id:
                continue

            if job_id not in current_data:
                current_data[job_id] = {}

            raw_state = server.get('state')
            if not isinstance(raw_state, dict):
                continue

            state = raw_state.copy()
            if "Misc" in state:
                del state["Misc"]

            if _sc_public_server_ids:
                is_priv = job_id not in _sc_public_server_ids
                state["IsPrivate"] = is_priv
                if job_id not in _sc_server_meta or _sc_server_meta[job_id].get("is_private") != is_priv:
                    if job_id not in _sc_server_meta:
                        _sc_server_meta[job_id] = {}
                    _sc_server_meta[job_id]["is_private"] = is_priv
                    meta_dirty = True
            elif job_id in _sc_server_meta and "is_private" in _sc_server_meta[job_id]:
                is_priv = bool(_sc_server_meta[job_id]["is_private"])
                state["IsPrivate"] = is_priv
            else:
                is_priv = False

            info = _sc_public_servers_info.get(job_id, {})
            if is_priv:
                if "PlayerCount" in state:
                    del state["PlayerCount"]
            else:
                player_count = info.get("playing", 0) if job_id in _sc_public_servers_info else 0
                state["PlayerCount"] = player_count
                if player_count > 0:
                    if job_id not in _sc_server_meta:
                        _sc_server_meta[job_id] = {}
                    _sc_server_meta[job_id]["last_player_count"] = player_count
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
                    state[unit] = unit_dict
                else:
                    state[unit] = {}

            heartbeat = server.get('lastHeartbeat', datetime.now(timezone.utc).isoformat())
            if job_id not in _sc_server_meta:
                _sc_server_meta[job_id] = {}
            if "start_timestamp" not in _sc_server_meta[job_id]:
                _sc_server_meta[job_id]["start_timestamp"] = heartbeat
                meta_dirty = True
            current_data[job_id][heartbeat] = state

        servers_dirty = bool(servers_list)
        pruned_dirty = prune_and_archive_servers_data(current_data, persistent_ids)
        if pruned_dirty:
            servers_dirty = True

        if servers_dirty:
            save_sc_data(current_data, "servers.json")
        if meta_dirty:
            save_server_meta()

        global_data = get_sc_data("global.json")
        stats_payload = resp_json.get('data', {}).get('stats', {})
        if stats_payload:
            global_data[str(datetime.now(timezone.utc).isoformat())] = stats_payload
            save_sc_data(global_data, "global.json")

        return True

def server_checker_worker():
    time.sleep(2)
    try:
        compress_finalized_archives()
    except Exception as e:
        logger.error(f"Error in initial archive compression: {e}")
    while True:
        try:
            pull_server_checker_data()
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

def convert_ISO_to_secs(timestamp_str, now=None):
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
    if s < 86400:
        h = s // 3600
        rem_m = (s % 3600) // 60
        return f"{h}h {rem_m}m" if rem_m > 0 else f"{h}h"
    d = s // 86400
    rem_h = (s % 86400) // 3600
    return f"{d}d {rem_h}h" if rem_h > 0 else f"{d}d"

def get_server_uptime_seconds(snapshots, is_historical, age_sec=None):
    if not snapshots:
        return 0
    try:
        first_ts = min(snapshots.keys())
        latest_ts = max(snapshots.keys())
        first_sec_ago = convert_ISO_to_secs(first_ts)
        latest_sec_ago = convert_ISO_to_secs(latest_ts) if age_sec is None else age_sec
        if is_historical:
            return max(0, first_sec_ago - latest_sec_ago)
        return max(0, first_sec_ago)
    except Exception:
        return 0

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

def is_server_historical(job_id, snapshots=None, latest_state=None, is_private=None, age_sec=None):
    """
    Determines if a server is historical.
    - For private servers: marked historical if heartbeat age > 600s.
    - For public servers: checked against the public servers list from the Roblox API.
      If the Roblox API public list is loaded and the server is not there, or has 0 players,
      or heartbeat age > 600s, it is marked historical.
    """
    if age_sec is None:
        if snapshots:
            latest_ts = max(snapshots.keys())
            age_sec = convert_ISO_to_secs(latest_ts)
        else:
            age_sec = 0

    if latest_state is None and snapshots:
        latest_ts = max(snapshots.keys())
        latest_state = snapshots.get(latest_ts, {})
    if latest_state is None:
        latest_state = {}

    if is_private is None:
        is_private = get_server_visibility(job_id, snapshots, latest_state, is_active=(age_sec <= 600))

    if is_private:
        return (age_sec > 600)

    info = _sc_public_servers_info.get(job_id)
    if _sc_public_server_ids:
        if info is None or job_id not in _sc_public_servers_info:
            return True
        return info.get("playing", 0) == 0 or age_sec > 600

    return (age_sec > 600) or (latest_state.get("PlayerCount", 0) == 0)

def get_active_cards_base(servers_data, persistent_ids):
    global _sc_active_cards_base, _sc_active_cards_key
    cache_key = (id(servers_data), len(servers_data), len(persistent_ids), len(_sc_public_server_ids))
    with _sc_active_lock:
        if _sc_active_cards_base is not None and _sc_active_cards_key == cache_key:
            return _sc_active_cards_base

    now_utc = datetime.now(timezone.utc)
    cards = []
    for job_id, snapshots in sorted(servers_data.items()):
        if not snapshots:
            continue
        latest_timestamp = max(snapshots.keys())
        latest_state = snapshots[latest_timestamp]
        info = _sc_public_servers_info.get(job_id, {})
        age_sec = convert_ISO_to_secs(latest_timestamp, now=now_utc)
        is_persistent = job_id in persistent_ids
        is_private = get_server_visibility(job_id, snapshots, latest_state, is_active=(age_sec <= 600))
        is_historical = is_server_historical(job_id, snapshots, latest_state, is_private=is_private, age_sec=age_sec)

        if is_historical and not is_persistent:
            continue

        if is_private:
            player_count = None
            max_players = None
        else:
            player_count = get_server_player_count(job_id, snapshots, latest_state, is_private=False)
            max_players = info.get("maxPlayers", 12) if info else 12

        first_timestamp = min(snapshots.keys())
        uptime_sec = get_server_uptime_seconds(snapshots, is_historical, age_sec)
        uptime_str = format_uptime_duration(uptime_sec)

        j_parts = [p for p in job_id.split("-") if p]
        short_id = f"{j_parts[1]}-{j_parts[2]}" if len(j_parts) >= 3 else ""

        unit1 = latest_state.get("Unit1", {})
        unit2 = latest_state.get("Unit2", {})

        cards.append({
            "job_id": job_id,
            "short_id": short_id,
            "is_private": is_private,
            "is_persistent": is_persistent,
            "is_historical": is_historical,
            "is_archived": False,
            "player_count": player_count,
            "max_players": max_players,
            "raw_timestamp": latest_timestamp,
            "first_timestamp": first_timestamp,
            "age_seconds": age_sec,
            "latest_timestamp": f"{age_sec}s ago",
            "uptime_seconds": uptime_sec,
            "uptime_str": uptime_str,
            "snapshot_count": len(snapshots),
            "unit1": {
                "demand_time_left": unit1.get("Demand Time Left", 0),
                "aprm": unit1.get("APRM", 0),
                "reactor_temp": unit1.get("Reactor Temp", 0),
            },
            "unit2": {
                "demand_time_left": unit2.get("Demand Time Left", 0),
                "aprm": unit2.get("APRM", 0),
                "reactor_temp": unit2.get("Reactor Temp", 0),
            },
        })

    with _sc_active_lock:
        _sc_active_cards_base = cards
        _sc_active_cards_key = cache_key

    return cards

def build_server_cards(data, search_query=None, is_archived=False, exact_search_only=True):
    if not data:
        return []

    persistent_data = load_persistent_servers()
    persistent_ids = set(persistent_data.get("persistent", {}).keys())
    clean_query = (search_query or "").strip()

    if not clean_query and not is_archived:
        return list(get_active_cards_base(data, persistent_ids))

    cards = []
    now_utc = datetime.now(timezone.utc)
    for job_id, snapshots in sorted(data.items()):
        if not snapshots:
            continue
        valid_ts_keys = [k for k in snapshots.keys() if not k.startswith('_')]
        if not valid_ts_keys:
            continue
        latest_timestamp = max(valid_ts_keys)
        latest_state = snapshots[latest_timestamp]
        unit1 = latest_state.get("Unit1", {})
        unit2 = latest_state.get("Unit2", {})

        info = _sc_public_servers_info.get(job_id, {})
        age_sec = convert_ISO_to_secs(latest_timestamp, now=now_utc)
        is_persistent = job_id in persistent_ids
        is_private = get_server_visibility(job_id, snapshots, latest_state, is_active=(age_sec <= 600))

        server_is_archived = is_archived or (isinstance(snapshots, dict) and bool(snapshots.get('_is_archived', False)))
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
                    is_exact_job_or_server_id_match(clean_query, job_id) or
                    clean_q_lower in job_id.lower() or
                    (short_id and clean_q_lower in short_id.lower())
                )
                if not matches:
                    continue

        first_timestamp = min(valid_ts_keys)
        uptime_sec = get_server_uptime_seconds(snapshots, is_historical, age_sec)
        uptime_str = format_uptime_duration(uptime_sec)

        j_parts = [p for p in job_id.split("-") if p]
        short_id = f"{j_parts[1]}-{j_parts[2]}" if len(j_parts) >= 3 else ""

        cards.append({
            "job_id": job_id,
            "short_id": short_id,
            "is_private": is_private,
            "is_persistent": is_persistent,
            "is_historical": is_historical,
            "is_archived": server_is_archived,
            "player_count": player_count,
            "max_players": max_players,
            "raw_timestamp": latest_timestamp,
            "first_timestamp": first_timestamp,
            "age_seconds": age_sec,
            "latest_timestamp": f"{age_sec}s ago",
            "uptime_seconds": uptime_sec,
            "uptime_str": uptime_str,
            "snapshot_count": len(valid_ts_keys),
            "unit1": {
                "demand_time_left": unit1.get("Demand Time Left", 0),
                "aprm": unit1.get("APRM", 0),
                "reactor_temp": unit1.get("Reactor Temp", 0),
            },
            "unit2": {
                "demand_time_left": unit2.get("Demand Time Left", 0),
                "aprm": unit2.get("APRM", 0),
                "reactor_temp": unit2.get("Reactor Temp", 0),
            },
        })
    return cards

def parse_label_seconds(label, fallback_idx=0):
    try:
        if isinstance(label, (int, float)):
            return float(label)
        return float(str(label).split()[0])
    except Exception:
        return float(fallback_idx)

def compress_points_raw(points, precision=2):
    """
    Compress collinear points where points is a list of (x, y) tuples.
    Returns list of retained (x, y) tuples.
    """
    if len(points) <= 2:
        return list(points)

    compressed = [points[0]]
    for i in range(1, len(points) - 1):
        x1, y1 = points[i - 1]
        x2, y2 = points[i]
        x3, y3 = points[i + 1]

        try:
            ry1 = round(y1, precision) if precision is not None else y1
            ry2 = round(y2, precision) if precision is not None else y2
            ry3 = round(y3, precision) if precision is not None else y3
            cross_product = (x2 - x1) * (ry3 - ry2) - (ry2 - ry1) * (x3 - x2)
        except Exception:
            cross_product = 1.0

        if abs(cross_product) > 1e-5:
            compressed.append(points[i])

    compressed.append(points[-1])
    return compressed

def compress_points(points, precision=2):
    """
    Compress collinear points where points is a list of (x, y) tuples.
    x is seconds_ago (float), y is metric value (float).
    precision controls the number of decimal places for y (default 2, None for unrounded).
    """
    raw = compress_points_raw(points, precision=precision)
    return [{"x": round(x, 1), "y": (round(y, precision) if precision is not None else y)} for x, y in raw]

def compress_paired_points(u1_points, u2_points, precision=2):
    """
    Compresses u1_points and u2_points (lists of (x, y) tuples).
    If a point in one unit is kept, but the other unit had its point at that timestamp removed
    due to compression, the other unit keeps and shows that point anyway.
    Points that are collinear in both units are compressed away.
    Returns (c_u1, c_u2) where each is a list of {"x": ..., "y": ...} dicts.
    """
    if not u1_points and not u2_points:
        return [], []
    if not u1_points:
        return [], compress_points(u2_points, precision=precision)
    if not u2_points:
        return compress_points(u1_points, precision=precision), []

    raw1 = compress_points_raw(u1_points, precision=precision)
    raw2 = compress_points_raw(u2_points, precision=precision)

    kept_x = {round(x, 1) for x, _ in raw1} | {round(x, 1) for x, _ in raw2}

    res_u1 = [
        {"x": round(x, 1), "y": (round(y, precision) if precision is not None else y)}
        for x, y in u1_points
        if round(x, 1) in kept_x
    ]
    res_u2 = [
        {"x": round(x, 1), "y": (round(y, precision) if precision is not None else y)}
        for x, y in u2_points
        if round(x, 1) in kept_x
    ]

    return res_u1, res_u2

def build_chart_payload(job_id, snapshots):
    metrics = {
        "Demand": ("3", "Electrical Demand (MW)", ["Demand", "DemandU1", "DemandU2"], 2),
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
        "CasingTemperature": ("2", "Casing Temperature (°C)", ["CasingTemperature", "Casing Temperature"], 4)
    }
    chart_payload = []
    ordered_snapshots = []

    if not snapshots:
        return {
            "job_id": job_id,
            "last_heartbeat_age": 0,
            "snapshots": [],
            "charts": [],
        }

    for timestamp, state in sorted(snapshots.items()):
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
            c_players = compress_points(player_points, precision=0)
            chart_payload.append({
                "metric": "Player Count",
                "datasets": [{
                    "label": "Players",
                    "data": c_players,
                    "borderColor": "#10b981",
                    "backgroundColor": "rgba(16, 185, 129, 0.08)",
                }]
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
            u1_state = entry["state"].get("Unit1", {})
            u2_state = entry["state"].get("Unit2", {})

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
            datasets.append({
                "label": "Unit 1",
                "data": c_u1,
                "borderColor": "#3b82f6",
                "backgroundColor": "rgba(59, 130, 246, 0.08)",
            })
            datasets.append({
                "label": "Unit 2",
                "data": c_u2,
                "borderColor": "#f59e0b",
                "backgroundColor": "rgba(245, 158, 11, 0.08)",
            })
        else:
            if u1_points and unit_type in ("1", "3"):
                c_u1 = compress_points(u1_points, precision=precision)
                datasets.append({
                    "label": "Unit 1",
                    "data": c_u1,
                    "borderColor": "#3b82f6",
                    "backgroundColor": "rgba(59, 130, 246, 0.08)",
                })

            if u2_points and unit_type in ("2", "3"):
                c_u2 = compress_points(u2_points, precision=precision)
                datasets.append({
                    "label": "Unit 2",
                    "data": c_u2,
                    "borderColor": "#f59e0b",
                    "backgroundColor": "rgba(245, 158, 11, 0.08)",
                })

        chart_payload.append({
            "metric": metric_title,
            "datasets": datasets,
        })

    last_heartbeat_age = ordered_snapshots[-1]["seconds_ago"] if ordered_snapshots else 0

    return {
        "job_id": job_id,
        "last_heartbeat_age": last_heartbeat_age,
        "snapshots": ordered_snapshots,
        "charts": chart_payload,
    }

def build_global_chart_payload(snapshots, max_history_seconds=7 * 24 * 3600):
    chart_payload = []

    if not snapshots:
        return {
            "snapshots": [],
            "charts": [],
        }

    u1_points = []
    u2_points = []

    for timestamp in sorted(snapshots.keys()):
        sec_ago = convert_ISO_to_secs(timestamp)
        if max_history_seconds is not None and sec_ago > max_history_seconds:
            continue
        data_entry = snapshots[timestamp] or {}
        unit1 = data_entry.get("unit1", {})
        unit2 = data_entry.get("unit2", {})

        v1 = unit1.get("megawatts")
        v2 = unit2.get("megawatts")
        if v1 is not None and isinstance(v1, (int, float)) and v1 > 0:
            u1_points.append((sec_ago, float(v1)))
        if v2 is not None and isinstance(v2, (int, float)) and v2 > 0:
            u2_points.append((sec_ago, float(v2)))

    datasets = []
    if u1_points and u2_points:
        c_u1, c_u2 = compress_paired_points(u1_points, u2_points, precision=2)
        datasets.append({
            "label": "Unit 1",
            "data": c_u1,
            "borderColor": "#3b82f6",
            "backgroundColor": "rgba(59, 130, 246, 0.08)",
        })
        datasets.append({
            "label": "Unit 2",
            "data": c_u2,
            "borderColor": "#f59e0b",
            "backgroundColor": "rgba(245, 158, 11, 0.08)",
        })
    elif u1_points:
        datasets.append({
            "label": "Unit 1",
            "data": compress_points(u1_points, precision=2),
            "borderColor": "#3b82f6",
            "backgroundColor": "rgba(59, 130, 246, 0.08)",
        })
    elif u2_points:
        datasets.append({
            "label": "Unit 2",
            "data": compress_points(u2_points, precision=2),
            "borderColor": "#f59e0b",
            "backgroundColor": "rgba(245, 158, 11, 0.08)",
        })

    chart_payload.append({
        "metric": "Global Power Output (MW)",
        "datasets": datasets,
    })

    return {
        "snapshots": [],
        "charts": chart_payload,
    }

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

@app.route("/servers/<job_id>", methods=["GET"])
def server_detail_page(job_id):
    servers_data = get_sc_data("servers.json")
    snapshots = servers_data.get(job_id) if servers_data else None
    is_archived = False

    if snapshots is None:
        if _sc_latest_data:
            for s in _sc_latest_data.get('data', {}).get('servers', []):
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
    if _sc_latest_data and not is_archived:
        for s in _sc_latest_data.get('data', {}).get('servers', []):
            if s.get('jobId') == job_id:
                server = s
                break

    persistent_data = load_persistent_servers()
    is_persistent = job_id in persistent_data.get("persistent", {})

    info = _sc_public_servers_info.get(job_id, {})
    latest_ts = max(snapshots.keys()) if snapshots else None
    latest_state = snapshots.get(latest_ts, {}) if latest_ts else {}
    age_sec = convert_ISO_to_secs(latest_ts) if latest_ts else 0

    is_private = get_server_visibility(job_id, snapshots, latest_state, is_active=(age_sec <= 600 and not is_archived))
    is_historical = is_server_historical(job_id, snapshots, latest_state, is_private=is_private, age_sec=age_sec) or is_archived
    if is_private:
        player_count = None
        max_players = None
    else:
        player_count = get_server_player_count(job_id, snapshots, latest_state, is_private=False)
        max_players = info.get("maxPlayers", 12) if info else 12
    is_admin = bool(get_authenticated_user())

    first_ts = min(snapshots.keys()) if snapshots else None
    uptime_sec = get_server_uptime_seconds(snapshots, is_historical, age_sec)
    uptime_str = format_uptime_duration(uptime_sec)

    if not server:
        latest_ts = max(snapshots.keys()) if snapshots else None
        latest_st = snapshots.get(latest_ts, {}) if latest_ts else {}
        unit1_st = latest_st.get("Unit1", {})
        unit2_st = latest_st.get("Unit2", {})

        summary = {
            "is_private": is_private,
            "is_persistent": is_persistent,
            "is_historical": is_historical,
            "is_archived": is_archived,
            "is_admin": is_admin,
            "player_count": player_count,
            "max_players": max_players,
            "first_timestamp": first_ts,
            "uptime_seconds": uptime_sec,
            "uptime_str": uptime_str,
            "scram_reason_u1": unit1_st.get("SCRAMreason", "N/A") or "N/A",
            "scram_reason_u2": unit2_st.get("SCRAMreason", "N/A") or "N/A",
            "time_to_next_demand": max(0.0, float(unit1_st.get("Demand Time Left", 0))),
            "next_demand": round(float(unit1_st.get("NextDemandU1", 0)) + float(unit2_st.get("NextDemandU2", 0)), 2),
            "dmandU1": unit1_st.get("NextDemandU1", 0),
            "dmandU2": unit2_st.get("NextDemandU2", 0),
        }
        return render_template("server_detail.html", **payload, **summary)

    unit1_state = server.get('state', {}).get('Unit1', {})
    unit2_state = server.get('state', {}).get('Unit2', {})

    scram_reasonU1 = unit1_state.get('SCRAMreason', 'N/A')
    scram_reasonU2 = unit2_state.get('SCRAMreason', 'N/A')
    dmand_left_data = float(unit1_state.get('Demand Time Left', 0))
    dmand_next1 = float(unit1_state.get('NextDemandU1', 0))
    dmand_next2 = float(unit2_state.get('NextDemandU2', 0))
    next_demand = round(dmand_next1 + dmand_next2, 2)

    try:
        hb_ts = server.get('lastHeartbeat', '')
        elapsed = time.time() - datetime.fromisoformat(hb_ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        elapsed = 0

    dmand_left = max(0.0, dmand_left_data - elapsed)

    summary = {
        "is_private": is_private,
        "is_persistent": is_persistent,
        "is_historical": is_historical,
        "is_archived": is_archived,
        "is_admin": is_admin,
        "player_count": player_count,
        "max_players": max_players,
        "first_timestamp": first_ts,
        "uptime_seconds": uptime_sec,
        "uptime_str": uptime_str,
        "scram_reason_u1": scram_reasonU1 or "N/A",
        "scram_reason_u2": scram_reasonU2 or "N/A",
        "time_to_next_demand": dmand_left,
        "next_demand": next_demand,
        "dmandU1": dmand_next1,
        "dmandU2": dmand_next2,
    }

    return render_template("server_detail.html", **payload, **summary)

@app.route("/api/servers/latest", methods=["GET"])
def get_latest_servers_api():
    if _sc_latest_data:
        return jsonify(_sc_latest_data)
    servers_data = get_sc_data("servers.json")
    return jsonify({"success": True, "servers": servers_data})

@app.route("/api/servers/lookup", methods=["GET"])
def lookup_server_api():
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

def get_historical_cards_base(servers_data, persistent_ids):
    global _sc_historical_cards_base, _sc_historical_cards_key
    cache_key = (id(servers_data), len(servers_data), len(persistent_ids), len(_sc_public_server_ids))
    with _sc_historical_lock:
        if _sc_historical_cards_base is not None and _sc_historical_cards_key == cache_key:
            return _sc_historical_cards_base

    now_utc = datetime.now(timezone.utc)
    base_cards = []
    for job_id, snapshots in servers_data.items():
        if not snapshots:
            continue
        latest_timestamp = max(snapshots.keys())
        latest_state = snapshots[latest_timestamp]
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

        first_timestamp = min(snapshots.keys())
        uptime_sec = get_server_uptime_seconds(snapshots, is_historical, age_sec)
        uptime_str = format_uptime_duration(uptime_sec)

        unit1 = latest_state.get("Unit1", {})
        unit2 = latest_state.get("Unit2", {})

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
            "latest_timestamp": f"{age_sec}s ago",
            "uptime_seconds": uptime_sec,
            "uptime_str": uptime_str,
            "snapshot_count": len(snapshots),
            "unit1": {
                "demand_time_left": unit1.get("Demand Time Left", 0),
                "aprm": unit1.get("APRM", 0),
                "reactor_temp": unit1.get("Reactor Temp", 0),
            },
            "unit2": {
                "demand_time_left": unit2.get("Demand Time Left", 0),
                "aprm": unit2.get("APRM", 0),
                "reactor_temp": unit2.get("Reactor Temp", 0),
            },
        })

    with _sc_historical_lock:
        _sc_historical_cards_base = base_cards
        _sc_historical_cards_key = cache_key

    return base_cards

@app.route("/api/servers/historical", methods=["GET"])
def get_historical_servers_api():
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

    sort_option = request.args.get("sort", "newest").strip().lower()
    if sort_option == "players_desc":
        historical_cards.sort(key=lambda c: (c.get("player_count") or 0, c.get("snapshot_count", 0)), reverse=True)
    elif sort_option == "players_asc":
        historical_cards.sort(key=lambda c: (c.get("player_count") or 0, c.get("snapshot_count", 0)))
    elif sort_option == "snapshots_desc":
        historical_cards.sort(key=lambda c: (c.get("snapshot_count", 0), c.get("player_count") or 0), reverse=True)
    elif sort_option == "snapshots_asc":
        historical_cards.sort(key=lambda c: (c.get("snapshot_count", 0), c.get("player_count") or 0))
    elif sort_option == "oldest":
        historical_cards.sort(key=lambda c: (c.get("uptime_seconds", 0), c.get("player_count") or 0), reverse=True)
    elif sort_option == "public_first":
        historical_cards.sort(key=lambda c: (1 if c.get("is_private") else 0, -c.get("uptime_seconds", 0)))
    elif sort_option == "private_first":
        historical_cards.sort(key=lambda c: (0 if c.get("is_private") else 1, -c.get("uptime_seconds", 0)))
    else:  # newest
        historical_cards.sort(key=lambda c: (c.get("uptime_seconds", 0), -(c.get("player_count") or 0)))

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

@app.route("/api/servers/refresh", methods=["POST"])
def refresh_servers_api():
    success = pull_server_checker_data()
    return jsonify({"success": success})

@app.route("/archives", methods=["GET"])
def browse_archives_page():
    days_list, summary_stats = get_all_archive_days_info()
    return render_template("archives.html", days=days_list, stats=summary_stats)

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

@app.route("/api/archives", methods=["GET"])
def get_archives_api():
    days_list, summary_stats = get_all_archive_days_info()
    return jsonify({
        "success": True,
        "days": days_list,
        "stats": summary_stats
    })

@app.route("/api/archives/<date_str>", methods=["GET"])
def get_archive_day_api(date_str):
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
        return jsonify({"success": False, "message": f"No archive found for date {date_str}."}), 404

    day_data = get_sc_data(target_rel)
    if not isinstance(day_data, dict):
        return jsonify({"success": False, "message": "Failed to read archive data."}), 500

    query = (request.args.get("q") or "").strip()
    server_cards = build_server_cards(day_data, search_query=query, is_archived=True, exact_search_only=False)

    return jsonify({
        "success": True,
        "date": date_str,
        "filename": filename,
        "is_compressed": is_compressed,
        "total_servers": len(server_cards),
        "servers": server_cards
    })

_servers_cache = {"data": None, "timestamp": 0, "content_type": "application/json", "status_code": 200}
_cache_lock = threading.Lock()

@app.route("/api/public-servers", methods=["GET"])
@app.route("/public-servers", methods=["GET"])
def proxy_public_servers():
    if _sc_latest_data:
        res_json = dict(_sc_latest_data)
        if "success" not in res_json:
            res_json["success"] = True
        return jsonify(res_json)

    now = time.time()
    with _cache_lock:
        if _servers_cache["data"] is not None and (now - _servers_cache["timestamp"]) < 60:
            return Response(_servers_cache["data"], status=_servers_cache["status_code"], content_type=_servers_cache["content_type"])

    primary_url = "https://hydrogen.realisticbwr.org/api/public/servers"
    fallback_url = "https://realisticbwr.org/api/public/servers"

    for url in [primary_url, fallback_url]:
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": "RBWR-Operator-Tablet/1.0 (RBWR Thermal Calculator Utility)"},
                timeout=10
            )
            if resp.status_code == 200:
                try:
                    res_json = resp.json()
                    if isinstance(res_json, dict) and "success" not in res_json:
                        res_json["success"] = True
                    content = json.dumps(res_json).encode("utf-8")
                except Exception:
                    content = resp.content

                with _cache_lock:
                    _servers_cache["data"] = content
                    _servers_cache["timestamp"] = time.time()
                    _servers_cache["content_type"] = "application/json"
                    _servers_cache["status_code"] = 200
                return Response(content, status=200, content_type="application/json")
        except Exception as e:
            logger.warning(f"Error fetching from {url}: {e}")

    with _cache_lock:
        if _servers_cache["data"] is not None:
            return Response(_servers_cache["data"], status=_servers_cache["status_code"], content_type=_servers_cache["content_type"])
    return jsonify({"success": False, "error": "Unable to reach game API"}), 500

@app.route("/version/latest", methods=["GET"])
def get_latest_version():
    data = load_versions()
    latest_ver = data.get("latest")
    latest_meta = data.get("versions", {}).get(latest_ver)
    if not latest_meta:
        return jsonify({"detail": "Latest version metadata not found"}), 404
    return jsonify(latest_meta)

@app.route("/versions", methods=["GET"])
def get_all_versions():
    data = load_versions()
    return jsonify(data.get("versions", {}))

@app.route("/download/latest", methods=["GET"])
def download_latest_file():
    data = load_versions()
    latest_ver = data.get("latest")
    latest_meta = data.get("versions", {}).get(latest_ver)
    if not latest_meta:
        return jsonify({"detail": "Latest version metadata not found"}), 404
    
    filename = latest_meta.get("filename")
    filepath = os.path.join(FILES_DIR, filename)
    
    if not os.path.exists(filepath):
        parent_filepath = os.path.join(os.path.dirname(BASE_DIR), filename)
        if os.path.exists(parent_filepath):
            return send_from_directory(os.path.dirname(BASE_DIR), filename, as_attachment=True)
        return jsonify({"detail": f"Latest release file '{filename}' is missing on the server."}), 404
        
    return send_from_directory(FILES_DIR, filename, as_attachment=True)

@app.route("/download/<version>", methods=["GET"])
def download_version_file(version):
    data = load_versions()
    version_meta = data.get("versions", {}).get(version)
    if not version_meta:
        return jsonify({"detail": f"Version '{version}' not found in the catalog."}), 404
    
    filename = version_meta.get("filename")
    filepath = os.path.join(FILES_DIR, filename)
    
    if not os.path.exists(filepath):
        return jsonify({"detail": f"File for version '{version}' is missing on the server."}), 404
        
    return send_from_directory(FILES_DIR, filename, as_attachment=True)

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

@app.route("/suggestions", methods=["GET", "POST"])
def suggestions_route():
    if request.method == "POST":
        return submit_ticket()
    
    if request.args.get("format") == "json" or request.headers.get("Accept") == "application/json":
        return jsonify({"tickets": get_public_tickets(), "suggestions": get_public_tickets()})
        
    return redirect("/tickets" + (f"?{request.query_string.decode('utf-8')}" if request.query_string else ""))

@app.route("/api/tickets", methods=["GET"])
def get_tickets_api():
    return jsonify({"tickets": get_public_tickets(), "suggestions": get_public_tickets()})

@app.route("/api/suggestions", methods=["GET"])
def get_suggestions_api():
    return jsonify({"tickets": get_public_tickets(), "suggestions": get_public_tickets()})

@app.route("/api/tickets/<int:ticket_id>/messages", methods=["GET"])
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

@app.route("/api/tickets/<int:ticket_id>/messages", methods=["POST"])
def add_ticket_message_api(ticket_id):
    ip = request.remote_addr or "unknown"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()

    if is_ip_banned(ip):
        return jsonify({"detail": "Your IP is banned from participating in ticket discussions."}), 403
    
    try:
        req_json = request.get_json() or {}
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

    discord_channel_id = target_ticket.get("discord_channel_id")
    if discord_channel_id and disnake_bot and disnake_bot.is_ready() and disnake_bot_loop and disnake_bot_loop.is_running():
        def _fwd_to_discord(ch_id, m_text, s_name, is_adm, current_msg_id):
            sender_label = "Administrator" if is_adm else "Ticket Author"
            content = f"**[{sender_label}] {s_name}**:\n{m_text}"
            async def _send_fwd_async():
                if not disnake_bot:
                    return None
                
                channel = disnake_bot.get_channel(int(ch_id))
                if not channel:
                    channel = await disnake_bot.fetch_channel(int(ch_id))

                if not channel or not isinstance(channel, disnake.TextChannel):
                    logger.warning(f"[Disnake Forward] Channel {ch_id} is not a text channel or doesnt exist.")
                    return None
                    
                sent = await channel.send(content=content)
                return str(sent.id)
            try:
                fut = asyncio.run_coroutine_threadsafe(_send_fwd_async(), disnake_bot_loop)  # pyright: ignore[reportArgumentType]
                d_id = fut.result(timeout=8)
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
            args=(discord_channel_id, msg_text, msg_obj.get("sender_name", "User"), is_admin, msg_obj.get("id")),
            daemon=True
        ).start()

    return jsonify({
        "message": "Reply posted successfully.",
        "ticket_id": ticket_id,
        "new_message": msg_obj,
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
    
    new_id = 1
    if suggestions:
        new_id = max(s.get("id", 0) for s in suggestions) + 1
        
    discord_user = session.get("discord_user") or {}
    discord_id = discord_user.get("id") or None
    discord_username = discord_user.get("global_name") or discord_user.get("username") or None
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

    return jsonify({
        "message": f"{'Bug report' if ticket_type == 'bug_report' else 'Suggestion'} submitted successfully.",
        "id": new_id,
        "type": ticket_type
    })

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
        payload = CrashPayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400
    
    data = load_crashes()
    crashes = data.setdefault("crashes", [])
    
    new_id = 1
    if crashes:
        new_id = max(c.get("id", 0) for c in crashes) + 1
        
    new_crash = {
        "id": new_id,
        "version": payload.version.strip(),
        "traceback": payload.traceback.strip(),
        "log_data": payload.log_data.strip(),
        "os_info": payload.os_info.strip(),
        "status": "OPEN",
        "ip": ip,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    crashes.append(new_crash)
    save_crashes(data)
    broadcast_update("dashboard")
    return jsonify({"message": "Crash report submitted successfully.", "id": new_id})

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
        payload = CrashStatusPayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400

    data = load_crashes()
    crashes = data.get("crashes", [])
    for c in crashes:
        if c.get("id") == payload.id:
            c["status"] = payload.status
            save_crashes(data)
            broadcast_update("dashboard")
            return jsonify({"message": f"Crash #{payload.id} status updated to {payload.status}.", "id": payload.id, "status": payload.status})
    return jsonify({"detail": f"Crash report with ID {payload.id} not found."}), 404

@app.route("/admin/crashes/delete", methods=["POST"])
@admin_required
def delete_crash(username):
    if not has_permission(username, "crashes"):
        return jsonify({"detail": "Permission denied for crash logs section"}), 403
    try:
        req_json = request.get_json() or {}
        payload = DeleteCrashPayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400

    data = load_crashes()
    crashes = data.get("crashes", [])
    initial_len = len(crashes)
    data["crashes"] = [c for c in crashes if c.get("id") != payload.id]

    if len(data["crashes"]) < initial_len:
        save_crashes(data)
        broadcast_update("dashboard")
        return jsonify({"message": f"Crash report #{payload.id} deleted successfully.", "id": payload.id})

    return jsonify({"detail": f"Crash report with ID {payload.id} not found."}), 404

@app.route("/admin/tickets/status", methods=["POST"])
@app.route("/admin/suggestions/status", methods=["POST"])
@admin_required
def update_suggestion_status(username):
    if not has_permission(username, "suggestions"):
        return jsonify({"detail": "Permission denied for tickets section"}), 403
    try:
        req_json = request.get_json() or {}
        payload = StatusUpdatePayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400

    data = load_suggestions()
    suggestions = data.get("suggestions", [])
    for s in suggestions:
        if s.get("id") == payload.id:
            s["status"] = payload.status
            save_suggestions(data)
            broadcast_update("dashboard")
            return jsonify({"message": "Status updated successfully.", "id": payload.id, "status": payload.status})
    return jsonify({"detail": f"Ticket with ID {payload.id} not found."}), 404

@app.route("/admin/tickets/comment", methods=["POST"])
@app.route("/admin/suggestions/comment", methods=["POST"])
@admin_required
def update_suggestion_comment(username):
    if not has_permission(username, "suggestions"):
        return jsonify({"detail": "Permission denied for tickets section"}), 403
    try:
        req_json = request.get_json() or {}
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
            return jsonify({"message": "Admin comment saved successfully.", "id": payload.id, "comment": payload.comment.strip(), "comment_by": username})
    return jsonify({"detail": f"Ticket with ID {payload.id} not found."}), 404

@app.route("/admin/tickets/visibility", methods=["POST"])
@app.route("/admin/suggestions/visibility", methods=["POST"])
@admin_required
def update_suggestion_visibility(username):
    if not has_permission(username, "suggestions"):
        return jsonify({"detail": "Permission denied for tickets section"}), 403
    try:
        req_json = request.get_json() or {}
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
            return jsonify({"message": f"Ticket #{payload.id} visibility updated.", "id": payload.id, "hidden": payload.hidden})
    return jsonify({"detail": f"Ticket with ID {payload.id} not found."}), 404

@app.route("/admin/tickets/delete", methods=["POST"])
@app.route("/admin/suggestions/delete", methods=["POST"])
@admin_required
def delete_suggestion(username):
    if not has_permission(username, "suggestions"):
        return jsonify({"detail": "Permission denied for tickets section"}), 403
    try:
        req_json = request.get_json() or {}
        payload = DeleteSuggestionPayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400

    data = load_suggestions()
    suggestions = data.get("suggestions", [])
    initial_len = len(suggestions)
    data["suggestions"] = [s for s in suggestions if s.get("id") != payload.id]

    if len(data["suggestions"]) < initial_len:
        save_suggestions(data)
        broadcast_update("dashboard")
        return jsonify({"message": f"Ticket #{payload.id} deleted successfully.", "id": payload.id})

    return jsonify({"detail": f"Ticket with ID {payload.id} not found."}), 404

@app.route("/admin/tickets/ban", methods=["POST"])
@app.route("/admin/suggestions/ban", methods=["POST"])
@admin_required
def ban_ip(username):
    if not has_permission(username, "bans"):
        return jsonify({"detail": "Permission denied for bans section"}), 403
    try:
        req_json = request.get_json() or {}
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
    return jsonify({"message": f"IP {ip_to_ban} has been banned.", "ip": ip_to_ban})

@app.route("/admin/tickets/unban", methods=["POST"])
@app.route("/admin/suggestions/unban", methods=["POST"])
@admin_required
def unban_ip(username):
    if not has_permission(username, "bans"):
        return jsonify({"detail": "Permission denied for bans section"}), 403
    try:
        req_json = request.get_json() or {}
        payload = UnbanPayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400

    data = load_banned_ips()
    banned = data.get("banned", {})
    if payload.ip in banned:
        del banned[payload.ip]
        save_banned_ips(data)
        broadcast_update("dashboard")
        return jsonify({"message": f"IP {payload.ip} unbanned successfully.", "ip": payload.ip})
    return jsonify({"detail": f"IP {payload.ip} is not currently banned."}), 404

@app.route("/admin/tickets", methods=["GET"])
@app.route("/admin/suggestions", methods=["GET"])
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
        notifier=notifier_cfg
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
        servers=server_cards,
        notifier=notifier_cfg
    )

@app.route("/admin/servers/persist", methods=["POST"])
@app.route("/api/admin/servers/persist", methods=["POST"])
@admin_required
def toggle_server_persistence(username):
    if not has_permission(username, "servers"):
        return jsonify({"detail": "Permission denied for servers section"}), 403
    try:
        req_json = request.get_json() or {}
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
    return jsonify({"success": True, "message": msg, "job_id": job_id, "is_persistent": payload.persistent})

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
        notifier=notifier_cfg
    )

class CreateAdminPayload(BaseModel):
    discord_id: str = Field(..., min_length=15, max_length=25)
    username: str = Field(default="", max_length=50)

class DeleteAdminPayload(BaseModel):
    discord_id: str

class NotifierConfigPayload(BaseModel):
    enabled: bool
    categories: list[str] = Field(default=["overlay", "point_graph", "server_checker", "general"])

@app.route("/admin/accounts/create", methods=["POST"])
@admin_required
def create_admin_account(username):
    if not is_root_user(username):
        return jsonify({"detail": "Forbidden - Root privileges required"}), 403
    try:
        req_json = request.get_json() or {}
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
        "permissions": {
            "suggestions": True,
            "crashes": True,
            "contact": True,
            "bans": True,
            "servers": True
        },
        "notifier": {
            "enabled": False,
            "categories": ["overlay", "point_graph", "server_checker", "general"]
        }
    }
    save_admins(admins_data)
    broadcast_update("accounts")
    return jsonify({"message": f"Admin with Discord ID '{discord_id}' added successfully."})

@app.route("/admin/accounts/permissions", methods=["POST"])
@admin_required
def update_admin_permissions(username):
    if not is_root_user(username):
        return jsonify({"detail": "Forbidden - Root privileges required"}), 403
    try:
        req_json = request.get_json() or {}
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

    admin_entry["permissions"] = {
        "suggestions": bool(payload.permissions.get("suggestions", True)),
        "crashes": bool(payload.permissions.get("crashes", True)),
        "contact": bool(payload.permissions.get("contact", True)),
        "bans": bool(payload.permissions.get("bans", True)),
        "servers": bool(payload.permissions.get("servers", True))
    }
    save_admins(admins_data)
    broadcast_update("accounts")
    broadcast_update("dashboard")
    return jsonify({"message": f"Permissions for admin '{target_id}' updated successfully."})

@app.route("/admin/accounts/delete", methods=["POST"])
@admin_required
def delete_admin_account(username):
    if not is_root_user(username):
        return jsonify({"detail": "Forbidden - Root privileges required"}), 403
    try:
        req_json = request.get_json() or {}
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
        return jsonify({"message": f"Admin account '{target_id}' removed successfully."})
    return jsonify({"detail": f"Admin account '{target_id}' not found."}), 404

@app.route("/api/admin/notifier", methods=["GET"])
@admin_required
def get_notifier_api(username):
    if not has_permission(username, "suggestions"):
        return jsonify({"detail": "Permission denied for suggestions"}), 403
    discord_id = session.get("discord_id") or username
    cfg = get_admin_notifier_config(discord_id)
    return jsonify({"notifier": cfg, "discord_id": session.get("discord_id") or ""})

@app.route("/api/admin/notifier", methods=["POST"])
@admin_required
def save_notifier_api(username):
    if not has_permission(username, "suggestions"):
        return jsonify({"detail": "Permission denied for suggestions"}), 403
    try:
        req_json = request.get_json() or {}
        payload = NotifierConfigPayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400
    
    discord_id = session.get("discord_id") or username
    save_admin_notifier_config(discord_id, {
        "enabled": payload.enabled,
        "categories": payload.categories
    })
    return jsonify({"success": True, "message": "Notifier preferences saved successfully."})

@app.route("/api/admin/notifier/test", methods=["POST"])
@admin_required
def test_notifier_api(username):
    return jsonify({
        "success": True,
        "message": "Direct DMs have been retired in favor of automated Discord ticket channels under category 1547529007334162432."
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
        "scope": "identify",
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
        session["discord_user"] = discord_user_obj

        next_dest = session.pop("oauth_next", None) or "/tickets"
        if not next_dest.startswith("/") or next_dest.startswith("//") or next_dest.startswith("/\\"):
            next_dest = "/tickets"

        root_ids = get_root_discord_ids()
        is_root = (d_id in root_ids)
        admins_data = load_admins()
        is_admin = is_root or (d_id in admins_data.get("admins", {}))

        if next_dest.startswith("/admin"):
            if is_admin:
                session.permanent = True
                session["admin_logged_in"] = True
                session["discord_id"] = d_id
                session["username"] = d_global_name or d_username
                session["is_root"] = is_root
                if d_id in admins_data.get("admins", {}):
                    admins_data["admins"][d_id]["username"] = d_global_name or d_username
                    admins_data["admins"][d_id]["avatar_url"] = d_avatar_url
                    save_admins(admins_data)
                return redirect(next_dest)
            else:
                return redirect(f"/admin/login?error={quote(f'Access Denied: Discord user {d_global_name} (ID: {d_id}) is not an authorized administrator. Please contact Root.')}")

        if is_admin:
            session.permanent = True
            session["admin_logged_in"] = True
            session["discord_id"] = d_id
            session["username"] = d_global_name or d_username
            session["is_root"] = is_root

        return redirect(next_dest)

    except Exception as e:
        logger.error(f"[Discord OAuth] Exception during callback: {e}", exc_info=True)
        next_dest = session.pop("oauth_next", None) or "/tickets"
        return redirect(f"{next_dest}?error={quote(f'Internal OAuth error: {str(e)}')}")

@app.route("/auth/discord/logout", methods=["GET"])
def discord_logout():
    session.pop("discord_user", None)
    session.pop("admin_logged_in", None)
    session.pop("discord_id", None)
    session.pop("username", None)
    session.pop("is_root", None)
    next_url = request.args.get("next") or request.referrer or "/tickets"
    if not next_url.startswith("/") or next_url.startswith("//") or next_url.startswith("/\\"):
        next_url = "/tickets"
    return redirect(next_url)

@app.route("/api/auth/me", methods=["GET"])
def api_auth_me():
    return jsonify({
        "logged_in": bool(session.get("discord_user")),
        "user": session.get("discord_user"),
        "is_admin": bool(session.get("admin_logged_in")),
        "is_root": bool(session.get("is_root")),
        "discord_id": session.get("discord_id") or ""
    })

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
            
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        
        root_user, root_pass = get_admin_credentials()
        is_root_username = secrets.compare_digest(username, root_user)
        is_root_password = secrets.compare_digest(password, root_pass)
        
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
            session["admin_logged_in"] = True
            session["username"] = username
            session["is_root"] = is_root_user(username)
            
            if not next_url.startswith("/") or next_url.startswith("//") or next_url.startswith("/\\"):
                next_url = "/admin"
            return redirect(next_url)
        else:
            record_login_attempt(ip)
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
                    subprocess.run("git config core.sparseCheckout true", shell=True, check=True)
                    sparse_file = os.path.join(".git", "info", "sparse-checkout")
                    os.makedirs(os.path.dirname(sparse_file), exist_ok=True)
                    with open(sparse_file, "w") as f:
                        f.write("server/*\n")
                    subprocess.run("git pull origin main", shell=True, check=True)
                
                if os.path.exists("server"):
                    safe_print("Copying server files...")
                    subprocess.run("cp -a server/. . && rm -rf server", shell=True, check=True)
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

        handler.start()
    except Exception:
        pass

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
    app.run(host=host, port=port, debug=False)