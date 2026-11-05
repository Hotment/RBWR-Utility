"""
Discord bot features managed from the admin panel.

* embed builder: list channels/roles, post or edit embeds as the bot, templates and history
* direct messages: write to server members as the bot, their replies show up in the panel
* autorole overview/settings/sync for the panel (same config file as /autorole)
* moderation (/mod, /unban, /warn, /warnings, /unwarn) with warning escalation rules
* automod: blocked words, invites, links, mass mentions, caps, emoji, walls of text, spam,
  repeated messages, raid protection and minimum account age
* welcome & goodbye messages, FAQ entries (/faq), custom prefix commands (e.g. !bug)
* error monitor: errors are stored in data/errors.json and shown in the admin panel;
  the alert in Discord pings DISCORD_ERROR_ALERT_PING_USER_ID, as before

The bot itself lives in bot/bot.py. It calls `register(bot, ...)` while it registers its own
commands, and the web server calls `configure(...)` once at startup. All blocking functions
below are safe to call from web request threads: they run on the bot's event loop and wait.
"""
from __future__ import annotations

import asyncio
import functools
import json
import logging
import os
import re
import secrets
import threading
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Coroutine

import disnake
from disnake.ext import commands

log = logging.getLogger("rbwr-bot-features")

# ---------------------------------------------------------------- storage
# data/ next to app.py (server/data in the repo, data/ in the flat production layout)
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

_lock = threading.RLock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JsonStore:
    """A JSON file; every read-modify-write goes through edit(), which holds a process-wide lock."""

    def __init__(self, filename: str, default: dict):
        self.path = os.path.join(DATA_DIR, filename)
        self.default = default

    def load(self) -> dict:
        with _lock:
            if not os.path.exists(self.path):
                return json.loads(json.dumps(self.default))
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, ValueError):
                return json.loads(json.dumps(self.default))

    def save(self, data: dict) -> None:
        with _lock:
            tmp_path = self.path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.path)

    @contextmanager
    def edit(self):
        with _lock:
            data = self.load()
            yield data
            self.save(data)


embeds_store = JsonStore("embeds.json", {"templates": {}, "history": []})
dms_store = JsonStore("dms.json", {"conversations": {}})
# default escalation: 3 active warnings -> 1h timeout, 5 -> 1 day timeout
warnings_store = JsonStore("warnings.json", {
    "warnings": [], "last_id": 0,
    "config": {"expire_days": 0, "rules": [{"count": 3, "action": "timeout", "duration": "1h"},
                                           {"count": 5, "action": "timeout", "duration": "1d"}]},
})
welcome_store = JsonStore("welcome.json", {"welcome": {}, "goodbye": {}})
faq_store = JsonStore("faq.json", {"entries": {}})
# custom prefix commands; {site} is the website URL, {target} the mentioned member (or the author)
commands_store = JsonStore("custom_commands.json", {"prefix": "!", "commands": {
    "bug": {"aliases": ["bugs", "report"], "response": "{target}, found a bug? Report it here: {site}/tickets",
            "template": "", "role_id": "", "cooldown": 10, "reply": True, "delete_trigger": False, "enabled": True, "uses": 0},
    "suggest": {"aliases": ["idea"], "response": "{target}, got an idea? Suggest it here: {site}/tickets",
                "template": "", "role_id": "", "cooldown": 10, "reply": True, "delete_trigger": False, "enabled": True, "uses": 0},
}})
automod_store = JsonStore("automod.json", {"config": {}, "incidents": [], "last_id": 0})
errors_store = JsonStore("errors.json", {"errors": [], "last_id": 0})


# GIFs and images in DMs: only these hosts are ever shown or stored, so a member can not make the panel load an arbitrary site
MEDIA_DOMAINS = ("discordapp.com", "discordapp.net", "tenor.com", "giphy.com", "klipy.com")
UPLOAD_NAME_RE = r"^[0-9a-f]{32}\.(png|jpg|gif|webp)$"
UPLOAD_DIR = os.path.join(DATA_DIR, "admin_uploads")
MAX_DM_MEDIA = 4
MAX_DM_IMAGE_BYTES = 8 * 1024 * 1024


def safe_media_url(url) -> bool:
    from urllib.parse import urlsplit
    try:
        parts = urlsplit(str(url))
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host == d or host.endswith("." + d) for d in MEDIA_DOMAINS)


