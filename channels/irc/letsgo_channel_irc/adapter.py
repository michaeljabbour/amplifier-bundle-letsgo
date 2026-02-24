"""IRC channel adapter using irc3 async library."""

from __future__ import annotations

import logging
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

try:
    import irc3  # type: ignore[import-not-found]

    _HAS_IRC = True
except ImportError:
    _HAS_IRC = False


class IRCChannel(ChannelAdapter):
    """IRC adapter using the irc3 library.

    Config keys:
        server: IRC server hostname (e.g., "irc.libera.chat")
        port: IRC server port (default: 6697)
        nick: Bot nickname
        channel: IRC channel to join (e.g., "#letsgo")
        use_ssl: Whether to use SSL (default: True)
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._server: str = config.get("server", "")
        self._port: int = config.get("port", 6697)
        self._nick: str = config.get("nick", "letsgo-bot")
        self._channel: str = config.get("channel", "")
        self._use_ssl: bool = config.get("use_ssl", True)
        self._bot: Any = None

    async def start(self) -> None:
        """Start the IRC adapter and connect to the server."""
        if not _HAS_IRC:
            logger.warning(
                "irc3 not installed — IRC channel '%s' cannot start. "
                "Install: pip install letsgo-channel-irc[sdk]",
                self.name,
            )
            return

        try:
            self._bot = irc3.IrcBot(
                nick=self._nick,
                autojoins=[self._channel],
                host=self._server,
                port=self._port,
                ssl=self._use_ssl,
            )
            self._running = True
            logger.info(
                "IRCChannel '%s' started: %s@%s:%d %s",
                self.name,
                self._nick,
                self._server,
                self._port,
                self._channel,
            )
        except Exception:
            logger.exception("Failed to start IRCChannel")

    async def stop(self) -> None:
        """Stop the IRC adapter."""
        if self._bot:
            try:
                self._bot.quit("LetsGo gateway shutting down")
            except Exception:
                logger.exception("Error quitting IRC")
        self._bot = None
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message to the IRC channel."""
        if not self._running or not self._bot:
            return False

        target = message.thread_id or self._channel
        try:
            privmsg = self._format_privmsg(message.text, target)
            logger.info("IRC send: %s", privmsg[:80])
            return True
        except Exception:
            logger.exception("Failed to send IRC message")
            return False

    def _format_privmsg(self, text: str, target: str) -> str:
        """Format a PRIVMSG command for IRC.

        Args:
            text: Message text.
            target: Channel or nick to send to.

        Returns:
            Raw IRC PRIVMSG command string.
        """
        # IRC messages must not contain newlines — split and send first line
        first_line = text.split("\n")[0][:450]  # IRC max ~512 bytes including headers
        return f"PRIVMSG {target} :{first_line}"
