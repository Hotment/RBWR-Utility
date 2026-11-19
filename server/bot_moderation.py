from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

import disnake
from disnake.ext import commands

import bot_features as bf

log = bf.log

NOTE_MAX_LENGTH = 1000
NOTES_PER_MEMBER = 50
MAX_TEMPBAN = timedelta(days=365)
MAX_LOCK = timedelta(days=7)
MAX_SLOWMODE = 21600
PURGE_MAX = 100
PURGE_CONFIRM_ABOVE = 20 
PURGE_SCAN_LIMIT = 500

LOCK_PERMS = ("send_messages", "send_messages_in_threads", "create_public_threads", "create_private_threads")
TIMERS_SECONDS = 30

_timers_task: asyncio.Task | None = None
_cooldowns: dict[tuple[str, int], float] = {}


def _allowed(user, discord_perm: str, command: str) -> bool:
    return bf.staff_allowed(user, "moderation", discord_perm, command)


async def _deny(inter: disnake.Interaction, discord_perm: str) -> None:
    perm = discord_perm.replace("_", " ").title()
    await inter.response.send_message(
        f"You can't use this. Website admins need the **Moderation** permission in the admin panel; "
        f"everyone else needs **{perm}** on Discord.", ephemeral=True)


def _cooldown_left(name: str, user_id: int, seconds: float) -> float:
    now = time.monotonic()
    left = _cooldowns.get((name, user_id), 0) - now
    if left > 0:
        return left
    _cooldowns[(name, user_id)] = now + seconds
    if len(_cooldowns) > 5000:
        for key in [k for k, until in _cooldowns.items() if until < now]:
            _cooldowns.pop(key, None)
    return 0


def _ts(iso: str | None) -> int:
    parsed = bf._parse_time(iso)
    return int(parsed.timestamp()) if parsed else int(time.time())


# ---------------------------------------------------------------- notes, history, temporary bans, locks

def member_history(user_id) -> list[dict]:
    return [h for h in bf.modstate_store.load().get("history", []) if h.get("user_id") == str(user_id)]


def member_notes(user_id) -> list[dict]:
    return [n for n in bf.modstate_store.load().get("notes", []) if n.get("user_id") == str(user_id)]


def _notes_text(notes: list[dict]) -> str:
    return "\n".join(f"`#{n['id']}` <t:{_ts(n.get('at'))}:d> **{n.get('by', '?')}:** {n['text'][:150]}"
                     for n in notes)[:1024] or "None"


def add_note(user: disnake.abc.User, text: str, author: disnake.abc.User) -> dict:
    with bf.modstate_store.edit() as data:
        notes = data.setdefault("notes", [])
        if sum(n.get("user_id") == str(user.id) for n in notes) >= NOTES_PER_MEMBER:
            raise bf.BotActionError(f"{getattr(user, 'display_name', user)} already has {NOTES_PER_MEMBER} notes. Remove old ones first.")
        data["last_note_id"] = data.get("last_note_id", 0) + 1
        note = {"id": data["last_note_id"], "user_id": str(user.id), "user_name": getattr(user, "display_name", str(user)),
                "text": text[:NOTE_MAX_LENGTH], "by": getattr(author, "display_name", str(author)),
                "by_id": str(author.id), "at": bf.utc_now()}
        notes.append(note)
        return note


def remove_note(note_id: int) -> dict | None:
    with bf.modstate_store.edit() as data:
        notes = data.setdefault("notes", [])
        note = next((n for n in notes if n.get("id") == note_id), None)
        if note:
            notes.remove(note)
        return note


def tempban_of(user_id) -> dict | None:
    return bf.modstate_store.load().get("tempbans", {}).get(str(user_id))


def clear_tempban(user_id) -> None:
    with bf.modstate_store.edit() as data:
        data.setdefault("tempbans", {}).pop(str(user_id), None)


