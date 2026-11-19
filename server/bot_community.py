from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Callable

import disnake
from disnake.ext import commands

import bot_features as bf

log = bf.log

STATS_INTERVAL = 600

starboard_store = bf.JsonStore("starboard.json", {
    "config": {"enabled": False, "channel_id": None, "emoji": "⭐", "threshold": 3,
               "self_star": False, "bots": False, "ignored_channels": []},
    "posts": {},
})
serverstats_store = bf.JsonStore("server_stats.json", {"config": {"enabled": False, "category_id": None, "counters": []}})

COUNTERS = {
    "members": ("Members: {value}", "Everyone on the server"),
    "humans": ("Humans: {value}", "Members who aren't bots"),
    "bots": ("Bots: {value}", "Bots on the server"),
    "boosts": ("Boosts: {value}", "Server boosts"),
    "boost_level": ("Boost level: {value}", "Server boost level (0-3)"),
    "channels": ("Channels: {value}", "Text and voice channels"),
    "roles": ("Roles: {value}", "Roles on the server"),
    "tickets": ("Open tickets: {value}", "Suggestions and bug reports still open on the website"),
}
DEFAULT_COUNTERS = ("members", "humans", "bots", "boosts")
CLOSED_STATUSES = {"implemented", "declined", "fixed", "invalid", "resolved", "closed", "accepted", "rejected", "completed"}

_tasks: dict[str, asyncio.Task] = {}
_star_locks: dict[int, asyncio.Lock] = {}


class _Hooks:
    load_tickets: Callable[[], dict] | None = None


hooks = _Hooks()


def configure(load_tickets: Callable[[], dict] | None = None) -> None:
    if load_tickets:
        hooks.load_tickets = load_tickets


def _allowed(user, command: str) -> bool:
    return bf.staff_allowed(user, "community", "manage_guild", command)


async def _staff_guild(inter: disnake.ApplicationCommandInteraction, command: str) -> disnake.Guild | None:
    if not _allowed(inter.author, command):
        await inter.response.send_message(
            "You can't use this. Website admins need the **Community** permission in the admin panel; "
            "everyone else needs **Manage Server** on Discord.", ephemeral=True)
        return None
    if not inter.guild:
        await inter.response.send_message("This command must be used in a server.", ephemeral=True)
        return None
    return inter.guild


def _embed(title: str, guild: disnake.Guild | None = None) -> disnake.Embed:
    embed = disnake.Embed(title=title, color=bf.BRAND, timestamp=datetime.now(timezone.utc))
    embed.set_footer(text=f"{bf.FOOTER} • {guild.name}" if guild else bf.FOOTER)
    return embed


def _start(name: str, coro_fn) -> None:
    task = _tasks.get(name)
    if task and not task.done():
        return
    task = asyncio.create_task(coro_fn())
    task.add_done_callback(bf._log_future_error)
    _tasks[name] = task


def _missing_perms(channel, me: disnake.Member, *perms: str) -> list[str]:
    have = channel.permissions_for(me)
    return [p.replace("_", " ") for p in perms if not getattr(have, p)]


def open_ticket_count() -> int:
    if not hooks.load_tickets:
        return 0
    try:
        tickets = hooks.load_tickets().get("suggestions", [])
    except Exception:
        return 0
    return sum(1 for t in tickets if not t.get("merged_into") and str(t.get("status") or "").lower() not in CLOSED_STATUSES)


# =============================================================================== starboard

def star_config() -> dict:
    return {**starboard_store.default["config"], **starboard_store.load().get("config", {})}


