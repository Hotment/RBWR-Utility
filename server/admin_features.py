"""
Admin panel API for the Discord bot features:
embed builder, direct messages, moderation & warnings, automod, autorole, welcome & goodbye,
FAQ, custom commands and the error monitor with alert pings.

Every route checks the admin login and the section permission it belongs to (root admins can do
everything). The routes keep the JSON shape of the original API, so the panel's JavaScript works as is.
"""
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Literal

from flask import Flask, jsonify, request, send_from_directory
from pydantic import BaseModel, Field, ValidationError

import bot_features as bf

# ---------------------------------------------------------------- wiring with app.py


class _Ctx:
    get_user: Callable[[], str | None] = staticmethod(lambda: None)
    has_permission: Callable[[str, str], bool] = staticmethod(lambda _u, _s: False)
    is_root: Callable[[str], bool] = staticmethod(lambda _u: False)
    identity: Callable[[str], dict] = staticmethod(lambda u: {"id": u, "name": u, "picture": None})
    host_url: Callable[[], str] = staticmethod(lambda: request.host_url.rstrip("/"))
    load_admins: Callable[[], dict] = staticmethod(lambda: {"admins": {}})
    report_error: Callable[..., bool] = staticmethod(lambda *a, **k: False)
    alerts_configured: Callable[[], bool] = staticmethod(lambda: False)
    log_audit: Callable[..., Any] = staticmethod(lambda *a, **k: None)


ctx = _Ctx()


class ApiError(Exception):
    def __init__(self, status: int, detail: Any):
        super().__init__(str(detail))
        self.status = status
        self.detail = detail


def _same_origin() -> bool:
    origin = request.headers.get("Origin")
    referer = request.headers.get("Referer")
    host_url = ctx.host_url()
    if origin:
        return origin.rstrip("/") == host_url
    if referer:
        return referer.startswith(host_url)
    return False


def guard(*sections: str):
    """Requires an admin login, a same-origin request for writes and one of the section permissions."""
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = ctx.get_user()
            if not user:
                return jsonify({"detail": "You are not logged in to the admin panel."}), 401
            if request.method in ("POST", "PUT", "PATCH", "DELETE") and not _same_origin():
                return jsonify({"detail": "CSRF verification failed - Same origin required"}), 403
            if sections and not ctx.is_root(user) and not any(ctx.has_permission(user, s) for s in sections):
                return jsonify({"detail": "You don't have access to this section."}), 403
            try:
                result = f(user, *args, **kwargs)
            except ApiError as exc:
                return jsonify({"detail": exc.detail}), exc.status
            except ValidationError as exc:
                return jsonify({"detail": exc.errors(include_url=False, include_context=False, include_input=False)}), 422
            except bf.BotActionError as exc:
                return jsonify({"detail": str(exc)}), 400
            return result if not isinstance(result, (dict, list)) else jsonify(result)
        return wrapper
    return deco


def body(model: type[BaseModel]) -> Any:
    return model.model_validate(request.get_json(silent=True) or {})


def display_name(user: str) -> str:
    return ctx.identity(user).get("name") or user


# ---------------------------------------------------------------- shared validation

def _check_url(value: str, label: str) -> str:
    value = value.strip()
    if value and not value.startswith(("https://", "http://")):
        raise ApiError(400, f"{label} must start with https://")
    return value