def image_ext(head: bytes) -> str | None:
    """The real type from the first bytes of an image (the sender's Content-Type is not trusted; no SVG)."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def _delete_dm_files(messages: list) -> None:
    for m in messages:
        names = list(m.get("images") or []) + [x.get("local") for x in (m.get("media") or []) if x.get("local")]
        for name in names:
            if re.match(UPLOAD_NAME_RE, str(name)):
                try:
                    os.remove(os.path.join(UPLOAD_DIR, name))
                except OSError:
                    pass


def add_dm_media(discord_message_id: str, media: list) -> bool:
    """Adds GIFs/images Discord resolved later (a link's embed arrives after the message) to a stored DM message."""
    with dms_store.edit() as data:
        for conv in data.get("conversations", {}).values():
            for m in conv.get("messages", []):
                if m.get("discord_message_id") == str(discord_message_id):
                    have = {x.get("url") or x.get("local") for x in m.get("media", [])}
                    m["media"] = ((m.get("media") or []) + [x for x in media if x.get("url") not in have])[:MAX_DM_MEDIA]
                    return True
    return False


def record_dm(user_id, profile: dict, message: dict, incoming: bool) -> None:
    """Adds a message to the bot's DM conversation with a member (keeps the last 500 per member)."""
    now = utc_now()
    with dms_store.edit() as data:
        conv = data.setdefault("conversations", {}).setdefault(
            str(user_id), {"user_id": str(user_id), "messages": [], "unread": 0}
        )
        conv.update({k: v for k, v in profile.items() if k != "id" and v})
        conv["messages"].append({**message, "at": now, "direction": "in" if incoming else "out"})
        dropped = conv["messages"][:-500]
        del conv["messages"][:-500]
        _delete_dm_files(dropped)
        conv["updated_at"] = now
        if incoming:
            conv["unread"] = conv.get("unread", 0) + 1


def add_embed_history(entry: dict) -> None:
    """Remembers the last 50 embeds the bot posted, so they can be re-opened and edited in the panel."""
    with embeds_store.edit() as data:
        history = data.setdefault("history", [])
        history.insert(0, {**entry, "sent_at": utc_now()})
        del history[50:]


def embed_templates() -> dict:
    return embeds_store.load().get("templates", {})


# ---------------------------------------------------------------- configuration

def _int_env(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    return int(value) if value.isdigit() else None


BRAND = disnake.Color(0x00D1FF)  # the color of RBWR bot embeds
FOOTER = "RBWR Utility"


class _Hooks:
    """Filled by configure() (web server) and register() (bot)."""

    def __init__(self):
        self.is_admin: Callable[[str], bool] = lambda _id: False
        self.is_owner: Callable[[str], bool] = lambda _id: False
        self.admin_name: Callable[[str], str | None] = lambda _id: None
        self.site_url: str = os.getenv("SERVER_BASE_URL", "https://rbwr.hotment.dev").rstrip("/")
        self.guild_id: int | None = _int_env("DISCORD_GUILD_ID")
        self.mod_log_channel_id: int | None = _int_env("DISCORD_MOD_LOG_CHANNEL_ID")
        self.autorole_load: Callable[[], dict] | None = None
        self.autorole_save: Callable[[dict], bool] | None = None
        self.autorole_resolve: Callable[[disnake.Guild], tuple] | None = None


hooks = _Hooks()
_bot: commands.InteractionBot | None = None
_loop: asyncio.AbstractEventLoop | None = None


def configure(is_admin=None, is_owner=None, admin_name=None, site_url: str | None = None) -> None:
    """Called by the web server: who counts as a website admin / owner (root) and their display name."""
    if is_admin:
        hooks.is_admin = is_admin
    if is_owner:
        hooks.is_owner = is_owner
    if admin_name:
        hooks.admin_name = admin_name
    if site_url:
        hooks.site_url = site_url.rstrip("/")


def _is_admin_id(user_id) -> bool:
    try:
        return bool(hooks.is_admin(str(user_id)))
    except Exception:
        return False


def _is_owner_id(user_id) -> bool:
    try:
        return bool(hooks.is_owner(str(user_id)))
    except Exception:
        return False


def _guild_id() -> int | None:
    return hooks.guild_id


# ---------------------------------------------------------------- helpers

def is_ready() -> bool:
    return bool(_bot and _bot.is_ready() and _loop and _loop.is_running())


def _log_future_error(fut: "asyncio.Future[Any]") -> None:
    try:
        exc = fut.exception()
    except Exception:
        return
    if exc:
        log.error("Background bot task failed: %s", exc, exc_info=exc)


async def _get_channel(channel_id) -> Any:
    if not channel_id or not _bot:
        return None
    try:
        cid = int(channel_id)
        return _bot.get_channel(cid) or await _bot.fetch_channel(cid)
    except Exception:
        return None


async def _get_guild() -> disnake.Guild | None:
    gid = _guild_id()
    if not _bot or not gid:
        return None
    try:
        return _bot.get_guild(gid) or await _bot.fetch_guild(gid)
    except Exception:
        return None


async def _get_member(user_id) -> disnake.Member | None:
    guild = await _get_guild()
    if not guild or not user_id:
        return None
    try:
        uid = int(user_id)
        return guild.get_member(uid) or await guild.fetch_member(uid)
    except Exception:
        return None


def discord_display_name(user_id) -> str | None:
    """Server nickname (or global name) of a Discord user from the bot's cache. Never blocks."""
    if not _bot or not str(user_id or "").isdigit():
        return None
    gid = _guild_id()
    guild = _bot.get_guild(gid) if gid else None
    member = guild.get_member(int(user_id)) if guild else None
    if member:
        return member.display_name
    user = _bot.get_user(int(user_id))
    return (user.global_name or user.name) if user else None


def _is_admin_user(user: disnake.User | disnake.Member) -> bool:
    if _is_admin_id(user.id):
        return True
    perms = getattr(user, "guild_permissions", None)
    return bool(perms and perms.administrator)


def _parse_time(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


class BotActionError(Exception):
    """A failure with a message that is safe to show to the admin who triggered it."""


def _run(coro_factory: Callable[[], Coroutine[Any, Any, Any]], timeout: float = 10) -> Any:
    """Runs a coroutine on the bot loop and waits for it, turning Discord errors into BotActionError."""
    if not is_ready():
        raise BotActionError("The Discord bot is offline.")
    fut = asyncio.run_coroutine_threadsafe(coro_factory(), _loop)  # type: ignore[arg-type]
    try:
        return fut.result(timeout=timeout)
    except BotActionError:
        raise
    except disnake.Forbidden:
        raise BotActionError("The bot doesn't have permission to do that in this channel.")
    except disnake.NotFound:
        raise BotActionError("That channel or message no longer exists.")
    except disnake.HTTPException as exc:
        log.warning("Discord rejected a request: %s", exc)
        raise BotActionError(f"Discord rejected the request: {exc.text}" if exc.text else "Discord rejected the request.")
    except TimeoutError:
        fut.cancel()
        raise BotActionError("Discord didn't respond in time. Try again.")


def can_manage_server(user: disnake.User | disnake.Member) -> bool:
    """Website owners (root admins), website admins and Discord server administrators."""
    if _is_owner_id(user.id) or _is_admin_id(user.id):
        return True
    perms = getattr(user, "guild_permissions", None)
    return bool(perms and perms.administrator)


def _mentions(allow: bool) -> disnake.AllowedMentions:
    return disnake.AllowedMentions.all() if allow else disnake.AllowedMentions.none()


def _panel_guild() -> disnake.Guild:
    """The RBWR Discord server managed from the admin panel."""
    gid = _guild_id()
    guild = _bot.get_guild(gid) if _bot and gid else None
    if not guild:
        raise BotActionError("DISCORD_GUILD_ID is not set or the bot isn't on that server.")
    return guild


# ---------------------------------------------------------------- embed builder

def list_text_channels() -> list[dict]:
    """Text channels on the server where the bot can post embeds (blocking)."""
    async def _channels():
        guild = _panel_guild()
        me = guild.me
        channels = sorted(guild.text_channels, key=lambda c: ((c.category.position if c.category else -1), c.position))
        return [
            {"id": str(c.id), "name": c.name, "category": c.category.name if c.category else ""}
            for c in channels
            if c.permissions_for(me).send_messages and c.permissions_for(me).embed_links and c.permissions_for(me).view_channel
        ]
    return _run(_channels, timeout=6)


def list_roles() -> dict:
    """Roles on the server that the embed builder can ping (blocking)."""
    async def _roles():
        guild = _panel_guild()
        return {
            "roles": [
                {"id": str(r.id), "name": r.name, "color": f"#{r.color.value:06x}" if r.color.value else None,
                 "mentionable": r.mentionable}
                for r in reversed(guild.roles) if not r.is_default()
            ],
            # with "Mention @everyone, @here and All Roles" the bot can ping roles that aren't mentionable
            "can_ping_all": bool(guild.me and guild.me.guild_permissions.mention_everyone),
        }
    return _run(_roles, timeout=6)


async def _post_embed(channel, content: str, embed_dict: dict | None, allow_mentions: bool, edit_message_id: str | None = None) -> dict:
    if not isinstance(channel, disnake.TextChannel) or channel.guild.id != _guild_id():
        raise BotActionError("Pick a text channel on the RBWR server.")
    kwargs = {
        "content": content or None,
        "embed": disnake.Embed.from_dict(embed_dict) if embed_dict else None,  # pyright: ignore[reportArgumentType]
        "allowed_mentions": _mentions(allow_mentions),
    }
    if edit_message_id:
        msg = await channel.fetch_message(int(edit_message_id))
        if not _bot or not _bot.user or msg.author.id != _bot.user.id:
            raise BotActionError("The bot can only edit messages it sent itself.")
        await msg.edit(**kwargs)
    else:
        msg = await channel.send(**kwargs)
    return {"message_id": str(msg.id), "channel_id": str(channel.id), "channel_name": channel.name, "jump_url": msg.jump_url}


def send_embed(channel_id: str, content: str, embed_dict: dict | None, allow_mentions: bool = False,
               edit_message_id: str | None = None) -> dict:
    """Posts (or edits) an embed message from the web panel (blocking). Raises BotActionError."""
    async def _send():
        channel = await _get_channel(channel_id)
        if channel is None:
            raise BotActionError("Channel not found.")
        return await _post_embed(channel, content, embed_dict, allow_mentions, edit_message_id)
    return _run(_send)


def template_message(name: str) -> tuple[str, dict | None, bool] | None:
    """(content, embed dict, allow mentions) of a saved Embed Builder template, or None."""
    template = embed_templates().get(name)
    if not template:
        return None
    embed = template.get("embed")
    if embed:
        embed = json.loads(json.dumps(embed))
        if "timestamp" in embed:
            embed["timestamp"] = utc_now()
    return template.get("content") or "", embed, bool(template.get("allow_mentions"))


# ---------------------------------------------------------------- direct messages
# Admins write to server members from the admin panel; members' replies to the bot are stored too.

def _member_info(member: disnake.Member | disnake.User) -> dict:
    return {
        "id": str(member.id),
        "name": member.display_name,
        "username": member.name,
        "avatar": str(member.display_avatar.url),
    }


def search_members(query: str) -> list[dict]:
    """Members of the server whose name or ID matches `query` (blocking)."""
    async def _search():
        guild = _panel_guild()
        q = query.strip().lower()
        if q.isdigit():
            member = await _get_member(q)
            return [_member_info(member)] if member and not member.bot else []
        # without the Server Members intent the member cache is empty, so ask Discord (prefix search)
        members = guild.members if _bot.intents.members else await guild.query_members(q, limit=25)  # pyright: ignore[reportOptionalMemberAccess]
        found = [m for m in members
                 if not m.bot and q in f"{m.name} {m.display_name} {m.global_name or ''}".lower()]
        found.sort(key=lambda m: m.display_name.lower())
        return [_member_info(m) for m in found[:25]]
    return _run(_search, timeout=8)


def send_dm(user_id: str, text: str, files: list[tuple[str, str]] = ()) -> dict:
    """Sends a DM (text and/or GIF/image files as (path, filename)) to a member of the server (blocking). Raises BotActionError."""
    async def _send():
        member = await _get_member(user_id)
        if not member:
            raise BotActionError("This user isn't on the RBWR server, so the bot can't message them.")
        if member.bot:
            raise BotActionError("Bots can't receive DMs.")
        try:
            msg = await member.send(text or None, files=[disnake.File(p, filename=n) for p, n in files] or None,
                                    allowed_mentions=disnake.AllowedMentions.none())
        except disnake.Forbidden:
            raise BotActionError(f"{member.display_name} doesn't accept DMs from the bot (DMs closed or the bot is blocked).")
        return {"message_id": str(msg.id), "profile": _member_info(member)}
    return _run(_send)


def _media_from_embeds(embeds: list[dict]) -> list[dict]:
    """GIFs and images Discord resolved from a link (Tenor, Giphy, Klipy...) or an attachment, as plain dicts of the embed JSON."""
    media = []
    for e in embeds or []:
        video = (e.get("video") or {}).get("url")
        image = (e.get("image") or {}).get("url") or (e.get("thumbnail") or {}).get("url")
        if video and safe_media_url(video):
            item = {"type": "video", "url": video}
            if image and safe_media_url(image):
                item["poster"] = image
            media.append(item)
        elif image and safe_media_url(image) and e.get("type") in ("gifv", "image", "rich", "link", None):
            media.append({"type": "image", "url": image})
    return media[:MAX_DM_MEDIA]


async def _save_dm_images(message: disnake.Message) -> tuple[list[dict], list[str]]:
    """Downloads the image attachments (Discord's links expire after a day). Returns (media, urls of the other attachments)."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    media, others = [], []
    for a in message.attachments:
        if len(media) < MAX_DM_MEDIA and (a.content_type or "").startswith("image/") and a.size <= MAX_DM_IMAGE_BYTES:
            try:
                data = await a.read()
            except disnake.HTTPException:
                data = b""
            ext = image_ext(data[:16])
            if ext:
                name = f"{secrets.token_hex(16)}.{ext}"
                with open(os.path.join(UPLOAD_DIR, name), "wb") as f:
                    f.write(data)
                media.append({"type": "image", "local": name})
                continue
        others.append(a.url)
    return media, others


async def record_incoming_dm(message: disnake.Message) -> None:
    """A DM sent to the bot -> shown in the admin panel's Messages view."""
    text = (message.content or "").strip()
    media, others = await _save_dm_images(message)
    if others:
        text = "\n".join([text] + others).strip()
    media = (media + _media_from_embeds([e.to_dict() for e in message.embeds]))[:MAX_DM_MEDIA]
    if not text and not media:
        return
    member = await _get_member(message.author.id)
    record_dm(
        message.author.id,
        _member_info(member or message.author),
        {"text": text[:4000], "discord_message_id": str(message.id), **({"media": media} if media else {})},
        incoming=True,
    )


# ---------------------------------------------------------------- autorole (admin panel)
# Uses the same config file as /autorole in bot.py (passed in through register()).

def _autorole_load() -> dict:
    data = hooks.autorole_load() if hooks.autorole_load else {}
    return data if isinstance(data, dict) else {}


def _autorole_config(guild_id: int) -> dict:
    return _autorole_load().get("guilds", {}).get(str(guild_id), {})


def _resolve_autorole(guild: disnake.Guild) -> tuple[disnake.Role | None, str | None, bool]:
    if hooks.autorole_resolve:
        return hooks.autorole_resolve(guild)
    return None, None, False


def _autorole_problem(guild: disnake.Guild, role: disnake.Role) -> str | None:
    """Why the bot can't give `role` to members, or None if it can."""
    me = guild.me
    if not me:
        return None
    if not me.guild_permissions.manage_roles:
        return "The bot lacks the 'Manage Roles' permission."
    if role >= me.top_role:
        return (f"Role '{role.name}' is higher than or equal to the bot's highest role '{me.top_role.name}'. "
                "Move the bot's role above it in Server Settings → Roles.")
    return None


_autorole_syncs: set[int] = set()  # guilds with a sync in progress
_background_tasks: set[asyncio.Task] = set()


def _role_info(guild: disnake.Guild, role: disnake.Role) -> dict:
    return {
        "id": str(role.id),
        "name": role.name,
        "color": f"#{role.color.value:06x}" if role.color.value else None,
        "problem": _autorole_problem(guild, role),
    }


def autorole_overview() -> dict:
    """Autorole state of the server for the admin panel (blocking)."""
    async def _overview():
        guild = _panel_guild()
        role, source, enabled = _resolve_autorole(guild)
        config = _autorole_config(guild.id)
        updated_by = config.get("updated_by")
        member = guild.get_member(int(updated_by)) if str(updated_by or "").isdigit() else None  # pyright: ignore[reportArgumentType]
        return {
            "guild": guild.name,
            "roles": [_role_info(guild, r) for r in reversed(guild.roles) if not r.is_default() and not r.managed],
            "role": _role_info(guild, role) if role else None,
            "configured_role_id": str(config["role_id"]) if config.get("role_id") else None,
            "source": source,
            "enabled": enabled,
            "include_bots": bool(config.get("include_bots")),
            "members_intent": bool(_bot and _bot.intents.members),
            "updated_at": config.get("updated_at"),
            "updated_by": member.display_name if member else updated_by,
            "last_sync": config.get("last_sync"),
            "syncing": guild.id in _autorole_syncs,
        }
    return _run(_overview, timeout=6)


def _update_autorole(guild_id: int, **fields) -> None:
    with _lock:
        config = _autorole_load()
        if not isinstance(config.get("guilds"), dict):
            config["guilds"] = {}
        entry = config["guilds"].setdefault(str(guild_id), {})
        entry.update(fields)
        if hooks.autorole_save:
            hooks.autorole_save(config)


def set_autorole(role_id: str | None, enabled: bool, include_bots: bool, updated_by: str) -> None:
    """Saves the autorole from the admin panel (blocking). An empty role_id clears the role."""
    async def _set():
        guild = _panel_guild()
        role = guild.get_role(int(role_id)) if role_id and role_id.isdigit() else None
        if role_id and not role:
            raise BotActionError("That role doesn't exist on the server anymore.")
        if role and (role.is_default() or role.managed):
            raise BotActionError("@everyone and bot/integration roles can't be used as an autorole.")
        _update_autorole(guild.id, enabled=enabled, include_bots=include_bots,
                         role_id=str(role.id) if role else None, role_name=role.name if role else None,
                         updated_at=utc_now(), updated_by=str(updated_by))
    _run(_set, timeout=6)


async def _sync_autorole(guild: disnake.Guild, role: disnake.Role, include_bots: bool, started_by: str) -> tuple[int, int]:
    assigned = failed = 0
    try:
        for member in guild.members:
            if (member.bot and not include_bots) or role in member.roles:
                continue
            try:
                await member.add_roles(role, reason=f"Autorole sync by {started_by}")
                assigned += 1
                await asyncio.sleep(0.3)
            except Exception as exc:
                log.warning("Autorole sync: could not give '%s' to %s: %s", role.name, member, exc)
                failed += 1
    finally:
        _autorole_syncs.discard(guild.id)
        _update_autorole(guild.id, last_sync={
            "role_name": role.name, "assigned": assigned, "failed": failed,
            "started_by": started_by, "finished_at": utc_now(),
        })
    return assigned, failed


def start_autorole_sync(include_bots: bool, started_by: str) -> None:
    """Starts giving the autorole to existing members in the background (blocking only for the checks)."""
    async def _start():
        guild = _panel_guild()
        role, _, _ = _resolve_autorole(guild)
        if not role:
            raise BotActionError("No autorole is configured. Set a role first.")
        if not _bot or not _bot.intents.members:
            raise BotActionError("The Server Members Intent is disabled in the Discord Developer Portal, so the bot can't list members.")
        problem = _autorole_problem(guild, role)
        if problem:
            raise BotActionError(problem)
        if guild.id in _autorole_syncs:
            raise BotActionError("A sync is already running for this server.")
        _autorole_syncs.add(guild.id)
        task = asyncio.create_task(_sync_autorole(guild, role, include_bots, started_by))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        task.add_done_callback(_log_future_error)
    _run(_start, timeout=6)


# ---------------------------------------------------------------- moderation (/mod)

# action -> (Discord permission it needs, button label, button style)
MOD_ACTIONS = {
    "warn": ("moderate_members", "Warn", disnake.ButtonStyle.secondary),
    "timeout": ("moderate_members", "Timeout", disnake.ButtonStyle.secondary),
    "untimeout": ("moderate_members", "Remove Timeout", disnake.ButtonStyle.success),
    "nick": ("manage_nicknames", "Change Nickname", disnake.ButtonStyle.primary),
    "kick": ("kick_members", "Kick", disnake.ButtonStyle.danger),
    "ban": ("ban_members", "Ban", disnake.ButtonStyle.danger),
}
MAX_TIMEOUT = timedelta(days=28)  # Discord's limit
_DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def _can_moderate(user: disnake.User | disnake.Member, action: str) -> bool:
    if can_manage_server(user):
        return True
    perms = getattr(user, "guild_permissions", None)
    return bool(perms and getattr(perms, MOD_ACTIONS[action][0]))


def parse_duration(text: str) -> timedelta | None:
    """'10m', '1h30m', '2d', '1w' or a plain number of minutes."""
    text = (text or "").strip().lower().replace(" ", "")
    if text.isdigit():
        return timedelta(minutes=int(text)) if int(text) else None
    total, number = 0, ""
    for ch in text:
        if ch.isdigit():
            number += ch
        elif ch in _DURATION_UNITS and number:
            total += int(number) * _DURATION_UNITS[ch]
            number = ""
        else:
            return None
    return timedelta(seconds=total) if total and not number else None


def _format_duration(delta: timedelta) -> str:
    seconds, parts = int(delta.total_seconds()), []
    for unit, size in (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if seconds >= size:
            parts.append(f"{seconds // size}{unit}")
            seconds %= size
    return " ".join(parts) or "0s"


def _bot_hierarchy_problem(member: disnake.Member) -> str | None:
    """Why the bot can't act on `member`, or None."""
    guild = member.guild
    if member.id == guild.owner_id:
        return "The server owner can't be moderated."
    if _bot and _bot.user and member.id == _bot.user.id:
        return "The bot can't moderate itself."
    if guild.me and guild.me.top_role <= member.top_role:
        return (f"The bot's highest role must be above {member.display_name}'s — "
                "move it up in Server Settings → Roles.")
    return None


def _hierarchy_problem(actor: disnake.User | disnake.Member, member: disnake.Member) -> str | None:
    """Why `actor` (or the bot) can't act on `member`, or None if nothing stops it."""
    guild = member.guild
    if member.id == actor.id:
        return "You can't moderate yourself."
    # website owners skip the role check, everyone else needs a higher role than the target
    if (isinstance(actor, disnake.Member) and actor.id != guild.owner_id
            and not _is_owner_id(actor.id) and actor.top_role <= member.top_role):
        return f"Your highest role must be above {member.display_name}'s."
    return _bot_hierarchy_problem(member)


def build_mod_panel(member: disnake.Member, actor: disnake.User | disnake.Member) -> tuple[disnake.Embed, list]:
    embed = disnake.Embed(title=f"Moderation — {member.display_name}", color=BRAND)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="User", value=f"{member.mention} (`{member}`)", inline=True)
    embed.add_field(name="ID", value=f"`{member.id}`", inline=True)
    embed.add_field(name="Nickname", value=member.nick or "—", inline=True)
    embed.add_field(name="Account Created", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
    if member.joined_at:
        embed.add_field(name="Joined Server", value=f"<t:{int(member.joined_at.timestamp())}:R>", inline=True)
    timeout = member.current_timeout
    embed.add_field(
        name="Timeout",
        value=f"Until <t:{int(timeout.timestamp())}:f> (<t:{int(timeout.timestamp())}:R>)" if timeout else "None",
        inline=True,
    )
    warnings = active_warnings(member.id)
    lines = []
    for w in warnings[-5:]:
        at = _parse_time(w.get("at"))
        lines.append(f"`#{w['id']}` " + (f"<t:{int(at.timestamp())}:d> " if at else "") + w["reason"][:80])
    embed.add_field(name=f"Active Warnings ({len(warnings)})", value="\n".join(lines)[:1024] or "None", inline=False)
    roles = [r.mention for r in reversed(member.roles) if not r.is_default()]
    embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles[:20])[:1024] or "—", inline=False)
    embed.set_footer(text=f"{FOOTER} • Moderation")

    buttons = [
        disnake.ui.Button(
            label=label, style=style, custom_id=f"rbwr_mod_{action}:{member.id}",
            disabled=not _can_moderate(actor, action) or (action == "untimeout" and not timeout),
        )
        for action, (_, label, style) in MOD_ACTIONS.items()
    ]
    return embed, [disnake.ui.ActionRow(*buttons[:5]), disnake.ui.ActionRow(*buttons[5:])]  # 5 buttons per row


def _mod_modal(action: str, member: disnake.Member) -> disnake.ui.Modal:
    reason = disnake.ui.TextInput(
        label="Reason", custom_id="reason", style=disnake.TextInputStyle.paragraph,
        required=False, max_length=400, placeholder="Shown in the audit log and sent to the member",
    )
    if action == "warn":
        title, inputs = "Warn", [
            disnake.ui.TextInput(label="Reason", custom_id="reason", style=disnake.TextInputStyle.paragraph,
                                 max_length=400, placeholder="Saved in the member's warning history and sent to them"),
        ]
    elif action == "timeout":
        title, inputs = "Timeout", [
            disnake.ui.TextInput(label="Duration", custom_id="duration", placeholder="e.g. 10m, 2h, 1d, 1w (max 28d)", max_length=20),
            reason,
        ]
    elif action == "nick":
        title, inputs = "Change Nickname", [
            disnake.ui.TextInput(label="New nickname (empty resets it)", custom_id="nick", required=False,
                                 max_length=32, value=member.nick or None),
            disnake.ui.TextInput(label="Reason", custom_id="reason", required=False, max_length=400),
        ]
    elif action == "ban":
        title, inputs = "Ban", [
            reason,
            disnake.ui.TextInput(label="Delete their messages from last N days (0-7)", custom_id="delete_days",
                                 required=False, max_length=1, value="0"),
        ]
    else:
        title, inputs = "Kick", [reason]
    return disnake.ui.Modal(
        title=f"{title}: {member.display_name}"[:45], custom_id=f"rbwr_mod_modal_{action}:{member.id}", components=inputs,
    )


async def _dm_mod_notice(member: disnake.Member, what: str, reason: str | None) -> None:
    embed = disnake.Embed(title=f"You were {what} in {member.guild.name}"[:256],
                          description=f"**Reason:** {reason or 'No reason given'}", color=BRAND)
    embed.set_footer(text=f"{FOOTER} • Moderation")
    try:
        await member.send(embed=embed)
    except Exception:
        log.info("Could not DM moderation notice to %s.", member)


async def _log_mod_action(actor: str, target: disnake.abc.Snowflake, text: str, reason: str | None) -> None:
    """`actor` is a mention or a name like "Alex (via website)"."""
    log.info("Moderation: %s -> %s: %s (%s)", actor, target.id, text, reason)
    channel = await _get_channel(hooks.mod_log_channel_id)
    if not isinstance(channel, disnake.TextChannel):
        return
    embed = disnake.Embed(title=f"Moderation: {text}"[:256], color=BRAND, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="Member", value=f"<@{target.id}> (`{target.id}`)", inline=True)
    embed.add_field(name="Moderator", value=actor, inline=True)
    embed.add_field(name="Reason", value=(reason or "No reason given")[:1024], inline=False)
    embed.set_footer(text=f"{FOOTER} • Moderation")
    try:
        await channel.send(embed=embed, allowed_mentions=disnake.AllowedMentions.none())
    except Exception as exc:
        log.warning("Could not post to the moderation log channel: %s", exc)


async def _run_mod_action(actor: str, actor_mention: str, member: disnake.Member, action: str,
                          values: dict[str, str]) -> str:
    """Performs a moderation action and returns what happened ("timed out for 1h", ...).
    `actor` goes to the audit log ("name (via /mod)"), `actor_mention` to the mod log channel."""
    reason = (values.get("reason") or "").strip() or None
    audit = f"{actor}: {reason or 'no reason given'}"[:512]
    if action == "warn":
        if not reason:
            raise BotActionError("A warning needs a reason.")
        warning, count = add_warning(member, reason, actor)
        text = f"warned (#{warning['id']}, {count} active)"
        await _dm_mod_notice(member, "warned", reason)
        await _log_mod_action(actor_mention, member, text, reason)
        auto = await _escalate_warnings(member, count)
        return f"{text}; automatic action: {auto}" if auto else text
    if action == "timeout":
        delta = parse_duration(values.get("duration", ""))
        if not delta:
            raise BotActionError("Invalid duration — use e.g. 10m, 2h, 1d or 1w.")
        if delta > MAX_TIMEOUT:
            raise BotActionError("Discord allows timeouts of up to 28 days.")
        await member.timeout(duration=delta, reason=audit)
        text = f"timed out for {_format_duration(delta)}"
        await _dm_mod_notice(member, text, reason)
    elif action == "untimeout":
        await member.timeout(duration=None, reason=audit)
        text = "timeout removed"
    elif action == "nick":
        nick = (values.get("nick") or "").strip() or None
        await member.edit(nick=nick, reason=audit)
        text = f"nickname changed to {nick}" if nick else "nickname reset"
    elif action == "kick":
        await _dm_mod_notice(member, "kicked", reason)  # before, the bot can't DM them once they left
        await member.kick(reason=audit)
        text = "kicked"
    elif action == "ban":
        days = (values.get("delete_days") or "0").strip()
        if not days.isdigit() or int(days) > 7:
            raise BotActionError("Message deletion must be a number of days from 0 to 7.")
        await _dm_mod_notice(member, "banned", reason)
        await member.ban(reason=audit, clean_history_duration=timedelta(days=int(days)))
        text = "banned"
    else:
        raise BotActionError("Unknown moderation action.")
    await _log_mod_action(actor_mention, member, text, reason)
    return text


async def _mod_target(inter: disnake.Interaction, user_id: int) -> disnake.Member | None:
    """The member a /mod panel acts on, or None (after replying) if they can't be moderated."""
    member = None
    if inter.guild:
        try:
            member = inter.guild.get_member(user_id) or await inter.guild.fetch_member(user_id)
        except disnake.NotFound:
            pass
    if not member:
        await inter.response.send_message("That member is no longer in the server.", ephemeral=True)
        return None
    problem = _hierarchy_problem(inter.author, member)
    if problem:
        await inter.response.send_message(problem, ephemeral=True)
        return None
    return member


async def _apply_mod_action(inter: disnake.MessageInteraction | disnake.ModalInteraction, member: disnake.Member,
                            action: str, values: dict[str, str]) -> None:
    try:
        text = await _run_mod_action(f"{inter.author} (via /mod)", inter.author.mention, member, action, values)
    except BotActionError as exc:
        await inter.response.send_message(str(exc), ephemeral=True)
        return
    except disnake.Forbidden:
        permission = MOD_ACTIONS[action][0].replace("_", " ").title()
        await inter.response.send_message(f"I'm missing the **{permission}** permission (or my role is too low).", ephemeral=True)
        return
    result = f"{member.mention} — {text}."
    if action in ("kick", "ban"):
        await inter.response.edit_message(content=result, components=[])
        return
    member = await member.guild.fetch_member(member.id)
    embed, components = build_mod_panel(member, inter.author)
    await inter.response.edit_message(content=result, embed=embed, components=components)


async def _handle_mod_button(inter: disnake.MessageInteraction, action: str, user_id: int) -> None:
    member = await _mod_target(inter, user_id)
    if not member:
        return
    if action == "untimeout":
        await _apply_mod_action(inter, member, action, {})
    else:
        await inter.response.send_modal(_mod_modal(action, member))


async def _handle_mod_modal(inter: disnake.ModalInteraction, action: str, user_id: int) -> None:
    member = await _mod_target(inter, user_id)
    if member:
        await _apply_mod_action(inter, member, action, inter.text_values)


# ---------------------------------------------------------------- warnings
# A warning counts as active until it's removed or, when expire_days is set, until it gets
# older than that. Reaching exactly a rule's count runs its action.

WARN_RULE_ACTIONS = ("timeout", "kick", "ban")


def warn_config() -> dict:
    return warnings_store.load().get("config") or {"expire_days": 0, "rules": []}


def save_warn_config(config: dict) -> dict:
    with warnings_store.edit() as data:
        data["config"] = config
    return config


def active_warnings(user_id) -> list[dict]:
    expire_days = int(warn_config().get("expire_days") or 0)
    cutoff = datetime.now(timezone.utc) - timedelta(days=expire_days) if expire_days else None
    return [
        w for w in warnings_store.load().get("warnings", [])
        if w.get("user_id") == str(user_id) and (not cutoff or (_parse_time(w.get("at")) or cutoff) > cutoff)
    ]


def add_warning(member: disnake.Member, reason: str, moderator: str) -> tuple[dict, int]:
    """Saves a warning and returns it with the member's number of active warnings."""
    with warnings_store.edit() as data:
        data["last_id"] = data.get("last_id", 0) + 1
        warning = {
            "id": data["last_id"], "user_id": str(member.id), "user_name": member.display_name,
            "reason": reason[:400], "moderator": moderator, "at": utc_now(),
        }
        data.setdefault("warnings", []).append(warning)
    return warning, len(active_warnings(member.id))


def remove_warning(warning_id: int) -> dict | None:
    with warnings_store.edit() as data:
        warning = next((w for w in data.get("warnings", []) if w.get("id") == warning_id), None)
        if warning:
            data["warnings"].remove(warning)
    return warning


async def _escalate_warnings(member: disnake.Member, count: int) -> str | None:
    """Runs the warning rule for exactly `count` active warnings, if there is one."""
    rule = next((r for r in warn_config().get("rules", []) if r.get("count") == count), None)
    if not rule or rule.get("action") not in WARN_RULE_ACTIONS:
        return None
    values = {"duration": rule.get("duration") or "1h", "reason": f"Reached {count} warnings"}
    try:
        return await _run_mod_action("Auto-moderation", "Auto-moderation", member, rule["action"], values)
    except (BotActionError, disnake.HTTPException) as exc:
        log.warning("Automatic %s of %s after %s warnings failed: %s", rule["action"], member, count, exc)
        return f"{rule['action']} failed"


def warnings_embed(user: disnake.User, warnings: list[dict]) -> disnake.Embed:
    embed = disnake.Embed(title=f"Warnings — {user.display_name}"[:256], color=BRAND)
    embed.set_thumbnail(url=user.display_avatar.url)
    for w in warnings[-20:]:
        at = _parse_time(w.get("at"))
        embed.add_field(
            name=f"#{w['id']} • {w.get('moderator') or '?'}"[:256],
            value=f"{w['reason'][:900]}\n<t:{int(at.timestamp())}:R>" if at else w["reason"][:1000],
            inline=False,
        )
    if not warnings:
        embed.description = "No active warnings."
    expire_days = warn_config().get("expire_days")
    embed.set_footer(text=f"{FOOTER} • {len(warnings)} active" + (f" • warnings expire after {expire_days} days" if expire_days else ""))
    return embed


# admin panel -> Moderation (blocking, raise BotActionError)

def _member_mod_info(member: disnake.Member) -> dict:
    timeout = member.current_timeout
    return {
        **_member_info(member),
        "nick": member.nick,
        "bot": member.bot,
        "created_at": member.created_at.isoformat(),
        "joined_at": member.joined_at.isoformat() if member.joined_at else None,
        "timeout_until": timeout.isoformat() if timeout else None,
        "roles": [{"name": r.name, "color": str(r.color) if r.color.value else None}
                  for r in reversed(member.roles) if not r.is_default()],
        "warnings": active_warnings(member.id),
        "problem": _bot_hierarchy_problem(member),
    }


async def _panel_member(user_id: str) -> disnake.Member:
    _panel_guild()
    member = await _get_member(user_id)
    if not member:
        raise BotActionError("This user isn't on the RBWR server.")
    return member


def get_member_moderation(user_id: str) -> dict:
    """Profile, roles and timeout of a server member for the Moderation view."""
    async def _get():
        return _member_mod_info(await _panel_member(user_id))
    return _run(_get)


def moderate_member(user_id: str, action: str, values: dict[str, str], actor: str) -> dict:
    """Runs a /mod action from the admin panel. Returns the result text and the refreshed member."""
    if action not in MOD_ACTIONS:
        raise BotActionError("Unknown moderation action.")

    async def _do():
        member = await _panel_member(user_id)
        problem = _bot_hierarchy_problem(member)
        if problem:
            raise BotActionError(problem)
        label = f"{actor} (via website)"
        try:
            text = await _run_mod_action(label, label, member, action, values)
        except disnake.Forbidden:
            permission = MOD_ACTIONS[action][0].replace("_", " ").title()
            raise BotActionError(f"The bot is missing the {permission} permission (or its role is too low).")
        if action in ("kick", "ban"):
            return {"result": text, "member": None}
        return {"result": text, "member": _member_mod_info(await member.guild.fetch_member(member.id))}
    return _run(_do, timeout=15)


def list_discord_bans() -> list[dict]:
    """Users banned from the server (up to 200)."""
    async def _list():
        guild = _panel_guild()
        try:
            entries = [entry async for entry in guild.bans(limit=200)]
        except disnake.Forbidden:
            raise BotActionError("The bot needs the Ban Members permission to see bans.")
        return [{**_member_info(e.user), "name": e.user.global_name or e.user.name, "reason": e.reason} for e in entries]
    return _run(_list, timeout=15)


def unban_user(user_id: str, reason: str | None, actor: str) -> None:
    async def _unban():
        guild = _panel_guild()
        target = disnake.Object(int(user_id))
        label = f"{actor} (via website)"
        try:
            await guild.unban(target, reason=f"{label}: {reason or 'no reason given'}"[:512])
        except disnake.NotFound:
            raise BotActionError("That user isn't banned.")
        except disnake.Forbidden:
            raise BotActionError("The bot is missing the Ban Members permission.")
        await _log_mod_action(label, target, "unbanned", reason)
    _run(_unban)


# ---------------------------------------------------------------- automod
# Settings and the incident log live in data/automod.json (admin panel -> Automod).
# Every message filter has its own action: log (only recorded), delete, warn (deleted + a warning,
# which can escalate through the warning rules) or timeout (deleted + a timeout).

AUTOMOD_ACTIONS = ("log", "delete", "warn", "timeout")
JOIN_ACTIONS = ("alert", "timeout", "kick")
# filter key -> (label, why the message was removed, shown to the member)
AUTOMOD_FILTERS = {
    "words": ("Blocked words", "it contains a blocked word"),
    "invites": ("Invite links", "invite links to other servers aren't allowed"),
    "links": ("Links", "links to that site aren't allowed"),
    "mentions": ("Mass mentions", "it mentions too many people"),
    "caps": ("Excessive caps", "it's mostly in capital letters"),
    "emoji": ("Emoji spam", "it has too many emoji"),
    "lines": ("Walls of text", "it has too many lines"),
    "spam": ("Message spam", "you're sending messages too fast"),
    "duplicates": ("Repeated messages", "you've sent the same message several times"),
}
AUTOMOD_LABELS = {**{k: v[0] for k, v in AUTOMOD_FILTERS.items()}, "raid": "Raid protection", "account_age": "New account"}
AUTOMOD_DEFAULTS = {
    "enabled": False,
    "log_channel_id": "",    # empty -> DISCORD_MOD_LOG_CHANNEL_ID
    "notify": True,          # short notice in the channel, removed after a few seconds
    "exempt_staff": True,    # panel admins and members with Manage Messages
    "exempt_roles": [],
    "exempt_channels": [],   # a channel, its category or the parent of a thread
    "filters": {
        "words": {"enabled": False, "action": "warn", "duration": "10m", "words": []},
        "invites": {"enabled": True, "action": "delete", "duration": "10m", "allow_own": True},
        "links": {"enabled": False, "action": "delete", "duration": "10m",
                  "allowed": ["hotment.dev", "roblox.com", "youtube.com", "youtu.be", "github.com", "discord.com", "tenor.com"]},
        "mentions": {"enabled": True, "action": "timeout", "duration": "10m", "max": 5},
        "caps": {"enabled": False, "action": "delete", "duration": "10m", "percent": 70, "min_length": 12},
        "emoji": {"enabled": False, "action": "delete", "duration": "10m", "max": 10},
        "lines": {"enabled": False, "action": "delete", "duration": "10m", "max": 15},
        "spam": {"enabled": True, "action": "timeout", "duration": "10m", "messages": 6, "seconds": 8},
        "duplicates": {"enabled": True, "action": "delete", "duration": "10m", "count": 3, "seconds": 60},
    },
    # `joins` members within `seconds` start raid mode for `lockdown_minutes`; members joining then get `action`
    "raid": {"enabled": False, "joins": 8, "seconds": 30, "action": "alert", "lockdown_minutes": 10},
    # accounts younger than `days` get `action` when they join
    "account_age": {"enabled": False, "days": 3, "action": "alert", "duration": "1d"},
}
AUTOMOD_PUNISH_COOLDOWN = 30  # seconds: one warning/timeout per burst, later messages are only deleted
AUTOMOD_NOTICE_COOLDOWN = 10
AUTOMOD_INCIDENT_LIMIT = 300

_INVITE_RE = re.compile(r"(?:discord(?:app)?\.com/invite|discord\.gg)/([a-z0-9-]+)", re.I)
_URL_RE = re.compile(r"(?:https?://|www\.)([^\s/<>?#]+)", re.I)
_MENTION_RE = re.compile(r"<(?:@[!&]?|#)\d+>")
_CUSTOM_EMOJI_RE = re.compile(r"<a?:\w+:\d+>")
_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿]")
_LEET = str.maketrans("013457@$!", "oieastasi")

_invite_guilds: dict[str, int | None] = {}  # invite code -> its server's ID (None: invalid)
_am_recent: dict[int, list[list]] = {}      # user ID -> [[time, channel ID, message ID (0 once deleted), text], ...]
_am_punished: dict[int, float] = {}
_am_notified: dict[int, float] = {}
_am_joins: list[datetime] = []
_raid_until: datetime | None = None
_discord_automod_synced: bool = False
_discord_automod_error: str | None = None


def automod_config() -> dict:
    """The saved settings on top of the defaults, so options added later get their default value."""
    config = json.loads(json.dumps(AUTOMOD_DEFAULTS))
    for key, value in (automod_store.load().get("config") or {}).items():
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            for sub, sub_value in value.items():
                if isinstance(sub_value, dict) and isinstance(config[key].get(sub), dict):
                    config[key][sub].update(sub_value)
                else:
                    config[key][sub] = sub_value
        else:
            config[key] = value
    return config


def save_automod_config(config: dict) -> dict:
    words = config["filters"]["words"]
    words["words"] = list(dict.fromkeys(w.strip().lower() for w in words["words"] if w.strip()))
    links = config["filters"]["links"]
    links["allowed"] = list(dict.fromkeys(
        d.strip().lower().removeprefix("https://").removeprefix("http://").removeprefix("www.").strip("/")
        for d in links["allowed"] if d.strip()
    ))
    with automod_store.edit() as data:
        data["config"] = config

    if is_ready():
        try:
            _run(lambda: sync_discord_automod_rules(config), timeout=15)
        except Exception as exc:
            log.warning("Could not sync Discord official automod rules: %s", exc)

    return automod_config()


async def sync_discord_automod_rules(config: dict | None = None) -> dict[str, Any]:
    global _discord_automod_synced, _discord_automod_error
    if config is None:
        config = automod_config()
    try:
        guild = _panel_guild()
    except Exception as exc:
        _discord_automod_synced = False
        _discord_automod_error = str(exc)
        return {"synced": False, "error": _discord_automod_error}

    me = guild.me or (await guild.getch_member(_bot.user.id) if _bot and _bot.user else None)
    if not me or not (me.guild_permissions.manage_guild or me.guild_permissions.administrator):
        _discord_automod_synced = False
        _discord_automod_error = "The bot lacks 'Manage Server' permission to configure official Discord AutoMod rules."
        log.warning(_discord_automod_error)
        return {"synced": False, "error": _discord_automod_error}

    try:
        existing_rules = await guild.fetch_automod_rules()
        existing_by_name = {r.name: r for r in existing_rules}
    except Exception as exc:
        _discord_automod_synced = False
        _discord_automod_error = f"Failed to fetch Discord AutoMod rules: {exc}"
        log.warning(_discord_automod_error)
        return {"synced": False, "error": _discord_automod_error}

    is_global_enabled = bool(config.get("enabled", False))
    log_ch_id = config.get("log_channel_id") or str(hooks.mod_log_channel_id or "")
    log_channel_obj = disnake.Object(id=int(log_ch_id)) if log_ch_id and str(log_ch_id).isdigit() else None

    exempt_roles = [disnake.Object(id=int(r)) for r in config.get("exempt_roles", []) if str(r).isdigit()][:20]
    exempt_channels = [disnake.Object(id=int(c)) for c in config.get("exempt_channels", []) if str(c).isdigit()][:50]

    def _build_actions(action_name: str, duration_str: str, allow_timeout: bool = True) -> list[disnake.AutoModAction]:
        actions: list[disnake.AutoModAction] = []
        if action_name != "log":
            actions.append(disnake.AutoModBlockMessageAction(custom_message="Message blocked by RBWR AutoMod."))
        if allow_timeout and action_name == "timeout":
            dur = parse_duration(duration_str) or timedelta(minutes=10)
            dur = max(timedelta(seconds=10), min(timedelta(weeks=4), dur))
            actions.append(disnake.AutoModTimeoutAction(duration=dur))
        if log_channel_obj:
            actions.append(disnake.AutoModSendAlertAction(channel=log_channel_obj))
        if not actions:
            actions.append(disnake.AutoModBlockMessageAction(custom_message="Message blocked by RBWR AutoMod."))
        return actions

    synced_rules: list[str] = []

    rule_name_words = "[RBWR] Blocked Words"
    cfg_words = config.get("filters", {}).get("words", {})
    words_list = [w[:60] for w in cfg_words.get("words", []) if w.strip()][:1000]
    words_enabled = is_global_enabled and bool(cfg_words.get("enabled")) and bool(words_list)
    words_actions = _build_actions(cfg_words.get("action", "warn"), cfg_words.get("duration", "10m"), allow_timeout=True)

    try:
        if rule_name_words in existing_by_name:
            existing = existing_by_name[rule_name_words]
            meta = disnake.AutoModTriggerMetadata(keyword_filter=words_list) if words_list else None
            edit_kwargs: dict[str, Any] = {
                "enabled": words_enabled,
                "actions": words_actions,
                "exempt_roles": exempt_roles,
                "exempt_channels": exempt_channels,
            }
            if meta:
                edit_kwargs["trigger_metadata"] = meta
            await existing.edit(**edit_kwargs)
            synced_rules.append(rule_name_words)
        elif words_enabled:
            meta = disnake.AutoModTriggerMetadata(keyword_filter=words_list)
            await guild.create_automod_rule(
                name=rule_name_words,
                event_type=disnake.AutoModEventType.message_send,
                trigger_type=disnake.AutoModTriggerType.keyword,
                trigger_metadata=meta,
                actions=words_actions,
                enabled=True,
                exempt_roles=exempt_roles,
                exempt_channels=exempt_channels,
                reason="RBWR Admin AutoMod sync"
            )
            synced_rules.append(rule_name_words)
    except Exception as exc:
        log.warning("Failed to sync %s: %s", rule_name_words, exc)

    rule_name_links = "[RBWR] Blocked Invites & Links"
    cfg_invites = config.get("filters", {}).get("invites", {})
    cfg_links = config.get("filters", {}).get("links", {})
    links_kw: list[str] = []
    if cfg_invites.get("enabled"):
        links_kw.extend(["*discord.gg/*", "*discord.com/invite/*", "*discord.me/*", "*discord.io/*"])
    if cfg_links.get("enabled"):
        links_kw.extend(["*http://*", "*https://*"])
    links_kw = list(dict.fromkeys(links_kw))[:1000]

    allow_list = [d[:60] for d in cfg_links.get("allowed", []) if d.strip()][:100] if cfg_links.get("enabled") else None
    links_enabled = is_global_enabled and bool(links_kw) and (bool(cfg_invites.get("enabled")) or bool(cfg_links.get("enabled")))
    links_actions = _build_actions(cfg_invites.get("action", "delete") if cfg_invites.get("enabled") else cfg_links.get("action", "delete"),
                                   cfg_invites.get("duration", "10m"), allow_timeout=True)

    try:
        if rule_name_links in existing_by_name:
            existing = existing_by_name[rule_name_links]
            meta = disnake.AutoModTriggerMetadata(keyword_filter=links_kw, allow_list=allow_list) if links_kw else None
            edit_kwargs = {
                "enabled": links_enabled,
                "actions": links_actions,
                "exempt_roles": exempt_roles,
                "exempt_channels": exempt_channels,
            }
            if meta:
                edit_kwargs["trigger_metadata"] = meta
            await existing.edit(**edit_kwargs)
            synced_rules.append(rule_name_links)
        elif links_enabled:
            meta = disnake.AutoModTriggerMetadata(keyword_filter=links_kw, allow_list=allow_list)
            await guild.create_automod_rule(
                name=rule_name_links,
                event_type=disnake.AutoModEventType.message_send,
                trigger_type=disnake.AutoModTriggerType.keyword,
                trigger_metadata=meta,
                actions=links_actions,
                enabled=True,
                exempt_roles=exempt_roles,
                exempt_channels=exempt_channels,
                reason="RBWR Admin AutoMod sync"
            )
            synced_rules.append(rule_name_links)
    except Exception as exc:
        log.warning("Failed to sync %s: %s", rule_name_links, exc)

    rule_name_mentions = "[RBWR] Mass Mentions"
    cfg_mentions = config.get("filters", {}).get("mentions", {})
    mentions_enabled = is_global_enabled and bool(cfg_mentions.get("enabled"))
    mention_limit = max(1, min(50, int(cfg_mentions.get("max", 5))))
    mentions_actions = _build_actions(cfg_mentions.get("action", "timeout"), cfg_mentions.get("duration", "10m"), allow_timeout=True)

    try:
        if rule_name_mentions in existing_by_name:
            existing = existing_by_name[rule_name_mentions]
            meta = disnake.AutoModTriggerMetadata(mention_total_limit=mention_limit)
            await existing.edit(
                enabled=mentions_enabled,
                trigger_metadata=meta,
                actions=mentions_actions,
                exempt_roles=exempt_roles,
                exempt_channels=exempt_channels,
            )
            synced_rules.append(rule_name_mentions)
        elif mentions_enabled:
            meta = disnake.AutoModTriggerMetadata(mention_total_limit=mention_limit)
            await guild.create_automod_rule(
                name=rule_name_mentions,
                event_type=disnake.AutoModEventType.message_send,
                trigger_type=disnake.AutoModTriggerType.mention_spam,
                trigger_metadata=meta,
                actions=mentions_actions,
                enabled=True,
                exempt_roles=exempt_roles,
                exempt_channels=exempt_channels,
                reason="RBWR Admin AutoMod sync"
            )
            synced_rules.append(rule_name_mentions)
    except Exception as exc:
        log.warning("Failed to sync %s: %s", rule_name_mentions, exc)

    rule_name_spam = "[RBWR] Suspected Spam"
    cfg_spam = config.get("filters", {}).get("spam", {})
    spam_enabled = is_global_enabled and bool(cfg_spam.get("enabled"))
    spam_actions = _build_actions(cfg_spam.get("action", "timeout"), cfg_spam.get("duration", "10m"), allow_timeout=False)

    try:
        if rule_name_spam in existing_by_name:
            existing = existing_by_name[rule_name_spam]
            await existing.edit(
                enabled=spam_enabled,
                actions=spam_actions,
                exempt_roles=exempt_roles,
                exempt_channels=exempt_channels,
            )
            synced_rules.append(rule_name_spam)
        elif spam_enabled:
            await guild.create_automod_rule(
                name=rule_name_spam,
                event_type=disnake.AutoModEventType.message_send,
                trigger_type=disnake.AutoModTriggerType.spam,
                actions=spam_actions,
                enabled=True,
                exempt_roles=exempt_roles,
                exempt_channels=exempt_channels,
                reason="RBWR Admin AutoMod sync"
            )
            synced_rules.append(rule_name_spam)
    except Exception as exc:
        log.warning("Failed to sync %s: %s", rule_name_spam, exc)

    _discord_automod_synced = True
    _discord_automod_error = None
    log.info("Synced %d official Discord AutoMod rules with guild %s", len(synced_rules), guild.id)
    return {"synced": True, "rules": synced_rules}

def raid_active() -> bool:
    return bool(_raid_until and _raid_until > datetime.now(timezone.utc))


def end_raid() -> None:
    global _raid_until
    _raid_until = None


def _normalize(text: str) -> str:
    """Lowercase, without accents and with look-alike digits and symbols replaced (h3ll0 -> hello)."""
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c)).translate(_LEET)


