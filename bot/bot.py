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
        self.select_menu.callback = self._select_callback
        self.add_item(self.select_menu)

        self.discuss_button = disnake.ui.Button(
            label="Open Discussions",
            style=disnake.ButtonStyle.primary,
            custom_id=f"ticket_open_discussions:{ticket_id}",
            emoji="💬",
        )
        self.discuss_button.callback = self._discuss_callback
        self.add_item(self.discuss_button)

    async def _select_callback(self, inter: disnake.MessageInteraction):
        await handle_ticket_status_select(inter, self.ticket_id)

    async def _discuss_callback(self, inter: disnake.MessageInteraction):
        await handle_ticket_open_discussions(inter, self.ticket_id)

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

async def handle_ticket_status_select(inter: disnake.MessageInteraction, ticket_id: int):
    if inter.response.is_done():
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

    await inter.response.send_message(
        f"Ticket #{ticket_id} status updated from `{prev_status}` to **`{new_status.upper()}`** by {inter.author.mention}."
    )

async def handle_ticket_open_discussions(inter: disnake.MessageInteraction, ticket_id: int):
    if inter.response.is_done():
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
    try:
        if isinstance(dest_ch, disnake.ForumChannel):
            forum_post = await dest_ch.create_thread(
                name=thread_name,
                content=init_msg,
                embed=embed,
                allowed_mentions=disnake.AllowedMentions(users=True)
            )
            created_thread = forum_post.thread
        elif isinstance(dest_ch, disnake.TextChannel):
            created_thread = await dest_ch.create_thread(
                name=thread_name,
                type=disnake.ChannelType.public_thread
            )
            await created_thread.send(
                content=init_msg,
                embed=embed,
                allowed_mentions=disnake.AllowedMentions(users=True)
            )
        elif isinstance(dest_ch, disnake.Thread):
            await dest_ch.send(
                content=init_msg,
                embed=embed,
                allowed_mentions=disnake.AllowedMentions(users=True)
            )
            created_thread = dest_ch
        elif hasattr(dest_ch, "create_thread"):
            created_thread = await dest_ch.create_thread(name=thread_name)
            await created_thread.send(
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

def create_bot_instance(data_supplier: Callable[[bool], dict[str, Any]] | None = None) -> commands.InteractionBot:
    test_guilds = [int(GUILD_ID)] if GUILD_ID.isdigit() else None
    intents = disnake.Intents.default()
    intents.message_content = True
    intents.guilds = True

    new_bot = commands.InteractionBot(
        intents=intents,
        test_guilds=test_guilds,
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

def register_bot_events_and_commands(b: commands.InteractionBot):
    @b.event
    async def on_ready():
        log.info(f"[Disnake Bot] Connected and active as {b.user} (ID: {b.user.id if b.user else 'N/A'})")

    @b.slash_command(
        name="server",
        description="Downloading information about a public RBWR server",
    )
    async def server_command(
        inter: disnake.ApplicationCommandInteraction,
        id: str = commands.Param(description="Full Job ID or shortened ID, e.g., 77f6-4b2f"),
        info: str = commands.Param(
            description="Information you want to retrieve",
            choices=INFO_CHOICES,
        ),
    ):
        await inter.response.defer()

        client: RBWRClient = getattr(b, "rbwr", None) or RBWRClient()
        try:
            server = await client.find_server(id, public_only=True)
        except Exception as e:
            log.exception("RBWR API error")
            await inter.followup.send(f"Fault: `{e}`")
            return

        if not server or not is_server_public(server):
            await inter.followup.send(f"Server `{id}` not found or is private.")
            return

        job_id = str(server.get("jobId", id))
        short = client.short_id(job_id)
        players = get_player_count(server)

        embed = disnake.Embed(
            title="RBWR Public Server",
            description=f"**Server ID:** `{short}`\n**Job ID:** `{job_id}`",
            color=disnake.Color.green(),
        )
        embed.set_footer(text=f"Players: {players}")

        info_val = getattr(info, "value", info)
        add_info(embed, server, 1, info_val)
        add_info(embed, server, 2, info_val)

        await inter.followup.send(embed=embed)

    @b.slash_command(
        name="serverlist",
        description="Show list of active public RBWR servers",
    )
    async def serverlist_command(inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer()
        client: RBWRClient = getattr(b, "rbwr", None) or RBWRClient()
        try:
            payload = await client.fetch(public_only=True)
            servers = payload.get("data", {}).get("servers", [])
            public_servers = [s for s in servers if is_server_public(s)]

            if public_servers:
                server_lines = []
                for s in public_servers:
                    jid = str(s.get("jobId", ""))
                    short = client.short_id(jid)
                    players = get_player_count(s)
                    p_info = f" ({players} players)" if players != "?" else ""
                    server_lines.append(f"• `{short}`{p_info}")

                header = f"**Active Public Servers ({len(public_servers)}):**\n\n"
                body = "\n".join(server_lines)
                full_text = header + body
                if len(full_text) > 4000:
                    body = "\n".join(server_lines[:100])
                    full_text = header + body + f"\n... and {len(public_servers) - 100} more"
                description_text = full_text
            else:
                description_text = "No active public servers found."

            embed = disnake.Embed(
                title="Active RBWR Public Servers",
                description=description_text,
                color=disnake.Color.green(),
            )
            embed.set_footer(text=f"Total Public Servers: {len(public_servers)}")

            await inter.followup.send(embed=embed)

        except Exception as e:
            await inter.followup.send(f"Fault: `{e}`")

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

    @b.slash_command(
        name="ticket_panel",
        description="Display or refresh the Ticket Admin Panel in this channel",
    )
    async def ticket_panel_command(
        inter: disnake.ApplicationCommandInteraction,
        id: int | None = commands.Param(default=None, description="Optional ticket ID (defaults to current channel's ticket)"),
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
                test_guilds = [int(GUILD_ID)] if GUILD_ID.isdigit() else None
                bot = commands.InteractionBot(
                    intents=intents,
                    test_guilds=test_guilds,
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