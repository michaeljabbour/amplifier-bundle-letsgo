"""Discord channel adapter (stub).

Gracefully degrades when ``discord.py`` is not installed.

Config keys:
    bot_token: Discord bot token
    guild_id: Discord server (guild) ID
"""

from __future__ import annotations

import logging
from typing import Any

from ..models import OutboundMessage
from .base import ChannelAdapter, OnMessageCallback

logger = logging.getLogger(__name__)


class DiscordChannel(ChannelAdapter):
    """Discord adapter -- requires ``discord.py``.

    When the dependency is missing the adapter loads without error but all
    operations are no-ops.  Install the real dependency to enable it::

        pip install discord.py

    Config:
        bot_token (str): Discord bot token.
        guild_id (str): Target guild ID.
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._bot_token: str = config.get("bot_token", "")
        self._guild_id: str = config.get("guild_id", "")
        self._available: bool = False
        self._on_message: OnMessageCallback | None = None

    async def start(self) -> None:
        logger.warning(
            "Discord adapter '%s' requires discord.py — "
            "install with: pip install discord.py",
            self.name,
        )
        self._available = False

    async def stop(self) -> None:
        if not self._available:
            return

    async def send(self, message: OutboundMessage) -> bool:
        if not self._available:
            logger.warning(
                "Discord adapter '%s' is not available — "
                "cannot send message (install discord.py)",
                self.name,
            )
            return False
        return False