def _star_embed(message: disnake.Message, count: int, emoji: str) -> disnake.Embed:
    author = message.author
    embed = disnake.Embed(description=(message.content or "")[:4000] or None, color=bf.BRAND, timestamp=message.created_at)
    embed.set_author(name=getattr(author, "display_name", author.name), icon_url=author.display_avatar.url)
    image = next((a.url for a in message.attachments if (a.content_type or "").startswith("image/")), None)
    if not image:
        image = next((e.image.url or e.thumbnail.url for e in message.embeds
                      if (e.image and e.image.url) or (e.thumbnail and e.thumbnail.url)), None)
    if image:
        embed.set_image(url=image)
    others = [a for a in message.attachments if a.url != image]
    if others:
        embed.add_field(name="Attachments", value="\n".join(f"[{a.filename}]({a.url})" for a in others[:5]), inline=False)
    embed.add_field(name=f"{emoji} {count}", value=f"{message.channel.mention} · [Jump to message]({message.jump_url})", inline=False)  # pyright: ignore[reportAttributeAccessIssue]
    embed.set_footer(text=f"#{getattr(message.channel, 'name', 'channel')}")
    return embed


def _jump_button(message: disnake.Message) -> list:
    return [disnake.ui.Button(style=disnake.ButtonStyle.link, label="Jump to message", url=message.jump_url)]


async def _count_stars(message: disnake.Message, emoji: str, self_star: bool) -> int:
    reaction = next((r for r in message.reactions if str(r.emoji) == emoji), None)
    if not reaction:
        return 0
    count = reaction.count
    if not self_star and reaction.count:
        try:
            async for user in reaction.users():
                if user.id == message.author.id:
                    count -= 1
                    break
        except disnake.HTTPException:
            pass
    return max(0, count)


def _save_post(message_id: int, star_id: int, channel_id: int, count: int) -> None:
    with starboard_store.edit() as data:
        data.setdefault("posts", {})[str(message_id)] = {"star_id": str(star_id), "channel_id": str(channel_id), "count": count}


async def _update_star(bot: commands.InteractionBot, payload) -> None:
    config = star_config()
    if not config["enabled"] or not config.get("channel_id") or not payload.guild_id:
        return
    if bf.hooks.guild_id and payload.guild_id != bf.hooks.guild_id:
        return
    if str(payload.emoji) != config["emoji"]:
        return
    if payload.channel_id == int(config["channel_id"]) or str(payload.channel_id) in map(str, config["ignored_channels"]):
        return
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    star_channel = guild.get_channel(int(config["channel_id"]))
    source = guild.get_channel_or_thread(payload.channel_id)
    if not isinstance(star_channel, disnake.TextChannel) or source is None:
        return
    if getattr(source, "nsfw", False) and not star_channel.nsfw:
        return
    lock = _star_locks.setdefault(payload.message_id, asyncio.Lock())
    async with lock:
        await _apply_star(config, source, star_channel, payload.message_id)
    if len(_star_locks) > 500:
        for mid, l in list(_star_locks.items()):
            if not l.locked():
                _star_locks.pop(mid, None)


async def _apply_star(config: dict, source, star_channel: disnake.TextChannel, message_id: int) -> None:
    try:
        message = await source.fetch_message(message_id)
    except disnake.HTTPException:
        return
    if message.author.bot and not config["bots"]:
        return
    count = await _count_stars(message, config["emoji"], config["self_star"])
    post = starboard_store.load().get("posts", {}).get(str(message.id))
    embed = _star_embed(message, count, config["emoji"])
    if post:
        try:
            star_msg = await star_channel.fetch_message(int(post["star_id"]))
        except disnake.NotFound:
            star_msg = None
        except disnake.HTTPException:
            return
        if count < config["threshold"]:
            if star_msg:
                await star_msg.delete()
            with starboard_store.edit() as data:
                data.get("posts", {}).pop(str(message.id), None)
            return
        if star_msg:
            await star_msg.edit(content=None, embed=embed)
        else:
            star_msg = await star_channel.send(embed=embed, components=_jump_button(message),
                                               allowed_mentions=disnake.AllowedMentions.none())
        _save_post(message.id, star_msg.id, source.id, count)
        return
    if count < config["threshold"]:
        return
    star_msg = await star_channel.send(embed=embed, components=_jump_button(message), allowed_mentions=disnake.AllowedMentions.none())
    _save_post(message.id, star_msg.id, source.id, count)