class EmbedField(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    value: str = Field(..., min_length=1, max_length=1024)
    inline: bool = False


class EmbedAuthor(BaseModel):
    name: str = Field(default="", max_length=256)
    url: str = Field(default="", max_length=500)
    icon_url: str = Field(default="", max_length=500)


class EmbedFooter(BaseModel):
    text: str = Field(default="", max_length=2048)
    icon_url: str = Field(default="", max_length=500)


class EmbedData(BaseModel):
    title: str = Field("", max_length=256)
    url: str = Field("", max_length=500)
    description: str = Field("", max_length=4096)
    color: int = Field(0x00D1FF, ge=0, le=0xFFFFFF)
    timestamp: bool = False
    author: EmbedAuthor = Field(default_factory=EmbedAuthor)
    thumbnail_url: str = Field("", max_length=500)
    image_url: str = Field("", max_length=500)
    footer: EmbedFooter = Field(default_factory=EmbedFooter)
    fields: list[EmbedField] = Field(default_factory=list, max_length=25)


class EmbedMessageIn(BaseModel):
    content: str = Field("", max_length=2000)
    embed: EmbedData | None = None
    allow_mentions: bool = False


class EmbedSendIn(EmbedMessageIn):
    channel_id: str = Field(..., pattern=r"^\d{15,22}$")
    edit_message_id: str | None = Field(None, pattern=r"^\d{15,22}$")


class EmbedTemplateIn(EmbedMessageIn):
    name: str = Field(..., min_length=1, max_length=64)


def build_discord_embed(data: EmbedData | None) -> dict | None:
    """Converts the builder form into Discord's embed JSON, enforcing Discord's limits."""
    if data is None:
        return None
    embed: dict = {"color": data.color}
    if data.title.strip():
        embed["title"] = data.title.strip()
    if url := _check_url(data.url, "Title URL"):
        embed["url"] = url
    if data.description.strip():
        embed["description"] = data.description.strip()
    if data.timestamp:
        embed["timestamp"] = bf.utc_now()
    if data.author.name.strip():
        embed["author"] = {"name": data.author.name.strip()}
        if url := _check_url(data.author.url, "Author URL"):
            embed["author"]["url"] = url
        if url := _check_url(data.author.icon_url, "Author icon URL"):
            embed["author"]["icon_url"] = url
    if url := _check_url(data.thumbnail_url, "Thumbnail URL"):
        embed["thumbnail"] = {"url": url}
    if url := _check_url(data.image_url, "Image URL"):
        embed["image"] = {"url": url}
    if data.footer.text.strip():
        embed["footer"] = {"text": data.footer.text.strip()}
        if url := _check_url(data.footer.icon_url, "Footer icon URL"):
            embed["footer"]["icon_url"] = url
    if data.fields:
        embed["fields"] = [{"name": f.name.strip(), "value": f.value.strip(), "inline": f.inline} for f in data.fields]

    total = sum(len(embed.get(k, "")) for k in ("title", "description")) + len(data.author.name) + len(data.footer.text) + \
        sum(len(f.name) + len(f.value) for f in data.fields)
    if total > 6000:
        raise ApiError(400, f"The embed is too long ({total} characters). Discord allows 6000 in total.")
    if len(embed) == 1:  # only the color: nothing visible
        return None
    return embed


def _embed_payload(payload: EmbedMessageIn) -> tuple[str, dict | None]:
    content = payload.content.strip()
    embed = build_discord_embed(payload.embed)
    if not content and not embed:
        raise ApiError(400, "Add a message or fill in at least one embed field.")
    return content, embed


def _check_post_channel(channel_id: str | None, required: bool = True) -> str | None:
    """A Discord channel ID the bot can post in (or None when optional and empty)."""
    channel_id = (channel_id or "").strip()
    if not channel_id and not required:
        return None
    try:
        channels = {c["id"] for c in bf.list_text_channels()}
    except bf.BotActionError as exc:
        raise ApiError(503, str(exc))
    if channel_id not in channels:
        raise ApiError(400, "Pick a Discord channel where the bot can post.")
    return channel_id


def _check_timeout(duration: str, what: str) -> None:
    delta = bf.parse_duration(duration)
    if not delta or delta > bf.MAX_TIMEOUT:
        raise ApiError(400, f"Invalid timeout duration for {what} — use e.g. 10m, 1h, 1d (max 28d).")


# ---------------------------------------------------------------- request bodies

class AutoroleIn(BaseModel):
    role_id: str | None = Field(None, max_length=22)  # empty clears the role
    enabled: bool = True
    include_bots: bool = False


class AutoroleSyncIn(BaseModel):
    include_bots: bool = False


class GreetingIn(BaseModel):
    enabled: bool = False
    channel_id: str = Field("", max_length=22)
    message: str = Field("", max_length=2000)
    template: str = Field("", max_length=64)  # Embed Builder template name, empty = text only
    avatar_thumbnail: bool = False


class FaqIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=32, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    title: str = Field(..., min_length=1, max_length=256)
    answer: str = Field(..., min_length=1, max_length=4000)
    original: str = Field("", max_length=32)  # the entry's name before editing (renames it)


COMMAND_NAME = r"^[a-z0-9][a-z0-9_-]*$"


class CustomCommandIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=32, pattern=COMMAND_NAME)
    aliases: list[str] = Field(default_factory=list, max_length=10)
    response: str = Field("", max_length=2000)
    template: str = Field("", max_length=64)  # Embed Builder template name
    embed: EmbedData | None = None            # an embed made just for this command (instead of a template)
    role_id: str = Field("", max_length=22)   # empty = everyone may use it
    cooldown: int = Field(10, ge=0, le=3600)  # seconds per channel
    reply: bool = True
    delete_trigger: bool = False
    enabled: bool = True
    original: str = Field("", max_length=32)  # the command's name before editing (renames it)


