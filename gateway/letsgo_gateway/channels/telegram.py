"""Telegram channel adapter (stub).

TODO: Implement full Telegram bot integration.

Config keys:
    bot_token: Telegram Bot API token from @BotFather
    allowed_chat_ids: List of chat IDs allowed to interact with the bot
"""

from __future__ import annotations

from typing import Any

from ..models import OutboundMessage
from .base import ChannelAdapter


class TelegramChannel(ChannelAdapter):
    """Telegram adapter — requires ``python-telegram-bot``.

    Config:
        bot_token (str): Bot API token.
        allowed_chat_ids (list[int]): Whitelisted chat IDs.
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._bot_token: str = config.get("bot_token", "")
        self._allowed_chat_ids: list[int] = config.get("allowed_chat_ids", [])

    async def start(self) -> None:
        raise NotImplementedError(
            "Telegram adapter requires python-telegram-bot. "
            "Install with: pip install python-telegram-bot"
        )

    async def stop(self) -> None:
        raise NotImplementedError(
            "Telegram adapter requires python-telegram-bot. "
            "Install with: pip install python-telegram-bot"
        )

    async def send(self, message: OutboundMessage) -> bool:
        raise NotImplementedError(
            "Telegram adapter requires python-telegram-bot. "
            "Install with: pip install python-telegram-bot"
        )
