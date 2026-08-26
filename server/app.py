from flask import Flask, request, jsonify, send_from_directory, redirect, Response, render_template, session
from pydantic import BaseModel, Field, ValidationError
import os
import json
import secrets
import requests
import hashlib
import binascii
from dotenv import load_dotenv
import time
import threading
from datetime import datetime, timezone, timedelta
from functools import wraps
from urllib.parse import quote
from flask_sock import Sock
from werkzeug.middleware.proxy_fix import ProxyFix

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILES_DIR = os.path.join(BASE_DIR, "files")
DATA_DIR = os.path.join(BASE_DIR, "data")
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

sock = Sock(app)
active_connections = set()

def get_dashboard_payload_data(username=None):
    perms = get_user_permissions(username) if username else {"suggestions": True, "crashes": True, "contact": True, "bans": True}
    
    suggestions = []
    if perms.get("suggestions", True):
        sug_data = load_suggestions()
        raw_sugs = sug_data.get("suggestions", [])
        for s in sorted(raw_sugs, key=lambda x: x.get("timestamp", ""), reverse=True):
            suggestions.append({
                "id": s.get("id"),
                "name": s.get("name", "Anonymous"),
                "suggestion": s.get("suggestion", ""),
                "ip": s.get("ip", ""),
                "timestamp": s.get("timestamp", ""),
                "status": s.get("status", "pending"),
                "admin_comment": s.get("admin_comment", ""),
                "comment_by": s.get("comment_by", ""),
                "comment_timestamp": s.get("comment_timestamp", ""),
                "target": s.get("target") or ("server_checker" if s.get("is_server_checker") else "overlay"),
                "is_server_checker": s.get("target") == "server_checker" or bool(s.get("is_server_checker")),
                "hidden": bool(s.get("hidden", False))
            })

    banned_ips = {}
    if perms.get("bans", True):
        ban_data = load_banned_ips()
        banned_ips = ban_data.get("banned", {})

    crashes = []
    if perms.get("crashes", True):
        crash_data = load_crashes()
        crashes = sorted(crash_data.get("crashes", []), key=lambda c: c.get("timestamp", ""), reverse=True)

    contact_messages = []
    if perms.get("contact", True):
        contact_data = load_contact_messages()
        contact_messages = sorted(contact_data.get("messages", []), key=lambda m: m.get("timestamp", ""), reverse=True)

    return {
        "suggestions": suggestions,
        "banned_ips": banned_ips,
        "crashes": crashes,
        "contact_messages": contact_messages
    }

