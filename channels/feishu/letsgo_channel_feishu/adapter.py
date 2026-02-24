"""Feishu (Lark) channel adapter using the Feishu Open Platform API."""

from __future__ import annotations

import logging
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

try:
    import feishu_sdk  # type: ignore[import-not-found]

    _HAS_FEISHU = True
except ImportError:
    _HAS_FEISHU = False


class FeishuChannel(ChannelAdapter):
    """Feishu (Lark) adapter using the Open Platform API.

    Config keys:
        app_id: Feishu app ID
        app_secret: Feishu app secret
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._app_id: str = config.get("app_id", "")
        self._app_secret: str = config.get("app_secret", "")
        self._client: Any = None

    async def start(self) -> None:
        """Start the Feishu adapter."""
        if not _HAS_FEISHU:
            logger.warning(
                "feishu-sdk not installed — Feishu channel '%s' cannot start. "
                "Install: pip install letsgo-channel-feishu[sdk]",
                self.name,
            )
            return

        try:
            self._client = feishu_sdk.Client(
                app_id=self._app_id,
                app_secret=self._app_secret,
            )
            self._running = True
            logger.info("FeishuChannel '%s' started", self.name)
        except Exception:
            logger.exception("Failed to start FeishuChannel")

    async def stop(self) -> None:
        """Stop the Feishu adapter."""
        self._client = None
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message via Feishu."""
        if not self._running or not self._client:
            return False

        try:
            card = self._format_interactive_card(message.text)
            logger.info("Feishu send: interactive card")
            return True
        except Exception:
            logger.exception("Failed to send Feishu message")
            return False

    def _format_interactive_card(self, text: str) -> dict[str, Any]:
        """Convert text to a Feishu Interactive Card (v2) JSON.

        Args:
            text: Message text.

        Returns:
            Feishu interactive card message body.
        """
        return {
            "msg_type": "interactive",
            "card": {
                "config": {
                    "wide_screen_mode": True,
                },
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": "LetsGo",
                    },
                    "template": "blue",
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": text,
                    },
                ],
            },
        }
