"""Matrix channel adapter using matrix-nio."""

from __future__ import annotations

import logging
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

# Graceful degradation
_HAS_NIO = False
try:
    from nio import AsyncClient, RoomMessageText

    _HAS_NIO = True
except ImportError:
    pass


class MatrixChannel(ChannelAdapter):
    """Matrix messaging adapter using matrix-nio.

    Config keys:
        homeserver: Matrix homeserver URL (e.g., "https://matrix.org")
        user_id: Bot user ID (e.g., "@letsgo:matrix.org")
        access_token: Access token for authentication
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._homeserver: str = config.get("homeserver", "")
        self._user_id: str = config.get("user_id", "")
        self._access_token: str = config.get("access_token", "")
        self._client: Any = None  # AsyncClient when nio is available

    async def start(self) -> None:
        """Connect to the Matrix homeserver and start syncing."""
        if not _HAS_NIO:
            logger.warning(
                "matrix-nio not installed — Matrix channel '%s' cannot start. "
                "Install with: pip install letsgo-channel-matrix[nio]",
                self.name,
            )
            return

        if not self._homeserver:
            logger.error("No homeserver configured for Matrix channel '%s'", self.name)
            return

        try:
            self._client = AsyncClient(self._homeserver, self._user_id)
            self._client.access_token = self._access_token

            # Register message callback
            self._client.add_event_callback(self._on_room_message, RoomMessageText)

            self._running = True
            logger.info(
                "MatrixChannel '%s' connected to %s", self.name, self._homeserver
            )
            # Note: sync_forever() would be called in the daemon's event loop
        except Exception:
            logger.exception("Failed to start Matrix channel '%s'", self.name)

    async def stop(self) -> None:
        """Disconnect from the Matrix homeserver."""
        if self._client and _HAS_NIO:
            await self._client.close()
            self._client = None
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message to a Matrix room."""
        if not self._running or not self._client:
            return False

        room_id = message.thread_id
        if not room_id:
            logger.warning("No room_id (thread_id) for Matrix message")
            return False

        body, formatted_body = self._format_message(message.text)
        try:
            await self._client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content={
                    "msgtype": "m.text",
                    "body": body,
                    "format": "org.matrix.custom.html",
                    "formatted_body": formatted_body,
                },
            )
            return True
        except Exception:
            logger.exception("Failed to send Matrix message to %s", room_id)
            return False

    def _format_message(self, text: str) -> tuple[str, str]:
        """Convert text to Matrix message format (plain + HTML).

        Returns:
            Tuple of (plain_body, html_formatted_body).
        """
        # Plain body is the text as-is
        plain = text
        # Simple HTML: preserve newlines as <br>, escape HTML chars
        html = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = html.replace("\n", "<br>")
        return plain, html

    async def _on_room_message(self, room: Any, event: Any) -> None:
        """Handle incoming Matrix room messages."""
        # Ignore own messages
        if event.sender == self._user_id:
            return

        if self._on_message:
            msg = InboundMessage(
                channel=ChannelType("matrix"),
                channel_name=self.name,
                sender_id=event.sender,
                sender_label=event.sender,
                text=event.body,
                thread_id=room.room_id,
            )
            await self._on_message(msg)