async def _lock_channel(channel: disnake.TextChannel, actor: disnake.abc.User, until: datetime | None,
                        reason: str | None) -> None:
    everyone = channel.guild.default_role
    overwrite = channel.overwrites_for(everyone)
    previous = {p: getattr(overwrite, p) for p in LOCK_PERMS}
    note = "**This channel is locked by the moderators**" + (
        f" until <t:{int(until.timestamp())}:t> (<t:{int(until.timestamp())}:R>)" if until else "") + "."
    if reason:
        note += f"\n**Reason:** {reason}"

    try:
        await channel.send(note, allowed_mentions=disnake.AllowedMentions.none())
    except disnake.HTTPException:
        pass
    for p in LOCK_PERMS:
        setattr(overwrite, p, False)
    await channel.set_permissions(everyone, overwrite=overwrite, reason=f"{actor} (via /lock): {reason or 'no reason given'}"[:512])
    with bf.modstate_store.edit() as data:
        data.setdefault("locks", {})[str(channel.id)] = {
            "guild_id": str(channel.guild.id), "previous": previous, "by": str(actor), "by_id": str(actor.id),
            "reason": (reason or "")[:400], "at": bf.utc_now(), "until": until.isoformat() if until else None,
        }


async def _unlock_channel(channel: disnake.TextChannel, actor: str) -> bool:
    lock = bf.modstate_store.load().get("locks", {}).get(str(channel.id))
    if not lock:
        return False
    everyone = channel.guild.default_role
    overwrite = channel.overwrites_for(everyone)
    for p, value in (lock.get("previous") or {}).items():
        if p in LOCK_PERMS:
            setattr(overwrite, p, value)
    await channel.set_permissions(everyone, overwrite=None if overwrite.is_empty() else overwrite,
                                  reason=f"{actor}: channel unlocked"[:512])
    with bf.modstate_store.edit() as data:
        data.setdefault("locks", {}).pop(str(channel.id), None)
    try:
        await channel.send("**This channel is unlocked.** You can write again.", allowed_mentions=disnake.AllowedMentions.none())
    except disnake.HTTPException:
        pass
    return True


async def _run_timers() -> None:
    now = datetime.now(timezone.utc)
    state = bf.modstate_store.load()
    for user_id, ban in list(state.get("tempbans", {}).items()):
        until = bf._parse_time(ban.get("until"))
        if not until or until > now:
            continue
        gid = int(ban.get("guild_id") or bf.hooks.guild_id or 0)
        guild = bf._bot.get_guild(gid) if bf._bot and gid else None
        if not guild:
            continue
        try:
            await guild.unban(disnake.Object(int(user_id)), reason="Temporary ban expired")
        except disnake.NotFound:
            pass
        except disnake.HTTPException as exc:
            log.warning("Could not lift the temporary ban of %s: %s", user_id, exc)
            continue
        clear_tempban(user_id)
        await bf._log_mod_action("Automatic (temporary ban expired)", disnake.Object(int(user_id)), "unbanned", ban.get("reason"))
    for channel_id, lock in list(state.get("locks", {}).items()):
        until = bf._parse_time(lock.get("until"))
        if not until or until > now:
            continue
        channel = await bf._get_channel(int(channel_id))
        if not isinstance(channel, disnake.TextChannel):
            with bf.modstate_store.edit() as data:
                data.setdefault("locks", {}).pop(channel_id, None)
            continue
        try:
            await _unlock_channel(channel, "Automatic (lock expired)")
        except disnake.HTTPException as exc:
            log.warning("Could not unlock channel %s: %s", channel_id, exc)


async def _timers_loop() -> None:
    while True:
        try:
            await _run_timers()
        except Exception:
            log.exception("Moderation timers failed")
        await asyncio.sleep(TIMERS_SECONDS)


def _start_timers() -> None:
    global _timers_task
    if _timers_task and not _timers_task.done():
        return
    _timers_task = asyncio.create_task(_timers_loop())
    _timers_task.add_done_callback(bf._log_future_error)