async def _forget_star(bot: commands.InteractionBot, message_id: int) -> None:
    post = starboard_store.load().get("posts", {}).get(str(message_id))
    if not post:
        return
    with starboard_store.edit() as data:
        data.get("posts", {}).pop(str(message_id), None)
    channel_id = star_config().get("channel_id")
    channel = bot.get_channel(int(channel_id)) if channel_id else None
    if isinstance(channel, disnake.TextChannel):
        try:
            await (await channel.fetch_message(int(post["star_id"]))).delete()
        except disnake.HTTPException:
            pass


def _star_view_embed(guild: disnake.Guild) -> disnake.Embed:
    c = star_config()
    embed = _embed("Starboard", guild)
    channel = guild.get_channel(int(c["channel_id"])) if c.get("channel_id") else None
    embed.add_field(name="Status", value="Enabled" if c["enabled"] and channel else "Disabled", inline=True)
    embed.add_field(name="Channel", value=channel.mention if channel else "Not set — use `/starboard setup`", inline=True)
    embed.add_field(name="Needs", value=f"{c['threshold']} × {c['emoji']}", inline=True)
    embed.add_field(name="Own reaction counts", value="Yes" if c["self_star"] else "No", inline=True)
    embed.add_field(name="Bot messages", value="Yes" if c["bots"] else "No", inline=True)
    embed.add_field(name="On the board", value=str(len(starboard_store.load().get("posts", {}))), inline=True)
    ignored = [guild.get_channel(int(i)) for i in c["ignored_channels"]]
    embed.add_field(name="Ignored channels", value=", ".join(ch.mention for ch in ignored if ch) or "None", inline=False)
    if channel:
        missing = _missing_perms(channel, guild.me, "view_channel", "send_messages", "embed_links", "read_message_history")
        if missing:
            embed.add_field(name="Missing permissions in the starboard channel", value=", ".join(missing), inline=False)
    return embed


async def create_starboard_channel(guild: disnake.Guild, by: str, emoji: str, threshold: int) -> disnake.TextChannel:
    return await guild.create_text_channel(
        "starboard", reason=f"Starboard set up by {by}",
        topic=f"The best messages of the server: anything with {threshold}+ {emoji} reactions lands here.",
        overwrites={
            guild.default_role: disnake.PermissionOverwrite(send_messages=False, add_reactions=True),
            guild.me: disnake.PermissionOverwrite(view_channel=True, send_messages=True, embed_links=True, read_message_history=True),
        })


# =============================================================================== server stats

def stats_config() -> dict:
    return {**serverstats_store.default["config"], **serverstats_store.load().get("config", {})}


def _counter_value(kind: str, guild: disnake.Guild, bot: commands.InteractionBot) -> str:
    if kind == "members":
        return f"{guild.member_count or len(guild.members):,}"
    if kind in ("humans", "bots"):
        if not bot.intents.members:
            return "?"
        return f"{sum(1 for m in guild.members if m.bot == (kind == 'bots')):,}"
    if kind == "boosts":
        return str(guild.premium_subscription_count or 0)
    if kind == "boost_level":
        return str(guild.premium_tier)
    if kind == "channels":
        return str(len(guild.text_channels) + len(guild.voice_channels))
    if kind == "roles":
        return str(len(guild.roles) - 1)
    if kind == "tickets":
        return str(open_ticket_count())
    return "?"


def _counter_name(counter: dict, guild: disnake.Guild, bot: commands.InteractionBot) -> str:
    template = counter.get("template") or COUNTERS[counter["type"]][0]
    return template.replace("{value}", _counter_value(counter["type"], guild, bot))[:100]