@functools.lru_cache(maxsize=8)
def _word_pattern(words: tuple[str, ...]) -> re.Pattern | None:
    """Whole-word matcher for the blocked words; * matches any letters (spam* -> spammer)."""
    parts = [re.escape(_normalize(w)).replace(r"\*", r"\w*") for w in words if w.strip()]
    return re.compile(r"(?<!\w)(?:" + "|".join(parts) + r")(?!\w)") if parts else None


def _content_violation(config: dict, text: str, mentions: int = 0, everyone: bool = False) -> tuple[str, str] | None:
    """The first content filter `text` breaks as (filter key, detail), or None. Invites are checked separately."""
    f = config["filters"]
    if f["words"]["enabled"]:
        pattern = _word_pattern(tuple(f["words"]["words"]))
        match = pattern.search(_normalize(text)) if pattern else None
        if match:
            return "words", f"Blocked word: {match.group(0)}"
    if f["links"]["enabled"]:
        allowed = f["links"]["allowed"]
        for host in _URL_RE.findall(_INVITE_RE.sub("", text)):
            host = host.lower().split(":")[0].removeprefix("www.")
            if not any(host == d or host.endswith("." + d) for d in allowed):
                return "links", f"Link to {host}"
    if f["mentions"]["enabled"]:
        if everyone:
            return "mentions", "Tried to ping @everyone or @here"
        if mentions > f["mentions"]["max"]:
            return "mentions", f"{mentions} mentions (max {f['mentions']['max']})"
    plain = _CUSTOM_EMOJI_RE.sub("", _MENTION_RE.sub("", _URL_RE.sub("", text)))
    letters = [c for c in plain if c.isalpha()]
    if f["caps"]["enabled"] and len(letters) >= f["caps"]["min_length"]:
        percent = round(100 * sum(c.isupper() for c in letters) / len(letters))
        if percent >= f["caps"]["percent"]:
            return "caps", f"{percent}% capital letters"
    if f["emoji"]["enabled"]:
        count = len(_CUSTOM_EMOJI_RE.findall(text)) + len(_EMOJI_RE.findall(text))
        if count > f["emoji"]["max"]:
            return "emoji", f"{count} emoji (max {f['emoji']['max']})"
    if f["lines"]["enabled"]:
        lines = text.count("\n") + 1
        if lines > f["lines"]["max"]:
            return "lines", f"{lines} lines (max {f['lines']['max']})"
    return None


