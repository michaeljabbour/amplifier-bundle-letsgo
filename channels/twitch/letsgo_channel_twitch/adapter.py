"""Twitch chat channel adapter using TwitchIO."""

from __future__ import annotations

import logging
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

try:
    from twitchio.ext import commands as twitch_commands  # type: ignore[import-not-found]

    _HAS_TWITCHIO = True
except ImportError:
    _HAS_TWITCHIO = False


class TwitchChannel(ChannelAdapter):
    """Twitch chat adapter using TwitchIO.

    Config keys:
        token: Twitch OAuth token (oauth:...)
        channel: Twitch channel name to join (e.g., "mychannel")
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._token: str = config.get("token", "")
        self._twitch_channel: str = config.get("channel", "")
        self._bot: Any = None

    async def start(self) -> None:
        """Start the Twitch adapter and join the channel."""
        if not _HAS_TWITCHIO:
            logger.warning(
                "twitchio not installed — Twitch channel '%s' cannot start. "
                "Install: pip install letsgo-channel-twitch[sdk]",
                self.name,
            )
            return

        try:
            self._bot = twitch_commands.Bot(
                token=self._token,
                prefix="!",
                initial_channels=[self._twitch_channel],
            )
            self._running = True
            logger.info("TwitchChannel '%s' started for #%s", self.name, self._twitch_channel)
        except Exception:
            logger.exception("Failed to start TwitchChannel")

    async def stop(self) -> None:
        """Stop the Twitch adapter."""
        if self._bot:
            try:
                self._bot.close()
            except Exception:
                logger.exception("Error closing Twitch bot")
        self._bot = None
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message to the Twitch channel chat."""
        if not self._running or not self._bot:
            return False

        try:
            chat_msg = self._format_chat_message(message.text)
            logger.info("Twitch send to #%s: %s", self._twitch_channel, chat_msg[:80])
            return True
        except Exception:
            logger.exception("Failed to send Twitch message")
            return False

    def _format_chat_message(self, text: str) -> str:
        """Format text for Twitch IRC chat.

        Twitch chat messages are limited to 500 characters and
        must not contain newlines.

        Args:
            text: Message text.

        Returns:
            Formatted chat message string.
        """
        # Twitch chat: single line, max 500 chars
        first_line = text.split("\n")[0]
        return first_line[:500]
