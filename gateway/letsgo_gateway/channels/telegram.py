"""Telegram channel adapter using python-telegram-bot v20+.

Gracefully degrades when ``python-telegram-bot`` is not installed.

Config keys:
    bot_token: Telegram Bot API token from @BotFather
    files_dir: Path for downloaded files (default: ~/.letsgo/gateway/files)
    max_message_length: Message split threshold (default: 4096)
    allowed_chat_ids: Optional list of whitelisted chat IDs
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from ..models import ChannelType, InboundMessage, OutboundMessage
from .base import ChannelAdapter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Graceful degradation: importable even without python-telegram-bot
# ---------------------------------------------------------------------------
_available = False
try:
    from telegram import Bot, BotCommand, Message, Update
    from telegram.constants import ChatAction
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )

    _available = True
except ImportError:  # pragma: no cover
    pass

# ---------------------------------------------------------------------------
# MIME -> extension mapping (ported from tinyclaw)
# ---------------------------------------------------------------------------
_MIME_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "video/mp4": ".mp4",
    "application/pdf": ".pdf",
}

# Extension sets for type-aware sending
_PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_AUDIO_EXTS = {".mp3", ".ogg", ".wav", ".m4a"}
_VIDEO_EXTS = {".mp4", ".avi", ".mov", ".webm"}


def _ext_from_mime(mime: str | None) -> str:
    """Derive a file extension from a MIME type."""
    if not mime:
        return ""
    return _MIME_EXT.get(mime, "")


def _sanitize_filename(name: str) -> str:
    """Strip unsafe characters, collapse to a safe basename."""
    import re

    base = os.path.basename(name)
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base).strip()
    return clean if clean else "file.bin"


def _unique_path(directory: Path, preferred: str) -> Path:
    """Return a non-colliding file path inside *directory*."""
    clean = _sanitize_filename(preferred)
    stem = Path(clean).stem
    ext = Path(clean).suffix
    candidate = directory / clean
    counter = 1
    while candidate.exists():
        candidate = directory / f"{stem}_{counter}{ext}"
        counter += 1
    return candidate


def _split_message(text: str, max_length: int = 4096) -> list[str]:
    """Split *text* respecting newline > space > hard-cut boundaries."""
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break
        # Prefer newline boundary
        idx = remaining.rfind("\n", 0, max_length)
        # Fall back to space
        if idx <= 0:
            idx = remaining.rfind(" ", 0, max_length)
        # Hard-cut
        if idx <= 0:
            idx = max_length
        chunks.append(remaining[:idx])
        remaining = remaining[idx:].lstrip("\n")
    return chunks


# ---------------------------------------------------------------------------
# TelegramChannel adapter
# ---------------------------------------------------------------------------


class TelegramChannel(ChannelAdapter):
    """Telegram adapter -- requires ``python-telegram-bot>=20``.

    When the dependency is missing the adapter loads without error but all
    operations are no-ops.  Install the real dependency to enable it::

        pip install "python-telegram-bot>=20"
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._bot_token: str = config.get("bot_token", "")
        self._files_dir = Path(
            config.get("files_dir", os.path.expanduser("~/.letsgo/gateway/files"))
        )
        self._max_message_length: int = int(config.get("max_message_length", 4096))
        self._allowed_chat_ids: list[int] = [
            int(c) for c in config.get("allowed_chat_ids", [])
        ]
        # SAFETY: Default to DM-only. Groups require explicit opt-in.
        # Set allow_groups: true in config to enable group messages.
        self._allow_groups: bool = config.get("allow_groups", False)
        self._available: bool = _available
        self._app: Any = None  # Application[...] when available

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if not self._available:
            logger.warning(
                "Telegram adapter '%s' requires python-telegram-bot -- "
                "install with: pip install 'python-telegram-bot>=20'",
                self.name,
            )
            return

        if not self._bot_token:
            logger.error(
                "Telegram adapter '%s': bot_token is not configured", self.name
            )
            return

        # Ensure files directory exists
        self._files_dir.mkdir(parents=True, exist_ok=True)

        # Build the Application
        self._app = Application.builder().token(self._bot_token).build()

        # Register command handlers (before the catch-all message handler)
        self._app.add_handler(CommandHandler("agent", self._cmd_agent))
        self._app.add_handler(CommandHandler("reset", self._cmd_reset))

        # Register message handler (text + all media types)
        self._app.add_handler(
            MessageHandler(
                filters.TEXT
                | filters.PHOTO
                | filters.Document.ALL
                | filters.AUDIO
                | filters.VOICE
                | filters.VIDEO
                | filters.VIDEO_NOTE
                | filters.Sticker.ALL,
                self._handle_message,
            )
        )

        # Register bot commands in Telegram's "/" menu
        try:
            await self._app.bot.set_my_commands(
                [
                    BotCommand("agent", "List available agents"),
                    BotCommand("reset", "Reset conversation history"),
                ]
            )
        except Exception:
            logger.warning("Telegram '%s': failed to register bot commands", self.name)

        # Initialize, start application, begin polling
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

        self._running = True
        logger.info("Telegram adapter '%s' started (polling)", self.name)

    async def stop(self) -> None:
        if not self._available or not self._app:
            return

        try:
            if self._app.updater and self._app.updater.running:
                await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        except Exception:
            logger.exception("Telegram '%s': error during shutdown", self.name)
        finally:
            self._running = False
            logger.info("Telegram adapter '%s' stopped", self.name)

    # ------------------------------------------------------------------
    # Inbound: commands
    # ------------------------------------------------------------------

    async def _cmd_agent(
        self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"
    ) -> None:
        """Handle /agent -- forward to gateway callback."""
        if not update.effective_message or not update.effective_chat:
            return
        if not self._is_chat_allowed(update.effective_chat.id):
            return
        await self._dispatch_inbound(update.effective_message, text="/agent")

    async def _cmd_reset(
        self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"
    ) -> None:
        """Handle /reset -- forward full command text to gateway callback."""
        if not update.effective_message or not update.effective_chat:
            return
        if not self._is_chat_allowed(update.effective_chat.id):
            return
        raw_text = update.effective_message.text or "/reset"
        await self._dispatch_inbound(update.effective_message, text=raw_text)

    # ------------------------------------------------------------------
    # Inbound: messages + media
    # ------------------------------------------------------------------

    async def _handle_message(
        self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"
    ) -> None:
        """Handle every non-command message (text, photos, documents, ...)."""
        msg = update.effective_message
        if msg is None or update.effective_chat is None:
            return
        if not self._is_chat_allowed(update.effective_chat.id):
            return

        # SAFETY: DM-only by default. Drop group/supergroup/channel messages
        # unless allow_groups is explicitly True in config.
        chat_type = update.effective_chat.type
        if not self._allow_groups and chat_type != "private":
            logger.debug(
                "Telegram '%s': dropping non-DM message (chat_type=%s, "
                "set allow_groups: true to enable)",
                self.name,
                chat_type,
            )
            return

        # Send typing indicator
        try:
            await update.effective_chat.send_action(ChatAction.TYPING)
        except Exception:
            pass

        # Gather text + media
        text = msg.text or msg.caption or ""
        downloaded: list[str] = []
        msg_id = str(msg.message_id)
        bot = self._app.bot

        # Photo -- pick largest resolution
        if msg.photo:
            fpath = await self._download_media(
                bot,
                msg.photo[-1].file_id,
                ".jpg",
                msg_id,
                f"photo_{msg_id}.jpg",
            )
            if fpath:
                downloaded.append(fpath)

        # Document
        if msg.document:
            ext = (
                Path(msg.document.file_name).suffix
                if msg.document.file_name
                else _ext_from_mime(msg.document.mime_type)
            ) or ".bin"
            fpath = await self._download_media(
                bot,
                msg.document.file_id,
                ext,
                msg_id,
                msg.document.file_name,
            )
            if fpath:
                downloaded.append(fpath)

        # Audio
        if msg.audio:
            ext = _ext_from_mime(msg.audio.mime_type) or ".mp3"
            fpath = await self._download_media(
                bot,
                msg.audio.file_id,
                ext,
                msg_id,
                msg.audio.file_name,
            )
            if fpath:
                downloaded.append(fpath)

        # Voice
        if msg.voice:
            fpath = await self._download_media(
                bot,
                msg.voice.file_id,
                ".ogg",
                msg_id,
                f"voice_{msg_id}.ogg",
            )
            if fpath:
                downloaded.append(fpath)

        # Video
        if msg.video:
            ext = _ext_from_mime(msg.video.mime_type) or ".mp4"
            fpath = await self._download_media(
                bot,
                msg.video.file_id,
                ext,
                msg_id,
                msg.video.file_name,
            )
            if fpath:
                downloaded.append(fpath)

        # Video note (round video)
        if msg.video_note:
            fpath = await self._download_media(
                bot,
                msg.video_note.file_id,
                ".mp4",
                msg_id,
                f"video_note_{msg_id}.mp4",
            )
            if fpath:
                downloaded.append(fpath)

        # Sticker
        if msg.sticker:
            if msg.sticker.is_animated:
                ext = ".tgs"
            elif msg.sticker.is_video:
                ext = ".webm"
            else:
                ext = ".webp"
            fpath = await self._download_media(
                bot,
                msg.sticker.file_id,
                ext,
                msg_id,
                f"sticker_{msg_id}{ext}",
            )
            if fpath:
                downloaded.append(fpath)
            if not text:
                text = f"[Sticker: {msg.sticker.emoji or 'sticker'}]"

        # Skip empty messages
        if not text.strip() and not downloaded:
            return

        # Append file references to message text
        full_text = text
        if downloaded:
            refs = "\n".join(f"[file: {f}]" for f in downloaded)
            full_text = f"{text}\n\n{refs}" if text else refs

        await self._dispatch_inbound(msg, text=full_text, attachments=downloaded)

    # ------------------------------------------------------------------
    # Inbound helpers
    # ------------------------------------------------------------------

    async def _dispatch_inbound(
        self,
        msg: "Message",
        *,
        text: str,
        attachments: list[str] | None = None,
    ) -> None:
        """Normalise a Telegram message into InboundMessage, invoke callback."""
        if not self._on_message:
            return

        sender = msg.from_user
        sender_label = ""
        if sender:
            sender_label = sender.first_name or ""
            if sender.last_name:
                sender_label += f" {sender.last_name}"

        inbound = InboundMessage(
            channel=ChannelType.TELEGRAM,
            channel_name=self.name,
            sender_id=str(msg.chat.id),
            sender_label=sender_label,
            text=text,
            thread_id=str(msg.chat.id),
            attachments=[{"path": p} for p in (attachments or [])],
            raw={
                "message_id": msg.message_id,
                "chat_id": msg.chat.id,
                "chat_type": msg.chat.type,
            },
        )

        try:
            response_text = await self._on_message(inbound)
            if response_text:
                await self._send_text(msg.chat.id, response_text)
        except Exception:
            logger.exception("Telegram '%s': callback error", self.name)

    async def _download_media(
        self,
        bot: "Bot",
        file_id: str,
        ext: str,
        msg_id: str,
        original_name: str | None = None,
    ) -> str | None:
        """Download a Telegram file by *file_id*, return local path or None."""
        try:
            tg_file = await bot.get_file(file_id)
            source = original_name or f"file_{msg_id}{ext}"
            # Ensure extension
            if not Path(source).suffix:
                source = f"{source}{ext or '.bin'}"
            preferred = f"telegram_{msg_id}_{_sanitize_filename(source)}"
            dest = _unique_path(self._files_dir, preferred)
            await tg_file.download_to_drive(dest)
            logger.info("Telegram '%s': downloaded %s", self.name, dest.name)
            return str(dest)
        except Exception:
            logger.exception(
                "Telegram '%s': failed to download file %s", self.name, file_id
            )
            return None

    def _is_chat_allowed(self, chat_id: int) -> bool:
        """Return True if *chat_id* passes the allowlist (empty = all)."""
        if not self._allowed_chat_ids:
            return True
        return chat_id in self._allowed_chat_ids

    # ------------------------------------------------------------------
    # Outbound: send
    # ------------------------------------------------------------------

    async def send(self, message: OutboundMessage) -> bool:
        """Send an outbound message to Telegram.

        Resolves the target chat from ``thread_id`` (the chat_id stored
        during inbound processing).  Supports proactive messaging when
        thread_id is set to a known chat_id.
        """
        if not self._available or not self._app:
            logger.warning(
                "Telegram adapter '%s' is not available -- "
                "cannot send message (install python-telegram-bot)",
                self.name,
            )
            return False

        chat_id_str = message.thread_id
        if not chat_id_str:
            logger.warning("Telegram '%s': no thread_id on outbound message", self.name)
            return False

        try:
            chat_id = int(chat_id_str)
        except (ValueError, TypeError):
            logger.error(
                "Telegram '%s': invalid thread_id '%s'", self.name, chat_id_str
            )
            return False

        bot = self._app.bot

        try:
            # Send attached files first (type-aware)
            for att in message.attachments:
                file_path = att.get("path", "")
                if not file_path or not os.path.isfile(file_path):
                    continue
                await self._send_file(bot, chat_id, file_path)

            # Send text (split if necessary)
            if message.text:
                await self._send_text(chat_id, message.text)

            return True
        except Exception:
            logger.exception("Telegram '%s': failed to send message", self.name)
            return False

    async def _send_text(self, chat_id: int, text: str) -> None:
        """Send text, splitting at the configured max length."""
        bot = self._app.bot
        chunks = _split_message(text, self._max_message_length)
        for chunk in chunks:
            await bot.send_message(chat_id=chat_id, text=chunk)

    async def _send_file(self, bot: "Bot", chat_id: int, file_path: str) -> None:
        """Send a file using the appropriate Telegram method based on extension."""
        ext = Path(file_path).suffix.lower()
        try:
            with open(file_path, "rb") as fh:
                if ext in _PHOTO_EXTS:
                    await bot.send_photo(chat_id=chat_id, photo=fh)
                elif ext in _AUDIO_EXTS:
                    await bot.send_audio(chat_id=chat_id, audio=fh)
                elif ext in _VIDEO_EXTS:
                    await bot.send_video(chat_id=chat_id, video=fh)
                else:
                    await bot.send_document(chat_id=chat_id, document=fh)
            logger.info("Telegram '%s': sent file %s", self.name, Path(file_path).name)
        except Exception:
            logger.exception(
                "Telegram '%s': failed to send file %s", self.name, file_path
            )
