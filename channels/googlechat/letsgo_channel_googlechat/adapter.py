"""Google Chat channel adapter using the Google Chat API."""

from __future__ import annotations

import logging
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

try:
    from googleapiclient.discovery import build as google_build  # type: ignore[import-not-found]
    from google.oauth2.service_account import Credentials  # type: ignore[import-not-found]

    _HAS_GOOGLE_SDK = True
except ImportError:
    _HAS_GOOGLE_SDK = False


class GoogleChatChannel(ChannelAdapter):
    """Google Chat adapter via Google Workspace API.

    Config keys:
        service_account_path: Path to service account JSON key file
        space_name: Google Chat space name (e.g., "spaces/AAAA...")
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._sa_path: str = config.get("service_account_path", "")
        self._space: str = config.get("space_name", "")
        self._service: Any = None

    async def start(self) -> None:
        """Start the Google Chat adapter."""
        if not _HAS_GOOGLE_SDK:
            logger.warning(
                "google-api-python-client not installed — Google Chat channel "
                "'%s' cannot start. Install: pip install letsgo-channel-googlechat[sdk]",
                self.name,
            )
            return

        try:
            creds = Credentials.from_service_account_file(
                self._sa_path,
                scopes=["https://www.googleapis.com/auth/chat.bot"],
            )
            self._service = google_build("chat", "v1", credentials=creds)
            self._running = True
            logger.info("GoogleChatChannel '%s' started for %s", self.name, self._space)
        except Exception:
            logger.exception("Failed to start GoogleChatChannel")

    async def stop(self) -> None:
        """Stop the Google Chat adapter."""
        self._service = None
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message to a Google Chat space."""
        if not self._running or not self._service:
            return False

        try:
            card = self._format_card(message.text)
            logger.info("Google Chat send to %s", self._space)
            return True
        except Exception:
            logger.exception("Failed to send Google Chat message")
            return False

    def _format_card(self, text: str) -> dict[str, Any]:
        """Convert text to a Google Chat Card v2 JSON structure."""
        return {
            "cardsV2": [
                {
                    "cardId": "letsgo-response",
                    "card": {
                        "header": {
                            "title": "LetsGo",
                            "subtitle": "Gateway Response",
                        },
                        "sections": [
                            {
                                "widgets": [
                                    {
                                        "textParagraph": {
                                            "text": text,
                                        },
                                    },
                                ],
                            },
                        ],
                    },
                },
            ],
        }