async def _foreign_invite(text: str, allow_own: bool, own_guild_id: int) -> str | None:
    """The first invite code in `text` that leads to another server (or doesn't work)."""
    for code in dict.fromkeys(_INVITE_RE.findall(text)):
        if not allow_own or not _bot:
            return code
        if code not in _invite_guilds:
            if len(_invite_guilds) > 1000:
                _invite_guilds.clear()
            try:
                invite = await _bot.fetch_invite(code)
                _invite_guilds[code] = invite.guild.id if invite.guild else None
            except disnake.HTTPException:
                _invite_guilds[code] = None
        if _invite_guilds[code] != own_guild_id:
            return code
    return None


def _behaviour_violation(config: dict, message: disnake.Message) -> tuple[str, str, list[list]] | None:
    """Message spam and repeated messages: (filter key, detail, the member's messages that count)."""
    f = config["filters"]
    now = time.monotonic()
    keep = max(f["spam"]["seconds"], f["duplicates"]["seconds"])
    text = _normalize(message.content or "").strip()
    history = [h for h in _am_recent.get(message.author.id, []) if now - h[0] < keep]
    history.append([now, message.channel.id, message.id, text])
    _am_recent[message.author.id] = history[-100:]
    if len(_am_recent) > 5000:  # forget members who have been quiet for a while
        for uid in [u for u, h in _am_recent.items() if now - h[-1][0] > keep]:
            del _am_recent[uid]
    if f["spam"]["enabled"]:
        burst = [h for h in history if now - h[0] < f["spam"]["seconds"]]
        if len(burst) >= f["spam"]["messages"]:
            return "spam", f"{len(burst)} messages in {f['spam']['seconds']}s", burst
    if f["duplicates"]["enabled"] and text:
        same = [h for h in history if h[3] == text and now - h[0] < f["duplicates"]["seconds"]]
        if len(same) >= f["duplicates"]["count"]:
            return "duplicates", f"Same message {len(same)}× in {f['duplicates']['seconds']}s", same
    return None