def _locked_overwrites(guild: disnake.Guild) -> dict:
    return {
        guild.default_role: disnake.PermissionOverwrite(view_channel=True, connect=False),
        guild.me: disnake.PermissionOverwrite(view_channel=True, connect=True, manage_channels=True),
    }


async def refresh_stats(bot: commands.InteractionBot, guild: disnake.Guild | None = None) -> int:
    config = stats_config()
    gid = bf.hooks.guild_id
    guild = guild or (bot.get_guild(gid) if gid else None)
    if not config["enabled"] or not guild:
        return 0
    renamed = 0
    for counter in config["counters"]:
        channel = guild.get_channel(int(counter["channel_id"])) if counter.get("channel_id") else None
        if not channel:
            continue
        name = _counter_name(counter, guild, bot)
        if channel.name != name:
            try:
                await channel.edit(name=name, reason="Server stats")
                renamed += 1
            except disnake.HTTPException as exc:
                log.warning("Could not rename the stats channel %s: %s", channel.id, exc)
    return renamed


async def _stats_loop(bot: commands.InteractionBot) -> None:
    await asyncio.sleep(20)
    while True:
        try:
            await refresh_stats(bot)
        except Exception:
            log.exception("Server stats update failed")
        await asyncio.sleep(STATS_INTERVAL)


async def _create_counter(guild: disnake.Guild, category: disnake.CategoryChannel, kind: str, template: str | None,
                          bot: commands.InteractionBot) -> dict:
    counter = {"type": kind, "template": template or COUNTERS[kind][0]}
    channel = await guild.create_voice_channel(_counter_name(counter, guild, bot), category=category,
                                               overwrites=_locked_overwrites(guild), reason="Server stats")
    counter["channel_id"] = str(channel.id)
    return counter


def _stats_view_embed(guild: disnake.Guild, bot: commands.InteractionBot) -> disnake.Embed:
    c = stats_config()
    embed = _embed("Server stats", guild)
    category = guild.get_channel(int(c["category_id"])) if c.get("category_id") else None
    embed.add_field(name="Status", value="Enabled" if c["enabled"] and category else "Not set up — use `/serverstats setup`", inline=False)
    lines = []
    for counter in c["counters"]:
        ch = guild.get_channel(int(counter["channel_id"])) if counter.get("channel_id") else None
        lines.append(f"`{counter['type']}` → {ch.mention if ch else '*(channel missing)*'} · {_counter_name(counter, guild, bot)}")
    embed.add_field(name="Counters", value="\n".join(lines) or "None", inline=False)
    embed.add_field(name="Updates", value="Every 10 minutes (Discord allows only 2 renames per channel per 10 minutes).", inline=False)
    if not bot.intents.members:
        embed.add_field(name="Humans/Bots", value="Need the **Server Members Intent** in the Developer Portal.", inline=False)
    return embed


async def build_serverstats(guild: disnake.Guild, by: str, bot: commands.InteractionBot) -> list[dict]:
    category = await guild.create_category("Server Stats", overwrites=_locked_overwrites(guild), position=0,
                                           reason=f"Server stats set up by {by}")
    counters = []
    for kind in DEFAULT_COUNTERS:
        if kind in ("humans", "bots") and not bot.intents.members:
            continue
        counters.append(await _create_counter(guild, category, kind, None, bot))
    with serverstats_store.edit() as data:
        data["config"] = {"enabled": True, "category_id": str(category.id), "counters": counters}
    return counters


async def add_counter(guild: disnake.Guild, kind: str, template: str | None, bot: commands.InteractionBot) -> dict:
    config = stats_config()
    category = guild.get_channel(int(config["category_id"])) if config.get("category_id") else None
    if not isinstance(category, disnake.CategoryChannel):
        raise bf.BotActionError("Set up server stats first.")
    if kind not in COUNTERS:
        raise bf.BotActionError("Unknown counter.")
    if any(c["type"] == kind for c in config["counters"]):
        raise bf.BotActionError(f"There's already a {kind} counter.")
    if template and "{value}" not in template:
        template = f"{template.rstrip()} {{value}}"
    new = await _create_counter(guild, category, kind, template, bot)
    with serverstats_store.edit() as data:
        data.setdefault("config", {}).setdefault("counters", []).append(new)
    return new


