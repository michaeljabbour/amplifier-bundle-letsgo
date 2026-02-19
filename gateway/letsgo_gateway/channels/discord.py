"""Discord channel adapter.

Full production adapter ported from tinyclaw's ``discord-client.ts``.
Gracefully degrades when ``discord.py`` is not installed.

Config keys
-----------
bot_token : str
    Discord bot token.
files_dir : str
    Path for downloaded files (default ``~/.letsgo/gateway/files``).
max_message_length : int
    Message split threshold (default ``2000``).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from ..models import ChannelType, InboundMessage, OutboundMessage
from .base import ChannelAdapter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------

try:
    import discord
    from discord import DMChannel, File, Intents, Message

    _discord_available = True
except ImportError:  # pragma: no cover
    _discord_available = False

    if TYPE_CHECKING:
        import discord
        from discord import DMChannel, File, Intents, Message

try:
    import aiohttp as _aiohttp
except ImportError:
    _aiohttp = None  # type: ignore[assignment]

# Async command handler: (sender_id, args_text) -> reply text
CommandHandler = Callable[[str, str], Awaitable[str]]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def split_message(text: str, max_length: int = 2000) -> list[str]:
    """Split *text* into chunks of at most *max_length* characters.

    Break preference: newline > space > hard cut.
    The delimiter character is consumed (not included in the next chunk).
    """
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        # Try to split at a newline boundary
        idx = remaining.rfind("\n", 0, max_length)
        # Fall back to space boundary
        if idx <= 0:
            idx = remaining.rfind(" ", 0, max_length)

        if idx > 0:
            # Split at the delimiter and skip past it
            chunks.append(remaining[:idx])
            remaining = remaining[idx + 1 :]
        else:
            # Hard cut -- no good boundary found
            chunks.append(remaining[:max_length])
            remaining = remaining[max_length:]

    return chunks


def _sanitize_filename(name: str) -> str:
    """Remove characters unsafe for filenames."""
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", os.path.basename(name)).strip()
    return clean or "file.bin"


def _unique_path(directory: Path, preferred: str) -> Path:
    """Return a non-colliding path inside *directory*."""
    clean = _sanitize_filename(preferred)
    stem = Path(clean).stem
    suffix = Path(clean).suffix
    candidate = directory / clean
    counter = 1
    while candidate.exists():
        candidate = directory / f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate


# ---------------------------------------------------------------------------
# Internal pending-message tracker
# ---------------------------------------------------------------------------


class _PendingMessage:
    """Tracks an inbound DM awaiting a response."""

    __slots__ = ("message", "channel", "created_mono")

    def __init__(self, message: Any, channel: Any) -> None:
        self.message = message
        self.channel = channel
        self.created_mono: float = time.monotonic()


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class DiscordChannel(ChannelAdapter):
    """Discord DM adapter -- requires ``discord.py``.

    When the dependency is missing the adapter loads without error but all
    operations are no-ops.  Install the dependency to enable it::

        pip install discord.py

    Config:
        bot_token (str): Discord bot token.
        files_dir (str): Directory for downloaded attachments.
        max_message_length (int): Max chars per outbound message chunk.
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._bot_token: str = config.get("bot_token", "")
        self._files_dir = Path(
            config.get("files_dir", os.path.expanduser("~/.letsgo/gateway/files"))
        )
        self._max_msg_len: int = int(config.get("max_message_length", 2000))
        self._available: bool = _discord_available

        # Discord client (created in start)
        self._client: discord.Client | None = None
        self._bot_task: asyncio.Task[None] | None = None
        self._typing_task: asyncio.Task[None] | None = None

        # Pending inbound messages awaiting a response (typing + reply)
        self._pending: dict[str, _PendingMessage] = {}

        # Optional per-command handlers registered by the gateway
        self._command_handlers: dict[str, CommandHandler] = {}

        # aiohttp session for attachment downloads
        self._http_session: Any = None

    # ---- command registration ------------------------------------------------

    def register_command(self, name: str, handler: CommandHandler) -> None:
        """Register an async *handler* for ``/name`` commands."""
        self._command_handlers[name.lower().lstrip("/")] = handler

    # ---- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        if not self._available:
            logger.warning(
                "Discord adapter '%s' requires discord.py -- "
                "install with: pip install discord.py",
                self.name,
            )
            return

        if not self._bot_token:
            logger.error("Discord adapter '%s': bot_token not configured", self.name)
            return

        self._files_dir.mkdir(parents=True, exist_ok=True)

        intents = Intents.default()
        intents.message_content = True
        intents.dm_messages = True

        self._client = discord.Client(intents=intents)
        self._register_events()

        # Run bot in a background task so start() returns immediately
        self._bot_task = asyncio.create_task(
            self._run_bot(), name=f"discord-bot-{self.name}"
        )
        self._typing_task = asyncio.create_task(
            self._typing_loop(), name=f"discord-typing-{self.name}"
        )
        self._running = True
        logger.info("Discord adapter '%s' starting", self.name)

    async def stop(self) -> None:
        if not self._available or not self._running:
            return

        self._running = False

        if self._typing_task and not self._typing_task.done():
            self._typing_task.cancel()

        if self._client:
            await self._client.close()

        if self._bot_task and not self._bot_task.done():
            self._bot_task.cancel()
            try:
                await self._bot_task
            except asyncio.CancelledError:
                pass

        if self._http_session:
            await self._http_session.close()
            self._http_session = None

        self._pending.clear()
        logger.info("Discord adapter '%s' stopped", self.name)

    # ---- bot runner ----------------------------------------------------------

    async def _run_bot(self) -> None:
        """Run the discord client (blocks until closed)."""
        try:
            assert self._client is not None
            await self._client.start(self._bot_token)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Discord bot '%s' crashed", self.name)

    def _register_events(self) -> None:
        """Wire discord.py event handlers to the client."""
        client = self._client
        assert client is not None

        @client.event
        async def on_ready() -> None:
            logger.info("Discord bot '%s' connected as %s", self.name, client.user)

        @client.event
        async def on_message(message: Message) -> None:
            await self._handle_message(message)

    # ---- inbound -------------------------------------------------------------

    async def _handle_message(self, message: Message) -> None:
        """Process a single inbound Discord message."""
        # Skip bot messages
        if message.author.bot:
            return

        # DM only -- skip guild (server) messages
        if message.guild is not None:
            return

        has_content = bool(message.content and message.content.strip())
        has_attachments = len(message.attachments) > 0
        if not has_content and not has_attachments:
            return

        sender_id = str(message.author.id)
        sender_label = message.author.display_name or message.author.name
        text = message.content or ""
        stripped = text.strip()

        # -- channel commands (handled before routing to _on_message) ----------

        if re.match(r"^[!/]agents?$", stripped, re.IGNORECASE):
            reply = await self._exec_command("agent", sender_id, "")
            await message.reply(reply)
            return

        reset_m = re.match(r"^[!/]reset(?:\s+(.+))?$", stripped, re.IGNORECASE)
        if reset_m:
            reply = await self._exec_command("reset", sender_id, reset_m.group(1) or "")
            await message.reply(reply)
            return

        # -- typing indicator --------------------------------------------------

        if isinstance(message.channel, DMChannel):
            try:
                await message.channel.trigger_typing()
            except Exception:
                pass

        # -- download attachments ----------------------------------------------

        downloaded: list[str] = []
        for att in message.attachments:
            try:
                local = await self._download_attachment(att)
                downloaded.append(str(local))
                logger.info(
                    "Downloaded %s (%s)",
                    local.name,
                    att.content_type or "unknown",
                )
            except Exception:
                logger.exception("Failed to download %s", att.filename)

        full_text = text
        if downloaded:
            refs = "\n".join(f"[file: {p}]" for p in downloaded)
            full_text = f"{full_text}\n\n{refs}" if full_text else refs

        # -- track pending for typing indicator --------------------------------

        msg_key = f"{sender_id}_{message.id}"
        if isinstance(message.channel, DMChannel):
            self._pending[msg_key] = _PendingMessage(message, message.channel)
        self._evict_stale()

        # -- route to callback -------------------------------------------------

        if not self._on_message:
            return

        inbound = InboundMessage(
            channel=ChannelType.DISCORD,
            channel_name=self.name,
            sender_id=sender_id,
            sender_label=sender_label,
            text=full_text,
            thread_id=msg_key,
            attachments=[{"path": p} for p in downloaded],
            raw={
                "message_id": str(message.id),
                "author_id": sender_id,
                "author_name": sender_label,
            },
        )
        try:
            response_text = await self._on_message(inbound)
            if response_text:
                await self.send(
                    OutboundMessage(
                        channel=ChannelType.DISCORD,
                        channel_name=self.name,
                        thread_id=msg_key,
                        text=response_text,
                    )
                )
        except Exception:
            logger.exception("on_message callback failed for '%s'", self.name)
        finally:
            self._pending.pop(msg_key, None)

    # ---- commands ------------------------------------------------------------

    async def _exec_command(self, name: str, sender_id: str, args: str) -> str:
        """Execute a registered command or return a sensible default."""
        handler = self._command_handlers.get(name)
        if handler:
            try:
                return await handler(sender_id, args)
            except Exception:
                logger.exception("Command /%s failed", name)
                return "Command failed -- check server logs."

        if name == "agent":
            return "No agents configured."
        if name == "reset":
            return "Reset is not configured for this adapter."
        return f"Unknown command: /{name}"

    # ---- attachment download -------------------------------------------------

    async def _download_attachment(self, attachment: Any) -> Path:
        """Download a single Discord attachment to *files_dir*."""
        if self._http_session is None:
            if _aiohttp is None:
                raise RuntimeError("aiohttp is required for attachment downloads")
            self._http_session = _aiohttp.ClientSession()

        preferred = f"discord_{attachment.id}_{attachment.filename or 'file.bin'}"
        dest = _unique_path(self._files_dir, preferred)

        async with self._http_session.get(attachment.url) as resp:
            resp.raise_for_status()
            dest.write_bytes(await resp.read())

        return dest

    # ---- typing indicator loop -----------------------------------------------

    async def _typing_loop(self) -> None:
        """Refresh typing indicator every 8 s for all pending messages."""
        try:
            while self._running:
                await asyncio.sleep(8)
                for pm in list(self._pending.values()):
                    try:
                        await pm.channel.trigger_typing()
                    except Exception:
                        pass  # typing failures are non-critical
        except asyncio.CancelledError:
            pass

    def _evict_stale(self, max_age: float = 600.0) -> None:
        """Remove pending entries older than *max_age* seconds."""
        now = time.monotonic()
        stale = [k for k, v in self._pending.items() if now - v.created_mono > max_age]
        for k in stale:
            del self._pending[k]

    # ---- outbound ------------------------------------------------------------

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message back to a Discord user.

        Uses *thread_id* to look up the pending inbound message for a reply.
        Falls back to proactive DM via the sender ID encoded in thread_id
        (format ``<sender_id>_<discord_msg_id>``).
        """
        if not self._available or self._client is None:
            logger.warning(
                "Discord adapter '%s' not available -- cannot send",
                self.name,
            )
            return False

        # Resolve target channel
        pending = self._pending.get(message.thread_id or "")
        channel: DMChannel | None = pending.channel if pending else None

        # Proactive send -- extract sender_id from thread_id
        if channel is None and message.thread_id:
            user_id_str = message.thread_id.split("_", 1)[0]
            try:
                user = await self._client.fetch_user(int(user_id_str))
                channel = await user.create_dm()
            except Exception:
                logger.exception("Could not open DM for sender %s", user_id_str)

        if channel is None:
            logger.warning(
                "No channel for thread_id=%s -- dropping message",
                message.thread_id,
            )
            return False

        try:
            # Send file attachments first
            if message.attachments:
                files: list[File] = []
                for att in message.attachments:
                    fp = att.get("path") or att.get("file")
                    if fp and os.path.isfile(fp):
                        files.append(File(fp))
                if files:
                    await channel.send(files=files)
                    logger.info("Sent %d file(s) to Discord", len(files))

            # Text -- split for Discord's character limit
            if message.text:
                chunks = split_message(message.text, self._max_msg_len)
                for i, chunk in enumerate(chunks):
                    if i == 0 and pending:
                        await pending.message.reply(chunk)
                    else:
                        await channel.send(chunk)

            return True
        except Exception:
            logger.exception("Failed to send Discord message")
            return False