def _automod_exempt(config: dict, member: disnake.Member, channel) -> bool:
    if config["exempt_staff"]:
        perms = member.guild_permissions
        if perms.administrator or perms.manage_messages or _is_admin_id(member.id):
            return True
    roles = set(config["exempt_roles"])
    if any(str(r.id) in roles for r in member.roles):
        return True
    channels = set(config["exempt_channels"])
    ids = (channel.id, getattr(channel, "category_id", None), getattr(channel, "parent_id", None))
    return any(i and str(i) in channels for i in ids)


async def _automod_record(key: str, user: Any, channel: Any, action: str, detail: str,
                          content: str = "", result: str = "") -> None:
    """Saves an incident for the admin panel and posts it to the automod log channel."""
    uid = str(getattr(user, "id", "") or "")
    uname = getattr(user, "display_name", getattr(user, "name", f"User {uid}"))
    avatar_obj = getattr(user, "display_avatar", getattr(user, "avatar", None))
    avatar_url = str(avatar_obj.url) if avatar_obj and hasattr(avatar_obj, "url") else ""
    cid = str(getattr(channel, "id", "") or "")
    cname = getattr(channel, "name", "") or ""

    incident = {
        "filter": key, "user_id": uid, "user_name": uname, "user_avatar": avatar_url,
        "channel_id": cid, "channel_name": cname,
        "action": action, "detail": detail[:300], "content": content[:500], "result": result[:300], "at": utc_now(),
    }
    with automod_store.edit() as data:
        data["last_id"] = data.get("last_id", 0) + 1
        incident["id"] = data["last_id"]
        data.setdefault("incidents", []).insert(0, incident)
        del data["incidents"][AUTOMOD_INCIDENT_LIMIT:]
    log.info("Automod: %s -> %s: %s (%s)", key, user.id, detail, result or action)

    log_channel = await _get_channel(automod_config()["log_channel_id"] or hooks.mod_log_channel_id)
    if not isinstance(log_channel, disnake.TextChannel):
        return
    embed = disnake.Embed(title=f"Automod: {AUTOMOD_LABELS[key]}", color=BRAND, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="Member", value=f"<@{user.id}> (`{user.id}`)", inline=True)
    if channel:
        embed.add_field(name="Channel", value=f"<#{channel.id}>", inline=True)
    embed.add_field(name="Action", value=result or action, inline=True)
    embed.add_field(name="Reason", value=detail[:1024], inline=False)
    if content:
        embed.add_field(name="Message", value=content[:1000].replace("```", "'''") or "—", inline=False)
    embed.set_footer(text=f"{FOOTER} • Automod")
    try:
        await log_channel.send(embed=embed, allowed_mentions=disnake.AllowedMentions.none())
    except Exception as exc:
        log.warning("Could not post to the automod log channel: %s", exc)


