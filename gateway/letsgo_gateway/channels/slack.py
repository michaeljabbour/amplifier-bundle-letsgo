"""Slack channel adapter (stub).

Gracefully degrades when ``slack-sdk`` is not installed.

Config keys:
    bot_token: Slack Bot User OAuth Token (xoxb-...)
    signing_secret: Slack app signing secret for request verification
"""

from __future__ import annotations

import logging
from typing import Any

from ..models import OutboundMessage
from .base import ChannelAdapter, OnMessageCallback

logger = logging.getLogger(__name__)


class SlackChannel(ChannelAdapter):
    """Slack adapter -- requires ``slack-sdk``.

    When the dependency is missing the adapter loads without error but all
    operations are no-ops.  Install the real dependency to enable it::

        pip install slack-sdk

    Config:
        bot_token (str): Slack bot OAuth token.
        signing_secret (str): Slack signing secret.
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._bot_token: str = config.get("bot_token", "")
        self._signing_secret: str = config.get("signing_secret", "")
        self._available: bool = False
        self._on_message: OnMessageCallback | None = None

    async def start(self) -> None:
        logger.warning(
            "Slack adapter '%s' requires slack-sdk — "
            "install with: pip install slack-sdk",
            self.name,
        )
        self._available = False

    async def stop(self) -> None:
        if not self._available:
            return

    async def send(self, message: OutboundMessage) -> bool:
        if not self._available:
            logger.warning(
                "Slack adapter '%s' is not available — "
                "cannot send message (install slack-sdk)",
                self.name,
            )
            return False
        return False