async def remove_counter(guild: disnake.Guild, kind: str, by: str) -> bool:
    with serverstats_store.edit() as data:
        counters = data.setdefault("config", {}).setdefault("counters", [])
        found = next((c for c in counters if c["type"] == kind), None)
        if found:
            counters.remove(found)
    if not found:
        return False
    channel = guild.get_channel(int(found["channel_id"])) if found.get("channel_id") else None
    if channel:
        try:
            await channel.delete(reason=f"Server stats counter removed by {by}")
        except disnake.HTTPException:
            pass
    return True


async def delete_serverstats(guild: disnake.Guild, by: str) -> None:
    config = stats_config()
    for cid in [c.get("channel_id") for c in config["counters"]] + [config.get("category_id")]:
        channel = guild.get_channel(int(cid)) if cid else None
        if channel:
            try:
                await channel.delete(reason=f"Server stats removed by {by}")
            except disnake.HTTPException:
                pass
    with serverstats_store.edit() as data:
        data["config"] = {"enabled": False, "category_id": None, "counters": []}


# =============================================================================== admin panel (blocking, from Flask)

def offline_state() -> dict:
    return {
        "bot_online": False,
        "starboard": {"config": star_config(), "posts": len(starboard_store.load().get("posts", {}))},
        "serverstats": {"config": stats_config(), "counters": [{**c, "preview": None, "exists": None} for c in stats_config()["counters"]]},
        "counter_types": {k: {"template": v[0], "label": v[1]} for k, v in COUNTERS.items()},
        "text_channels": [],
        "members_intent": None,
    }


def panel_state() -> dict:
    if not bf.is_ready():
        return offline_state()

    async def _state():
        guild = bf._panel_guild()
        bot = bf._bot
        state = offline_state()
        state["bot_online"] = True
        state["members_intent"] = bool(bot.intents.members)  # pyright: ignore[reportOptionalMemberAccess]
        state["text_channels"] = [{"id": str(c.id), "name": c.name, "category": c.category.name if c.category else ""}
                                  for c in sorted(guild.text_channels, key=lambda c: ((c.category.position if c.category else -1), c.position))]
        state["serverstats"]["counters"] = [
            {**c, "exists": bool(c.get("channel_id") and guild.get_channel(int(c["channel_id"]))),
             "preview": _counter_name(c, guild, bot)} for c in stats_config()["counters"]]  # pyright: ignore[reportArgumentType]
        return state
    try:
        return bf._run(_state, timeout=8)
    except bf.BotActionError:
        return offline_state()


def save_starboard(config: dict) -> None:
    with starboard_store.edit() as data:
        data.setdefault("config", {}).update(config)


def save_serverstats(enabled: bool, templates: dict[str, str]) -> None:
    with serverstats_store.edit() as data:
        cfg = data.setdefault("config", {})
        cfg["enabled"] = enabled
        for counter in cfg.setdefault("counters", []):
            new = (templates.get(counter["type"]) or "").strip()[:90]
            if new:
                counter["template"] = new if "{value}" in new else f"{new} {{value}}"


def panel_setup_starboard(by: str, emoji: str, threshold: int) -> str:
    async def _go():
        channel = await create_starboard_channel(bf._panel_guild(), by, emoji, threshold)
        save_starboard(dict(enabled=True, channel_id=str(channel.id), emoji=emoji, threshold=threshold))
        return channel.name
    return bf._run(_go, timeout=15)


def panel_setup_serverstats(by: str) -> int:
    async def _go():
        guild = bf._panel_guild()
        config = stats_config()
        if config.get("category_id") and guild.get_channel(int(config["category_id"])):
            raise bf.BotActionError("Server stats are already set up.")
        return len(await build_serverstats(guild, by, bf._bot))  # pyright: ignore[reportArgumentType]
    return bf._run(_go, timeout=30)


