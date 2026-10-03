import asyncio
from datetime import datetime, timezone
import logging
import os
import threading
from typing import Any, Callable

import aiohttp
import disnake
from disnake.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
GUILD_ID = os.getenv("DISCORD_GUILD_ID", "1547514559097733141").strip()
TICKETS_CATEGORY_ID = os.getenv("DISCORD_TICKETS_CATEGORY_ID", "1547529007334162432").strip()
SUGGESTIONS_DISCUSSION_CHANNEL_ID = int(os.getenv("DISCORD_SUGGESTIONS_DISCUSSION_CHANNEL_ID", "1555617766827098192").strip())
BUGS_DISCUSSION_CHANNEL_ID = int(os.getenv("DISCORD_BUGS_DISCUSSION_CHANNEL_ID", "1555618312333951066").strip())

DEFAULT_SERVER_BASE_URL = os.getenv("SERVER_BASE_URL", "https://rbwr.hotment.dev").rstrip("/")
RBWR_API_URL = os.getenv("RBWR_API_URL", f"{DEFAULT_SERVER_BASE_URL}/api/public-servers")

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("rbwr-bot")

INFO_ALIASES = {
    "aprm": "APRM", "rtp": "RTP", "xenon": "Xenon",
    "reactor_temp": "Reactor Temp", "temperature": "Reactor Temp",
    "outputmw": "Output (MW)", "recirc1": "Recirc1", "recirc2": "Recirc2",
    "rpm": "Turbine RPM", "pps": "PointsPerSecond",
    "demandtimeleft": "Demand Time Left", "scramreason": "SCRAMreason",
}

INFO_CHOICES = [
    disnake.OptionChoice(name="APRM", value="aprm"),
    disnake.OptionChoice(name="RTP", value="rtp"),
    disnake.OptionChoice(name="Xenon", value="xenon"),
    disnake.OptionChoice(name="Reactor Temperature", value="reactor_temp"),
    disnake.OptionChoice(name="Output (MW)", value="outputmw"),
    disnake.OptionChoice(name="Recirc 1", value="recirc1"),
    disnake.OptionChoice(name="Recirc 2", value="recirc2"),
    disnake.OptionChoice(name="Turbine RPM", value="rpm"),
    disnake.OptionChoice(name="Points / second", value="pps"),
    disnake.OptionChoice(name="Demand Time Left", value="demandtimeleft"),
    disnake.OptionChoice(name="SCRAM reason", value="scramreason"),
    disnake.OptionChoice(name="ALL", value="all"),
]

def is_server_public(server: dict[str, Any]) -> bool:
    """
    Returns True only if the server is confirmed to be public.
    Filters out private/VIP servers based on is_private flags,
    privateServerOwnerId, or internal state metadata.
    """
    if not isinstance(server, dict):
        return False

    if server.get("is_private") is True:
        return False
    if server.get("IsPrivate") is True:
        return False

    owner_id = server.get("privateServerOwnerId")
    if owner_id not in (None, "", 0, "None", "null", False):
        return False

    st = server.get("state")
    if isinstance(st, dict):
        if st.get("IsPrivate") is True:
            return False

    return True

