import html as _html
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, quote, urlparse

import requests

MAX_MEDIA_URLS = 5
MAX_MEDIA_URL_LENGTH = 1024

DISCORD_CDN_HOSTS = frozenset({"cdn.discordapp.com", "media.discordapp.net"})
DISCORD_REFRESH_API_URL = "https://discord.com/api/v10/attachments/refresh-urls"

CLOSED_TICKET_STATUSES = frozenset({
    "fixed",
    "resolved",
    "implemented",
    "accepted",
    "completed",
    "declined",
    "invalid",
    "closed",
    "rejected",
})

_URL_RE = re.compile(r"https?://[^\s<>'\"`\]\)]+", re.IGNORECASE)
_IMAGE_EXT_RE = re.compile(r"\.(?:png|jpe?g|gif|webp|bmp|avif)(?:$|\?)", re.IGNORECASE)

_refresh_cache_lock = threading.Lock()
# Maps (host, path) -> (refreshed_url, expires_at_epoch)
_refresh_cache: dict[tuple[str, str], tuple[str, float]] = {}


def sanitize_media_urls(raw: Any, max_count: int = MAX_MEDIA_URLS) -> list[str]:
    if not raw:
        return []
    items: list[str] = []
    if isinstance(raw, str):
        items = [part.strip() for part in re.split(r"[\r\n,]+", raw) if part.strip()]
    elif isinstance(raw, (list, tuple, set)):
        for entry in raw:
            if isinstance(entry, str) and entry.strip():
                items.append(entry.strip())

    cleaned: list[str] = []
    seen: set[str] = set()
    for url in items:
        if len(url) > MAX_MEDIA_URL_LENGTH:
            continue
        try:
            parsed = urlparse(url)
        except Exception:
            continue
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue
        if any(c in url for c in ("\r", "\n", "\t", " ")):
            continue
        if url in seen:
            continue
        seen.add(url)
        cleaned.append(url)
        if len(cleaned) >= max_count:
            break
    return cleaned


def is_discord_attachment_url(url: str) -> bool:
    if not url or not isinstance(url, str) or len(url) > MAX_MEDIA_URL_LENGTH:
        return False
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in DISCORD_CDN_HOSTS:
        return False
    path = parsed.path or ""
    return path.startswith("/attachments/") or path.startswith("/ephemeral-attachments/")


def is_embeddable_image_url(url: str) -> bool:
    if not url:
        return False
    if _IMAGE_EXT_RE.search(url):
        return True
    if is_discord_attachment_url(url):
        try:
            path = urlparse(url).path.lower()
            return bool(_IMAGE_EXT_RE.search(path))
        except Exception:
            return False
    return False


def extract_media_urls_from_text(text: str, max_count: int = MAX_MEDIA_URLS) -> list[str]:
    if not text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for match in _URL_RE.findall(text):
        cleaned = match.rstrip(".,;:!?")
        if cleaned in seen:
            continue
        if is_embeddable_image_url(cleaned) or is_discord_attachment_url(cleaned):
            seen.add(cleaned)
            found.append(cleaned)
            if len(found) >= max_count:
                break
    return found


def get_discord_url_expiry(url: str) -> Optional[float]:
    try:
        qs = parse_qs(urlparse(url).query)
        ex_vals = qs.get("ex")
        if not ex_vals:
            return None
        return float(int(ex_vals[0], 16))
    except Exception:
        return None