async def _automod_act(config: dict, message: disnake.Message, key: str, detail: str, related: list[list]) -> None:
    rule = config["filters"][key]
    action, member = rule["action"], message.author
    label, reason = AUTOMOD_FILTERS[key]
    done = []
    if action != "log":
        try:
            await message.delete()
            done.append("message deleted")
        except disnake.NotFound:
            pass
        except disnake.HTTPException as exc:
            done.append("couldn't delete the message")
            log.warning("Automod could not delete a message in #%s: %s", message.channel, exc)
        for entry in related:  # the rest of a spam burst
            if entry[2] and entry[2] != message.id and message.guild:
                channel = message.guild.get_channel_or_thread(entry[1])
                try:
                    await channel.get_partial_message(entry[2]).delete()  # pyright: ignore[reportOptionalMemberAccess, reportAttributeAccessIssue]
                except (AttributeError, disnake.HTTPException):
                    pass
            entry[2] = 0

    now = time.monotonic()
    if action in ("warn", "timeout") and now - _am_punished.get(member.id, -1e9) >= AUTOMOD_PUNISH_COOLDOWN:
        _am_punished[member.id] = now
        values = {"reason": f"Automod: {label} — {detail}"[:400], "duration": rule.get("duration") or "10m"}
        try:
            done.append(await _run_mod_action("Automod", "Automod", member, action, values))  # pyright: ignore[reportArgumentType]
        except (BotActionError, disnake.HTTPException) as exc:
            done.append(f"{action} failed")
            log.warning("Automod %s of %s failed: %s", action, member, exc)

    if action != "log" and config["notify"] and now - _am_notified.get(member.id, -1e9) >= AUTOMOD_NOTICE_COOLDOWN:
        _am_notified[member.id] = now
        try:
            await message.channel.send(f"{member.mention}, your message was removed because {reason}.",
                                       delete_after=8, allowed_mentions=disnake.AllowedMentions(users=True))
        except disnake.HTTPException:
            pass
    await _automod_record(key, member, message.channel, action, detail, message.content or "", ", ".join(done) or action)  # pyright: ignore[reportArgumentType]


async def automod_message(message: disnake.Message, edited: bool = False) -> bool:
    """Checks a server message against the automod filters. True if it was removed."""
    config = automod_config()
    member = message.author
    gid = _guild_id()
    if not config["enabled"] or not isinstance(member, disnake.Member) or not message.guild or (gid and message.guild.id != gid):
        return False
    if _automod_exempt(config, member, message.channel):
        return False
    text, hit, related = message.content or "", None, []
    invites = config["filters"]["invites"]
    if invites["enabled"] and text:
        code = await _foreign_invite(text, invites["allow_own"], message.guild.id)
        if code:
            hit = ("invites", f"Invite discord.gg/{code}")
    if not hit and text:
        everyone = ("@everyone" in text or "@here" in text) and not message.channel.permissions_for(member).mention_everyone  # pyright: ignore[reportAttributeAccessIssue]
        mentions = len(set(message.raw_mentions)) + len(set(message.raw_role_mentions))
        hit = _content_violation(config, text, mentions, everyone)
    if not hit and not edited:
        found = _behaviour_violation(config, message)
        if found:
            hit, related = found[:2], found[2]
    if not hit:
        return False
    await _automod_act(config, message, hit[0], hit[1], related)
    return config["filters"][hit[0]]["action"] != "log"


async def _automod_join_action(member: disnake.Member, key: str, action: str, detail: str, duration: str) -> bool:
    result = "alert only"
    if action in ("timeout", "kick"):
        try:
            result = await _run_mod_action("Automod", "Automod", member, action,
                                           {"reason": f"Automod: {detail}"[:400], "duration": duration})
        except (BotActionError, disnake.HTTPException) as exc:
            result = f"{action} failed"
            log.warning("Automod %s of new member %s failed: %s", action, member, exc)
    await _automod_record(key, member, None, action, detail, result=result)
    return result == "kicked"


async def automod_member_join(member: disnake.Member) -> bool:
    """Raid protection and the minimum account age. True if the member was kicked."""
    global _raid_until
    config = automod_config()
    gid = _guild_id()
    if not config["enabled"] or member.bot or (gid and member.guild.id != gid):
        return False
    now = datetime.now(timezone.utc)
    raid = config["raid"]
    if raid["enabled"]:
        _am_joins[:] = [t for t in _am_joins if (now - t).total_seconds() < raid["seconds"]] + [now]
        if len(_am_joins) >= raid["joins"]:
            started = not raid_active()
            _raid_until = now + timedelta(minutes=raid["lockdown_minutes"])
            if started:
                await _automod_record("raid", member, None, "alert",
                                      f"{len(_am_joins)} members joined within {raid['seconds']}s — raid mode for "
                                      f"{raid['lockdown_minutes']} min, new members get: {raid['action']}",
                                      result="raid mode started")
        if raid_active() and raid["action"] != "alert":
            return await _automod_join_action(member, "raid", raid["action"], "Joined during raid mode",
                                              f"{raid['lockdown_minutes']}m")
    age = config["account_age"]
    if age["enabled"] and now - member.created_at < timedelta(days=age["days"]):
        detail = f"Account created {_format_duration(now - member.created_at)} ago (minimum {age['days']} days)"
        return await _automod_join_action(member, "account_age", age["action"], detail, age["duration"])
    return False


def automod_status() -> dict:
    data = automod_store.load()
    return {
        "config": automod_config(),
        "incidents": data.get("incidents", [])[:150],
        "labels": AUTOMOD_LABELS,
        "raid_until": _raid_until.isoformat() if raid_active() and _raid_until else None,
        "bot_online": is_ready(),
        "message_content_intent": bool(_bot and _bot.intents.message_content),
        "members_intent": bool(_bot and _bot.intents.members),
        "discord_automod_synced": _discord_automod_synced,
        "discord_automod_error": _discord_automod_error,
    }


def automod_test(text: str) -> dict | None:
    """Which filter a message would trip with the saved settings (spam and repeats need real messages)."""
    config = automod_config()
    invites = config["filters"]["invites"]
    match = _INVITE_RE.search(text)
    if invites["enabled"] and match:
        own = _guild_id() or 0
        code = _run(lambda: _foreign_invite(text, invites["allow_own"], own)) if is_ready() else match.group(1)
        if code:
            return {"filter": "invites", "detail": f"Invite discord.gg/{code}", "action": invites["action"]}
    mentions = len(set(re.findall(r"<@[!&]?\d+>", text)))
    hit = _content_violation(config, text, mentions, "@everyone" in text or "@here" in text)
    return {"filter": hit[0], "detail": hit[1], "action": config["filters"][hit[0]]["action"]} if hit else None


# ---------------------------------------------------------------- welcome & goodbye messages
# Channel, message text and an optional Embed Builder template. Placeholders are filled in both.

GREETING_KINDS = ("welcome", "goodbye")
DEFAULT_GREETINGS = {
    "welcome": "Welcome to **{server}**, {user}! You're member #{member_count}.",
    "goodbye": "**{name}** has left the server.",
}


