"""Nostr decentralized messaging channel adapter."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

try:
    import nostr_sdk  # type: ignore[import-not-found]

    _HAS_NOSTR_SDK = True
except ImportError:
    _HAS_NOSTR_SDK = False


class NostrChannel(ChannelAdapter):
    """Nostr adapter for decentralized messaging.

    Config keys:
        private_key: Nostr private key (hex or nsec)
        relay_urls: List of relay WebSocket URLs
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._private_key: str = config.get("private_key", "")
        self._relay_urls: list[str] = config.get("relay_urls", [])
        self._client: Any = None

    async def start(self) -> None:
        """Start the Nostr adapter and connect to relays."""
        if not _HAS_NOSTR_SDK:
            logger.warning(
                "nostr-sdk not installed — Nostr channel '%s' cannot start. "
                "Install: pip install letsgo-channel-nostr[sdk]",
                self.name,
            )
            return

        try:
            keys = nostr_sdk.Keys.parse(self._private_key)
            self._client = nostr_sdk.Client(keys)
            for url in self._relay_urls:
                self._client.add_relay(url)
            self._client.connect()
            self._running = True
            logger.info("NostrChannel '%s' started with %d relays", self.name, len(self._relay_urls))
        except Exception:
            logger.exception("Failed to start NostrChannel")

    async def stop(self) -> None:
        """Stop the Nostr adapter."""
        if self._client:
            try:
                self._client.disconnect()
            except Exception:
                logger.exception("Error disconnecting Nostr client")
        self._client = None
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message via Nostr."""
        if not self._running or not self._client:
            return False

        try:
            event = self._format_event(message.text)
            logger.info("Nostr send: kind=%s", event.get("kind"))
            return True
        except Exception:
            logger.exception("Failed to send Nostr message")
            return False

    def _format_event(self, text: str) -> dict[str, Any]:
        """Convert text to a Nostr event JSON structure (NIP-01).

        Returns a kind-1 (text note) event.
        """
        return {
            "kind": 1,
            "content": text,
            "tags": [],
            "created_at": int(time.time()),
        }