def _discord_cache_key(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    return ((parsed.hostname or "").lower(), parsed.path or "")


def refresh_discord_attachment_url(
    url: str,
    *,
    bot_token: Optional[str] = None,
    min_remaining_seconds: int = 600,
    timeout: float = 8.0,
) -> str:
    """
    Refresh an expired or soon-to-expire Discord CDN attachment URL via
    POST /api/v10/attachments/refresh-urls using the Discord bot token.
    Returns the original URL unchanged if it is not a Discord attachment URL,
    still has sufficient TTL, or if the API refresh fails.
    """
    if not is_discord_attachment_url(url):
        return url

    now = time.time()
    key = _discord_cache_key(url)

    with _refresh_cache_lock:
        cached = _refresh_cache.get(key)
        if cached and cached[1] > now + min_remaining_seconds:
            return cached[0]

    qs = parse_qs(urlparse(url).query)
    incoming_exp = get_discord_url_expiry(url)
    if incoming_exp and qs.get("hm") and incoming_exp > now + min_remaining_seconds:
        with _refresh_cache_lock:
            _refresh_cache[key] = (url, incoming_exp)
        return url

    token = (bot_token if bot_token is not None else os.environ.get("DISCORD_BOT_TOKEN", "")).strip()
    if not token:
        return url

    try:
        resp = requests.post(
            DISCORD_REFRESH_API_URL,
            headers={
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json",
            },
            json={"attachment_urls": [url]},
            timeout=timeout,
        )
        if resp.status_code == 200:
            payload = resp.json()
            refreshed_list = payload.get("refreshed_urls") or []
            if refreshed_list and isinstance(refreshed_list[0], dict):
                refreshed = str(refreshed_list[0].get("refreshed") or "").strip()
                if refreshed and is_discord_attachment_url(refreshed):
                    exp = get_discord_url_expiry(refreshed) or (now + 12 * 3600)
                    with _refresh_cache_lock:
                        if len(_refresh_cache) > 2000:
                            _refresh_cache.clear()
                        _refresh_cache[key] = (refreshed, exp)
                    return refreshed
    except Exception:
        pass

    return url


def get_display_media_url(url: str) -> str:
    if is_discord_attachment_url(url):
        return f"/tickets/media/resolve?url={quote(url, safe='')}"
    return url


def parse_iso_utc(raw: Any) -> Optional[datetime]:
    if not raw or not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def evaluate_auto_archive(
    ticket: dict[str, Any],
    *,
    now: Optional[datetime] = None,
    no_reply_days: int = 7,
    with_reply_days: int = 30,
) -> tuple[bool, str]:
    """
    Determine whether a ticket should be auto-archived (and its Discord channel deleted):
    - Only applies to completed/closed/merged tickets that are not already archived.
    - 7 days of inactivity if no reply was ever sent in `messages`.
    - 30 days of inactivity if at least one reply exists in `messages`.
    """
    if not isinstance(ticket, dict) or ticket.get("archived"):
        return False, "already_archived"

    status = str(ticket.get("status") or "").strip().lower()
    is_closed = (status in CLOSED_TICKET_STATUSES) or bool(ticket.get("merged_into"))
    if not is_closed:
        return False, "still_active"

    now_dt = now or datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)

    messages = ticket.get("messages") or []
    has_replies = len(messages) > 0
    threshold_days = with_reply_days if has_replies else no_reply_days

    candidates: list[datetime] = []
    for field in ("timestamp", "status_updated_at", "comment_timestamp", "reopened_at"):
        dt = parse_iso_utc(ticket.get(field))
        if dt:
            candidates.append(dt)

    if has_replies:
        for m in messages:
            if isinstance(m, dict):
                dt = parse_iso_utc(m.get("timestamp"))
                if dt:
                    candidates.append(dt)

    if not candidates:
        return False, "no_timestamp"

    last_activity = max(candidates)
    age = now_dt - last_activity
    if age >= timedelta(days=threshold_days):
        reason = f"inactive_{threshold_days}d_{'with_replies' if has_replies else 'no_replies'}"
        return True, reason

    return False, "within_grace_period"


def run_auto_archive_sweep(
    load_fn: Callable[[], dict[str, Any]],
    save_fn: Callable[[dict[str, Any]], None],
    *,
    close_channel_fn: Optional[Callable[..., tuple[bool, str]]] = None,
    broadcast_fn: Optional[Callable[[], None]] = None,
    now: Optional[datetime] = None,
    no_reply_days: int = 7,
    with_reply_days: int = 30,
) -> list[dict[str, Any]]:
    now_dt = now or datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()

    data = load_fn()
    suggestions = data.get("suggestions", [])
    archived_items: list[dict[str, Any]] = []
    channels_to_close: list[int] = []

    for s in suggestions:
        should_archive, reason = evaluate_auto_archive(
            s,
            now=now_dt,
            no_reply_days=no_reply_days,
            with_reply_days=with_reply_days,
        )
        if not should_archive:
            continue

        tid = s.get("id")
        had_channel = bool(s.get("discord_channel_id"))
        s["archived"] = True
        s["archived_at"] = now_iso
        s["archived_by"] = "Auto-Archive"
        s["auto_archived"] = True
        s["auto_archive_reason"] = reason

        archived_items.append({
            "id": tid,
            "reason": reason,
            "had_channel": had_channel,
        })
        if had_channel and tid is not None:
            channels_to_close.append(int(tid))

    if not archived_items:
        return []

    save_fn(data)
    if broadcast_fn:
        try:
            broadcast_fn()
        except Exception:
            pass

    if close_channel_fn and channels_to_close:
        for tid in channels_to_close:
            try:
                close_channel_fn(tid, closed_by="Auto-Archive", archive=True)
            except Exception:
                pass

    return archived_items