def panel_add_counter(kind: str, template: str | None) -> None:
    async def _go():
        await add_counter(bf._panel_guild(), kind, template, bf._bot)  # pyright: ignore[reportArgumentType]
    bf._run(_go, timeout=15)


def panel_remove_counter(kind: str, by: str) -> bool:
    async def _go():
        return await remove_counter(bf._panel_guild(), kind, by)
    return bf._run(_go, timeout=15)


def panel_delete_serverstats(by: str) -> None:
    async def _go():
        await delete_serverstats(bf._panel_guild(), by)
    bf._run(_go, timeout=30)


def panel_refresh_serverstats() -> int:
    async def _go():
        return await refresh_stats(bf._bot, bf._panel_guild())  # pyright: ignore[reportArgumentType]
    return bf._run(_go, timeout=30)


# =============================================================================== registration

def register(bot: commands.InteractionBot, *, guild_ids, install, contexts) -> None:
    staff = dict(guild_ids=guild_ids, install_types=install, contexts=contexts,
                 default_member_permissions=disnake.Permissions(manage_guild=True))
    counter_choices = {f"{k} — {v[1]}"[:100]: k for k, v in COUNTERS.items()}

    @bot.listen("on_ready")
    async def _community_ready():
        _start("serverstats", lambda: _stats_loop(bot))

    @bot.listen("on_raw_reaction_add")
    async def _star_add(payload: disnake.RawReactionActionEvent):
        try:
            await _update_star(bot, payload)
        except Exception:
            log.exception("Starboard update failed")

    @bot.listen("on_raw_reaction_remove")
    async def _star_remove(payload: disnake.RawReactionActionEvent):
        try:
            await _update_star(bot, payload)
        except Exception:
            log.exception("Starboard update failed")

    @bot.listen("on_raw_message_delete")
    async def _star_source_deleted(payload: disnake.RawMessageDeleteEvent):
        try:
            await _forget_star(bot, payload.message_id)
        except Exception:
            log.exception("Starboard cleanup failed")

    # ------------------------------------------------ /starboard

    @bot.slash_command(name="starboard", description="Repost messages with enough reactions to a hall of fame channel", **staff)
    async def starboard_command(inter: disnake.ApplicationCommandInteraction):
        pass

    @starboard_command.sub_command(name="setup", description="Set up the starboard in one go (creates #starboard if you don't pick a channel)")
    async def starboard_setup(
        inter: disnake.ApplicationCommandInteraction,
        channel: disnake.TextChannel = commands.Param(default=None, description="Use an existing channel instead of creating one"),
        emoji: str = commands.Param(default="⭐", description="The reaction that counts (default: star)"),
        threshold: int = commands.Param(default=3, ge=1, le=100, description="How many reactions are needed (default 3)"),
    ):
        guild = await _staff_guild(inter, "starboard")
        if not guild:
            return
        await inter.response.defer(ephemeral=True)
        if channel is None:
            try:
                channel = await create_starboard_channel(guild, str(inter.author), emoji.strip(), threshold)
            except disnake.HTTPException as exc:
                await inter.followup.send(f"I couldn't create the channel: {exc}. Give me **Manage Channels** or pick a channel.", ephemeral=True)
                return
        save_starboard(dict(enabled=True, channel_id=str(channel.id), emoji=emoji.strip(), threshold=threshold))
        embed = _star_view_embed(guild)
        embed.title = "Starboard is ready"
        embed.description = f"Messages with **{threshold}** × {emoji.strip()} now appear in {channel.mention}."
        await inter.followup.send(embed=embed, ephemeral=True)

    @starboard_command.sub_command(name="settings", description="Change how the starboard works")
    async def starboard_settings(
        inter: disnake.ApplicationCommandInteraction,
        emoji: str = commands.Param(default=None, description="The reaction that counts"),
        threshold: int = commands.Param(default=None, ge=1, le=100, description="How many reactions are needed"),
        self_star: bool = commands.Param(default=None, description="Count the author's own reaction"),
        bots: bool = commands.Param(default=None, description="Allow bot messages on the board"),
        channel: disnake.TextChannel = commands.Param(default=None, description="Move the board to another channel"),
    ):
        guild = await _staff_guild(inter, "starboard")
        if not guild:
            return
        changes = {k: v for k, v in dict(emoji=emoji.strip() if emoji else None, threshold=threshold, self_star=self_star,
                                          bots=bots, channel_id=str(channel.id) if channel else None).items() if v is not None}
        save_starboard(changes)
        embed = _star_view_embed(guild)
        embed.title = "Starboard updated" if changes else "Starboard (nothing changed)"
        await inter.response.send_message(embed=embed, ephemeral=True)

    @starboard_command.sub_command(name="ignore", description="Ignore a channel (or stop ignoring it)")
    async def starboard_ignore(
        inter: disnake.ApplicationCommandInteraction,
        channel: disnake.abc.GuildChannel = commands.Param(description="Channel whose messages never go on the board"),
    ):
        guild = await _staff_guild(inter, "starboard")
        if not guild:
            return
        with starboard_store.edit() as data:
            ignored = [str(i) for i in data.setdefault("config", {}).get("ignored_channels", [])]
            if str(channel.id) in ignored:
                ignored.remove(str(channel.id))
                text = f"{channel.mention} is no longer ignored."
            else:
                ignored.append(str(channel.id))
                text = f"Messages in {channel.mention} won't go on the starboard."
            data["config"]["ignored_channels"] = ignored
        await inter.response.send_message(text, ephemeral=True)

    @starboard_command.sub_command(name="view", description="Show the starboard settings")
    async def starboard_view(inter: disnake.ApplicationCommandInteraction):
        guild = await _staff_guild(inter, "starboard")
        if guild:
            await inter.response.send_message(embed=_star_view_embed(guild), ephemeral=True)

    @starboard_command.sub_command(name="enable", description="Turn the starboard on")
    async def starboard_enable(inter: disnake.ApplicationCommandInteraction):
        if await _staff_guild(inter, "starboard"):
            save_starboard({"enabled": True})
            await inter.response.send_message("Starboard enabled.", ephemeral=True)

    @starboard_command.sub_command(name="disable", description="Turn the starboard off (the posts stay)")
    async def starboard_disable(inter: disnake.ApplicationCommandInteraction):
        if await _staff_guild(inter, "starboard"):
            save_starboard({"enabled": False})
            await inter.response.send_message("Starboard disabled. Existing posts stay where they are.", ephemeral=True)

    # ------------------------------------------------ /serverstats

    @bot.slash_command(name="serverstats", description="Live numbers in channel names: members, boosts, open tickets…", **staff)
    async def serverstats_command(inter: disnake.ApplicationCommandInteraction):
        pass

    @serverstats_command.sub_command(name="setup", description="Create the Server Stats category with the usual counters")
    async def serverstats_setup(inter: disnake.ApplicationCommandInteraction):
        guild = await _staff_guild(inter, "serverstats")
        if not guild:
            return
        config = stats_config()
        if config.get("category_id") and guild.get_channel(int(config["category_id"])):
            await inter.response.send_message("Server stats are already set up. Use `/serverstats add` for more counters, "
                                              "or `/serverstats delete` to start over.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)
        try:
            await build_serverstats(guild, str(inter.author), bot)
        except disnake.HTTPException as exc:
            await inter.followup.send(f"I couldn't create the channels: {exc}. I need **Manage Channels**.", ephemeral=True)
            return
        embed = _stats_view_embed(guild, bot)
        embed.title = "Server stats are ready"
        embed.description = "Members see the numbers but can't join these channels. Add more with `/serverstats add`."
        await inter.followup.send(embed=embed, ephemeral=True)

    @serverstats_command.sub_command(name="add", description="Add a counter")
    async def serverstats_add(
        inter: disnake.ApplicationCommandInteraction,
        counter: str = commands.Param(choices=counter_choices, description="What to count"),
        name: str = commands.Param(default=None, description="Channel name, {value} = the number, e.g. 'Operators: {value}'"),
    ):
        guild = await _staff_guild(inter, "serverstats")
        if not guild:
            return
        await inter.response.defer(ephemeral=True)
        try:
            new = await add_counter(guild, counter, name, bot)
        except bf.BotActionError as exc:
            await inter.followup.send(f"{exc} (`/serverstats setup` creates the category; `/serverstats rename` changes a name.)", ephemeral=True)
            return
        except disnake.HTTPException as exc:
            await inter.followup.send(f"I couldn't create the channel: {exc}", ephemeral=True)
            return
        await inter.followup.send(f"Added <#{new['channel_id']}>.", ephemeral=True)

    @serverstats_command.sub_command(name="remove", description="Remove a counter and its channel")
    async def serverstats_remove(
        inter: disnake.ApplicationCommandInteraction,
        counter: str = commands.Param(choices=counter_choices, description="Which counter"),
    ):
        guild = await _staff_guild(inter, "serverstats")
        if not guild:
            return
        await inter.response.defer(ephemeral=True)
        if not await remove_counter(guild, counter, str(inter.author)):
            await inter.followup.send(f"There's no `{counter}` counter.", ephemeral=True)
            return
        await inter.followup.send(f"Removed the `{counter}` counter.", ephemeral=True)

    @serverstats_command.sub_command(name="rename", description="Change a counter's channel name")
    async def serverstats_rename(
        inter: disnake.ApplicationCommandInteraction,
        counter: str = commands.Param(choices=counter_choices, description="Which counter"),
        name: str = commands.Param(description="New name, {value} = the number, e.g. 'Operators: {value}'"),
    ):
        guild = await _staff_guild(inter, "serverstats")
        if not guild:
            return
        if not any(c["type"] == counter for c in stats_config()["counters"]):
            await inter.response.send_message(f"There's no `{counter}` counter. Add it with `/serverstats add`.", ephemeral=True)
            return
        save_serverstats(stats_config()["enabled"], {counter: name})
        await inter.response.defer(ephemeral=True)
        await refresh_stats(bot, guild)
        await inter.followup.send("Renamed. (If nothing changed, Discord's limit of 2 renames per 10 minutes kicked in; it'll update soon.)",
                                  ephemeral=True)

    @serverstats_command.sub_command(name="refresh", description="Update the numbers now")
    async def serverstats_refresh(inter: disnake.ApplicationCommandInteraction):
        guild = await _staff_guild(inter, "serverstats")
        if not guild:
            return
        await inter.response.defer(ephemeral=True)
        renamed = await refresh_stats(bot, guild)
        await inter.followup.send(f"Updated {renamed} channel{'s' if renamed != 1 else ''}. The rest were already up to date.", ephemeral=True)

    @serverstats_command.sub_command(name="view", description="Show the counters")
    async def serverstats_view(inter: disnake.ApplicationCommandInteraction):
        guild = await _staff_guild(inter, "serverstats")
        if guild:
            await inter.response.send_message(embed=_stats_view_embed(guild, bot), ephemeral=True)

    @serverstats_command.sub_command(name="delete", description="Remove all stats channels and the category")
    async def serverstats_delete(inter: disnake.ApplicationCommandInteraction):
        guild = await _staff_guild(inter, "serverstats")
        if not guild:
            return
        await inter.response.defer(ephemeral=True)
        await delete_serverstats(guild, str(inter.author))
        await inter.followup.send("Server stats removed.", ephemeral=True)
