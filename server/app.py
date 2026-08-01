from flask import Flask, request, jsonify, send_from_directory, redirect, Response, render_template, session
from pydantic import BaseModel, Field, ValidationError
import os
import json
import secrets
import requests
import hashlib
import binascii
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
from functools import wraps
from urllib.parse import quote
from flask_sock import Sock
from werkzeug.middleware.proxy_fix import ProxyFix

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILES_DIR = os.path.join(BASE_DIR, "files")
VERSIONS_FILE = os.path.join(BASE_DIR, "versions.json")
SUGGESTIONS_FILE = os.path.join(BASE_DIR, "suggestions.json")
BANNED_FILE = os.path.join(BASE_DIR, "banned_ips.json")
CRASHES_FILE = os.path.join(BASE_DIR, "crashes.json")
ADMINS_FILE = os.path.join(BASE_DIR, "admins.json")
ENV_FILE = os.path.join(BASE_DIR, ".env")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# Ensure files directory exists
os.makedirs(FILES_DIR, exist_ok=True)
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

def get_dashboard_payload_data():
    sug_data = load_suggestions()
    suggestions = sug_data.get("suggestions", [])
    suggestions = sorted(suggestions, key=lambda s: s.get("timestamp", ""), reverse=True)
    
    ban_data = load_banned_ips()
    banned_ips = ban_data.get("banned", {})
    
    crash_data = load_crashes()
    crashes = crash_data.get("crashes", [])
    crashes = sorted(crashes, key=lambda c: c.get("timestamp", ""), reverse=True)
    
    return {
        "suggestions": suggestions,
        "banned_ips": banned_ips,
        "crashes": crashes
    }

def get_accounts_payload_data():
    admins_data = load_admins()
    admins_list = []
    for u, info in admins_data.get("admins", {}).items():
        admins_list.append({
            "username": u,
            "created_at": info.get("created_at")
        })
    return {"admins": admins_list}

def broadcast_update(data_type):
    if data_type == "dashboard":
        payload = {
            "type": "dashboard",
            "data": get_dashboard_payload_data()
        }
    elif data_type == "accounts":
        payload = {
            "type": "accounts",
            "data": get_accounts_payload_data()
        }
    else:
        return
        
    message = json.dumps(payload)
    for ws in list(active_connections):
        try:
            ws.send(message)
        except Exception:
            active_connections.discard(ws)

@sock.route('/admin/ws')
def admin_ws(ws):
    if not session.get("admin_logged_in"):
        ws.close(1008)
        return
        
    active_connections.add(ws)
    
    try:
        initial_payload = {
            "type": "all",
            "dashboard": get_dashboard_payload_data(),
            "accounts": get_accounts_payload_data() if is_root_user(session.get("username") or "") else None
        }
        ws.send(json.dumps(initial_payload))
    except Exception:
        active_connections.discard(ws)
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
        active_connections.discard(ws)

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

# --- Authentication & Persistence Helpers ---
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

def get_authenticated_user():
    username = session.get("username")
    if session.get("admin_logged_in") and username:
        # Check if root
        root_user, _ = get_admin_credentials()
        if secrets.compare_digest(username, root_user):
            return username
        # Check other admins
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