def _fmt_ts(raw: Any) -> str:
    dt = parse_iso_utc(raw)
    if not dt:
        return str(raw or "N/A")
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def generate_ticket_transcript_txt(ticket: dict[str, Any]) -> str:
    tid = ticket.get("id", "?")
    t_type = "Bug Report" if ticket.get("type") == "bug_report" else "Feature Suggestion"
    title = ticket.get("title") or "(Untitled)"
    status = str(ticket.get("status") or "pending").upper()
    target = str(ticket.get("target") or "overlay")
    is_anon = bool(ticket.get("anonymous"))
    author = "Anonymous" if is_anon else (ticket.get("discord_username") or ticket.get("name") or "Anonymous")
    resolved_ver = (ticket.get("resolved_version") or "").strip()
    upvotes = len(ticket.get("upvotes") or [])
    body = (ticket.get("suggestion") or ticket.get("description") or "").strip()
    media_urls = sanitize_media_urls(ticket.get("media_urls") or [])
    messages = ticket.get("messages") or []

    lines = [
        "=" * 72,
        f"RBWR UTILITY TICKET TRANSCRIPT  |  TICKET #{tid}",
        "=" * 72,
        f"Type:             {t_type}",
        f"Title:            {title}",
        f"Category:         {target}",
        f"Status:           {status}",
    ]
    if resolved_ver:
        lines.append(f"Release Version:  {resolved_ver}")
    lines.extend([
        f"Author:           {author}",
        f"Created:          {_fmt_ts(ticket.get('timestamp'))}",
        f"Archived:         {'Yes (' + _fmt_ts(ticket.get('archived_at')) + ')' if ticket.get('archived') else 'No'}",
        f"Upvotes:          {upvotes}",
        f"Exported:         {_fmt_ts(datetime.now(timezone.utc).isoformat())}",
        "-" * 72,
        "DESCRIPTION",
        "-" * 72,
        body or "(No description provided)",
    ])

    if media_urls:
        lines.extend(["", "-" * 72, "ATTACHED MEDIA URLS", "-" * 72])
        for idx, u in enumerate(media_urls, start=1):
            lines.append(f"  {idx}. {u}")

    if ticket.get("admin_comment"):
        lines.extend([
            "",
            "-" * 72,
            f"DEVELOPER NOTE ({ticket.get('comment_by') or 'Administrator'} @ {_fmt_ts(ticket.get('comment_timestamp'))})",
            "-" * 72,
            str(ticket.get("admin_comment")).strip(),
        ])

    lines.extend(["", "-" * 72, f"CONVERSATION HISTORY ({len(messages)} message(s))", "-" * 72])
    if not messages:
        lines.append("(No messages in conversation history)")
    else:
        for m in messages:
            role = "ADMIN" if m.get("sender_type") == "admin" else "AUTHOR"
            sender = m.get("sender_name") or ("Administrator" if role == "ADMIN" else "Author")
            src = f" [{m.get('source')}]" if m.get("source") else ""
            edited = " (edited)" if m.get("edited") else ""
            lines.append(f"[{_fmt_ts(m.get('timestamp'))}] [{role}] {sender}{src}{edited}:")
            msg_text = str(m.get("message") or "").strip()
            for msg_line in (msg_text.splitlines() or ["(empty)"]):
                lines.append(f"  {msg_line}")
            msg_media = sanitize_media_urls(m.get("media_urls") or [])
            for u in msg_media:
                lines.append(f"  [Media] {u}")
            lines.append("")

    lines.append("=" * 72)
    return "\n".join(lines) + "\n"


