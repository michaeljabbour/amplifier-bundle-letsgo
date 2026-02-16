"""Discord channel adapter (stub).

TODO: Implement full Discord bot integration.

Config keys:
    bot_token: Discord bot token
    guild_id: Discord server (guild) ID
"""

from __future__ import annotations

from typing import Any

from ..models import OutboundMessage
from .base import ChannelAdapter


class DiscordChannel(ChannelAdapter):
    """Discord adapter — requires ``discord.py``.

    Config:
        bot_token (str): Discord bot token.
        guild_id (str): Target guild ID.
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._bot_token: str = config.get("bot_token", "")
        self._guild_id: str = config.get("guild_id", "")

    async def start(self) -> None:
        raise NotImplementedError(
            "Discord adapter requires discord.py. "
            "Install with: pip install discord.py"
        )

    async def stop(self) -> None:
        raise NotImplementedError(
            "Discord adapter requires discord.py. "
            "Install with: pip install discord.py"
        )

    async def send(self, message: OutboundMessage) -> bool:
        raise NotImplementedError(
            "Discord adapter requires discord.py. "
            "Install with: pip install discord.py"
        )