class CommandPrefixIn(BaseModel):
    prefix: str = Field(..., min_length=1, max_length=5, pattern=r"^\S+$")


class DmIn(BaseModel):
    message: str = Field("", max_length=2000)
    images: list[str] = Field(default_factory=list, max_length=4)


class ModerationIn(BaseModel):
    action: Literal["warn", "timeout", "untimeout", "nick", "kick", "ban"]
    duration: str = Field("", max_length=20)
    nick: str = Field("", max_length=32)
    reason: str = Field("", max_length=400)
    delete_days: int = Field(0, ge=0, le=7)


class UnbanIn(BaseModel):
    reason: str = Field("", max_length=400)


class WarnRuleIn(BaseModel):
    count: int = Field(..., ge=1, le=50)
    action: Literal["timeout", "kick", "ban"]
    duration: str = Field("", max_length=20)


class WarnConfigIn(BaseModel):
    expire_days: int = Field(0, ge=0, le=3650)  # 0 = warnings never expire
    rules: list[WarnRuleIn] = Field(default_factory=list, max_length=10)


AutomodAction = Literal["log", "delete", "warn", "timeout"]
JoinAction = Literal["alert", "timeout", "kick"]


class AmFilterIn(BaseModel):
    enabled: bool = False
    action: AutomodAction = "delete"
    duration: str = Field("10m", max_length=20)


class AmWordsIn(AmFilterIn):
    words: list[str] = Field(default_factory=list, max_length=500)


class AmInvitesIn(AmFilterIn):
    allow_own: bool = True


class AmLinksIn(AmFilterIn):
    allowed: list[str] = Field(default_factory=list, max_length=100)


class AmMaxIn(AmFilterIn):
    max: int = Field(5, ge=1, le=100)


class AmCapsIn(AmFilterIn):
    percent: int = Field(70, ge=50, le=100)
    min_length: int = Field(12, ge=5, le=500)


class AmSpamIn(AmFilterIn):
    messages: int = Field(6, ge=2, le=50)
    seconds: int = Field(8, ge=2, le=120)


class AmDuplicatesIn(AmFilterIn):
    count: int = Field(3, ge=2, le=20)
    seconds: int = Field(60, ge=5, le=3600)


class AmFiltersIn(BaseModel):
    words: AmWordsIn
    invites: AmInvitesIn
    links: AmLinksIn
    mentions: AmMaxIn
    caps: AmCapsIn
    emoji: AmMaxIn
    lines: AmMaxIn
    spam: AmSpamIn
    duplicates: AmDuplicatesIn


class AmRaidIn(BaseModel):
    enabled: bool = False
    joins: int = Field(8, ge=3, le=100)
    seconds: int = Field(30, ge=5, le=600)
    action: JoinAction = "alert"
    lockdown_minutes: int = Field(10, ge=1, le=1440)


class AmAccountAgeIn(BaseModel):
    enabled: bool = False
    days: int = Field(3, ge=1, le=365)
    action: JoinAction = "alert"
    duration: str = Field("1d", max_length=20)


class AutomodIn(BaseModel):
    enabled: bool = False
    log_channel_id: str = Field("", max_length=22)
    notify: bool = True
    exempt_staff: bool = True
    exempt_roles: list[str] = Field(default_factory=list, max_length=50)
    exempt_channels: list[str] = Field(default_factory=list, max_length=100)
    filters: AmFiltersIn
    raid: AmRaidIn
    account_age: AmAccountAgeIn


class AutomodTestIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


class ErrorStatusIn(BaseModel):
    resolved: bool




# ---------------------------------------------------------------- routes

# the channel and role pickers are used by every bot section
BOT_SECTIONS = ("embeds", "autorole", "welcome", "faq", "commands", "moderation", "automod", "dms", "errors")