def greeting_config(kind: str) -> dict:
    return welcome_store.load().get(kind) or {}


def _fill_placeholders(value: Any, values: dict[str, str]) -> Any:
    if isinstance(value, str):
        for key, replacement in values.items():
            value = value.replace("{" + key + "}", replacement)
        return value
    if isinstance(value, dict):
        return {k: _fill_placeholders(v, values) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill_placeholders(v, values) for v in value]
    return value


def render_greeting(kind: str, member: disnake.Member, config: dict | None = None) -> tuple[str, dict | None]:
    """(message text, embed dict or None) for `member` with the placeholders filled in."""
    config = config if config is not None else greeting_config(kind)
    values = {
        "user": member.mention,
        "name": member.display_name,
        "username": member.name,
        "server": member.guild.name,
        "member_count": str(member.guild.member_count or len(member.guild.members)),
    }
    embed = None
    template = embed_templates().get(config.get("template") or "")
    if template and template.get("embed"):
        embed = _fill_placeholders(template["embed"], values)
        if "timestamp" in embed:
            embed["timestamp"] = utc_now()
        if config.get("avatar_thumbnail"):
            embed["thumbnail"] = {"url": str(member.display_avatar.url)}
    text = config.get("message") or ("" if embed else DEFAULT_GREETINGS[kind])
    return _fill_placeholders(text, values)[:2000], embed


async def _send_greeting(kind: str, member: disnake.Member) -> disnake.Message:
    config = greeting_config(kind)
    channel = await _get_channel(config.get("channel_id"))
    if not isinstance(channel, disnake.TextChannel):
        raise BotActionError(f"Pick a channel for the {kind} message first.")
    content, embed = render_greeting(kind, member, config)
    send_kwargs: dict[str, Any] = {
        "allowed_mentions": disnake.AllowedMentions(users=[member] if kind == "welcome" else False, roles=False, everyone=False),
    }
    if content:
        send_kwargs["content"] = content
    if embed:
        send_kwargs["embed"] = disnake.Embed.from_dict(embed)  # pyright: ignore[reportArgumentType]
    return await channel.send(**send_kwargs)


async def greet_member(kind: str, member: disnake.Member) -> None:
    config = greeting_config(kind)
    gid = _guild_id()
    if member.bot or not config.get("enabled") or not config.get("channel_id") or (gid and member.guild.id != gid):
        return
    try:
        await _send_greeting(kind, member)
    except (BotActionError, disnake.HTTPException) as exc:
        log.error("Could not post the %s message for %s: %s", kind, member, exc)


def greeting_test(kind: str, user_id: str | None) -> dict:
    """Posts the welcome/goodbye message for the admin (or the bot) to try it out (blocking)."""
    async def _test():
        guild = _panel_guild()
        member = (await _get_member(user_id) if user_id and str(user_id).isdigit() else None) or guild.me
        msg = await _send_greeting(kind, member)
        return {"jump_url": msg.jump_url}
    return _run(_test)


# ---------------------------------------------------------------- FAQ (/faq)

def faq_entries() -> dict:
    return faq_store.load().get("entries", {})


def faq_embed(key: str, entry: dict) -> disnake.Embed:
    embed = disnake.Embed(title=entry.get("title") or key, description=(entry.get("answer") or "")[:4096], color=BRAND)
    embed.set_footer(text=f"{FOOTER} FAQ • /faq {key}")
    return embed


# ---------------------------------------------------------------- custom commands (!bug, ...)

DEFAULT_COMMAND_PREFIX = "!"
_command_cooldowns: dict[tuple[str, int], float] = {}  # (command, channel ID) -> last use


def message_content_enabled() -> bool:
    return bool(_bot and _bot.intents.message_content)


def custom_commands() -> tuple[str, dict]:
    data = commands_store.load()
    return data.get("prefix") or DEFAULT_COMMAND_PREFIX, data.get("commands", {})


def find_custom_command(cmds: dict, name: str) -> str | None:
    """The command called `name` directly or through one of its aliases."""
    name = name.lower()
    if name in cmds:
        return name
    return next((key for key, c in cmds.items() if name in c.get("aliases", [])), None)


def render_custom_command(cmd: dict, member: disnake.Member, channel, args: str, target: disnake.Member | disnake.User | None) -> tuple[str, dict | None]:
    """(message text, embed dict or None) with the placeholders filled in."""
    target = target or member
    values = {
        "user": member.mention,
        "name": member.display_name,
        "username": member.name,
        "target": target.mention,
        "target_name": target.display_name,
        "server": member.guild.name,
        "channel": getattr(channel, "mention", ""),
        "args": args,
        "site": hooks.site_url,
    }
    embed = cmd.get("embed")  # made in the command's own editor, else an Embed Builder template
    if not embed:
        template = embed_templates().get(cmd.get("template") or "")
        embed = (template or {}).get("embed")
    if embed:
        embed = _fill_placeholders(embed, values)
        if "timestamp" in embed:
            embed["timestamp"] = utc_now()
    return _fill_placeholders(cmd.get("response") or "", values)[:2000], embed


def _command_list_embed(prefix: str, cmds: dict) -> disnake.Embed:
    lines = [
        f"`{prefix}{key}`" + (f" ({', '.join(f'`{prefix}{a}`' for a in c['aliases'])})" if c.get("aliases") else "")
        for key, c in sorted(cmds.items()) if c.get("enabled", True)
    ]
    embed = disnake.Embed(title="Commands", description="\n".join(lines)[:4096] or "No commands yet.", color=BRAND)
    embed.set_footer(text=f"{FOOTER} • Custom commands")
    return embed


async def run_custom_command(message: disnake.Message) -> bool:
    """Answers a prefix command like !bug. True if the message was a command."""
    prefix, cmds = custom_commands()
    text = (message.content or "").strip()
    gid = _guild_id()
    if not message.guild or not text.startswith(prefix) or len(text) == len(prefix) or (gid and message.guild.id != gid):
        return False
    word, args = (text[len(prefix):].split(maxsplit=1) + [""])[:2]
    member, channel = message.author, message.channel
    if not isinstance(member, disnake.Member):
        return False
    key = find_custom_command(cmds, word)
    if not key:
        if word.lower() in ("commands", "help") and cmds:  # built-in list, unless a command took the name
            await channel.send(embed=_command_list_embed(prefix, cmds))
            return True
        return False
    cmd = cmds[key]
    staff = _is_admin_user(member) or getattr(member.guild_permissions, "manage_messages", False)
    if not cmd.get("enabled", True):
        return False
    if cmd.get("role_id") and not staff and not any(str(r.id) == cmd["role_id"] for r in getattr(member, "roles", [])):
        return False
    now = time.monotonic()
    cooldown = int(cmd.get("cooldown") or 0)
    if cooldown and not staff and now - _command_cooldowns.get((key, channel.id), -1e9) < cooldown:
        return True  # used a moment ago in this channel: ignored, so it can't be spammed
    _command_cooldowns[(key, channel.id)] = now

    target = next((m for m in message.mentions if m.id != member.id), None)
    content, embed = render_custom_command(cmd, member, channel, args, target)
    if not content and not embed:
        return False
    kwargs = {
        "content": content or None,
        "embed": disnake.Embed.from_dict(embed) if embed else None,  # pyright: ignore[reportArgumentType]
        # only the author and the mentioned member can be pinged, never roles or @everyone
        "allowed_mentions": disnake.AllowedMentions(users=[u for u in (member, target) if u], roles=False, everyone=False),
    }
    try:
        if cmd.get("reply", True) and not cmd.get("delete_trigger"):
            await message.reply(mention_author=False, **kwargs)
        else:
            await channel.send(**kwargs)
    except disnake.HTTPException as exc:
        log.warning("Could not answer %s%s in #%s: %s", prefix, key, channel, exc)
        return True
    if cmd.get("delete_trigger"):
        try:
            await message.delete()
        except disnake.HTTPException:
            pass
    with commands_store.edit() as data:
        if key in data.get("commands", {}):
            data["commands"][key]["uses"] = data["commands"][key].get("uses", 0) + 1
    return True


# ---------------------------------------------------------------- error monitor
# Errors reported through bot.report_error_to_discord / send_error_alert_async are stored here
# (identical unresolved errors are counted instead of duplicated) and listed in the admin panel.
# The alert in Discord pings DISCORD_ERROR_ALERT_PING_USER_ID, as before.

MAX_ERRORS = 500


_local = threading.local()


def record_error(origin: str, error_type: str, message: str, tb: str = "", context: dict | None = None) -> dict | None:
    """Stores an error (or bumps the counter of an identical unresolved one). Returns a copy of the entry."""
    if getattr(_local, "busy", False):  # never recurse if recording itself fails
        return None
    _local.busy = True
    try:
        now = utc_now()
        message = (message or "")[:2000]
        with errors_store.edit() as data:
            errors = data.setdefault("errors", [])
            existing = next(
                (e for e in reversed(errors)
                 if not e.get("resolved") and e["origin"] == origin and e["type"] == error_type and e["message"] == message),
                None,
            )
            if existing:
                existing["count"] = existing.get("count", 1) + 1
                existing["last_seen"] = now
                if tb:
                    existing["traceback"] = tb[-20000:]
                entry = existing
            else:
                data["last_id"] = data.get("last_id", 0) + 1
                entry = {
                    "id": data["last_id"],
                    "origin": origin,
                    "type": error_type,
                    "level": "ERROR",
                    "message": message,
                    "traceback": (tb or "")[-20000:],
                    "context": {str(k): str(v)[:500] for k, v in (context or {}).items() if v is not None},
                    "count": 1,
                    "first_seen": now,
                    "last_seen": now,
                    "resolved": False,
                }
                errors.append(entry)
                del errors[:-MAX_ERRORS]
            return dict(entry)
    except Exception as exc:
        log.warning("Could not record error: %s", exc)
        return None
    finally:
        _local.busy = False


# ---------------------------------------------------------------- discord events & commands

def _parse_custom_id(custom_id: str) -> tuple[str, int] | None:
    prefix, _, raw_id = (custom_id or "").partition(":")
    return (prefix, int(raw_id)) if raw_id.isdigit() else None


async def _report_interaction_error(inter: disnake.Interaction, what: str, error: BaseException) -> None:
    log.error("%s failed (user %s / %s, channel %s)", what, inter.author, inter.author.id, inter.channel_id,
              exc_info=(type(error), error, error.__traceback__))
    text = "Something went wrong — the error has been reported to the developers."
    try:
        if inter.response.is_done():
            await inter.followup.send(text, ephemeral=True)
        else:
            await inter.response.send_message(text, ephemeral=True)
    except Exception:
        pass


def attach(bot: commands.InteractionBot, loop: asyncio.AbstractEventLoop | None = None) -> None:
    """Remembers the running bot (called from on_ready)."""
    global _bot, _loop
    _bot = bot
    if loop is not None:
        _loop = loop
    else:
        try:
            _loop = asyncio.get_running_loop()
        except RuntimeError:
            pass


async def on_member_join(member: disnake.Member, assign_autorole: Callable[[disnake.Member], Coroutine] | None = None) -> None:
    """Automod join checks, then the autorole, then the welcome message."""
    try:
        if await automod_member_join(member):
            return  # kicked
    except Exception:
        log.exception("Automod join check failed for %s", member)
    if assign_autorole:
        try:
            await assign_autorole(member)
        except Exception:
            log.exception("Autorole failed for %s in %s", member, member.guild.name)
    await greet_member("welcome", member)


async def on_guild_message(message: disnake.Message) -> bool:
    """Automod and custom commands for a server message. True if the message was handled (stop processing)."""
    try:
        if await automod_message(message):
            return True
    except Exception:
        log.exception("Automod failed on a message in #%s", message.channel)
    try:
        if await run_custom_command(message):
            return True
    except Exception:
        log.exception("Custom command failed in #%s", message.channel)
    return False