def user_summary_embed(user: disnake.abc.User, title: str) -> disnake.Embed:
    member = user if isinstance(user, disnake.Member) else None
    embed = disnake.Embed(title=f"{title} — {getattr(user, 'display_name', user)}"[:256], color=bf.BRAND)
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="User", value=f"{user.mention} (`{user}`)", inline=True)
    embed.add_field(name="ID", value=f"`{user.id}`", inline=True)
    embed.add_field(name="Account Created", value=f"<t:{int(user.created_at.timestamp())}:R>", inline=True)
    if member:
        if member.joined_at:
            embed.add_field(name="Joined Server", value=f"<t:{int(member.joined_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Nickname", value=member.nick or "—", inline=True)
        timeout = member.current_timeout
        embed.add_field(name="Timeout", value=f"Until <t:{int(timeout.timestamp())}:R>" if timeout else "None", inline=True)
        roles = [r.mention for r in reversed(member.roles) if not r.is_default()]
        embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles[:15])[:1024] or "—", inline=False)
    else:
        embed.add_field(name="Member", value="Not in the server", inline=True)
    ban = tempban_of(user.id)
    if ban:
        embed.add_field(name="Temporary Ban", value=f"Until <t:{_ts(ban.get('until'))}:f>", inline=True)
    warnings = bf.active_warnings(user.id)
    embed.add_field(
        name=f"Active Warnings ({len(warnings)})",
        value="\n".join(f"`#{w['id']}` <t:{_ts(w.get('at'))}:d> {w['reason'][:80]}" for w in warnings[-5:])[:1024] or "None",
        inline=False,
    )
    notes = member_notes(user.id)
    embed.add_field(name=f"Moderator Notes ({len(notes)})", value=_notes_text(notes[-5:]), inline=False)
    embed.set_footer(text=f"{bf.FOOTER} • Moderation — only visible to you")
    return embed