def init_app(app: Flask, **hooks) -> None:
    """Registers the routes. `hooks` fill the _Ctx attributes (get_user, has_permission, is_root, ...)."""
    for key, value in hooks.items():
        setattr(ctx, key, value)

    def route(rule: str, methods: list[str], *sections: str):
        def deco(f):
            app.add_url_rule(rule, endpoint=f"admin_features_{f.__name__}", view_func=guard(*sections)(f), methods=methods)
            return f
        return deco

    # ------------------------------------------------ discord lookups

    @route("/api/admin/discord/channels", ["GET"], *BOT_SECTIONS)
    def discord_channels(user):
        try:
            return {"channels": bf.list_text_channels()}
        except bf.BotActionError as exc:
            raise ApiError(503, str(exc))

    @route("/api/admin/discord/roles", ["GET"], *BOT_SECTIONS)
    def discord_roles(user):
        try:
            return bf.list_roles()
        except bf.BotActionError as exc:
            raise ApiError(503, str(exc))

    @route("/api/admin/discord/members", ["GET"], "dms", "moderation")
    def discord_members(user):
        q = request.args.get("q", "")
        if len(q.strip()) < 2:
            return {"members": []}
        try:
            return {"members": bf.search_members(q[:64])}
        except bf.BotActionError as exc:
            raise ApiError(503, str(exc))

    @route("/api/admin/bot-status", ["GET"])
    def bot_status(user):
        return {"online": bf.is_ready()}

    # ------------------------------------------------ embed builder

    @route("/api/admin/embeds", ["GET"], "embeds", "welcome", "commands")
    def list_embeds(user):
        data = bf.embeds_store.load()
        templates = [{"name": name, **t} for name, t in sorted(data.get("templates", {}).items())]
        return {"templates": templates, "history": data.get("history", [])}

    @route("/api/admin/embeds/send", ["POST"], "embeds")
    def send_embed(user):
        payload: EmbedSendIn = body(EmbedSendIn)
        content, embed = _embed_payload(payload)
        result = bf.send_embed(payload.channel_id, content, embed, payload.allow_mentions, payload.edit_message_id)
        bf.add_embed_history({
            **result,
            "content": content,
            "embed": embed,
            "data": payload.embed.model_dump() if payload.embed else None,
            "allow_mentions": payload.allow_mentions,
            "sent_by": display_name(user),
            "source": "web",
            "edited": bool(payload.edit_message_id),
        })
        ctx.log_audit(user, "bot.send_embed", "bot", f"Sent embed to channel #{payload.channel_id}" + (" (edit)" if payload.edit_message_id else ""), target=f"Channel {payload.channel_id}", details={"channel_id": payload.channel_id, "edit_id": payload.edit_message_id})
        return result

    @route("/api/admin/embeds/templates", ["POST"], "embeds")
    def save_embed_template(user):
        payload: EmbedTemplateIn = body(EmbedTemplateIn)
        content, embed = _embed_payload(payload)
        name = payload.name.strip()
        with bf.embeds_store.edit() as data:
            data.setdefault("templates", {})[name] = {
                "content": content,
                "embed": embed,
                "data": payload.embed.model_dump() if payload.embed else None,
                "allow_mentions": payload.allow_mentions,
                "updated_by": display_name(user),
                "updated_at": bf.utc_now(),
            }
        ctx.log_audit(user, "bot.save_embed_template", "bot", f"Saved embed template '{name}'", target=name)
        return {"name": name}

    @route("/api/admin/embeds/templates/<path:name>", ["DELETE"], "embeds")
    def delete_embed_template(user, name):
        with bf.embeds_store.edit() as data:
            if data.get("templates", {}).pop(name, None) is None:
                raise ApiError(404, "Template not found.")
        ctx.log_audit(user, "bot.delete_embed_template", "bot", f"Deleted embed template '{name}'", target=name)
        return {"deleted": name}

    # ------------------------------------------------ autorole

    @route("/api/admin/autorole", ["GET"], "autorole")
    def get_autorole(user):
        try:
            return bf.autorole_overview()
        except bf.BotActionError as exc:
            raise ApiError(503, str(exc))

    @route("/api/admin/autorole", ["POST"], "autorole")
    def set_autorole(user):
        payload: AutoroleIn = body(AutoroleIn)
        bf.set_autorole((payload.role_id or "").strip() or None, payload.enabled, payload.include_bots,
                        ctx.identity(user).get("id") or user)
        ctx.log_audit(user, "bot.autorole_update", "bot", f"{'Enabled' if payload.enabled else 'Disabled'} autorole (role {payload.role_id or 'none'})", target="Autorole", details={"role_id": payload.role_id, "enabled": payload.enabled, "include_bots": payload.include_bots})
        return bf.autorole_overview()

    @route("/api/admin/autorole/sync", ["POST"], "autorole")
    def sync_autorole(user):
        payload: AutoroleSyncIn = body(AutoroleSyncIn)
        bf.start_autorole_sync(payload.include_bots, display_name(user))
        ctx.log_audit(user, "bot.autorole_sync", "bot", "Triggered autorole synchronization", target="Autorole")
        return bf.autorole_overview()

    # ------------------------------------------------ welcome & goodbye

    def _greetings() -> dict:
        data = bf.welcome_store.load()
        return {
            "welcome": data.get("welcome") or {},
            "goodbye": data.get("goodbye") or {},
            "templates": sorted(bf.embed_templates()),
            "defaults": bf.DEFAULT_GREETINGS,
            "bot_online": bf.is_ready(),
        }

    @route("/api/admin/welcome", ["GET"], "welcome")
    def get_welcome(user):
        return _greetings()

    @route("/api/admin/welcome/<kind>", ["PUT"], "welcome")
    def set_welcome(user, kind):
        if kind not in bf.GREETING_KINDS:
            raise ApiError(404, "Unknown message.")
        payload: GreetingIn = body(GreetingIn)
        channel_id = _check_post_channel(payload.channel_id, required=payload.enabled)
        template = payload.template.strip()
        if template and template not in bf.embed_templates():
            raise ApiError(400, "That embed template doesn't exist anymore.")
        with bf.welcome_store.edit() as data:
            data[kind] = {
                "enabled": payload.enabled, "channel_id": channel_id, "message": payload.message.strip(),
                "template": template or None, "avatar_thumbnail": payload.avatar_thumbnail,
                "updated_by": display_name(user), "updated_at": bf.utc_now(),
            }
        ctx.log_audit(user, f"bot.{kind}_update", "bot", f"Updated {kind} settings ({'enabled' if payload.enabled else 'disabled'})", target=kind.capitalize(), details={"enabled": payload.enabled, "channel_id": channel_id})
        return _greetings()

    @route("/api/admin/welcome/<kind>/test", ["POST"], "welcome")
    def test_welcome(user, kind):
        if kind not in bf.GREETING_KINDS:
            raise ApiError(404, "Unknown message.")
        return bf.greeting_test(kind, ctx.identity(user).get("discord_id"))

    # ------------------------------------------------ FAQ

    def _faq_list() -> dict:
        entries = bf.faq_store.load().get("entries", {})
        return {"entries": [{"name": k, **e} for k, e in sorted(entries.items())]}

    @route("/api/admin/faq", ["GET"], "faq")
    def list_faq(user):
        return _faq_list()

    @route("/api/admin/faq", ["POST"], "faq")
    def save_faq(user):
        payload: FaqIn = body(FaqIn)
        name, original = payload.name.strip().lower(), payload.original.strip().lower()
        with bf.faq_store.edit() as data:
            entries = data.setdefault("entries", {})
            if name != original and name in entries:
                raise ApiError(400, f"There's already an entry named {name}.")
            previous = entries.pop(original, {}) if original else {}
            entries[name] = {
                "title": payload.title.strip(), "answer": payload.answer.strip(), "uses": previous.get("uses", 0),
                "updated_by": display_name(user), "updated_at": bf.utc_now(),
            }
        ctx.log_audit(user, "bot.faq_save", "bot", f"Saved FAQ entry '{name}'", target=f"FAQ: {name}", details={"title": payload.title.strip()})
        return _faq_list()

    @route("/api/admin/faq/<name>", ["DELETE"], "faq")
    def delete_faq(user, name):
        with bf.faq_store.edit() as data:
            if data.get("entries", {}).pop(name, None) is None:
                raise ApiError(404, "FAQ entry not found.")
        ctx.log_audit(user, "bot.faq_delete", "bot", f"Deleted FAQ entry '{name}'", target=f"FAQ: {name}")
        return _faq_list()

    # ------------------------------------------------ custom commands

    def _commands_list() -> dict:
        prefix, cmds = bf.custom_commands()
        return {
            "prefix": prefix,
            "commands": [{"name": k, **c} for k, c in sorted(cmds.items())],
            "templates": sorted(bf.embed_templates()),
            "message_content_intent": bf.message_content_enabled(),
            "site_url": bf.hooks.site_url,
        }

    site_stand_in = "https://site.invalid"

    def _command_embed(data: EmbedData | None) -> dict | None:
        """build_discord_embed, but its links may start with {site} (filled in when the command is used)."""
        if data is None:
            return None
        raw = json.dumps(data.model_dump()).replace("{site}", site_stand_in)
        embed = build_discord_embed(EmbedData.model_validate_json(raw))
        return json.loads(json.dumps(embed).replace(site_stand_in, "{site}")) if embed else None

    @route("/api/admin/commands", ["GET"], "commands")
    def list_commands(user):
        return _commands_list()

    @route("/api/admin/commands", ["POST"], "commands")
    def save_command(user):
        payload: CustomCommandIn = body(CustomCommandIn)
        name, original = payload.name.strip().lower(), payload.original.strip().lower()
        aliases = list(dict.fromkeys(a.strip().lower() for a in payload.aliases if a.strip() and a.strip().lower() != name))
        if any(not re.match(COMMAND_NAME, a) or len(a) > 32 for a in aliases):
            raise ApiError(400, "Aliases may only use lowercase letters, numbers, - and _.")
        embed = None if payload.template else _command_embed(payload.embed)
        if not payload.response.strip() and not payload.template and not embed:
            raise ApiError(400, "Write a response, fill in the embed or pick an embed template.")
        if payload.template and payload.template not in bf.embed_templates():
            raise ApiError(400, "That embed template doesn't exist anymore.")
        if payload.role_id and not payload.role_id.isdigit():
            raise ApiError(400, "Invalid role ID.")
        with bf.commands_store.edit() as data:
            cmds = data.setdefault("commands", {})
            for key, c in cmds.items():
                if key == original:
                    continue
                taken = {key, *c.get("aliases", [])} & {name, *aliases}
                if taken:
                    raise ApiError(400, f"{data.get('prefix') or '!'}{taken.pop()} is already used by {key}.")
            previous = cmds.pop(original, {}) if original else {}
            cmds[name] = {
                "aliases": aliases, "response": payload.response.strip(), "template": payload.template,
                "embed": embed, "role_id": payload.role_id, "cooldown": payload.cooldown, "reply": payload.reply,
                "delete_trigger": payload.delete_trigger, "enabled": payload.enabled, "uses": previous.get("uses", 0),
                "updated_by": display_name(user), "updated_at": bf.utc_now(),
            }
        ctx.log_audit(user, "bot.command_save", "bot", f"Saved custom command '{name}'", target=f"!{name}", details={"aliases": aliases, "enabled": payload.enabled})
        return _commands_list()

    @route("/api/admin/commands/prefix", ["PUT"], "commands")
    def set_command_prefix(user):
        payload: CommandPrefixIn = body(CommandPrefixIn)
        with bf.commands_store.edit() as data:
            data["prefix"] = payload.prefix
        ctx.log_audit(user, "bot.command_prefix", "bot", f"Changed command prefix to '{payload.prefix}'", target="Commands", details={"prefix": payload.prefix})
        return _commands_list()

    @route("/api/admin/commands/<name>", ["DELETE"], "commands")
    def delete_command(user, name):
        with bf.commands_store.edit() as data:
            if data.get("commands", {}).pop(name, None) is None:
                raise ApiError(404, "Command not found.")
        ctx.log_audit(user, "bot.command_delete", "bot", f"Deleted custom command '{name}'", target=f"!{name}")
        return _commands_list()

    # ------------------------------------------------ direct messages

    def _dm_summary(conv: dict) -> dict:
        last = (conv.get("messages") or [{}])[-1]
        return {
            **{k: conv.get(k) for k in ("user_id", "name", "username", "avatar", "unread", "updated_at")},
            "last": {"text": (last.get("text") or ("📎 GIF / image" if last.get("images") or last.get("media") else ""))[:120],
                     "direction": last.get("direction")},
        }

    @route("/api/admin/dms", ["GET"], "dms")
    def list_dms(user):
        conversations = bf.dms_store.load().get("conversations", {}).values()
        ordered = sorted(conversations, key=lambda c: c.get("updated_at", ""), reverse=True)
        return {"conversations": [_dm_summary(c) for c in ordered], "bot_online": bf.is_ready()}

    @route("/api/admin/dms/<user_id>", ["GET"], "dms")
    def get_dm(user, user_id):
        conv = bf.dms_store.load().get("conversations", {}).get(user_id)
        if conv and conv.get("unread"):
            with bf.dms_store.edit() as data:
                data["conversations"][user_id]["unread"] = 0
        return {"conversation": conv}

    @route("/api/admin/dms/<user_id>", ["POST"], "dms")
    def send_dm(user, user_id):
        payload: DmIn = body(DmIn)
        text = payload.message.strip()
        images = list(dict.fromkeys(payload.images))
        if not user_id.isdigit() or not (text or images):
            raise ApiError(400, "Pick a member and write a message or attach a GIF.")
        files = []
        for name in images:
            path = os.path.join(bf.UPLOAD_DIR, name)
            if not re.match(bf.UPLOAD_NAME_RE, name):
                raise ApiError(400, "Invalid attachment.")
            if not os.path.exists(path):
                raise ApiError(400, "An attached image no longer exists — attach it again.")
            files.append((path, f"image.{name.rsplit('.', 1)[1]}"))
        result = bf.send_dm(user_id, text, files)
        bf.record_dm(
            user_id, result["profile"],
            {"text": text, "images": images, "discord_message_id": result["message_id"], "sent_by": display_name(user)},
            incoming=False,
        )
        ctx.log_audit(user, "bot.send_dm", "bot", f"Sent DM to Discord member {user_id}", target=f"User {user_id}", details={"user_id": user_id})
        return {"sent": True}

    @route("/api/admin/uploads", ["POST"], "dms")
    def upload_image(user):
        if (request.content_length or 0) > bf.MAX_DM_IMAGE_BYTES:
            raise ApiError(413, "The image is larger than 8 MB.")
        data = request.get_data(cache=False)
        if len(data) > bf.MAX_DM_IMAGE_BYTES:
            raise ApiError(413, "The image is larger than 8 MB.")
        ext = bf.image_ext(data[:16])
        if not ext:
            raise ApiError(400, "Only PNG, JPEG, GIF and WebP images are supported.")
        os.makedirs(bf.UPLOAD_DIR, exist_ok=True)
        name = f"{secrets.token_hex(16)}.{ext}"
        with open(os.path.join(bf.UPLOAD_DIR, name), "wb") as f:
            f.write(data)
        return {"name": name}

    @route("/api/admin/uploads/<name>", ["GET"], "dms")
    def get_upload(user, name):
        if not re.match(bf.UPLOAD_NAME_RE, name) or not os.path.exists(os.path.join(bf.UPLOAD_DIR, name)):
            raise ApiError(404, "Image not found.")
        return send_from_directory(bf.UPLOAD_DIR, name, max_age=3600)

    # ------------------------------------------------ moderation

    @route("/api/admin/moderation/members/<user_id>", ["GET"], "moderation")
    def get_mod_member(user, user_id):
        if not user_id.isdigit():
            raise ApiError(400, "Invalid user ID.")
        return {"member": bf.get_member_moderation(user_id)}

    @route("/api/admin/moderation/members/<user_id>", ["POST"], "moderation")
    def moderate_member(user, user_id):
        if not user_id.isdigit():
            raise ApiError(400, "Invalid user ID.")
        payload: ModerationIn = body(ModerationIn)
        values = {"duration": payload.duration, "nick": payload.nick, "reason": payload.reason,
                  "delete_days": str(payload.delete_days)}
        res = bf.moderate_member(user_id, payload.action, values, display_name(user))
        ctx.log_audit(user, f"bot.mod_{payload.action}", "bot", f"Executed moderation '{payload.action}' on Discord member {user_id} ({payload.reason or 'no reason'})", target=f"User {user_id}", details={"action": payload.action, "user_id": user_id, "reason": payload.reason, "duration": payload.duration})
        return res

    @route("/api/admin/moderation/bans", ["GET"], "moderation")
    def list_discord_bans(user):
        try:
            return {"bans": bf.list_discord_bans()}
        except bf.BotActionError as exc:
            raise ApiError(503, str(exc))

    @route("/api/admin/moderation/bans/<user_id>/unban", ["POST"], "moderation")
    def discord_unban(user, user_id):
        if not user_id.isdigit():
            raise ApiError(400, "Invalid user ID.")
        payload: UnbanIn = body(UnbanIn)
        bf.unban_user(user_id, payload.reason.strip() or None, display_name(user))
        ctx.log_audit(user, "bot.mod_unban", "bot", f"Unbanned Discord member {user_id} ({payload.reason.strip() or 'no reason'})", target=f"User {user_id}", details={"user_id": user_id, "reason": payload.reason.strip()})
        return {"unbanned": user_id}

    @route("/api/admin/moderation/warnings/<int:warning_id>", ["DELETE"], "moderation")
    def remove_warning(user, warning_id):
        if not bf.remove_warning(warning_id):
            raise ApiError(404, "Warning not found.")
        ctx.log_audit(user, "bot.mod_remove_warning", "bot", f"Removed warning #{warning_id}", target=f"Warning #{warning_id}", details={"warning_id": warning_id})
        return {"deleted": warning_id}

    @route("/api/admin/moderation/warn-config", ["GET"], "moderation")
    def get_warn_config(user):
        return bf.warn_config()

    @route("/api/admin/moderation/warn-config", ["PUT"], "moderation")
    def set_warn_config(user):
        payload: WarnConfigIn = body(WarnConfigIn)
        rules = sorted(payload.rules, key=lambda r: r.count)
        if len({r.count for r in rules}) != len(rules):
            raise ApiError(400, "Each warning count can only have one rule.")
        for r in rules:
            if r.action == "timeout":
                _check_timeout(r.duration, f"{r.count} warnings")
        config = {"expire_days": payload.expire_days,
                  "rules": [{"count": r.count, "action": r.action, "duration": r.duration.strip() if r.action == "timeout" else ""}
                            for r in rules]}
        res = bf.save_warn_config(config)
        ctx.log_audit(user, "bot.mod_warn_config", "bot", "Updated moderation warning rules and thresholds", target="Warn Config")
        return res

    # ------------------------------------------------ automod

    @route("/api/admin/automod", ["GET"], "automod")
    def get_automod(user):
        return bf.automod_status()

    @route("/api/admin/automod", ["PUT"], "automod")
    def set_automod(user):
        payload: AutomodIn = body(AutomodIn)
        ids = [payload.log_channel_id, *payload.exempt_roles, *payload.exempt_channels]
        if any(i and not i.isdigit() for i in ids):
            raise ApiError(400, "Invalid channel or role ID.")
        config = payload.model_dump()
        for key, rule in config["filters"].items():
            if rule["action"] == "timeout":
                _check_timeout(rule["duration"], bf.AUTOMOD_LABELS[key])
        if payload.account_age.action == "timeout":
            _check_timeout(payload.account_age.duration, "new accounts")
        bf.save_automod_config(config)
        ctx.log_audit(user, "bot.automod_save", "bot", "Updated automod filter rules and configuration", target="Automod")
        return bf.automod_status()

    @route("/api/admin/automod/test", ["POST"], "automod")
    def test_automod(user):
        payload: AutomodTestIn = body(AutomodTestIn)
        try:
            return {"hit": bf.automod_test(payload.text)}
        except bf.BotActionError as exc:
            raise ApiError(503, str(exc))

    @route("/api/admin/automod/raid/end", ["POST"], "automod")
    def end_raid(user):
        bf.end_raid()
        ctx.log_audit(user, "bot.automod_end_raid", "bot", "Manually ended automod raid lockdown", target="Automod")
        return bf.automod_status()

    @route("/api/admin/automod/incidents", ["DELETE"], "automod")
    def clear_automod_incidents(user):
        with bf.automod_store.edit() as data:
            data["incidents"] = []
        ctx.log_audit(user, "bot.automod_clear_incidents", "bot", "Cleared automod incident logs", target="Automod Incidents")
        return bf.automod_status()

    # ------------------------------------------------ error monitor

    @route("/api/admin/errors", ["GET"], "errors")
    def list_errors(user):
        errors_list = sorted(bf.errors_store.load().get("errors", []), key=lambda e: e.get("last_seen", ""), reverse=True)
        return {"errors": errors_list, "alerts_configured": bool(ctx.alerts_configured())}

    @route("/api/admin/errors/<int:error_id>/status", ["POST"], "errors")
    def set_error_status(user, error_id):
        payload: ErrorStatusIn = body(ErrorStatusIn)
        with bf.errors_store.edit() as data:
            entry = next((e for e in data.get("errors", []) if e.get("id") == error_id), None)
            if entry is None:
                raise ApiError(404, "Error not found.")
            entry["resolved"] = payload.resolved
            entry["resolved_by"] = display_name(user) if payload.resolved else None
        ctx.log_audit(user, "bot.error_status", "bot", f"{'Resolved' if payload.resolved else 'Reopened'} bot error #{error_id}", target=f"Error #{error_id}", details={"error_id": error_id, "resolved": payload.resolved})
        return {"id": error_id, "resolved": payload.resolved}

    @route("/api/admin/errors/<int:error_id>", ["DELETE"], "errors")
    def delete_error(user, error_id):
        with bf.errors_store.edit() as data:
            before = len(data.get("errors", []))
            data["errors"] = [e for e in data.get("errors", []) if e.get("id") != error_id]
            if len(data["errors"]) == before:
                raise ApiError(404, "Error not found.")
        ctx.log_audit(user, "bot.error_delete", "bot", f"Deleted bot error record #{error_id}", target=f"Error #{error_id}", details={"error_id": error_id})
        return {"deleted": error_id}

    @route("/api/admin/errors/clear-resolved", ["POST"], "errors")
    def clear_resolved_errors(user):
        with bf.errors_store.edit() as data:
            data["errors"] = [e for e in data.get("errors", []) if not e.get("resolved")]
        ctx.log_audit(user, "bot.error_clear_resolved", "bot", "Cleared resolved bot error records", target="Bot Errors")
        return {"ok": True}

    @route("/api/admin/errors/test", ["POST"], "errors")
    def test_error_alert(user):
        # the time keeps every test unique, so each one is alerted instead of grouped with the last
        message = (f"Test alert triggered by {display_name(user)} "
                   f"at {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC")
        sent = ctx.report_error("Test alert", RuntimeError(message), context_info={"Triggered by": display_name(user)})
        return {"sent": bool(sent), "alerts_configured": bool(ctx.alerts_configured())}