def register(bot: commands.InteractionBot, *, guild_id: str | int | None = None,
             autorole_load=None, autorole_save=None, autorole_resolve=None) -> None:
    """Adds the listeners and slash commands of these features to the RBWR bot."""
    global _bot
    _bot = bot
    if guild_id and str(guild_id).isdigit():
        hooks.guild_id = int(guild_id)
    if autorole_load:
        hooks.autorole_load = autorole_load
    if autorole_save:
        hooks.autorole_save = autorole_save
    if autorole_resolve:
        hooks.autorole_resolve = autorole_resolve

    gid = hooks.guild_id
    guild_ids = [gid] if gid else None
    guild_install = disnake.ApplicationInstallTypes(guild=True, user=False)
    guild_contexts = disnake.InteractionContextTypes(guild=True, bot_dm=False, private_channel=False)

    @bot.listen("on_ready")
    async def _features_ready():
        attach(bot)
        try:
            await sync_discord_automod_rules()
        except Exception as exc:
            log.warning("Initial Discord AutoMod sync failed: %s", exc)

    @bot.listen("on_automod_action_execution")
    async def _features_discord_automod_exec(execution: disnake.AutoModActionExecution):
        try:
            guild = execution.guild
            if not guild or (hooks.guild_id and guild.id != hooks.guild_id):
                return
            rule_trigger = getattr(execution, "rule_trigger_type", None)
            matched_txt = (execution.matched_content or "").lower()

            key = "words"
            if rule_trigger == disnake.AutoModTriggerType.mention_spam:
                key = "mentions"
            elif rule_trigger == disnake.AutoModTriggerType.spam:
                key = "spam"
            elif "discord.gg" in matched_txt or "discord.com/invite" in matched_txt:
                key = "invites"
            elif "http://" in matched_txt or "https://" in matched_txt:
                key = "links"

            user = execution.user
            if not user and execution.user_id:
                try:
                    user = await guild.getch_member(execution.user_id)
                except Exception:
                    pass

            channel = execution.channel or (guild.get_channel(execution.channel_id) if execution.channel_id else None)
            act_type = execution.action.type.name.lower() if execution.action else "block"
            matched = execution.matched_keyword or execution.matched_content or "Rule pattern"
            detail = f"Discord Official AutoMod: {matched}"

            await _automod_record(
                key=key,
                user=user or disnake.Object(id=execution.user_id),
                channel=channel,
                action=act_type,
                detail=detail,
                content=execution.content or "",
                result=f"Blocked natively by Discord ({act_type})"
            )
        except Exception as exc:
            log.warning("Failed to record Discord official AutoMod execution: %s", exc)

    @bot.listen("on_message_interaction")
    async def _features_component(inter: disnake.MessageInteraction):
        parsed = _parse_custom_id(getattr(inter.data, "custom_id", "") or "")
        if not parsed or not parsed[0].startswith("rbwr_mod_"):
            return
        action = parsed[0].removeprefix("rbwr_mod_")
        if action not in MOD_ACTIONS:
            return
        if not _can_moderate(inter.author, action):
            await inter.response.send_message("You don't have permission to do that.", ephemeral=True)
            return
        try:
            await _handle_mod_button(inter, action, parsed[1])
        except Exception as exc:
            await _report_interaction_error(inter, f"Moderation action {action} (user {parsed[1]})", exc)

    @bot.listen("on_modal_submit")
    async def _features_modal(inter: disnake.ModalInteraction):
        parsed = _parse_custom_id(inter.custom_id)
        if not parsed or not parsed[0].startswith("rbwr_mod_modal_"):
            return
        action = parsed[0].removeprefix("rbwr_mod_modal_")
        if action not in MOD_ACTIONS:
            return
        if not _can_moderate(inter.author, action):
            await inter.response.send_message("You don't have permission to do that.", ephemeral=True)
            return
        try:
            await _handle_mod_modal(inter, action, parsed[1])
        except Exception as exc:
            await _report_interaction_error(inter, f"Moderation modal {action} (user {parsed[1]})", exc)

    @bot.listen("on_message_edit")
    async def _features_automod_edit(before: disnake.Message, after: disnake.Message):
        if after.author.bot or after.guild is None or before.content == after.content:
            return
        try:
            await automod_message(after, edited=True)
        except Exception:
            log.exception("Automod failed on an edited message in #%s", after.channel)

    @bot.listen("on_raw_message_edit")
    async def _features_dm_embeds(payload: disnake.RawMessageUpdateEvent):
        # the embed of a link (a GIF from Discord's GIF picker) arrives after the message itself
        if payload.guild_id is None and payload.data.get("embeds"):
            media = _media_from_embeds(payload.data["embeds"])
            if media:
                add_dm_media(str(payload.message_id), media)

    @bot.listen("on_member_remove")
    async def _features_member_remove(member: disnake.Member):
        await greet_member("goodbye", member)

    @bot.slash_command(
        name="mod",
        description="Open the moderation panel for a member (warn, timeout, nickname, kick, ban)",
        guild_ids=guild_ids,
        install_types=guild_install,
        contexts=guild_contexts,
        default_member_permissions=disnake.Permissions(moderate_members=True),
    )
    async def mod_command(
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member = commands.Param(description="Member to moderate"),
    ):
        if not any(_can_moderate(inter.author, a) for a in MOD_ACTIONS):
            await inter.response.send_message("You need a moderation permission (e.g. Timeout Members) to use this.", ephemeral=True)
            return
        if not isinstance(member, disnake.Member):
            await inter.response.send_message("That user is not a member of this server.", ephemeral=True)
            return
        embed, components = build_mod_panel(member, inter.author)
        await inter.response.send_message(embed=embed, components=components, ephemeral=True)

    @bot.slash_command(
        name="unban",
        description="Lift a ban by Discord user ID",
        guild_ids=guild_ids,
        install_types=guild_install,
        contexts=guild_contexts,
        default_member_permissions=disnake.Permissions(ban_members=True),
    )
    async def unban_command(
        inter: disnake.ApplicationCommandInteraction,
        user_id: str = commands.Param(description="Discord user ID of the banned user"),
        reason: str = commands.Param(default=None, description="Reason (shown in the audit log)"),
    ):
        if not _can_moderate(inter.author, "ban"):
            await inter.response.send_message("You need the Ban Members permission to use this.", ephemeral=True)
            return
        if not user_id.strip().isdigit() or not inter.guild:
            await inter.response.send_message("That's not a valid user ID.", ephemeral=True)
            return
        target = disnake.Object(int(user_id.strip()))
        try:
            await inter.guild.unban(target, reason=f"{inter.author} (via /unban): {reason or 'no reason given'}"[:512])
        except disnake.NotFound:
            await inter.response.send_message("That user isn't banned.", ephemeral=True)
            return
        except disnake.Forbidden:
            await inter.response.send_message("I'm missing the **Ban Members** permission.", ephemeral=True)
            return
        await _log_mod_action(inter.author.mention, target, "unbanned", reason)
        await inter.response.send_message(f"<@{target.id}> (`{target.id}`) has been unbanned.", ephemeral=True,
                                          allowed_mentions=disnake.AllowedMentions.none())

    async def _warn_target(inter: disnake.ApplicationCommandInteraction, member: disnake.Member) -> bool:
        """Checks that the author may warn `member` (replies and returns False if not)."""
        if not _can_moderate(inter.author, "warn"):
            await inter.response.send_message("You need the Timeout Members permission to use this.", ephemeral=True)
            return False
        if not isinstance(member, disnake.Member):
            await inter.response.send_message("That user is not a member of this server.", ephemeral=True)
            return False
        problem = _hierarchy_problem(inter.author, member)
        if problem:
            await inter.response.send_message(problem, ephemeral=True)
            return False
        return True

    @bot.slash_command(
        name="warn",
        description="Warn a member (enough active warnings trigger an automatic timeout, kick or ban)",
        guild_ids=guild_ids,
        install_types=guild_install,
        contexts=guild_contexts,
        default_member_permissions=disnake.Permissions(moderate_members=True),
    )
    async def warn_command(
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member = commands.Param(description="Member to warn"),
        reason: str = commands.Param(description="Why — saved in their history and sent to them", max_length=400),
    ):
        if not await _warn_target(inter, member):
            return
        await inter.response.defer(ephemeral=True)
        try:
            text = await _run_mod_action(f"{inter.author} (via /warn)", inter.author.mention, member, "warn", {"reason": reason})
        except BotActionError as exc:
            await inter.followup.send(str(exc), ephemeral=True)
            return
        await inter.followup.send(f"{member.mention} — {text}.", ephemeral=True, allowed_mentions=disnake.AllowedMentions.none())

    @bot.slash_command(
        name="warnings",
        description="Show a member's active warnings",
        guild_ids=guild_ids,
        install_types=guild_install,
        contexts=guild_contexts,
        default_member_permissions=disnake.Permissions(moderate_members=True),
    )
    async def warnings_command(
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.User = commands.Param(description="Member whose warnings to show"),
    ):
        if not _can_moderate(inter.author, "warn"):
            await inter.response.send_message("You need the Timeout Members permission to use this.", ephemeral=True)
            return
        await inter.response.send_message(embed=warnings_embed(member, active_warnings(member.id)), ephemeral=True)

    @bot.slash_command(
        name="unwarn",
        description="Remove a warning by its number (see /warnings)",
        guild_ids=guild_ids,
        install_types=guild_install,
        contexts=guild_contexts,
        default_member_permissions=disnake.Permissions(moderate_members=True),
    )
    async def unwarn_command(
        inter: disnake.ApplicationCommandInteraction,
        warning: int = commands.Param(description="Warning number, e.g. 12 for #12", ge=1),
    ):
        if not _can_moderate(inter.author, "warn"):
            await inter.response.send_message("You need the Timeout Members permission to use this.", ephemeral=True)
            return
        removed = remove_warning(warning)
        if not removed:
            await inter.response.send_message(f"Warning #{warning} doesn't exist.", ephemeral=True)
            return
        await _log_mod_action(inter.author.mention, disnake.Object(int(removed["user_id"])),
                              f"warning #{warning} removed", removed.get("reason"))
        await inter.response.send_message(f"Warning #{warning} of <@{removed['user_id']}> removed.", ephemeral=True,
                                          allowed_mentions=disnake.AllowedMentions.none())

    @bot.slash_command(
        name="faq",
        description="Post an answer to a frequently asked question",
        guild_ids=guild_ids,
        install_types=guild_install,
        contexts=guild_contexts,
    )
    async def faq_command(
        inter: disnake.ApplicationCommandInteraction,
        name: str = commands.Param(default=None, description="Which question (leave empty to list them)"),
        user: disnake.User = commands.Param(default=None, description="Mention someone with the answer"),
    ):
        entries = faq_entries()
        if not name:
            listing = "\n".join(f"`{key}` — {e.get('title') or key}" for key, e in sorted(entries.items()))
            embed = disnake.Embed(title="RBWR FAQ", color=BRAND,
                                  description=(listing or "No FAQ entries yet.")[:4000] + ("\n\nUse `/faq name:` to post one." if listing else ""))
            await inter.response.send_message(embed=embed, ephemeral=True)
            return
        key = name.strip().lower()
        entry = entries.get(key)
        if not entry:
            await inter.response.send_message(f"There's no FAQ entry `{name}`. Run `/faq` to see the list.", ephemeral=True)
            return
        await inter.response.send_message(
            content=user.mention if user else None,
            embed=faq_embed(key, entry),
            allowed_mentions=disnake.AllowedMentions(users=[user] if user else False, roles=False, everyone=False),
        )
        with faq_store.edit() as data:
            if key in data.get("entries", {}):
                data["entries"][key]["uses"] = data["entries"][key].get("uses", 0) + 1

    @faq_command.autocomplete("name")
    async def faq_autocomplete(inter: disnake.ApplicationCommandInteraction, string: str):
        q = (string or "").lower()
        matches = [(f"{e.get('title') or key}"[:100], key) for key, e in sorted(faq_entries().items())
                   if q in key or q in (e.get("title") or "").lower()]
        return dict(matches[:25])  # title shown in Discord -> key sent to the command