class _ConfirmView(disnake.ui.View):

    def __init__(self, author_id: int, confirm_label: str):
        super().__init__(timeout=30)
        self.author_id, self.value = author_id, None
        self.children[0].label = confirm_label  # pyright: ignore[reportAttributeAccessIssue]

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        if inter.author.id != self.author_id:
            await inter.response.send_message("This isn't your confirmation.", ephemeral=True)
            return False
        return True

    @disnake.ui.button(label="Confirm", style=disnake.ButtonStyle.danger)
    async def confirm(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        self.value = True
        await inter.response.edit_message(content="Working on it…", view=None)
        self.stop()

    @disnake.ui.button(label="Cancel", style=disnake.ButtonStyle.secondary)
    async def cancel(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        self.value = False
        await inter.response.edit_message(content="Cancelled.", view=None)
        self.stop()


def _bot_missing(channel, *perms: str) -> str | None:
    have = channel.permissions_for(channel.guild.me)
    return next((p for p in perms if not (have.administrator or getattr(have, p))), None)


# ---------------------------------------------------------------- commands

def register(bot: commands.InteractionBot, *, guild_ids, install, contexts) -> None:
    staff = dict(guild_ids=guild_ids, install_types=install, contexts=contexts)

    @bot.listen("on_ready")
    async def _moderation_ready():
        _start_timers()

    @bot.listen("on_member_unban")
    async def _moderation_unbanned(guild: disnake.Guild, user: disnake.User):
        if tempban_of(user.id):
            clear_tempban(user.id)

    # ------------------------------------------------ members

    @bot.slash_command(name="nick", description="Change a member's server nickname (leave it empty to reset it)",
                       default_member_permissions=disnake.Permissions(manage_nicknames=True), **staff)
    async def nick_command(
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member = commands.Param(description="Whose nickname to change"),
        nickname: str = commands.Param(default=None, max_length=32, description="New nickname (leave empty to reset)"),
        reason: str = commands.Param(default=None, max_length=400, description="Reason (shown in the audit log)"),
    ):
        if not _allowed(inter.author, "manage_nicknames", "nick"):
            await _deny(inter, "manage_nicknames")
            return
        if not isinstance(member, disnake.Member):
            await inter.response.send_message("That user is not a member of this server.", ephemeral=True)
            return
        if member.id != inter.author.id:
            problem = bf._hierarchy_problem(inter.author, member)
            if problem:
                await inter.response.send_message(problem, ephemeral=True)
                return
        await inter.response.defer(ephemeral=True)
        try:
            text = await bf._run_mod_action(f"{inter.author} (via /nick)", inter.author.mention, member, "nick",
                                            {"nick": nickname or "", "reason": reason or ""})
        except disnake.Forbidden:
            await inter.followup.send("I'm missing the **Manage Nicknames** permission, or my role is below theirs "
                                      "(the server owner's nickname can't be changed by bots).", ephemeral=True)
            return
        await inter.followup.send(f"{member.mention} — {text}.", ephemeral=True, allowed_mentions=disnake.AllowedMentions.none())

    @bot.slash_command(name="tempban", description="Ban a member for a limited time (lifted automatically)",
                       default_member_permissions=disnake.Permissions(ban_members=True), **staff)
    async def tempban_command(
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member = commands.Param(description="Member to ban"),
        duration: str = commands.Param(description="How long: e.g. 12h, 3d, 2w (max 365d)", max_length=20),
        reason: str = commands.Param(default=None, description="Why — shown in the audit log and sent to them", max_length=400),
        delete_days: int = commands.Param(default=0, ge=0, le=7, description="Delete their messages from the last N days"),
    ):
        if not _allowed(inter.author, "ban_members", "tempban"):
            await _deny(inter, "ban_members")
            return
        if not isinstance(member, disnake.Member):
            await inter.response.send_message("That user is not a member of this server.", ephemeral=True)
            return
        problem = bf._hierarchy_problem(inter.author, member)
        if problem:
            await inter.response.send_message(problem, ephemeral=True)
            return
        delta = bf.parse_duration(duration)
        if not delta or delta < timedelta(minutes=1):
            await inter.response.send_message("Invalid duration — use e.g. 12h, 3d or 2w.", ephemeral=True)
            return
        if delta > MAX_TEMPBAN:
            await inter.response.send_message("A temporary ban can last at most 365 days — use a normal ban for longer.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)
        until = datetime.now(timezone.utc) + delta
        length = bf._format_duration(delta)
        await bf._dm_mod_notice(member, f"banned for {length}", reason)
        try:
            await member.ban(reason=f"{inter.author} (via /tempban {length}): {reason or 'no reason given'}"[:512],
                             clean_history_duration=timedelta(days=delete_days))
        except disnake.Forbidden:
            await inter.followup.send("I'm missing the **Ban Members** permission (or my role is too low).", ephemeral=True)
            return
        with bf.modstate_store.edit() as data:
            data.setdefault("tempbans", {})[str(member.id)] = {
                "guild_id": str(member.guild.id), "until": until.isoformat(), "reason": (reason or "")[:400],
                "by": str(inter.author), "by_id": str(inter.author.id), "name": str(member), "at": bf.utc_now(),
            }
        text = f"banned for {length} (until <t:{int(until.timestamp())}:f>)"
        await bf._log_mod_action(inter.author.mention, member, text, reason)
        await inter.followup.send(f"{member.mention} — {text}.", ephemeral=True, allowed_mentions=disnake.AllowedMentions.none())

    @bot.slash_command(name="note", description="Private moderator notes about a member",
                       default_member_permissions=disnake.Permissions(moderate_members=True), **staff)
    async def note_command(inter: disnake.ApplicationCommandInteraction):
        pass

    @note_command.sub_command(name="add", description="Add a private note (only moderators see it, in /modlog and User info)")
    async def note_add(
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.User = commands.Param(description="Who the note is about"),
        text: str = commands.Param(description="The note", max_length=NOTE_MAX_LENGTH),
    ):
        if not _allowed(inter.author, "moderate_members", "note"):
            await _deny(inter, "moderate_members")
            return
        if member.bot:
            await inter.response.send_message("Notes are for members, not bots.", ephemeral=True)
            return
        try:
            note = add_note(member, text.strip(), inter.author)
        except bf.BotActionError as exc:
            await inter.response.send_message(str(exc), ephemeral=True)
            return
        bf.record_mod_history(member.id, inter.author.mention, f"note #{note['id']} added", None)
        await inter.response.send_message(f"Note `#{note['id']}` saved for {member.mention}.", ephemeral=True,
                                          allowed_mentions=disnake.AllowedMentions.none())

    @note_command.sub_command(name="remove", description="Remove a note by its number (see /modlog)")
    async def note_remove(
        inter: disnake.ApplicationCommandInteraction,
        note: int = commands.Param(description="Note number, e.g. 4 for #4", ge=1),
    ):
        if not _allowed(inter.author, "moderate_members", "note"):
            await _deny(inter, "moderate_members")
            return
        removed = remove_note(note)
        if not removed:
            await inter.response.send_message(f"Note #{note} doesn't exist.", ephemeral=True)
            return
        bf.record_mod_history(removed["user_id"], inter.author.mention, f"note #{note} removed", None)
        await inter.response.send_message(f"Note #{note} about <@{removed['user_id']}> removed.", ephemeral=True,
                                          allowed_mentions=disnake.AllowedMentions.none())

    @bot.slash_command(name="modlog", description="A member's full moderation history: actions, warnings and notes",
                       default_member_permissions=disnake.Permissions(moderate_members=True), **staff)
    async def modlog_command(
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.User = commands.Param(description="Member (or the ID of someone who left)"),
    ):
        if not _allowed(inter.author, "moderate_members", "modlog"):
            await _deny(inter, "moderate_members")
            return
        embed = user_summary_embed(member, "Mod Log")
        history = member_history(member.id)
        lines = []
        for h in reversed(history):
            line = (f"<t:{_ts(h.get('at'))}:d> **{h['text']}** — {h['actor']}"
                    + (f"\n  ↳ {h['reason'][:100]}" if h.get("reason") else ""))
            if len("\n".join(lines + [line])) > 1000:
                break
            lines.append(line)
        more = len(history) - len(lines)
        embed.add_field(name=f"Actions ({len(history)})",
                        value=("\n".join(lines) + (f"\n…and {more} older" if more > 0 else "")) if lines else "None",
                        inline=False)
        incidents = [i for i in bf.automod_store.load().get("incidents", []) if str(i.get("user_id")) == str(member.id)]
        if incidents:
            embed.add_field(name="Automod", value=f"{len(incidents)} incident(s)", inline=False)
        await inter.response.send_message(embed=embed, ephemeral=True)

    @bot.user_command(name="User info", default_member_permissions=disnake.Permissions(moderate_members=True), **staff)
    async def userinfo_menu(inter: disnake.UserCommandInteraction, user: disnake.User):
        if not _allowed(inter.author, "moderate_members", "userinfo"):
            await _deny(inter, "moderate_members")
            return
        await inter.response.send_message(embed=user_summary_embed(user, "User Info"), ephemeral=True)

    # ------------------------------------------------ channels

    @bot.slash_command(name="purge", description="Delete recent messages in this channel",
                       default_member_permissions=disnake.Permissions(manage_messages=True), **staff)
    async def purge_command(
        inter: disnake.ApplicationCommandInteraction,
        amount: int = commands.Param(description=f"How many messages to delete (1-{PURGE_MAX})", ge=1, le=PURGE_MAX),
        member: disnake.User = commands.Param(default=None, description="Only messages from this member"),
        contains: str = commands.Param(default=None, description="Only messages containing this text", max_length=100),
        include_pinned: bool = commands.Param(default=False, description="Also delete pinned messages"),
    ):
        if not _allowed(inter.author, "manage_messages", "purge"):
            await _deny(inter, "manage_messages")
            return
        channel = inter.channel
        if not hasattr(channel, "purge") or not inter.guild:
            await inter.response.send_message("Messages can't be purged here.", ephemeral=True)
            return
        missing = _bot_missing(channel, "manage_messages", "read_message_history")
        if missing:
            await inter.response.send_message(f"I'm missing the **{missing.replace('_', ' ').title()}** permission in this channel.", ephemeral=True)
            return
        if member and member.id != inter.author.id:
            target = inter.guild.get_member(member.id)
            problem = bf._hierarchy_problem(inter.author, target) if target else None
            if problem:
                await inter.response.send_message(problem, ephemeral=True)
                return
        left = _cooldown_left("purge", inter.author.id, 5)
        if left:
            await inter.response.send_message(f"Wait {left:.0f}s before purging again.", ephemeral=True)
            return

        what = f"{amount} message{'s' if amount != 1 else ''}" + (f" from {member.mention}" if member else "") \
            + (f" containing “{contains}”" if contains else "")
        if amount > PURGE_CONFIRM_ABOVE:
            view = _ConfirmView(inter.author.id, f"Delete {amount}")
            await inter.response.send_message(f"Delete up to {what} in {channel.mention}? This can't be undone.",  # pyright: ignore[reportAttributeAccessIssue]
                                              view=view, ephemeral=True, allowed_mentions=disnake.AllowedMentions.none())
            if await view.wait() or not view.value:
                if view.value is None:
                    await inter.edit_original_response(content="Timed out — nothing was deleted.", view=None)
                return
        else:
            await inter.response.defer(ephemeral=True)

        needle = (contains or "").lower()
        matched = 0

        def check(message: disnake.Message) -> bool:
            nonlocal matched
            if matched >= amount:
                return False
            if message.pinned and not include_pinned:
                return False
            if member and message.author.id != member.id:
                return False
            if needle and needle not in (message.content or "").lower():
                return False
            matched += 1
            return True

        filtered = bool(member or contains or not include_pinned)
        try:
            deleted = await channel.purge(limit=PURGE_SCAN_LIMIT if filtered else amount, check=check, bulk=True,  # pyright: ignore[reportAttributeAccessIssue]
                                          oldest_first=False,
                                          after=datetime.now(timezone.utc) - timedelta(days=14) + timedelta(minutes=1))
        except disnake.Forbidden:
            await inter.edit_original_response(content="I'm missing the permission to delete messages here.", view=None)
            return
        except disnake.HTTPException as exc:
            await inter.edit_original_response(content=f"Discord refused: {exc.text or exc}", view=None)
            return
        result = f"purged {len(deleted)} message{'s' if len(deleted) != 1 else ''} in #{getattr(channel, 'name', 'channel')}"
        await bf._log_mod_action(inter.author.mention, member or inter.author, result,
                                 f"Filters: {what}" if (member or contains) else None)
        await inter.edit_original_response(
            content=f"Deleted {len(deleted)} message{'s' if len(deleted) != 1 else ''}."
                    + (" (Only messages from the last 14 days can be purged.)" if len(deleted) < amount else ""),
            view=None, allowed_mentions=disnake.AllowedMentions.none())

    @bot.slash_command(name="slowmode", description="Set how often members can post in a channel",
                       default_member_permissions=disnake.Permissions(manage_channels=True), **staff)
    async def slowmode_command(
        inter: disnake.ApplicationCommandInteraction,
        delay: str = commands.Param(description="e.g. 5s, 30s, 2m, 1h (max 6h) — or off", max_length=20),
        channel: disnake.TextChannel = commands.Param(default=None, description="Which channel (defaults to this one)"),
    ):
        if not _allowed(inter.author, "manage_channels", "slowmode"):
            await _deny(inter, "manage_channels")
            return
        target = channel or inter.channel
        if not isinstance(target, (disnake.TextChannel, disnake.Thread)):
            await inter.response.send_message("Slowmode works in text channels and threads.", ephemeral=True)
            return
        spec = delay.strip().lower()
        if spec in ("off", "0", "none", "0s"):
            seconds = 0
        else:
            parsed = bf.parse_duration(spec if not spec.isdigit() else spec + "s")
            if not parsed:
                await inter.response.send_message("Invalid delay — use e.g. 10s, 2m or 1h, or `off`.", ephemeral=True)
                return
            seconds = int(parsed.total_seconds())
            if seconds > MAX_SLOWMODE:
                await inter.response.send_message("Discord allows a slowmode of at most 6 hours.", ephemeral=True)
                return
        if _bot_missing(target, "manage_channels"):
            await inter.response.send_message(f"I'm missing the **Manage Channels** permission in {target.mention}.", ephemeral=True)
            return
        try:
            await target.edit(slowmode_delay=seconds, reason=f"{inter.author} (via /slowmode)"[:512])
        except disnake.HTTPException as exc:
            await inter.response.send_message(f"Discord refused: {exc.text or exc}", ephemeral=True)
            return
        length = bf._format_duration(timedelta(seconds=seconds))
        text = f"slowmode in #{target.name} " + (f"set to {length}" if seconds else "turned off")
        await bf._log_mod_action(inter.author.mention, inter.author, text, None)
        await inter.response.send_message(f"Slowmode in {target.mention} " + (f"set to **{length}**." if seconds else "turned **off**."),
                                          ephemeral=True)

    @bot.slash_command(name="lock", description="Stop everyone from writing in a channel (optionally for a while)",
                       default_member_permissions=disnake.Permissions(manage_channels=True), **staff)
    async def lock_command(
        inter: disnake.ApplicationCommandInteraction,
        channel: disnake.TextChannel = commands.Param(default=None, description="Which channel (defaults to this one)"),
        duration: str = commands.Param(default=None, description="Unlock automatically after e.g. 30m, 2h, 1d (max 7d)", max_length=20),
        reason: str = commands.Param(default=None, description="Shown in the channel", max_length=300),
    ):
        if not _allowed(inter.author, "manage_channels", "lock"):
            await _deny(inter, "manage_channels")
            return
        target = channel or inter.channel
        if not isinstance(target, disnake.TextChannel):
            await inter.response.send_message("Only text channels can be locked.", ephemeral=True)
            return
        if str(target.id) in bf.modstate_store.load().get("locks", {}):
            await inter.response.send_message(f"{target.mention} is already locked. Use `/unlock` first.", ephemeral=True)
            return
        until = None
        if duration:
            delta = bf.parse_duration(duration)
            if not delta or delta < timedelta(minutes=1) or delta > MAX_LOCK:
                await inter.response.send_message("Invalid duration — use e.g. 30m, 2h or 1d (at most 7 days).", ephemeral=True)
                return
            until = datetime.now(timezone.utc) + delta
        if _bot_missing(target, "manage_roles", "manage_channels"):
            await inter.response.send_message(f"I need **Manage Permissions** and **Manage Channels** in {target.mention}.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)
        try:
            await _lock_channel(target, inter.author, until, reason)
        except disnake.HTTPException as exc:
            await inter.followup.send(f"Couldn't lock it: {exc.text or exc}", ephemeral=True)
            return
        text = f"locked #{target.name}" + (f" until <t:{int(until.timestamp())}:f>" if until else "")
        await bf._log_mod_action(inter.author.mention, inter.author, text, reason)
        await inter.followup.send(f"{target.mention} is locked" + (f" until <t:{int(until.timestamp())}:t>." if until else ". Use `/unlock` to open it."),
                                  ephemeral=True)

    @bot.slash_command(name="unlock", description="Let everyone write in a channel locked with /lock again",
                       default_member_permissions=disnake.Permissions(manage_channels=True), **staff)
    async def unlock_command(
        inter: disnake.ApplicationCommandInteraction,
        channel: disnake.TextChannel = commands.Param(default=None, description="Which channel (defaults to this one)"),
    ):
        if not _allowed(inter.author, "manage_channels", "lock"):
            await _deny(inter, "manage_channels")
            return
        target = channel or inter.channel
        if not isinstance(target, disnake.TextChannel):
            await inter.response.send_message("Only text channels can be unlocked.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)
        try:
            unlocked = await _unlock_channel(target, f"{inter.author} (via /unlock)")
        except disnake.HTTPException as exc:
            await inter.followup.send(f"Couldn't unlock it: {exc.text or exc}", ephemeral=True)
            return
        if not unlocked:
            await inter.followup.send(f"{target.mention} wasn't locked with `/lock`.", ephemeral=True)
            return
        await bf._log_mod_action(inter.author.mention, inter.author, f"unlocked #{target.name}", None)
        await inter.followup.send(f"{target.mention} is unlocked.", ephemeral=True)