def get_public_suggestions():
    data = load_suggestions()
    suggestions = data.get("suggestions", [])
    public_list = []
    for s in sorted(suggestions, key=lambda x: x.get("timestamp", ""), reverse=True):
        public_list.append({
            "id": s.get("id"),
            "name": s.get("name", "Anonymous"),
            "suggestion": s.get("suggestion", ""),
            "timestamp": s.get("timestamp", ""),
            "status": s.get("status", "pending"),
            "admin_comment": s.get("admin_comment", ""),
            "comment_by": s.get("comment_by", ""),
            "comment_timestamp": s.get("comment_timestamp", "")
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
        # Permanent ban
        return True
    
    try:
        expires_at = datetime.fromisoformat(expires_at_str)
        if datetime.now(timezone.utc) > expires_at:
            # Ban expired, remove record
            del banned[ip]
            save_banned_ips(data)
            return False
        return True
    except Exception:
        return True

# --- Request Payloads ---

class SuggestionPayload(BaseModel):
    name: str = Field(default="", max_length=50)
    suggestion: str = Field(..., max_length=2000)
    anonymous: bool

class CrashPayload(BaseModel):
    version: str = Field(..., max_length=20)
    traceback: str = Field(..., max_length=20000)
    log_data: str = Field(default="", max_length=50000)

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

# --- API Endpoints ---

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
            "https://api.github.com/repos/Hotment/rbwr_themal_calculator/releases/latest",
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
    data = load_versions()
    latest_ver = data.get("latest", "1.5.5")
    return render_template("calculator.html", latest_version=latest_ver)

@app.route("/points", methods=["GET"])
def points_page():
    data = load_versions()
    latest_ver = data.get("latest", "1.5.5")
    return render_template("points.html", latest_version=latest_ver)

@app.route("/tablet", methods=["GET"])
@app.route("/operator-tablet", methods=["GET"])
def operator_tablet_page():
    data = load_versions()
    latest_ver = data.get("latest", "1.5.5")
    return render_template("operator_tablet.html", latest_version=latest_ver)

@app.route("/api/public-servers", methods=["GET"])
def proxy_public_servers():
    try:
        resp = requests.get("https://realisticbwr.org/api/public/servers", headers={"User-Agent": "RBWR-Operator-Tablet/1.0 (RBWR Thermal Calculator Utility)"}, timeout=10)
        return Response(resp.content, status=resp.status_code, content_type=resp.headers.get("Content-Type", "application/json"))
    except Exception as e:
        logger.error(f"Error fetching public servers API: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


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
        
    data = load_versions()
    latest_ver = data.get("latest", "1.5.5")
    return render_template("suggestions.html", latest_version=latest_ver, suggestions=get_public_suggestions())

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
    
    # Enforce rate limiting: 1 feedback entry per 12 hours per IP
    if ip != "unknown":
        now = datetime.now(timezone.utc)
        limit_period = timedelta(hours=12)
        for s in suggestions:
            if s.get("ip") == ip:
                try:
                    s_time = datetime.fromisoformat(s.get("timestamp"))
                    if now - s_time < limit_period:
                        time_left = limit_period - (now - s_time)
                        hours_left = int(time_left.total_seconds() // 3600)
                        mins_left = int((time_left.total_seconds() % 3600) // 60)
                        msg = f"Rate limit: Try again in {hours_left}h {mins_left}m."
                        return jsonify({"detail": msg}), 429
                except (ValueError, TypeError):
                    continue
    
    new_id = 1
    if suggestions:
        new_id = max(s.get("id", 0) for s in suggestions) + 1
        
    name = "Anonymous" if payload.anonymous or not payload.name.strip() else payload.name.strip()
    
    new_sug = {
        "id": new_id,
        "name": name,
        "suggestion": payload.suggestion.strip(),
        "ip": ip,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "pending"
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
        "ip": ip,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    crashes.append(new_crash)
    save_crashes(data)
    broadcast_update("dashboard")
    return jsonify({"message": "Crash report submitted successfully.", "id": new_id})

# --- Admin API / Dashboard ---

@app.route("/admin/suggestions/status", methods=["POST"])
@admin_required
def update_suggestion_status(username):
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

@app.route("/admin/suggestions/delete", methods=["POST"])
@admin_required
def delete_suggestion(username):
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
    return render_template("admin_panel.html", username=username, active_view="suggestions", is_root=is_root_user(username))

@app.route("/admin/crashes", methods=["GET"])
@admin_required
def view_crashes_dashboard(username):
    return render_template("admin_panel.html", username=username, active_view="crashes", is_root=is_root_user(username))

@app.route("/admin", methods=["GET"])
@admin_required
def admin_root(username):
    return render_template("admin_panel.html", username=username, active_view="overview", is_root=is_root_user(username))

@app.route("/admin/accounts", methods=["GET"])
@admin_required
def view_accounts_dashboard(username):
    if not is_root_user(username):
        return redirect("/admin")
    return render_template("admin_panel.html", username=username, active_view="accounts", is_root=True)

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
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    save_admins(admins_data)
    broadcast_update("accounts")
    return jsonify({"message": f"Admin account '{new_user}' created successfully."})

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

_login_attempts = {}

def is_login_rate_limited(ip: str) -> bool:
    if ip == "unknown":
        return False
    now = datetime.now(timezone.utc)
    attempts = _login_attempts.setdefault(ip, [])
    # Filter out attempts older than 1 minute
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
        
        # Check root
        root_user, root_pass = get_admin_credentials()
        is_root_username = secrets.compare_digest(username, root_user)
        is_root_password = secrets.compare_digest(password, root_pass)
        
        authenticated = False
        if is_root_username and is_root_password:
            authenticated = True
        else:
            # Check other admins
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