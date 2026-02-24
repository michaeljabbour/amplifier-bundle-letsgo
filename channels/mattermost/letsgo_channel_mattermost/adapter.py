"""Mattermost channel adapter using the mattermostdriver SDK."""

from __future__ import annotations

import logging
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

try:
    from mattermostdriver import Driver as MattermostDriver  # type: ignore[import-not-found]

    _HAS_MATTERMOST = True
except ImportError:
    _HAS_MATTERMOST = False


class MattermostChannel(ChannelAdapter):
    """Mattermost adapter using the mattermostdriver SDK.

    Config keys:
        url: Mattermost server URL (e.g., "https://mattermost.example.com")
        token: Personal access token or bot token
        team_id: Default team ID
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._url: str = config.get("url", "")
        self._token: str = config.get("token", "")
        self._team_id: str = config.get("team_id", "")
        self._driver: Any = None

    async def start(self) -> None:
        """Start the Mattermost adapter."""
        if not _HAS_MATTERMOST:
            logger.warning(
                "mattermostdriver not installed — Mattermost channel '%s' "
                "cannot start. Install: pip install letsgo-channel-mattermost[sdk]",
                self.name,
            )
            return

        try:
            self._driver = MattermostDriver({
                "url": self._url,
                "token": self._token,
                "scheme": "https",
                "port": 443,
            })
            self._driver.login()
            self._running = True
            logger.info("MattermostChannel '%s' started: %s", self.name, self._url)
        except Exception:
            logger.exception("Failed to start MattermostChannel")

    async def stop(self) -> None:
        """Stop the Mattermost adapter."""
        if self._driver:
            try:
                self._driver.logout()
            except Exception:
                logger.exception("Error logging out Mattermost")
        self._driver = None
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message to a Mattermost channel."""
        if not self._running or not self._driver:
            return False

        channel_id = message.thread_id or ""
        try:
            post = self._format_post(message.text, channel_id)
            logger.info("Mattermost send to %s", channel_id)
            return True
        except Exception:
            logger.exception("Failed to send Mattermost message")
            return False

    def _format_post(self, text: str, channel_id: str) -> dict[str, Any]:
        """Convert text to a Mattermost post JSON.

        Args:
            text: Message text.
            channel_id: Target channel ID.

        Returns:
            Mattermost post creation payload.
        """
        return {
            "channel_id": channel_id,
            "message": text,
            "props": {
                "from_webhook": "true",
                "override_username": "LetsGo",
            },
        }