def get_accounts_payload_data():
    admins_data = load_admins()
    admins_list = []
    for u, info in admins_data.get("admins", {}).items():
        admins_list.append({
            "username": u,
            "created_at": info.get("created_at"),
            "permissions": info.get("permissions") or {
                "suggestions": True,
                "crashes": True,
                "contact": True,
                "bans": True
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

def is_root_user(username: str) -> bool:
    root_user, _ = get_admin_credentials()
    return secrets.compare_digest(username, root_user)

def get_user_permissions(username: str) -> dict:
    if not username:
        return {"suggestions": True, "crashes": True, "contact": True, "bans": True}
    if is_root_user(username):
        return {"suggestions": True, "crashes": True, "contact": True, "bans": True}
    admins_data = load_admins()
    admin_info = admins_data.get("admins", {}).get(username, {})
    perms = admin_info.get("permissions")
    if perms is None:
        return {"suggestions": True, "crashes": True, "contact": True, "bans": True}
    return {
        "suggestions": bool(perms.get("suggestions", True)),
        "crashes": bool(perms.get("crashes", True)),
        "contact": bool(perms.get("contact", True)),
        "bans": bool(perms.get("bans", True))
    }

def has_permission(username: str, section: str) -> bool:
    if not username:
        return False
    if is_root_user(username):
        return True
    return get_user_permissions(username).get(section, True)

def get_authenticated_user():
    username = session.get("username")
    if session.get("admin_logged_in") and username:
        root_user, _ = get_admin_credentials()
        if secrets.compare_digest(username, root_user):
            return username
        admins_data = load_admins()
        if username in admins_data.get("admins", {}):
            return username
        
    auth = request.authorization
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
    data = load_suggestions()
    suggestions = data.get("suggestions", [])
    public_list = []
    for s in sorted(suggestions, key=lambda x: x.get("timestamp", ""), reverse=True):
        if s.get("hidden"):
            continue
        public_list.append({
            "id": s.get("id"),
            "name": s.get("name", "Anonymous"),
            "suggestion": s.get("suggestion", ""),
            "timestamp": s.get("timestamp", ""),
            "status": s.get("status", "pending"),
            "admin_comment": s.get("admin_comment", ""),
            "comment_by": s.get("comment_by", ""),
            "comment_timestamp": s.get("comment_timestamp", ""),
            "target": s.get("target") or ("server_checker" if s.get("is_server_checker") else "overlay"),
            "is_server_checker": s.get("target") == "server_checker" or bool(s.get("is_server_checker"))
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
    suggestion: str = Field(..., max_length=2000)
    anonymous: bool
    target: str = Field(default="overlay", max_length=50)
    is_server_checker: bool = Field(default=False)

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
    "Reactor Scram State",
    "Startup XFMR",
    "DoAutoScramU1",
    "DieselRPM",
    "Turbine RPM",
    "FWP1",
    "FWP2",
    "Recirc1",
    "Recirc2",
    "APRM Setpoint",
    "AutoPressure",
    "NextDemandU1",
    "BypassTurbineAutoTrip",
    "Vibrations",
    "Fuel Burn (default 0.54)",
    "Avg. Rod",
    "TurbineTrip",
    "TotalPowerGenerated",
    "Offsite Power",
    "StartupUnit1",
    "BusA",
    "BusB",
    "Disk Ruptured",
    "RPS Trip State B",
    "RPS Trip State A",
    "TRIPreason",
    "PointsPerSecond",
    "DCBus",
    "StartupUnit2",
    "SCRAMreason",
    "DiffPressure",
    "NextDemandU2",
    "DoAutoScramU2",
    "Demand Time Left",
    "CasingTemperature",
]

_sc_lock = threading.RLock()
_sc_public_server_ids = []
_sc_server_ids = []
_sc_latest_data = {}

def get_sc_data(filename: str, max_retries: int = 6):
    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath):
        return {}
    for attempt in range(max_retries):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (PermissionError, json.JSONDecodeError):
            if attempt < max_retries - 1:
                time.sleep(0.05 * (attempt + 1))
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(0.05)
    return {}

def save_sc_data(data, filename: str, max_retries: int = 10):
    filepath = os.path.join(DATA_DIR, filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    unique_id = f"{os.getpid()}_{threading.get_ident()}_{time.time_ns()}"
    temp_path = f"{filepath}.{unique_id}.tmp"
    
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
            f.flush()
            
        for attempt in range(max_retries):
            try:
                os.replace(temp_path, filepath)
                return True
            except PermissionError:
                if attempt < max_retries - 1:
                    time.sleep(0.04 * (attempt + 1))
                else:
                    try:
                        with open(filepath, "w", encoding="utf-8") as f:
                            json.dump(data, f)
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

def update_public_roblox_servers():
    url = "https://games.roblox.com/v1/games/11765852158/servers/Public?limit=100"
    try:
        response = requests.get(url, headers={"User-Agent": "RBWR-Server-Checker/1.0 (RBWR Utilities)"}, timeout=10)
        if response.status_code == 200:
            data = response.json()
            with _sc_lock:
                _sc_public_server_ids.clear()
                for server in data.get('data', []):
                    if 'id' in server:
                        _sc_public_server_ids.append(server['id'])
            return True
        else:
            logger.warning(f"Failed to update Roblox public servers. Status: {response.status_code}")
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
        logger.warning("All server telemetry endpoints failed or timed out.")
        return False

    try:
        resp_json = response.json()
    except Exception as e:
        logger.error(f"Failed to decode server telemetry JSON: {e}")
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
        
        success_public = False
        if found_new_server or not _sc_public_server_ids:
            success_public = update_public_roblox_servers()

        rbwr_api_ids = [s.get('jobId') for s in servers_list if s.get('jobId')]

        if success_public and _sc_public_server_ids:
            for job_id in list(current_data.keys()):
                if job_id not in _sc_public_server_ids and job_id not in rbwr_api_ids:
                    del current_data[job_id]
        
        _sc_latest_data.clear()
        _sc_latest_data.update(resp_json)

        for server in servers_list:
            job_id = server.get('jobId')
            if not job_id:
                continue

            if _sc_public_server_ids and job_id not in _sc_public_server_ids:
                continue

            if job_id not in current_data:
                current_data[job_id] = {}

            raw_state = server.get('state')
            if not isinstance(raw_state, dict):
                continue

            state = raw_state.copy()
            if "Misc" in state:
                del state["Misc"]

            for unit in ("Unit1", "Unit2"):
                unit_state = state.get(unit)
                if isinstance(unit_state, dict):
                    state[unit] = {
                        k: (round(v, 2) if not isinstance(v, (str, bool)) and isinstance(v, (int, float)) else v)
                        for k, v in unit_state.items()
                        if k not in SERVER_CHECKER_PURGE_KEYS
                    }
                else:
                    state[unit] = {}

            heartbeat = server.get('lastHeartbeat', datetime.now(timezone.utc).isoformat())
            current_data[job_id][heartbeat] = state
        save_sc_data(current_data, "servers.json")

        global_data = get_sc_data("global.json")
        stats_payload = resp_json.get('data', {}).get('stats', {})
        if stats_payload:
            global_data[str(datetime.now(timezone.utc).isoformat())] = stats_payload
            save_sc_data(global_data, "global.json")

        return True

def server_checker_worker():
    time.sleep(2)
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
        
        is_reloader_active = os.environ.get("WERKZEUG_RUN_MAIN") is not None
        if is_reloader_active and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
            return
            
        _sc_worker_started = True
        _sc_worker_thread = threading.Thread(target=server_checker_worker, daemon=True, name="SCWorkerThread")
        _sc_worker_thread.start()
        logger.info("Started background server checker worker thread.")

start_server_checker_worker()

@app.before_request
def ensure_server_checker_worker():
    if not _sc_worker_started:
        start_server_checker_worker()

def convert_ISO_to_secs(timestamp_str):
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age_seconds = (now - dt).total_seconds()
        return max(0, round(age_seconds))
    except Exception:
        return 0

def build_server_cards(data):
    cards = []
    if not data:
        return cards

    for job_id, snapshots in sorted(data.items()):
        if not snapshots:
            continue
        latest_timestamp = max(snapshots.keys())
        latest_state = snapshots[latest_timestamp]
        unit1 = latest_state.get("Unit1", {})
        unit2 = latest_state.get("Unit2", {})
        cards.append({
            "job_id": job_id,
            "latest_timestamp": f"{convert_ISO_to_secs(latest_timestamp)}s ago",
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
    return cards

def parse_label_seconds(label, fallback_idx=0):
    try:
        if isinstance(label, (int, float)):
            return float(label)
        return float(str(label).split()[0])
    except Exception:
        return float(fallback_idx)

def compress_points(points):
    """
    Compress collinear points where points is a list of (x, y) tuples.
    x is seconds_ago (float), y is metric value (float).
    """
    if len(points) <= 2:
        return [{"x": round(x, 1), "y": round(y, 2)} for x, y in points]

    compressed = [points[0]]
    for i in range(1, len(points) - 1):
        x1, y1 = points[i - 1]
        x2, y2 = points[i]
        x3, y3 = points[i + 1]

        try:
            cross_product = (x2 - x1) * (y3 - y2) - (y2 - y1) * (x3 - x2)
        except Exception:
            cross_product = 1.0

        if abs(cross_product) > 1e-5:
            compressed.append(points[i])

    compressed.append(points[-1])
    return [{"x": round(x, 1), "y": round(y, 2)} for x, y in compressed]

def build_chart_payload(job_id, snapshots):
    metrics = {
        "APRM": ("3", "APRM (%)", ["APRM"]),
        "RTP": ("2", "RTP (%)", ["RTP"]),
        "Xenon": ("3", "Xenon (%)", ["Xenon"]),
        "Iodine": ("3", "Iodine (%)", ["Iodine"]),
        "Pressure": ("3", "Reactor Pressure (PSI)", ["Pressure"]),
        "Reactor Temp": ("3", "Reactor Temperature (°F)", ["Reactor Temp"]),
        "ReactorLevel": ("3", "Reactor Water Level (in)", ["ReactorLevel"]),
        "Deareator Level": ("3", "Deaerator Level (in)", ["Deareator Level", "Deaerator Level"]),
        "Hotwell Level": ("3", "Hotwell Level (in)", ["Hotwell Level"]),
        "TurbineHealth": ("2", "Turbine Health (%)", ["TurbineHealth", "Turbine Health"]),
        "GeneratorTemperature": ("2", "Generator Temperature (°F)", ["GeneratorTemperature", "Generator Temperature"]),
        "Demand": ("3", "Electrical Demand (MW)", ["Demand", "DemandU1", "DemandU2"])
    }
    chart_payload = []
    ordered_snapshots = []

    if not snapshots:
        return {
            "job_id": job_id,
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

    for metric_key, (unit_type, metric_title, field_aliases) in metrics.items():
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
                    u1_points.append((sec_ago, float(v1)))

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
                    u2_points.append((sec_ago, float(v2)))

        datasets = []
        if u1_points and unit_type in ("1", "3"):
            c_u1 = compress_points(u1_points)
            datasets.append({
                "label": "Unit 1",
                "data": c_u1,
                "borderColor": "#3b82f6",
                "backgroundColor": "rgba(59, 130, 246, 0.08)",
            })

        if u2_points and unit_type in ("2", "3"):
            c_u2 = compress_points(u2_points)
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

    return {
        "job_id": job_id,
        "snapshots": ordered_snapshots,
        "charts": chart_payload,
    }

def build_global_chart_payload(snapshots):
    chart_payload = []
    ordered_snapshots = []

    if not snapshots:
        return {
            "snapshots": [],
            "charts": [],
        }

    for timestamp, data in sorted(snapshots.items()):
        sec_ago = convert_ISO_to_secs(timestamp)
        ordered_snapshots.append({
            "timestamp": timestamp,
            "seconds_ago": sec_ago,
            "display_time": f"{sec_ago}s ago",
            "data": data,
        })

    u1_points = []
    u2_points = []

    for entry in ordered_snapshots:
        sec_ago = entry["seconds_ago"]
        data_entry = entry.get("data", {})
        unit1 = data_entry.get("unit1", {})
        unit2 = data_entry.get("unit2", {})

        v1 = unit1.get("megawatts")
        v2 = unit2.get("megawatts")
        if v1 is not None and isinstance(v1, (int, float)) and v1 > 0:
            u1_points.append((sec_ago, float(v1)))
        if v2 is not None and isinstance(v2, (int, float)) and v2 > 0:
            u2_points.append((sec_ago, float(v2)))

    datasets = []
    if u1_points:
        datasets.append({
            "label": "Unit 1",
            "data": compress_points(u1_points),
            "borderColor": "#3b82f6",
            "backgroundColor": "rgba(59, 130, 246, 0.08)",
        })
    if u2_points:
        datasets.append({
            "label": "Unit 2",
            "data": compress_points(u2_points),
            "borderColor": "#f59e0b",
            "backgroundColor": "rgba(245, 158, 11, 0.08)",
        })

    chart_payload.append({
        "metric": "Global Power Output (MW)",
        "datasets": datasets,
    })

    return {
        "snapshots": ordered_snapshots,
        "charts": chart_payload,
    }

@app.route("/servers", methods=["GET"])
def servers_page():
    servers_data = get_sc_data("servers.json")
    global_data = get_sc_data("global.json")
    global_payload = build_global_chart_payload(global_data)
    server_cards = build_server_cards(servers_data)
    
    return render_template(
        "servers.html",
        servers=server_cards,
        charts=global_payload.get("charts", [])
    )

@app.route("/servers/<job_id>", methods=["GET"])
def server_detail_page(job_id):
    servers_data = get_sc_data("servers.json")
    snapshots = servers_data.get(job_id)
    if snapshots is None:
        if _sc_latest_data:
            for s in _sc_latest_data.get('data', {}).get('servers', []):
                if s.get('jobId') == job_id:
                    snapshots = {s.get('lastHeartbeat', datetime.now(timezone.utc).isoformat()): s.get('state', {})}
                    break
                    
    if snapshots is None:
        return redirect("/servers")

    try:
        payload = build_chart_payload(job_id, snapshots)
    except Exception as e:
        logger.error(f"Error building chart payload for {job_id}: {e}")
        return redirect("/servers")

    server = None
    if _sc_latest_data:
        for s in _sc_latest_data.get('data', {}).get('servers', []):
            if s.get('jobId') == job_id:
                server = s
                break

    if not server:
        latest_ts = max(snapshots.keys()) if snapshots else None
        latest_st = snapshots.get(latest_ts, {}) if latest_ts else {}
        unit1_st = latest_st.get("Unit1", {})
        unit2_st = latest_st.get("Unit2", {})
        
        summary = {
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

@app.route("/api/servers/refresh", methods=["POST"])
def refresh_servers_api():
    success = pull_server_checker_data()
    return jsonify({"success": success})

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
    return jsonify({"success": False, "error": "Unable to reach server telemetry API"}), 500

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

@app.route("/suggestions", methods=["GET", "POST"])
def suggestions_route():
    if request.method == "POST":
        return submit_suggestion()
    
    if request.args.get("format") == "json" or request.headers.get("Accept") == "application/json":
        return jsonify({"suggestions": get_public_suggestions()})
        
    return render_template("suggestions.html", suggestions=get_public_suggestions())

@app.route("/api/suggestions", methods=["GET"])
def get_suggestions_api():
    return jsonify({"suggestions": get_public_suggestions()})

def submit_suggestion():
    ip = request.remote_addr or "unknown"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()

    if is_ip_banned(ip):
        return jsonify({"detail": "Your IP is banned from submitting feedback."}), 403
    
    try:
        req_json = request.get_json() or {}
        payload = SuggestionPayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400
    
    if not payload.suggestion.strip():
        return jsonify({"detail": "Feedback details cannot be empty."}), 400
    
    data = load_suggestions()
    suggestions = data.setdefault("suggestions", [])
    
    if ip != "unknown":
        now = datetime.now(timezone.utc)
        limit_period = timedelta(minutes=30)
        for s in suggestions:
            if s.get("ip") == ip:
                try:
                    s_time = datetime.fromisoformat(s.get("timestamp"))
                    if now - s_time < limit_period:
                        time_left = limit_period - (now - s_time)
                        hours_left = int(time_left.total_seconds() // 3600)
                        mins_left = int((time_left.total_seconds() % 3600) // 60)
                        msg = f"Rate limit: Try again in {f"{hours_left}h " if hours_left > 0 else ""}{mins_left}m."
                        return jsonify({"detail": msg}), 429
                except (ValueError, TypeError):
                    continue
    
    new_id = 1
    if suggestions:
        new_id = max(s.get("id", 0) for s in suggestions) + 1
        
    name = "Anonymous" if payload.anonymous or not payload.name.strip() else payload.name.strip()
    if payload.target in ["point_graph", "points_graph", "point_history"]:
        target_val = "point_graph"
    elif payload.target == "server_checker" or payload.is_server_checker:
        target_val = "server_checker"
    else:
        target_val = "overlay"
    
    new_sug = {
        "id": new_id,
        "name": name,
        "suggestion": payload.suggestion.strip(),
        "ip": ip,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
        "target": target_val,
        "is_server_checker": target_val == "server_checker"
    }
    suggestions.append(new_sug)
    save_suggestions(data)
    broadcast_update("dashboard")
    return jsonify({"message": "Feedback submitted successfully.", "id": new_id})

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
    username: str
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

@app.route("/admin/suggestions/status", methods=["POST"])
@admin_required
def update_suggestion_status(username):
    if not has_permission(username, "suggestions"):
        return jsonify({"detail": "Permission denied for suggestions section"}), 403
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
    return jsonify({"detail": f"Feedback/suggestion with ID {payload.id} not found."}), 404

@app.route("/admin/suggestions/comment", methods=["POST"])
@admin_required
def update_suggestion_comment(username):
    if not has_permission(username, "suggestions"):
        return jsonify({"detail": "Permission denied for suggestions section"}), 403
    try:
        req_json = request.get_json() or {}
        payload = CommentPayload(**req_json)
    except ValidationError as e:
        return jsonify({"detail": e.errors()}), 400

    data = load_suggestions()
    suggestions = data.get("suggestions", [])
    for s in suggestions:
        if s.get("id") == payload.id:
            comment_str = payload.comment.strip()
            s["admin_comment"] = comment_str
            s["comment_by"] = username if comment_str else ""
            s["comment_timestamp"] = datetime.now(timezone.utc).isoformat() if comment_str else ""
            save_suggestions(data)
            broadcast_update("dashboard")
            return jsonify({
                "message": "Comment updated successfully.",
                "id": payload.id,
                "admin_comment": comment_str,
                "comment_by": s.get("comment_by", ""),
                "comment_timestamp": s.get("comment_timestamp", "")
            })
    return jsonify({"detail": f"Feedback/suggestion with ID {payload.id} not found."}), 404

@app.route("/admin/suggestions/visibility", methods=["POST"])
@admin_required
def update_suggestion_visibility(username):
    if not has_permission(username, "suggestions"):
        return jsonify({"detail": "Permission denied for suggestions section"}), 403
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
            return jsonify({"message": f"Suggestion #{payload.id} visibility updated.", "id": payload.id, "hidden": payload.hidden})
    return jsonify({"detail": f"Feedback/suggestion with ID {payload.id} not found."}), 404

@app.route("/admin/suggestions/delete", methods=["POST"])
@admin_required
def delete_suggestion(username):
    if not has_permission(username, "suggestions"):
        return jsonify({"detail": "Permission denied for suggestions section"}), 403
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
        return jsonify({"message": f"Suggestion #{payload.id} deleted successfully.", "id": payload.id})

    return jsonify({"detail": f"Feedback/suggestion with ID {payload.id} not found."}), 404

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

    data = load_banned_ips()
    banned = data.setdefault("banned", {})
    
    expires_at = None
    if payload.duration_minutes is not None:
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=payload.duration_minutes)).isoformat()
        
    banned[payload.ip] = {
        "banned_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at,
        "reason": payload.reason.strip() or "No reason provided"
    }
    save_banned_ips(data)
    broadcast_update("dashboard")
    return jsonify({"message": f"IP {payload.ip} banned successfully.", "ip": payload.ip})

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

@app.route("/admin/suggestions", methods=["GET"])
@admin_required
def view_suggestions_dashboard(username):
    if not has_permission(username, "suggestions"):
        return redirect("/admin")
    return render_template("admin_panel.html", username=username, active_view="suggestions", is_root=is_root_user(username), permissions=get_user_permissions(username))

@app.route("/admin/crashes", methods=["GET"])
@admin_required
def view_crashes_dashboard(username):
    if not has_permission(username, "crashes"):
        return redirect("/admin")
    return render_template("admin_panel.html", username=username, active_view="crashes", is_root=is_root_user(username), permissions=get_user_permissions(username))

@app.route("/admin/contact", methods=["GET"])
@admin_required
def view_contact_dashboard(username):
    if not has_permission(username, "contact"):
        return redirect("/admin")
    return render_template("admin_panel.html", username=username, active_view="contact", is_root=is_root_user(username), permissions=get_user_permissions(username))

@app.route("/admin/bans", methods=["GET"])
@admin_required
def view_bans_dashboard(username):
    if not has_permission(username, "bans"):
        return redirect("/admin")
    return render_template("admin_panel.html", username=username, active_view="bans", is_root=is_root_user(username), permissions=get_user_permissions(username))

@app.route("/admin", methods=["GET"])
@admin_required
def admin_root(username):
    return render_template("admin_panel.html", username=username, active_view="overview", is_root=is_root_user(username), permissions=get_user_permissions(username))

@app.route("/admin/accounts", methods=["GET"])
@admin_required
def view_accounts_dashboard(username):
    if not is_root_user(username):
        return redirect("/admin")
    return render_template("admin_panel.html", username=username, active_view="accounts", is_root=True, permissions=get_user_permissions(username))

class CreateAdminPayload(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=100)

class DeleteAdminPayload(BaseModel):
    username: str

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

    new_user = payload.username.strip()
    root_user, _ = get_admin_credentials()
    if secrets.compare_digest(new_user.lower(), root_user.lower()):
        return jsonify({"detail": "Cannot create an account with the root username."}), 400

    admins_data = load_admins()
    admins = admins_data.setdefault("admins", {})
    if new_user in admins:
        return jsonify({"detail": f"Admin account '{new_user}' already exists."}), 400

    admins[new_user] = {
        "password_hash": hash_password(payload.password),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "permissions": {
            "suggestions": True,
            "crashes": True,
            "contact": True,
            "bans": True
        }
    }
    save_admins(admins_data)
    broadcast_update("accounts")
    return jsonify({"message": f"Admin account '{new_user}' created successfully."})

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

    target_user = payload.username.strip()
    admins_data = load_admins()
    admins = admins_data.get("admins", {})
    if target_user not in admins:
        return jsonify({"detail": f"Admin account '{target_user}' not found."}), 404

    admins[target_user]["permissions"] = {
        "suggestions": bool(payload.permissions.get("suggestions", True)),
        "crashes": bool(payload.permissions.get("crashes", True)),
        "contact": bool(payload.permissions.get("contact", True)),
        "bans": bool(payload.permissions.get("bans", True))
    }
    save_admins(admins_data)
    broadcast_update("accounts")
    broadcast_update("dashboard")
    return jsonify({"message": f"Permissions for '{target_user}' updated successfully."})

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

    target_user = payload.username.strip()
    admins_data = load_admins()
    admins = admins_data.get("admins", {})
    if target_user in admins:
        del admins[target_user]
        save_admins(admins_data)
        broadcast_update("accounts")
        return jsonify({"message": f"Admin account '{target_user}' removed successfully."})
    return jsonify({"detail": f"Admin account '{target_user}' not found."}), 404

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
    error = None
    next_url = request.args.get("next") or request.form.get("next") or "/admin"
    
    ip = request.remote_addr or "unknown"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
        
    if is_ip_banned(ip):
        return render_template("admin_login.html", error="Your IP is banned.", next_url=next_url), 403
        
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
            return render_template("admin_login.html", error="CSRF verification failed - Same origin required.", next_url=next_url), 403
            
        if is_login_rate_limited(ip):
            return render_template("admin_login.html", error="Too many login attempts. Please try again in 1 minute.", next_url=next_url), 429
            
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
            
            if not next_url.startswith("/") or next_url.startswith("//") or next_url.startswith("/\\"):
                next_url = "/admin"
            return redirect(next_url)
        else:
            record_login_attempt(ip)
            error = "Invalid username or secret key credentials."
            
    return render_template("admin_login.html", error=error, next_url=next_url)

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
        
    app.run(host=host, port=port, debug=False)