class RBWRClient:
    def __init__(
        self,
        api_url: str | None = None,
        data_supplier: Callable[[bool], dict[str, Any]] | None = None,
    ):
        self.api_url = api_url or RBWR_API_URL
        self.data_supplier = data_supplier
        self.session: aiohttp.ClientSession | None = None
        self.cache: dict[str, Any] | None = None

    def start(self) -> bool:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers={
                "User-Agent": "RBWR-Discord-Bot/1.0",
                "Accept": "application/json",
            })
        return True

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def fetch(self, public_only: bool = True) -> dict[str, Any]:
        if self.data_supplier is not None:
            try:
                res = self.data_supplier(public_only)
                if isinstance(res, dict):
                    servers = res.get("data", {}).get("servers", [])
                    if public_only and isinstance(servers, list):
                        res = dict(res, data=dict(res.get("data", {}), servers=[s for s in servers if is_server_public(s)]))
                    self.cache = res
                    return res
            except Exception as ex:
                log.warning(f"[RBWRClient] Direct server data supplier failed, falling back to HTTP: {ex}")

        if self.session is None or self.session.closed:
            self.start()

        session = self.session
        if session is None:
            raise RuntimeError("Failed to start RBWR HTTP client session")

        last_error = None
        params = {"public_only": "true"} if public_only else None
        try:
            async with session.get(self.api_url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    if isinstance(data, dict):
                        servers = data.get("data", {}).get("servers", [])
                        if public_only and isinstance(servers, list):
                            filtered = [s for s in servers if is_server_public(s)]
                            data["data"] = dict(data.get("data", {}), servers=filtered)
                        self.cache = data
                        return data
                last_error = f"HTTP {r.status}"
        except Exception as e:
            last_error = str(e)

        if self.cache is not None:
            if public_only:
                cached_copy = dict(self.cache)
                raw_servers = cached_copy.get("data", {}).get("servers", [])
                if isinstance(raw_servers, list):
                    cached_copy["data"] = dict(cached_copy.get("data", {}), servers=[s for s in raw_servers if is_server_public(s)])
                return cached_copy
            return self.cache
        raise RuntimeError(f"Failed to fetch RBWR data from server API: {last_error}")

    @staticmethod
    def norm(value: str) -> str:
        return value.strip().lower().replace("-", "")

    @staticmethod
    def short_id(job_id: str) -> str:
        parts = [p for p in job_id.split("-") if p]
        return f"{parts[1]}-{parts[2]}" if len(parts) >= 3 else job_id

    async def find_server(self, server_id: str, public_only: bool = True) -> dict[str, Any] | None:
        payload = await self.fetch(public_only=public_only)
        servers = payload.get("data", {}).get("servers", [])
        wanted = self.norm(server_id)

        for server in servers:
            if public_only and not is_server_public(server):
                continue
            job_id = str(server.get("jobId", ""))
            if job_id and (
                self.norm(job_id) == wanted or
                self.norm(self.short_id(job_id)) == wanted
            ):
                return server
        return None

disnake_bot: commands.InteractionBot | None = None
disnake_bot_loop: asyncio.AbstractEventLoop | None = None

class TicketBridge:
    def __init__(self):
        self.load_suggestions: Callable[[], dict[str, Any]] | None = None
        self.save_suggestions: Callable[[dict[str, Any]], None] | None = None
        self.load_admins: Callable[[], dict[str, Any]] | None = None
        self.is_website_admin: Callable[[str], bool] | None = None
        self.broadcast_dashboard: Callable[[], None] | None = None
        self.broadcast_ticket_update: Callable[..., None] | None = None

    def is_configured(self) -> bool:
        return bool(self.load_suggestions and self.save_suggestions and self.is_website_admin)

ticket_bridge = TicketBridge()

def configure_ticket_bridge(
    load_suggestions: Callable[[], dict[str, Any]] | None = None,
    save_suggestions: Callable[[dict[str, Any]], None] | None = None,
    load_admins: Callable[[], dict[str, Any]] | None = None,
    is_website_admin: Callable[[str], bool] | None = None,
    broadcast_dashboard: Callable[[], None] | None = None,
    broadcast_ticket_update: Callable[..., None] | None = None,
):
    ticket_bridge.load_suggestions = load_suggestions
    ticket_bridge.save_suggestions = save_suggestions
    ticket_bridge.load_admins = load_admins
    ticket_bridge.is_website_admin = is_website_admin
    ticket_bridge.broadcast_dashboard = broadcast_dashboard
    ticket_bridge.broadcast_ticket_update = broadcast_ticket_update

def is_user_in_guild(discord_id: str | int | None) -> bool:
    """
    Checks if a Discord user is currently in the configured guild (GUILD_ID).
    Returns True if present, False otherwise.
    """
    global disnake_bot, disnake_bot_loop
    if not discord_id:
        return False
    try:
        uid = int(str(discord_id).strip())
    except (ValueError, TypeError):
        return False

    if not disnake_bot or not disnake_bot.is_ready() or not disnake_bot_loop or not disnake_bot_loop.is_running():
        return False

    bot_ref = disnake_bot

    async def _check():
        try:
            guild_id = int(GUILD_ID)
            guild = bot_ref.get_guild(guild_id)
            if not guild:
                guild = await bot_ref.fetch_guild(guild_id)
            if not guild:
                return False

            member = guild.get_member(uid)
            if member is not None:
                return True

            try:
                member = await guild.fetch_member(uid)
                return member is not None
            except disnake.NotFound:
                return False
            except Exception as e:
                log.warning(f"[Guild Check] fetch_member failed for {uid}: {e}")
                return False
        except Exception as ex:
            log.warning(f"[Guild Check] Guild check error for {uid}: {ex}")
            return False

    try:
        fut = asyncio.run_coroutine_threadsafe(_check(), disnake_bot_loop)
        return bool(fut.result(timeout=4))
    except Exception as ex:
        log.warning(f"[Guild Check] Guild check execution error: {ex}")
        return False

def notify_ticket_author_dm(
    ticket: dict[str, Any],
    event_type: str,
    details: dict[str, Any],
) -> None:
    """
    Sends a direct message to the ticket author if they are in the guild (GUILD_ID).
    event_type can be: 'message', 'note', or 'status'.
    """
    global disnake_bot, disnake_bot_loop
    if not disnake_bot or not disnake_bot.is_ready() or not disnake_bot_loop or not disnake_bot_loop.is_running():
        return

    author_id_str = ticket.get("discord_id")
    if not author_id_str:
        return
    try:
        author_id = int(str(author_id_str).strip())
    except (ValueError, TypeError):
        return

    bot_ref = disnake_bot

    async def _send_dm_async():
        try:
            guild_id = int(GUILD_ID)
            guild = bot_ref.get_guild(guild_id)
            if not guild:
                guild = await bot_ref.fetch_guild(guild_id)
            if not guild:
                return

            member = guild.get_member(author_id)
            if not member:
                try:
                    member = await guild.fetch_member(author_id)
                except disnake.NotFound:
                    return
                except Exception as e:
                    log.warning(f"[DM Notify] Could not fetch member {author_id}: {e}")
                    return

            if not member:
                return

            ticket_id = ticket.get("id")
            is_bug = (ticket.get("type") == "bug_report")
            type_label = "Bug Report" if is_bug else "Suggestion"
            ticket_title = ticket.get("title") or (ticket.get("suggestion") or ticket.get("description") or f"{type_label} #{ticket_id}")[:60]

            embed = None
            if event_type == "message":
                sender_name = details.get("sender_name", "Administrator")
                msg_content = details.get("message", "")
                embed = disnake.Embed(
                    title=f"New Message: {type_label} #{ticket_id}",
                    description=f"**{sender_name}** sent a message regarding your {type_label.lower()}:\n\n> {msg_content[:1500]}",
                    color=disnake.Color.blurple(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="Ticket Title", value=ticket_title, inline=False)
                embed.set_footer(text="RBWR Community Portal • rbwr.hotment.dev/tickets")

            elif event_type == "note":
                comment_by = details.get("comment_by", "Administrator")
                comment_text = details.get("comment", "")
                embed = disnake.Embed(
                    title=f"Developer Note: {type_label} #{ticket_id}",
                    description=f"A developer note was added or edited by **{comment_by}**:\n\n> {comment_text[:1500]}",
                    color=disnake.Color.gold(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="Ticket Title", value=ticket_title, inline=False)
                embed.set_footer(text="RBWR Community Portal • rbwr.hotment.dev/tickets")

            elif event_type == "status":
                new_status = str(details.get("status", "updated")).upper()
                changed_by = details.get("changed_by", "Administrator")
                embed_color = disnake.Color.green() if new_status in ("FIXED", "RESOLVED", "IMPLEMENTED", "ACCEPTED") else (
                    disnake.Color.red() if new_status in ("INVALID", "DECLINED", "CLOSED") else disnake.Color.blue()
                )
                embed = disnake.Embed(
                    title=f"Status Changed: {type_label} #{ticket_id}",
                    description=f"The status of your {type_label.lower()} has been changed to **`{new_status}`** by **{changed_by}**.",
                    color=embed_color,
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="Ticket Title", value=ticket_title, inline=False)
                embed.add_field(name="New Status", value=f"`{new_status}`", inline=True)
                embed.set_footer(text="RBWR Community Portal • rbwr.hotment.dev/tickets")

            if embed:
                try:
                    await member.send(embed=embed)
                    log.info(f"[DM Notify] Successfully sent {event_type} DM to user {member} (ID: {author_id}) for ticket #{ticket_id}")
                except disnake.Forbidden:
                    log.info(f"[DM Notify] Could not send DM to {member}: direct messages disabled by recipient.")
                except Exception as ex:
                    log.warning(f"[DM Notify] Failed to send DM to {member}: {ex}")

        except Exception as e:
            log.warning(f"[DM Notify] Error in _send_dm_async: {e}")

    try:
        asyncio.run_coroutine_threadsafe(_send_dm_async(), disnake_bot_loop)
    except Exception as ex:
        log.warning(f"[DM Notify] Failed to dispatch DM task: {ex}")

class TicketPanelView(disnake.ui.View):
    def __init__(self, ticket_id: int, ticket_type: str, current_status: str):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        self.ticket_type = ticket_type
        self.current_status = (current_status or "open").lower()

        is_bug = (ticket_type == "bug_report")
        if is_bug:
            options = [
                disnake.SelectOption(label="Open", value="open", description="Newly reported bug", emoji="🐛", default=(self.current_status == "open")),
                disnake.SelectOption(label="Investigating", value="investigating", description="Investigating root cause", emoji="🔍", default=(self.current_status == "investigating")),
                disnake.SelectOption(label="Confirmed", value="confirmed", description="Bug reproduced and confirmed", emoji="⚠️", default=(self.current_status == "confirmed")),
                disnake.SelectOption(label="Fixed / Resolved", value="fixed", description="Bug resolved and deployed", emoji="✅", default=(self.current_status in ("fixed", "resolved"))),
                disnake.SelectOption(label="Closed", value="closed", description="Issue closed", emoji="📁", default=(self.current_status == "closed")),
                disnake.SelectOption(label="Invalid", value="invalid", description="Not a bug or cannot reproduce", emoji="🚫", default=(self.current_status == "invalid")),
            ]
        else:
            options = [
                disnake.SelectOption(label="Pending", value="pending", description="Awaiting developer review", emoji="⏳", default=(self.current_status == "pending")),
                disnake.SelectOption(label="Considering", value="considering", description="Under active consideration", emoji="🤔", default=(self.current_status == "considering")),
                disnake.SelectOption(label="Accepted", value="accepted", description="Suggestion has been approved", emoji="✅", default=(self.current_status == "accepted")),
                disnake.SelectOption(label="Planned", value="planned", description="Scheduled for implementation", emoji="📌", default=(self.current_status == "planned")),
                disnake.SelectOption(label="Implemented", value="implemented", description="Feature is now live", emoji="🚀", default=(self.current_status == "implemented")),
                disnake.SelectOption(label="Declined", value="declined", description="Will not be implemented", emoji="❌", default=(self.current_status == "declined")),
            ]

        self.select_menu = disnake.ui.StringSelect(
            custom_id=f"ticket_status_select:{ticket_id}",
            placeholder=f"Change State (Current: {self.current_status.upper()})",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.add_item(self.select_menu)

        self.discuss_button = disnake.ui.Button(
            label="Open Discussions",
            style=disnake.ButtonStyle.primary,
            custom_id=f"ticket_open_discussions:{ticket_id}",
            emoji="💬",
        )
        self.add_item(self.discuss_button)

_handled_interaction_ids: set[int] = set()

def _check_and_mark_interaction(inter_id: int) -> bool:
    """Returns True if this interaction has already been processed, preventing duplicate executions."""
    if inter_id in _handled_interaction_ids:
        return True
    _handled_interaction_ids.add(inter_id)
    if len(_handled_interaction_ids) > 1000:
        excess = len(_handled_interaction_ids) - 500
        for _ in range(excess):
            _handled_interaction_ids.pop()
    return False

def build_ticket_panel(ticket_id: int, ticket_type: str, current_status: str) -> tuple[disnake.Embed, disnake.ui.View]:
    is_bug = (ticket_type == "bug_report")
    status_clean = (current_status or ("open" if is_bug else "pending")).lower()

    panel_embed = disnake.Embed(
        title=f"Ticket Panel — {'Bug Report' if is_bug else 'Suggestion'} #{ticket_id}",
        description=(
            "**Admin Management Controls**\n"
            "• Use the dropdown menu below to change ticket state.\n"
            "• Click **Open Discussions** to create a community thread and ping the author."
        ),
        color=disnake.Color.dark_theme() if hasattr(disnake.Color, "dark_theme") else disnake.Color.blurple(),
        timestamp=datetime.now(timezone.utc)
    )
    panel_embed.add_field(name="Current State", value=f"`{status_clean.upper()}`", inline=True)
    panel_embed.add_field(name="Ticket Type", value="Bug Report" if is_bug else "Feature Suggestion", inline=True)
    panel_embed.set_footer(text=f"RBWR Utility • Admin Ticket Panel #{ticket_id}")

    view = TicketPanelView(ticket_id=ticket_id, ticket_type=ticket_type, current_status=status_clean)
    return panel_embed, view

def update_discussion_thread_status(ticket: dict[str, Any], new_status: str) -> None:
    """
    Updates the embed in the discussion thread to reflect the new ticket status.
    Can be safely called from both the bot event loop and web server threads.
    """
    global disnake_bot, disnake_bot_loop
    if not disnake_bot or not disnake_bot.is_ready() or not disnake_bot_loop or not disnake_bot_loop.is_running():
        return

    thread_id_val = ticket.get("discussion_thread_id")
    if not thread_id_val:
        return

    bot_ref = disnake_bot

    async def _update_async():
        try:
            tid = int(thread_id_val)
            ch = bot_ref.get_channel(tid)
            if not ch or not isinstance(ch, disnake.Thread):
                try:
                    ch = await bot_ref.fetch_channel(tid)
                except Exception as ex:
                    log.warning(f"[Discussion Status Update] Could not fetch thread {tid}: {ex}")
                    return

            if not ch or not isinstance(ch, disnake.Thread):
                return

            msg = None
            msg_id_val = ticket.get("discussion_message_id")
            if msg_id_val:
                try:
                    msg = await ch.fetch_message(int(msg_id_val))
                except Exception:
                    msg = None

            if not msg:
                try:
                    msg = await ch.fetch_message(tid)
                except Exception:
                    msg = None

            if not msg and hasattr(ch, "history"):
                try:
                    async for m in ch.history(oldest_first=True, limit=5):
                        if bot_ref.user and m.author.id == bot_ref.user.id and m.embeds:
                            msg = m
                            break
                except Exception:
                    msg = None

            if not msg or not msg.embeds:
                return

            old_embed = msg.embeds[0]
            new_embed = disnake.Embed.from_dict(old_embed.to_dict())

            status_upper = str(new_status).upper()
            found_field = False
            for idx, field in enumerate(new_embed.fields):
                if field.name and field.name.strip().lower() == "status":
                    new_embed.set_field_at(idx, name="Status", value=f"`{status_upper}`", inline=True)
                    found_field = True
                    break

            if not found_field:
                new_embed.add_field(name="Status", value=f"`{status_upper}`", inline=True)

            if status_upper in ("FIXED", "RESOLVED", "IMPLEMENTED", "ACCEPTED"):
                new_embed.color = disnake.Color.green()
            elif status_upper == "PLANNED":
                new_embed.color = disnake.Color.teal()
            elif status_upper in ("INVALID", "DECLINED", "CLOSED"):
                new_embed.color = disnake.Color.red()

            await msg.edit(embed=new_embed)
            log.info(f"[Discussion Status Update] Updated discussion embed for ticket #{ticket.get('id')} to {status_upper}")
        except Exception as e:
            log.warning(f"[Discussion Status Update] Failed to update discussion thread message: {e}")

    try:
        asyncio.run_coroutine_threadsafe(_update_async(), disnake_bot_loop)
    except Exception as ex:
        log.warning(f"[Discussion Status Update] Failed to dispatch update task: {ex}")

def notify_ticket_deleted(ticket: dict[str, Any], deleted_by: str = "Administrator") -> None:
    """
    Sends a message in the ticket's Discord admin channel (and discussion thread if active)
    indicating that the ticket has been deleted.
    """
    global disnake_bot, disnake_bot_loop
    if not disnake_bot or not disnake_bot.is_ready() or not disnake_bot_loop or not disnake_bot_loop.is_running():
        return

    ticket_id = ticket.get("id")
    channel_id_val = ticket.get("discord_channel_id")
    discussion_thread_id_val = ticket.get("discussion_thread_id")

    bot_ref = disnake_bot

    async def _notify_async():
        ch = None
        if channel_id_val:
            try:
                ch = bot_ref.get_channel(int(channel_id_val))
                if not ch:
                    ch = await bot_ref.fetch_channel(int(channel_id_val))
            except Exception as ex:
                log.warning(f"[Ticket Deletion Notification] Could not fetch channel {channel_id_val}: {ex}")

        if not ch and ticket_id:
            try:
                cat_id = int(TICKETS_CATEGORY_ID) if TICKETS_CATEGORY_ID.isdigit() else None
                for g in bot_ref.guilds:
                    for c in g.text_channels:
                        if cat_id and c.category_id != cat_id:
                            continue
                        name_lower = c.name.lower()
                        if (
                            name_lower == f"ticket-{ticket_id}"
                            or name_lower.startswith(f"ticket-{ticket_id}-")
                            or name_lower == f"suggestion-{ticket_id}"
                            or name_lower.startswith(f"suggestion-{ticket_id}-")
                            or name_lower == f"bug-{ticket_id}"
                            or name_lower.startswith(f"bug-{ticket_id}-")
                        ):
                            ch = c
                            break
                    if ch:
                        break
            except Exception as ex:
                log.warning(f"[Ticket Deletion Notification] Fallback channel lookup failed: {ex}")

        if ch and hasattr(ch, "send") and isinstance(ch, disnake.TextChannel):
            try:
                title_txt = ticket.get("title") or (ticket.get("suggestion") or ticket.get("description") or "")[:80] or "No Title"
                t_type = str(ticket.get("type", "suggestion")).replace("_", " ").title()

                embed = disnake.Embed(
                    title=f"Ticket #{ticket_id} Deleted",
                    description=f"This ticket has been permanently deleted from the website by **{deleted_by}**.",
                    color=disnake.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="Title", value=title_txt[:250], inline=False)
                embed.add_field(name="Type", value=t_type, inline=True)
                embed.add_field(name="Author", value=ticket.get("name") or "Anonymous", inline=True)
                embed.add_field(name="Deleted By", value=deleted_by, inline=True)
                embed.set_footer(text=f"RBWR Utility • Ticket #{ticket_id} Deleted")

                await ch.send(content=f"**Ticket #{ticket_id} was deleted by {deleted_by}.**", embed=embed)
                log.info(f"[Ticket Deletion Notification] Successfully notified #{getattr(ch, 'name', ch.id)} of deletion of Ticket #{ticket_id}")
            except Exception as e:
                log.warning(f"[Ticket Deletion Notification] Failed to post deletion in ticket channel: {e}")

        if discussion_thread_id_val:
            try:
                dt_id = int(discussion_thread_id_val)
                dt_ch = bot_ref.get_channel(dt_id)
                if not dt_ch:
                    dt_ch = await bot_ref.fetch_channel(dt_id)
                if dt_ch and hasattr(dt_ch, "send") and isinstance(dt_ch, disnake.Thread):
                    await dt_ch.send(
                        content=f"**Notice:** The ticket for this discussion (#{ticket_id}) was deleted from the website by **{deleted_by}**."
                    )
            except Exception as e:
                log.warning(f"[Ticket Deletion Notification] Failed to notify discussion thread: {e}")

    try:
        asyncio.run_coroutine_threadsafe(_notify_async(), disnake_bot_loop)
    except Exception as ex:
        log.warning(f"[Ticket Deletion Notification] Failed to dispatch task: {ex}")

async def handle_ticket_status_select(inter: disnake.MessageInteraction, ticket_id: int):
    if _check_and_mark_interaction(inter.id) or inter.response.is_done():
        return

    sender_discord_id = str(inter.author.id)
    is_guild_admin = inter.author.guild_permissions.administrator if (hasattr(inter.author, "guild_permissions") and isinstance(inter.author, disnake.Member)) else None
    is_admin = (ticket_bridge.is_website_admin and ticket_bridge.is_website_admin(sender_discord_id)) or is_guild_admin

    if not is_admin:
        await inter.response.send_message("Only website administrators can change ticket status.", ephemeral=True)
        return

    new_status = inter.values[0] if inter.values else None
    if not new_status:
        return

    if not ticket_bridge.load_suggestions or not ticket_bridge.save_suggestions:
        await inter.response.send_message("Ticket bridge is not configured.", ephemeral=True)
        return

    data = ticket_bridge.load_suggestions()
    suggestions = data.get("suggestions", [])
    target = next((s for s in suggestions if s.get("id") == ticket_id), None)
    if not target:
        await inter.response.send_message(f"Ticket #{ticket_id} not found in database.", ephemeral=True)
        return

    prev_status = str(target.get("status") or "pending").upper()
    target["status"] = new_status
    ticket_bridge.save_suggestions(data)

    if ticket_bridge.broadcast_dashboard:
        ticket_bridge.broadcast_dashboard()

    if ticket_bridge.broadcast_ticket_update:
        ticket_bridge.broadcast_ticket_update(
            ticket_id,
            None,
            target.get("messages", []),
            target.get("discord_id"),
            target.get("anonymous")
        )

    notify_ticket_author_dm(
        ticket=target,
        event_type="status",
        details={
            "changed_by": inter.author.display_name,
            "status": new_status
        }
    )

    update_discussion_thread_status(
        ticket=target,
        new_status=new_status
    )

    await inter.response.send_message(
        f"Ticket #{ticket_id} status updated from `{prev_status}` to **`{new_status.upper()}`** by {inter.author.mention}."
    )

async def handle_ticket_open_discussions(inter: disnake.MessageInteraction, ticket_id: int):
    if _check_and_mark_interaction(inter.id) or inter.response.is_done():
        return

    sender_discord_id = str(inter.author.id)
    is_guild_admin = inter.author.guild_permissions.administrator if (hasattr(inter.author, "guild_permissions") and isinstance(inter.author, disnake.Member)) else None
    is_admin = (ticket_bridge.is_website_admin and ticket_bridge.is_website_admin(sender_discord_id)) or is_guild_admin

    if not is_admin:
        await inter.response.send_message("Only administrators can open discussion threads.", ephemeral=True)
        return

    if not ticket_bridge.load_suggestions:
        await inter.response.send_message("Ticket bridge is not configured.", ephemeral=True)
        return

    data = ticket_bridge.load_suggestions()
    suggestions = data.get("suggestions", [])
    target = next((s for s in suggestions if s.get("id") == ticket_id), None)
    if not target:
        await inter.response.send_message(f"Ticket #{ticket_id} not found in database.", ephemeral=True)
        return

    existing_thread_id = target.get("discussion_thread_id")
    if existing_thread_id:
        await inter.response.send_message(
            f"A discussion thread has already been created for Ticket #{ticket_id}: <#{existing_thread_id}>",
            ephemeral=True
        )
        return

    await inter.response.defer(ephemeral=False)

    is_bug = (target.get("type") == "bug_report")
    target_channel_id = BUGS_DISCUSSION_CHANNEL_ID if is_bug else SUGGESTIONS_DISCUSSION_CHANNEL_ID

    bot_ref = inter.bot
    dest_ch = bot_ref.get_channel(target_channel_id)
    if not dest_ch:
        try:
            dest_ch = await bot_ref.fetch_channel(target_channel_id)
        except Exception as e:
            await inter.followup.send(f"Failed to access discussion channel <#{target_channel_id}>: `{e}`", ephemeral=True)
            return

    raw_title = target.get("title") or (target.get("suggestion") or target.get("description") or f"Ticket #{ticket_id}")[:60]
    thread_name = f"[{'Bug' if is_bug else 'Suggestion'} #{ticket_id}] {raw_title}"[:95]
    desc_content = target.get("suggestion") or target.get("description") or "No description provided."

    author_discord_id = target.get("discord_id")
    if author_discord_id and str(author_discord_id).isdigit():
        author_ping = f"<@{author_discord_id}>"
    else:
        author_ping = f"**{target.get('name', 'Anonymous')}**"

    embed = disnake.Embed(
        title=f"{'Bug Report' if is_bug else 'Feature Suggestion'} #{ticket_id}: {raw_title}",
        description=desc_content[:3500],
        color=disnake.Color.red() if is_bug else disnake.Color.blurple(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="Author", value=author_ping, inline=True)
    embed.add_field(name="Type", value="Bug Report" if is_bug else "Feature Suggestion", inline=True)
    embed.add_field(name="Status", value=(target.get("status") or ("open" if is_bug else "pending")).upper(), inline=True)
    embed.set_footer(text=f"RBWR Community Discussion • Ticket #{ticket_id}")

    init_msg = f"{author_ping} — Discussion thread opened for Ticket #{ticket_id}!"

    created_thread = None
    starter_msg = None
    try:
        if isinstance(dest_ch, disnake.ForumChannel):
            forum_post = await dest_ch.create_thread(
                name=thread_name,
                content=init_msg,
                embed=embed,
                allowed_mentions=disnake.AllowedMentions(users=True)
            )
            created_thread = forum_post.thread
            starter_msg = getattr(forum_post, "message", None)
        elif isinstance(dest_ch, disnake.TextChannel):
            created_thread = await dest_ch.create_thread(
                name=thread_name,
                type=disnake.ChannelType.public_thread
            )
            starter_msg = await created_thread.send(
                content=init_msg,
                embed=embed,
                allowed_mentions=disnake.AllowedMentions(users=True)
            )
        elif isinstance(dest_ch, disnake.Thread):
            starter_msg = await dest_ch.send(
                content=init_msg,
                embed=embed,
                allowed_mentions=disnake.AllowedMentions(users=True)
            )
            created_thread = dest_ch
        elif hasattr(dest_ch, "create_thread"):
            created_thread = await dest_ch.create_thread(name=thread_name)
            starter_msg = await created_thread.send(
                content=init_msg,
                embed=embed,
                allowed_mentions=disnake.AllowedMentions(users=True)
            )
    except Exception as ex:
        log.error(f"[Discussion Thread] Error creating thread in {dest_ch}: {ex}", exc_info=True)
        await inter.followup.send(f"Failed to create thread in {dest_ch.mention}: `{ex}`", ephemeral=True)
        return

    if created_thread:
        target["discussion_thread_id"] = str(created_thread.id)
        target["discussion_channel_id"] = str(target_channel_id)
        if starter_msg:
            target["discussion_message_id"] = str(starter_msg.id)
        if ticket_bridge.save_suggestions:
            ticket_bridge.save_suggestions(data)
        if ticket_bridge.broadcast_dashboard:
            ticket_bridge.broadcast_dashboard()

        await inter.followup.send(
            f"Discussion thread created for **Ticket #{ticket_id}** in {dest_ch.mention}: {created_thread.mention}!"
        )
    else:
        await inter.followup.send(
            f"Unable to create discussion thread in {dest_ch.mention}.",
            ephemeral=True
        )

ROBLOX_PLACE_ID = "11765852158"

def get_server_points_rate(server: dict[str, Any]) -> float | None:
    misc = server.get("state", {}).get("Misc", {})
    if isinstance(misc, dict) and "Total points/second" in misc:
        val = misc.get("Total points/second")
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                pass
    return None

def get_unit_state(server: dict[str, Any], unit: int) -> dict[str, Any]:
    st = server.get("state", {})
    if isinstance(st, dict):
        u = st.get(f"Unit{unit}", {})
        if isinstance(u, dict):
            return u
    return {}

def get_unit_aprm(u_state: dict[str, Any]) -> float:
    aprm = u_state.get("APRM")
    if aprm is not None:
        try:
            return float(aprm)
        except (ValueError, TypeError):
            pass
    return 0.0

def is_unit_running(u_state: dict[str, Any]) -> bool:
    return get_unit_aprm(u_state) > 5.0

def get_unit_status_badge(u_state: dict[str, Any]) -> str:
    aprm = get_unit_aprm(u_state)
    scram = u_state.get("SCRAMreason")
    if scram and str(scram).strip() not in ("None", "", "null"):
        return f"SCRAM: {str(scram).strip()} ({aprm:.1f}%)"
    if aprm > 5.0:
        return f"Running ({aprm:.1f}% APRM)"
    return f"Offline ({aprm:.1f}% APRM)"

def make_roblox_join_url(job_id: str) -> str:
    return f"https://www.roblox.com/games/start?placeId={ROBLOX_PLACE_ID}&gameInstanceId={job_id}"

def make_web_server_url(job_id: str) -> str:
    return f"{DEFAULT_SERVER_BASE_URL}/servers/{job_id}"

class ServerBrowserView(disnake.ui.View):
    PAGE_SIZE = 5

    def __init__(
        self,
        client: RBWRClient,
        author_id: int,
        all_servers: list[dict[str, Any]],
        query: str = "",
        sort_by: str = "points",
        filter_status: str = "all",
    ):
        super().__init__(timeout=300)
        self.client = client
        self.author_id = author_id
        self.raw_servers = all_servers
        self.query = (query or "").strip().lower()
        self.sort_by = sort_by
        self.filter_status = filter_status
        self.page = 0
        self.selected_server_job_id: str | None = None

        self.filtered_servers: list[dict[str, Any]] = []
        self._apply_filtering_and_sorting()
        self.rebuild_components()

    def _apply_filtering_and_sorting(self):
        matched = []
        for s in self.raw_servers:
            if not is_server_public(s):
                continue

            jid = str(s.get("jobId", ""))
            short = self.client.short_id(jid).lower()
            u1 = get_unit_state(s, 1)
            u2 = get_unit_state(s, 2)
            u1_running = is_unit_running(u1)
            u2_running = is_unit_running(u2)
            pts = get_server_points_rate(s)
            u1_scram = str(u1.get("SCRAMreason", "None")).strip()
            u2_scram = str(u2.get("SCRAMreason", "None")).strip()
            has_scram = (u1_scram not in ("None", "", "null")) or (u2_scram not in ("None", "", "null"))

            if self.query:
                q = self.query.replace("-", "")
                norm_jid = jid.lower().replace("-", "")
                norm_short = short.replace("-", "")
                if (q not in norm_jid) and (q not in norm_short) and (q not in u1_scram.lower()) and (q not in u2_scram.lower()):
                    continue

            if self.filter_status == "running":
                if not (u1_running or u2_running):
                    continue
            elif self.filter_status == "both":
                if not (u1_running and u2_running):
                    continue
            elif self.filter_status == "points":
                if pts is None or pts <= 0:
                    continue
            elif self.filter_status == "scrammed":
                if not has_scram:
                    continue

            matched.append(s)

        def sort_key_fn(s: dict[str, Any]):
            u1 = get_unit_state(s, 1)
            u2 = get_unit_state(s, 2)
            pts = get_server_points_rate(s)
            pts_val = pts if pts is not None else -1.0
            u1_aprm = get_unit_aprm(u1)
            u2_aprm = get_unit_aprm(u2)
            run_count = int(is_unit_running(u1)) + int(is_unit_running(u2))

            if self.sort_by == "points":
                return (pts_val, run_count, u1_aprm + u2_aprm)
            elif self.sort_by == "active_reactors":
                return (run_count, u1_aprm + u2_aprm, pts_val)
            elif self.sort_by == "aprm_u1":
                return (u1_aprm, u2_aprm)
            elif self.sort_by == "aprm_u2":
                return (u2_aprm, u1_aprm)
            elif self.sort_by == "players":
                p_str = get_player_count(s)
                try:
                    p_num = int(p_str)
                except ValueError:
                    p_num = -1
                return (p_num, pts_val)
            elif self.sort_by == "id":
                return self.client.short_id(str(s.get("jobId", "")))
            return pts_val

        reverse = (self.sort_by != "id")
        matched.sort(key=sort_key_fn, reverse=reverse)
        self.filtered_servers = matched

        max_page = max(0, (len(self.filtered_servers) - 1) // self.PAGE_SIZE)
        if self.page > max_page:
            self.page = max_page

    def build_embed(self) -> disnake.Embed:
        if self.selected_server_job_id:
            selected = next((s for s in self.filtered_servers if str(s.get("jobId")) == self.selected_server_job_id), None)
            if not selected:
                selected = next((s for s in self.raw_servers if str(s.get("jobId")) == self.selected_server_job_id), None)
            if selected:
                return self._build_detail_embed(selected)

        total_matched = len(self.filtered_servers)
        total_pages = max(1, (total_matched + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        start_idx = self.page * self.PAGE_SIZE
        page_servers = self.filtered_servers[start_idx : start_idx + self.PAGE_SIZE]

        active_reactors = sum(
            int(is_unit_running(get_unit_state(s, 1))) + int(is_unit_running(get_unit_state(s, 2)))
            for s in self.filtered_servers
        )
        total_gen = sum(
            (get_server_points_rate(s) or 0.0)
            for s in self.filtered_servers
        )

        embed = disnake.Embed(
            title="⚡ RBWR Live Server Browser",
            color=disnake.Color.teal() if total_matched > 0 else disnake.Color.dark_grey(),
            timestamp=datetime.now(timezone.utc),
        )

        filter_names = {
            "all": "All Public",
            "running": "Running (≥ 1 Unit)",
            "both": "Dual Running",
            "points": "Points (> 0/s)",
            "scrammed": "Scrammed",
        }
        sort_names = {
            "points": "Points / sec",
            "active_reactors": "Active Units",
            "aprm_u1": "U1 APRM",
            "aprm_u2": "U2 APRM",
            "players": "Players",
            "id": "Server ID",
        }

        desc_lines = [
            f"**Filter:** `{filter_names.get(self.filter_status, self.filter_status)}` • **Sort:** `{sort_names.get(self.sort_by, self.sort_by)}`"
        ]
        if self.query:
            desc_lines.append(f"🔍 **Search Query:** `{self.query}`")

        desc_lines.append(
            f"**Matching:** `{total_matched}` • **Active Units:** `{active_reactors}` • ⚡ **Total Gen:** `{total_gen:.2f} pts/s`\n"
        )

        if not page_servers:
            desc_lines.append("*No public servers matched your search / filter criteria.*")
            desc_lines.append("Try adjusting your filter or search query above.")
        else:
            for s in page_servers:
                jid = str(s.get("jobId", "unknown"))
                short = self.client.short_id(jid)
                u1 = get_unit_state(s, 1)
                u2 = get_unit_state(s, 2)
                u1_badge = get_unit_status_badge(u1)
                u2_badge = get_unit_status_badge(u2)
                pts = get_server_points_rate(s)
                pts_str = f"{pts:.2f} pts/s" if pts is not None else "N/A"
                players = get_player_count(s)
                p_display = f"{players}/12" if players != "?" else "?"
                web_url = make_web_server_url(jid)
                join_url = make_roblox_join_url(jid)

                desc_lines.append(
                    f"**[`{short}`]({web_url})** • [`Join Game`]({join_url})\n"
                    f"`Job ID:` `{jid}`\n"
                    f"• **U1:** {u1_badge} | **U2:** {u2_badge}\n"
                    f"• **Points:** `{pts_str}` | **Players:** 👥 `{p_display}`\n"
                )

        embed.description = "\n".join(desc_lines)
        embed.set_footer(
            text=f"Page {self.page + 1}/{total_pages} • Total Public: {len(self.raw_servers)} • User App Ready"
        )
        return embed

    def _build_detail_embed(self, server: dict[str, Any]) -> disnake.Embed:
        jid = str(server.get("jobId", "unknown"))
        short = self.client.short_id(jid)
        u1 = get_unit_state(server, 1)
        u2 = get_unit_state(server, 2)
        pts = get_server_points_rate(server)
        pts_str = f"{pts:.4f}".rstrip("0").rstrip(".") + " pts/s" if pts is not None else "N/A"
        players = get_player_count(server)
        p_display = f"{players}/12" if players != "?" else "?"

        u1_running = is_unit_running(u1)
        u2_running = is_unit_running(u2)
        if u1_running and u2_running:
            color = disnake.Color.green()
        elif u1_running or u2_running:
            color = disnake.Color.gold()
        else:
            color = disnake.Color.dark_theme() if hasattr(disnake.Color, "dark_theme") else disnake.Color.greyple()

        embed = disnake.Embed(
            title=f"RBWR Server Telemetry — {short}",
            description=(
                f"**Job ID:** `{jid}`\n"
                f"**Points Generation:** `{pts_str}`\n"
                f"**Active Players:** `{p_display}`\n"
                f"**Visibility:** `Public`"
            ),
            color=color,
            timestamp=datetime.now(timezone.utc),
        )

        def unit_field(u_num: int, u_data: dict[str, Any]) -> str:
            scram = u_data.get("SCRAMreason")
            scram_text = f"**SCRAM:** {scram}\n" if (scram and str(scram).strip() not in ("None", "", "null")) else ""
            demand_left = u_data.get("Demand Time Left")
            demand_text = f"**Demand Timer:** `{demand_left}s`\n" if demand_left is not None else ""
            return (
                f"{scram_text}"
                f"**APRM:** `{fmt(u_data.get('APRM'))}%`\n"
                f"**RTP:** `{fmt(u_data.get('RTP'))}%`\n"
                f"**Reactor Temp:** `{fmt(u_data.get('Reactor Temp'))} °C`\n"
                f"**Output:** `{fmt(u_data.get('Output (MW)'))} MW`\n"
                f"**Turbine RPM:** `{fmt(u_data.get('Turbine RPM'))}`\n"
                f"**Points / sec:** `{fmt(u_data.get('PointsPerSecond'))}`\n"
                f"**Xenon:** `{fmt(u_data.get('Xenon'))}`\n"
                f"{demand_text}"
            )

        embed.add_field(name=f"Unit 1 ({get_unit_status_badge(u1)})", value=unit_field(1, u1), inline=True)
        embed.add_field(name=f"Unit 2 ({get_unit_status_badge(u2)})", value=unit_field(2, u2), inline=True)

        misc = server.get("state", {}).get("Misc", {})
        if isinstance(misc, dict) and misc:
            misc_lines = []
            for k in ("Outside Temperature", "EDG Diesel Storage", "FSS Smoke Detected", "Evacuation Cooldown"):
                if k in misc:
                    misc_lines.append(f"**{k}:** `{misc[k]}`")
            if misc_lines:
                embed.add_field(name="Environmental / Facility", value="\n".join(misc_lines), inline=False)

        embed.set_footer(text=f"RBWR Utility • Server ID: {short}")
        return embed

    def rebuild_components(self):
        self.clear_items()

        if self.selected_server_job_id:
            jid = self.selected_server_job_id
            self.add_item(disnake.ui.Button(
                label="Join in Roblox",
                url=make_roblox_join_url(jid),
                emoji="🎮",
                row=0,
            ))
            self.add_item(disnake.ui.Button(
                label="Open Web View",
                url=make_web_server_url(jid),
                emoji="🌐",
                row=0,
            ))
            back_btn = disnake.ui.Button(
                label="Back to Server List",
                style=disnake.ButtonStyle.secondary,
                emoji="◀",
                row=0,
            )
            back_btn.callback = self.on_back_to_list
            self.add_item(back_btn)
            return

        filter_options = [
            disnake.SelectOption(label="All Public Servers", value="all", emoji="🌐", description="Show all online public servers", default=(self.filter_status == "all")),
            disnake.SelectOption(label="Running Reactors", value="running", emoji="🔥", description="At least 1 unit running (>5% APRM)", default=(self.filter_status == "running")),
            disnake.SelectOption(label="Dual Running Reactors", value="both", emoji="⚡", description="Both units actively running", default=(self.filter_status == "both")),
            disnake.SelectOption(label="Earning Points", value="points", emoji="💰", description="Points rate > 0 pts/sec", default=(self.filter_status == "points")),
            disnake.SelectOption(label="Scrammed Reactors", value="scrammed", emoji="🚨", description="Servers with an active reactor SCRAM", default=(self.filter_status == "scrammed")),
        ]
        filter_select = disnake.ui.StringSelect(
            custom_id="browser_filter_select",
            placeholder="Filter servers...",
            options=filter_options,
            row=0,
        )
        filter_select.callback = self.on_filter_change
        self.add_item(filter_select)

        sort_options = [
            disnake.SelectOption(label="Highest Points / sec", value="points", emoji="⚡", description="Sort by highest points generation rate", default=(self.sort_by == "points")),
            disnake.SelectOption(label="Most Running Reactors", value="active_reactors", emoji="⚛️", description="Dual running > single running > offline", default=(self.sort_by == "active_reactors")),
            disnake.SelectOption(label="Highest Unit 1 APRM", value="aprm_u1", emoji="📈", description="Sort by Unit 1 core power", default=(self.sort_by == "aprm_u1")),
            disnake.SelectOption(label="Highest Unit 2 APRM", value="aprm_u2", emoji="📈", description="Sort by Unit 2 core power", default=(self.sort_by == "aprm_u2")),
            disnake.SelectOption(label="Most Players", value="players", emoji="👥", description="Sort by player population", default=(self.sort_by == "players")),
            disnake.SelectOption(label="Server ID (A-Z)", value="id", emoji="🔤", description="Alphabetical sort by short ID", default=(self.sort_by == "id")),
        ]
        sort_select = disnake.ui.StringSelect(
            custom_id="browser_sort_select",
            placeholder="Sort by...",
            options=sort_options,
            row=1,
        )
        sort_select.callback = self.on_sort_change
        self.add_item(sort_select)

        start_idx = self.page * self.PAGE_SIZE
        page_servers = self.filtered_servers[start_idx : start_idx + self.PAGE_SIZE]
        if page_servers:
            inspect_options = []
            for s in page_servers:
                jid = str(s.get("jobId", ""))
                short = self.client.short_id(jid)
                u1 = get_unit_state(s, 1)
                u2 = get_unit_state(s, 2)
                pts = get_server_points_rate(s)
                pts_str = f"{pts:.2f} pts/s" if pts is not None else "N/A"
                label = f"{short} • {pts_str}"
                desc = f"U1: {get_unit_aprm(u1):.0f}% | U2: {get_unit_aprm(u2):.0f}%"
                inspect_options.append(disnake.SelectOption(
                    label=label[:100],
                    value=jid,
                    description=desc[:100],
                    emoji="🔍"
                ))
            inspect_select = disnake.ui.StringSelect(
                custom_id="browser_inspect_select",
                placeholder="Select a server to inspect full telemetry...",
                options=inspect_options,
                row=2,
            )
            inspect_select.callback = self.on_inspect_select
            self.add_item(inspect_select)

        total_matched = len(self.filtered_servers)
        total_pages = max(1, (total_matched + self.PAGE_SIZE - 1) // self.PAGE_SIZE)

        prev_btn = disnake.ui.Button(
            label="◀ Prev",
            style=disnake.ButtonStyle.primary,
            disabled=(self.page <= 0),
            row=3,
        )
        prev_btn.callback = self.on_prev
        self.add_item(prev_btn)

        page_indicator = disnake.ui.Button(
            label=f"Page {self.page + 1} / {total_pages}",
            style=disnake.ButtonStyle.secondary,
            disabled=True,
            row=3,
        )
        self.add_item(page_indicator)

        next_btn = disnake.ui.Button(
            label="Next ▶",
            style=disnake.ButtonStyle.primary,
            disabled=(self.page >= total_pages - 1),
            row=3,
        )
        next_btn.callback = self.on_next
        self.add_item(next_btn)

        refresh_btn = disnake.ui.Button(
            label="Refresh",
            style=disnake.ButtonStyle.success,
            emoji="🔄",
            row=3,
        )
        refresh_btn.callback = self.on_refresh
        self.add_item(refresh_btn)

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        if self.author_id and interaction.author.id != self.author_id:
            await interaction.response.send_message(
                "This server browser belongs to another session. Use `/servers` to open your own interactive browser!",
                ephemeral=True
            )
            return False
        return True

    async def on_prev(self, inter: disnake.MessageInteraction):
        if self.page > 0:
            self.page -= 1
        self.rebuild_components()
        await inter.response.edit_message(embed=self.build_embed(), view=self)

    async def on_next(self, inter: disnake.MessageInteraction):
        total_pages = max(1, (len(self.filtered_servers) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        if self.page < total_pages - 1:
            self.page += 1
        self.rebuild_components()
        await inter.response.edit_message(embed=self.build_embed(), view=self)

    async def on_filter_change(self, inter: disnake.MessageInteraction):
        self.filter_status = inter.values[0]  # pyright: ignore[reportOptionalSubscript]
        self.page = 0
        self.selected_server_job_id = None
        self._apply_filtering_and_sorting()
        self.rebuild_components()
        await inter.response.edit_message(embed=self.build_embed(), view=self)

    async def on_sort_change(self, inter: disnake.MessageInteraction):
        self.sort_by = inter.values[0]  # pyright: ignore[reportOptionalSubscript]
        self.page = 0
        self.selected_server_job_id = None
        self._apply_filtering_and_sorting()
        self.rebuild_components()
        await inter.response.edit_message(embed=self.build_embed(), view=self)

    async def on_inspect_select(self, inter: disnake.MessageInteraction):
        self.selected_server_job_id = inter.values[0]  # pyright: ignore[reportOptionalSubscript]
        self.rebuild_components()
        await inter.response.edit_message(embed=self.build_embed(), view=self)

    async def on_back_to_list(self, inter: disnake.MessageInteraction):
        self.selected_server_job_id = None
        self.rebuild_components()
        await inter.response.edit_message(embed=self.build_embed(), view=self)

    async def on_refresh(self, inter: disnake.MessageInteraction):
        await inter.response.defer()
        try:
            payload = await self.client.fetch(public_only=True)
            self.raw_servers = payload.get("data", {}).get("servers", [])
        except Exception:
            pass
        self._apply_filtering_and_sorting()
        self.rebuild_components()
        await inter.edit_original_response(embed=self.build_embed(), view=self)

def create_bot_instance(data_supplier: Callable[[bool], dict[str, Any]] | None = None) -> commands.InteractionBot:
    intents = disnake.Intents.default()
    intents.message_content = True
    intents.guilds = True

    new_bot = commands.InteractionBot(
        intents=intents,
        test_guilds=None,
        default_install_types=disnake.ApplicationInstallTypes.all(),
        default_contexts=disnake.InteractionContextTypes.all(),
    )
    new_bot.rbwr = RBWRClient(data_supplier=data_supplier)  # pyright: ignore[reportAttributeAccessIssue]

    register_bot_events_and_commands(new_bot)
    return new_bot

def fmt(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)

def get_player_count(server: dict[str, Any]) -> str:
    if not is_server_public(server):
        return "?"
    for key in ("playerCount", "PlayerCount", "players", "Players", "player_count"):
        if key in server and server[key] is not None:
            return str(server[key])
    return "?"

def state_for(server: dict[str, Any], unit: int) -> dict[str, Any]:
    return server.get("state", {}).get(f"Unit{unit}", {}) or {}

def add_info(embed: disnake.Embed, server: dict[str, Any], unit: int, info: str):
    st = state_for(server, unit)

    if info == "all":
        lines = [
            f"**APRM:** {fmt(st.get('APRM'))}",
            f"**RTP:** {fmt(st.get('RTP'))}",
            f"**Xenon:** {fmt(st.get('Xenon'))}",
            f"**Reactor Temp:** {fmt(st.get('Reactor Temp'))}",
            f"**Output:** {fmt(st.get('Output (MW)'))} MW",
            f"**Turbine RPM:** {fmt(st.get('Turbine RPM'))}",
            f"**Points/s:** {fmt(st.get('PointsPerSecond'))}",
            f"**Demand time:** {fmt(st.get('Demand Time Left'))} s",
            f"**SCRAM:** {fmt(st.get('SCRAMreason'))}",
        ]
        embed.add_field(name=f"Unit {unit}", value="\n".join(lines), inline=True)
        return

    if info == "demand":
        key = "NextDemandU1" if unit == 1 else "NextDemandU2"
        label, value = "Next demand", st.get(key)
    else:
        key = INFO_ALIASES.get(info, info)
        label, value = key, st.get(key)

    embed.add_field(name=f"U{unit} — {label}", value=fmt(value), inline=True)

SORT_CHOICES = [
    disnake.OptionChoice(name="Highest Points / sec", value="points"),
    disnake.OptionChoice(name="Most Running Reactors", value="active_reactors"),
    disnake.OptionChoice(name="Highest Unit 1 APRM", value="aprm_u1"),
    disnake.OptionChoice(name="Highest Unit 2 APRM", value="aprm_u2"),
    disnake.OptionChoice(name="Most Players", value="players"),
    disnake.OptionChoice(name="Server ID (A-Z)", value="id"),
]

FILTER_CHOICES = [
    disnake.OptionChoice(name="All Public Servers", value="all"),
    disnake.OptionChoice(name="Running Reactors (≥ 1 Unit)", value="running"),
    disnake.OptionChoice(name="Dual Running Reactors (Both Units)", value="both"),
    disnake.OptionChoice(name="Earning Points (> 0 pts/s)", value="points"),
    disnake.OptionChoice(name="Scrammed Reactors", value="scrammed"),
]

def register_bot_events_and_commands(b: commands.InteractionBot):
    @b.event
    async def on_ready():
        log.info(f"[Disnake Bot] Connected and active as {b.user} (ID: {b.user.id if b.user else 'N/A'})")

    @b.slash_command(
        name="server",
        description="View real-time telemetry and stats for a public RBWR server",
        install_types=disnake.ApplicationInstallTypes.all(),
        contexts=disnake.InteractionContextTypes.all(),
    )
    async def server_command(
        inter: disnake.ApplicationCommandInteraction,
        id: str = commands.Param(description="Job ID or short ID (e.g. 191f-49d5)"),
        info: str = commands.Param(
            default="all",
            description="Specific metric or ALL for complete inspection",
            choices=INFO_CHOICES,
        ),
    ):
        await inter.response.defer()

        client: RBWRClient = getattr(b, "rbwr", None) or RBWRClient()
        try:
            server = await client.find_server(id, public_only=True)
        except Exception as e:
            log.exception("RBWR API error")
            await inter.followup.send(f"Error fetching server data: `{e}`")
            return

        if not server or not is_server_public(server):
            await inter.followup.send(f"Server `{id}` not found or is private / offline.")
            return

        job_id = str(server.get("jobId", id))
        short = client.short_id(job_id)
        info_val = getattr(info, "value", info)

        view = disnake.ui.View(timeout=180)
        view.add_item(disnake.ui.Button(
            label="Join in Roblox",
            url=make_roblox_join_url(job_id),
            emoji="🎮",
        ))
        view.add_item(disnake.ui.Button(
            label="Open Web View",
            url=make_web_server_url(job_id),
            emoji="🌐",
        ))

        if info_val == "all":
            browser_view = ServerBrowserView(
                client=client,
                author_id=inter.author.id,
                all_servers=[server],
            )
            embed = browser_view._build_detail_embed(server)
            await inter.followup.send(embed=embed, view=view)
        else:
            players = get_player_count(server)
            embed = disnake.Embed(
                title=f"RBWR Server — {short}",
                description=f"**Server ID:** `{short}`\n**Job ID:** `{job_id}`",
                color=disnake.Color.teal(),
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text=f"Players: {players} • RBWR Telemetry")
            add_info(embed, server, 1, info_val)
            add_info(embed, server, 2, info_val)
            await inter.followup.send(embed=embed, view=view)

    @server_command.autocomplete("id")
    async def server_id_autocomplete(inter: disnake.ApplicationCommandInteraction, user_input: str):
        client: RBWRClient = getattr(b, "rbwr", None) or RBWRClient()
        try:
            payload = await client.fetch(public_only=True)
            servers = payload.get("data", {}).get("servers", [])
        except Exception:
            return []

        clean_input = (user_input or "").strip().lower().replace("-", "")
        choices = []

        for s in servers:
            if not is_server_public(s):
                continue
            jid = str(s.get("jobId", ""))
            short = client.short_id(jid)
            u1 = get_unit_state(s, 1)
            u2 = get_unit_state(s, 2)
            pts = get_server_points_rate(s)
            pts_str = f"{pts:.2f} pts/s" if pts is not None else "N/A"
            u1_aprm = get_unit_aprm(u1)
            u2_aprm = get_unit_aprm(u2)

            norm_jid = jid.lower().replace("-", "")
            norm_short = short.lower().replace("-", "")

            if not clean_input or clean_input in norm_jid or clean_input in norm_short:
                label = f"{short} • U1: {u1_aprm:.0f}% | U2: {u2_aprm:.0f}% | {pts_str}"
                choices.append(disnake.OptionChoice(name=label[:100], value=short))
                if len(choices) >= 25:
                    break

        return choices

    @b.slash_command(
        name="servers",
        description="Interactive browser & search for active RBWR servers",
        install_types=disnake.ApplicationInstallTypes.all(),
        contexts=disnake.InteractionContextTypes.all(),
    )
    async def servers_command(
        inter: disnake.ApplicationCommandInteraction,
        query: str = commands.Param(default="", description="Search by Job ID, short ID, or SCRAM reason"),
        sort_by: str = commands.Param(default="points", description="Sorting criteria", choices=SORT_CHOICES),
        filter: str = commands.Param(default="all", description="Filter criteria", choices=FILTER_CHOICES),
    ):
        await inter.response.defer()
        client: RBWRClient = getattr(b, "rbwr", None) or RBWRClient()
        try:
            payload = await client.fetch(public_only=True)
            servers = payload.get("data", {}).get("servers", [])
        except Exception as e:
            await inter.followup.send(f"Error fetching servers: `{e}`")
            return

        browser_view = ServerBrowserView(
            client=client,
            author_id=inter.author.id,
            all_servers=servers,
            query=query,
            sort_by=sort_by,
            filter_status=filter,
        )
        await inter.followup.send(embed=browser_view.build_embed(), view=browser_view)

    @b.slash_command(
        name="serverlist",
        description="Interactive browser & search for active RBWR servers",
        install_types=disnake.ApplicationInstallTypes.all(),
        contexts=disnake.InteractionContextTypes.all(),
    )
    async def serverlist_command(
        inter: disnake.ApplicationCommandInteraction,
        query: str = commands.Param(default="", description="Search by Job ID, short ID, or SCRAM reason"),
        sort_by: str = commands.Param(default="points", description="Sorting criteria", choices=SORT_CHOICES),
        filter: str = commands.Param(default="all", description="Filter criteria", choices=FILTER_CHOICES),
    ):
        await servers_command(inter, query=query, sort_by=sort_by, filter=filter)

    @b.listen("on_interaction")
    async def global_ticket_interaction_listener(inter: disnake.Interaction):
        if not isinstance(inter, disnake.MessageInteraction):
            return
        cid = str(getattr(inter.data, "custom_id", "") or "")
        if cid.startswith("ticket_status_select:"):
            try:
                t_id = int(cid.split(":")[1])
                await handle_ticket_status_select(inter, t_id)
            except Exception as ex:
                log.error(f"[Component Handler] Status select error: {ex}", exc_info=True)
        elif cid.startswith("ticket_open_discussions:"):
            try:
                t_id = int(cid.split(":")[1])
                await handle_ticket_open_discussions(inter, t_id)
            except Exception as ex:
                log.error(f"[Component Handler] Open discussions error: {ex}", exc_info=True)

    async def _show_panel_interactive(
        inter: disnake.ApplicationCommandInteraction,
        id: int | None = None
    ):
        await inter.response.defer(ephemeral=True)
        sender_discord_id = str(inter.author.id)
        is_guild_admin = inter.author.guild_permissions.administrator if (hasattr(inter.author, "guild_permissions") and isinstance(inter.author, disnake.Member)) else None
        is_admin = (ticket_bridge.is_website_admin and ticket_bridge.is_website_admin(sender_discord_id)) or is_guild_admin
        if not is_admin:
            await inter.followup.send("Only administrators can spawn ticket panels.", ephemeral=True)
            return

        if not ticket_bridge.load_suggestions:
            await inter.followup.send("Ticket bridge is not configured.", ephemeral=True)
            return

        data = ticket_bridge.load_suggestions()
        suggestions = data.get("suggestions", [])
        ch_id = str(inter.channel.id)

        target = None
        if id is not None:
            target = next((s for s in suggestions if s.get("id") == id), None)
        else:
            target = next((s for s in suggestions if str(s.get("discord_channel_id", "")) == ch_id), None)
            if not target:
                ch_name = getattr(inter.channel, "name", "")
                for s in suggestions:
                    if f"ticket-{s.get('id')}" in ch_name or f"bug-{s.get('id')}" in ch_name:
                        target = s
                        break

        if not target:
            await inter.followup.send("Could not match this channel to an active ticket. Please specify a ticket ID.", ephemeral=True)
            return

        t_id = target.get("id")
        t_type = target.get("type", "suggestion")
        st = target.get("status") or ("open" if t_type == "bug_report" else "pending")

        panel_embed, panel_view = build_ticket_panel(ticket_id=t_id, ticket_type=t_type, current_status=st)
        await inter.channel.send(embed=panel_embed, view=panel_view)
        await inter.followup.send(f"Spawned Ticket Admin Panel for Ticket #{t_id}!", ephemeral=True)

    admin_guild_ids = [int(GUILD_ID)] if GUILD_ID.isdigit() else None

    @b.slash_command(
        name="panel",
        description="Show the ticket admin panel here without needing to scroll up",
        guild_ids=admin_guild_ids,
    )
    async def panel_command(
        inter: disnake.ApplicationCommandInteraction,
        id: int | None = commands.Param(default=None, description="Optional ticket ID (defaults to current channel's ticket)"),
    ):
        await _show_panel_interactive(inter, id)

    @b.slash_command(
        name="ticket_panel",
        description="Display or refresh the Ticket Admin Panel in this channel",
        guild_ids=admin_guild_ids,
    )
    async def ticket_panel_command(
        inter: disnake.ApplicationCommandInteraction,
        id: int | None = commands.Param(default=None, description="Optional ticket ID (defaults to current channel's ticket)"),
    ):
        await _show_panel_interactive(inter, id)

    @b.event
    async def on_message(message: disnake.Message):
        if not message.guild or message.author.bot:
            return
        if b.user and message.author.id == b.user.id:
            return

        if not ticket_bridge.is_configured():
            return

        cat_id = str(getattr(message.channel, "category_id", "") or "")
        target_cat_id = str(TICKETS_CATEGORY_ID).strip()
        ch_id = str(message.channel.id)

        assert ticket_bridge.load_suggestions is not None
        data = ticket_bridge.load_suggestions()
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

        sender_discord_id = str(message.author.id)

        assert ticket_bridge.is_website_admin is not None
        if not ticket_bridge.is_website_admin(sender_discord_id):
            log.info(
                f"[Disnake Bot] Ignored message from non-website-admin {message.author} "
                f"(ID: {sender_discord_id}) in #{getattr(message.channel, 'name', ch_id)}: "
                f"author is not an administrator on the website."
            )
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

        admin_entry = None
        if ticket_bridge.load_admins:
            admins_data = ticket_bridge.load_admins()
            admin_entry = admins_data.get("admins", {}).get(sender_discord_id)
            if not admin_entry:
                for k, v in admins_data.get("admins", {}).items():
                    if isinstance(v, dict) and str(v.get("discord_id", "")).strip() == sender_discord_id:
                        admin_entry = v
                        break

        configured_admin_name = admin_entry.get("username") if admin_entry else None
        sender_name = configured_admin_name or message.author.display_name or getattr(message.author, "global_name", None) or message.author.name or "Administrator"
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
        assert ticket_bridge.save_suggestions is not None
        ticket_bridge.save_suggestions(data)

        if ticket_bridge.broadcast_dashboard:
            ticket_bridge.broadcast_dashboard()

        log.info(f"[Disnake Bot] Ingested admin reply from #{getattr(message.channel, 'name', ch_id)} (Author: {sender_name}) for ticket #{target_ticket.get('id')}")

        try:
            await message.add_reaction("📨")
        except Exception:
            pass

        if ticket_bridge.broadcast_ticket_update:
            ticket_bridge.broadcast_ticket_update(
                target_ticket.get("id"),
                new_msg_obj,
                messages,
                target_ticket.get("discord_id"),
                target_ticket.get("anonymous")
            )

        try:
            notify_ticket_author_dm(
                ticket=target_ticket,
                event_type="message",
                details={
                    "sender_name": sender_name,
                    "message": msg_content
                }
            )
        except Exception as dm_err:
            log.warning(f"[Disnake Bot] Failed to send author DM on Discord admin message: {dm_err}")

def create_discord_ticket_channel(ticket: dict[str, Any]) -> str | None:
    global disnake_bot, disnake_bot_loop
    if not disnake_bot or not disnake_bot.is_ready() or not disnake_bot_loop or not disnake_bot_loop.is_running():
        log.warning("[Disnake Channel] Disnake bot is not ready; cannot create ticket channel.")
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

    bot_ref = disnake_bot

    async def _create_async():
        guild_id = int(GUILD_ID)
        guild = bot_ref.get_guild(guild_id)
        if not guild:
            guild = await bot_ref.fetch_guild(guild_id)

        cat_id = int(TICKETS_CATEGORY_ID)
        category = bot_ref.get_channel(cat_id)
        if not category:
            try:
                category = await bot_ref.fetch_channel(cat_id)
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
        try:
            panel_embed, panel_view = build_ticket_panel(
                ticket_id=ticket_id,  # pyright: ignore[reportArgumentType]
                ticket_type=ticket_type,
                current_status=ticket.get("status") or ("open" if is_bug else "pending")
            )
            await ch.send(embed=panel_embed, view=panel_view)
        except Exception as panel_err:
            log.warning(f"[Disnake Channel] Failed to send ticket panel: {panel_err}", exc_info=True)
        return str(ch.id)

    try:
        future = asyncio.run_coroutine_threadsafe(_create_async(), disnake_bot_loop)
        channel_id = future.result(timeout=10)
        log.info(f"[Disnake Channel] Created Discord channel #{channel_name} ({channel_id}) for ticket #{ticket_id}")
        return channel_id
    except Exception as ex:
        log.error(f"[Disnake Channel] Error creating channel: {ex}", exc_info=True)
        return None

def forward_ticket_reply_to_discord(
    channel_id: str,
    message_text: str,
    sender_name: str,
    is_admin: bool,
) -> str | None:
    global disnake_bot, disnake_bot_loop
    if not disnake_bot or not disnake_bot.is_ready() or not disnake_bot_loop or not disnake_bot_loop.is_running():
        return None

    sender_label = "Administrator" if is_admin else "Ticket Author"
    content = f"**[{sender_label}] {sender_name}**:\n{message_text}"
    bot_ref = disnake_bot

    async def _send_fwd_async():
        ch = bot_ref.get_channel(int(channel_id))
        if not ch:
            ch = await bot_ref.fetch_channel(int(channel_id))

        if not ch or not isinstance(ch, disnake.TextChannel):
            log.warning(f"[Disnake Forward] Channel {channel_id} is not a text channel or doesn't exist.")
            return None

        sent = await ch.send(content=content)
        return str(sent.id)

    try:
        fut = asyncio.run_coroutine_threadsafe(_send_fwd_async(), disnake_bot_loop)
        return fut.result(timeout=8)
    except Exception as ex:
        log.warning(f"[Disnake Forward] Failed to forward message to Discord: {ex}")
        return None

def start_bot_thread(
    load_suggestions: Callable[[], dict[str, Any]] | None = None,
    save_suggestions: Callable[[dict[str, Any]], None] | None = None,
    load_admins: Callable[[], dict[str, Any]] | None = None,
    is_website_admin: Callable[[str], bool] | None = None,
    broadcast_dashboard: Callable[[], None] | None = None,
    broadcast_ticket_update: Callable[..., None] | None = None,
    get_servers_data: Callable[[bool], dict[str, Any]] | None = None,
    token: str | None = None,
) -> threading.Thread | None:
    """
    Spawns the Disnake Discord bot in a background daemon thread, wiring the ticket bridge callbacks.
    """
    configure_ticket_bridge(
        load_suggestions=load_suggestions,
        save_suggestions=save_suggestions,
        load_admins=load_admins,
        is_website_admin=is_website_admin,
        broadcast_dashboard=broadcast_dashboard,
        broadcast_ticket_update=broadcast_ticket_update,
    )

    bot_token = token or TOKEN or os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if not bot_token:
        log.warning("[Disnake Bot] DISCORD_BOT_TOKEN is not configured; Disnake bot is disabled.")
        return None

    def _worker():
        global disnake_bot, disnake_bot_loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        disnake_bot_loop = loop

        bot = create_bot_instance(data_supplier=get_servers_data)
        disnake_bot = bot

        try:
            loop.run_until_complete(bot.start(bot_token))
        except disnake.errors.PrivilegedIntentsRequired:
            log.warning("[Disnake Bot] Privileged Message Content Intent is disabled in Discord Developer Portal. Retrying with basic intents...")
            try:
                intents = disnake.Intents.default()
                intents.message_content = False
                intents.guilds = True
                bot = commands.InteractionBot(
                    intents=intents,
                    test_guilds=None,
                    default_install_types=disnake.ApplicationInstallTypes.all(),
                    default_contexts=disnake.InteractionContextTypes.all(),
                )
                bot.rbwr = RBWRClient(data_supplier=get_servers_data)  # pyright: ignore[reportAttributeAccessIssue]
                register_bot_events_and_commands(bot)
                disnake_bot = bot
                loop.run_until_complete(bot.start(bot_token))
            except Exception as retry_err:
                log.error(f"[Disnake Bot] Fallback start failed: {retry_err}")
        except Exception as e:
            log.error(f"[Disnake Bot] Bot encountered error: {e}", exc_info=True)

    thread = threading.Thread(target=_worker, daemon=True, name="DisnakeBotThread")
    thread.start()
    return thread

if __name__ == "__main__":
    bot_token = TOKEN or os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if not bot_token:
        log.error("DISCORD_BOT_TOKEN is not set in environment or .env file.")
        exit(1)

    standalone_bot = create_bot_instance()
    standalone_bot.run(bot_token)