def generate_ticket_transcript_html(ticket: dict[str, Any]) -> str:
    esc = _html.escape
    tid = esc(str(ticket.get("id", "?")))
    t_type = "Bug Report" if ticket.get("type") == "bug_report" else "Feature Suggestion"
    title = esc(str(ticket.get("title") or "(Untitled)"))
    status = esc(str(ticket.get("status") or "pending").upper())
    target = esc(str(ticket.get("target") or "overlay"))
    is_anon = bool(ticket.get("anonymous"))
    author = esc("Anonymous" if is_anon else str(ticket.get("discord_username") or ticket.get("name") or "Anonymous"))
    resolved_ver = esc(str(ticket.get("resolved_version") or "").strip())
    upvotes = len(ticket.get("upvotes") or [])
    body = esc(str(ticket.get("suggestion") or ticket.get("description") or "").strip())
    media_urls = sanitize_media_urls(ticket.get("media_urls") or [])
    messages = ticket.get("messages") or []

    media_html = ""
    if media_urls:
        links = "".join(
            f'<li><a href="{esc(u)}" target="_blank" rel="noopener noreferrer">{esc(u)}</a></li>'
            for u in media_urls
        )
        media_html = f'<section class="card"><h2>Attached Media URLs</h2><ul class="media-list">{links}</ul></section>'

    note_html = ""
    if ticket.get("admin_comment"):
        note_html = (
            f'<section class="card note"><h2>Developer Note ({esc(str(ticket.get("comment_by") or "Administrator"))} &bull; {esc(_fmt_ts(ticket.get("comment_timestamp")))})</h2>'
            f'<pre>{esc(str(ticket.get("admin_comment")).strip())}</pre></section>'
        )

    msg_blocks: list[str] = []
    for m in messages:
        is_admin = m.get("sender_type") == "admin"
        role = "Administrator" if is_admin else "Author"
        cls = "msg admin" if is_admin else "msg author"
        sender = esc(str(m.get("sender_name") or role))
        ts = esc(_fmt_ts(m.get("timestamp")))
        src = f' <span class="badge">{esc(str(m.get("source")))}</span>' if m.get("source") else ""
        edited = ' <span class="muted">(edited)</span>' if m.get("edited") else ""
        msg_text = esc(str(m.get("message") or "").strip())
        msg_media = sanitize_media_urls(m.get("media_urls") or [])
        m_links = ""
        if msg_media:
            m_links = '<ul class="media-list">' + "".join(
                f'<li><a href="{esc(u)}" target="_blank" rel="noopener noreferrer">{esc(u)}</a></li>'
                for u in msg_media
            ) + "</ul>"
        msg_blocks.append(
            f'<div class="{cls}"><div class="msg-head"><div><strong>{sender}</strong> '
            f'<span class="badge">{role}</span>{src}{edited}</div><span class="muted">{ts}</span></div>'
            f'<pre>{msg_text}</pre>{m_links}</div>'
        )
    msgs_html = "".join(msg_blocks) or '<p class="muted">No messages in conversation history.</p>'

    version_meta = f'<div><span>Release Version</span><strong>{resolved_ver}</strong></div>' if resolved_ver else ""
    archived_val = f"Yes ({esc(_fmt_ts(ticket.get('archived_at')))})" if ticket.get("archived") else "No"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ticket #{tid} Transcript - RBWR Utility</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin: 0; padding: 28px 16px; background: #090b10; color: #e2e8f0; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; line-height: 1.55; }}
  .wrap {{ max-width: 880px; margin: 0 auto; display: flex; flex-direction: column; gap: 18px; }}
  .card {{ background: #111520; border: 1px solid #1e293b; border-radius: 12px; padding: 18px 20px; }}
  .note {{ border-color: #2563eb66; background: #0f1c34; }}
  h1 {{ margin: 0 0 6px; font-size: 20px; color: #f8fafc; }}
  h2 {{ margin: 0 0 12px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: #94a3b8; }}
  .meta {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; margin-top: 14px; font-size: 12px; }}
  .meta div {{ background: #0b0e16; border: 1px solid #1e293b; border-radius: 8px; padding: 8px 10px; display: flex; flex-direction: column; gap: 2px; }}
  .meta span {{ font-size: 10px; text-transform: uppercase; color: #64748b; }}
  .meta strong {{ color: #f1f5f9; }}
  pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; font-family: inherit; font-size: 13px; color: #e2e8f0; }}
  .msg {{ border-radius: 10px; padding: 12px 14px; margin-bottom: 10px; border: 1px solid #1e293b; background: #0b0e16; }}
  .msg.admin {{ border-color: #3b82f655; background: #0d182d; }}
  .msg.author {{ border-color: #10b98155; background: #0a201a; }}
  .msg-head {{ display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; font-size: 12px; }}
  .badge {{ display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 10px; text-transform: uppercase; background: #1e293b; color: #cbd5e1; border: 1px solid #334155; }}
  .muted {{ color: #94a3b8; font-size: 11px; }}
  .media-list {{ margin: 8px 0 0; padding-left: 18px; font-size: 12px; }}
  .media-list a {{ color: #60a5fa; word-break: break-all; }}
</style>
</head>
<body>
<div class="wrap">
  <header class="card">
    <div class="muted">RBWR UTILITY TICKET TRANSCRIPT &bull; EXPORTED {esc(_fmt_ts(datetime.now(timezone.utc).isoformat()))}</div>
    <h1>#{tid}: {title}</h1>
    <div class="meta">
      <div><span>Type</span><strong>{esc(t_type)}</strong></div>
      <div><span>Category</span><strong>{target}</strong></div>
      <div><span>Status</span><strong>{status}</strong></div>
      {version_meta}
      <div><span>Author</span><strong>{author}</strong></div>
      <div><span>Created</span><strong>{esc(_fmt_ts(ticket.get("timestamp")))}</strong></div>
      <div><span>Archived</span><strong>{archived_val}</strong></div>
      <div><span>Upvotes</span><strong>{upvotes}</strong></div>
    </div>
  </header>
  <section class="card">
    <h2>Description</h2>
    <pre>{body or "(No description provided)"}</pre>
  </section>
  {media_html}
  {note_html}
  <section class="card">
    <h2>Conversation History ({len(messages)} message(s))</h2>
    {msgs_html}
  </section>
</div>
</body>
</html>
"""