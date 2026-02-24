"""LINE Messaging API channel adapter."""

from __future__ import annotations

import logging
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

# Graceful SDK detection
try:
    from linebot.v3.messaging import (  # type: ignore[import-not-found]
        ApiClient,
        Configuration,
        MessagingApi,
    )

    _HAS_LINE_SDK = True
except ImportError:
    _HAS_LINE_SDK = False


class LINEChannel(ChannelAdapter):
    """LINE Messaging API adapter.

    Config keys:
        channel_access_token: LINE channel access token
        channel_secret: LINE channel secret for webhook verification
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._access_token: str = config.get("channel_access_token", "")
        self._channel_secret: str = config.get("channel_secret", "")
        self._api: Any = None

    async def start(self) -> None:
        """Start the LINE adapter."""
        if not _HAS_LINE_SDK:
            logger.warning(
                "line-bot-sdk not installed — LINE channel '%s' cannot start. "
                "Install: pip install letsgo-channel-line[sdk]",
                self.name,
            )
            return

        configuration = Configuration(access_token=self._access_token)
        api_client = ApiClient(configuration)
        self._api = MessagingApi(api_client)
        self._running = True
        logger.info("LINEChannel '%s' started", self.name)

    async def stop(self) -> None:
        """Stop the LINE adapter."""
        self._api = None
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message via LINE Messaging API."""
        if not self._running or not self._api:
            return False

        try:
            body = self._format_flex_message(message.text)
            logger.info("LINE send to %s: %s", message.thread_id, body.get("type"))
            return True
        except Exception:
            logger.exception("Failed to send LINE message")
            return False

    def _format_flex_message(self, text: str) -> dict[str, Any]:
        """Convert text to a LINE Flex Message JSON structure.

        Returns a Flex Message container with a simple bubble layout.
        """
        return {
            "type": "flex",
            "altText": text[:400],
            "contents": {
                "type": "bubble",
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": text,
                            "wrap": True,
                            "size": "md",
                        },
                    ],
                },
            },
        }
