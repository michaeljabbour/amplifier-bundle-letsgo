"""Telegram channel adapter (stub).

Gracefully degrades when ``python-telegram-bot`` is not installed.

Config keys:
    bot_token: Telegram Bot API token from @BotFather
    allowed_chat_ids: List of chat IDs allowed to interact with the bot
"""

from __future__ import annotations

import logging
from typing import Any

from ..models import OutboundMessage
from .base import ChannelAdapter, OnMessageCallback

logger = logging.getLogger(__name__)


class TelegramChannel(ChannelAdapter):
    """Telegram adapter -- requires ``python-telegram-bot``.

    When the dependency is missing the adapter loads without error but all
    operations are no-ops.  Install the real dependency to enable it::

        pip install python-telegram-bot

    Config:
        bot_token (str): Bot API token.
        allowed_chat_ids (list[int]): Whitelisted chat IDs.
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._bot_token: str = config.get("bot_token", "")
        self._allowed_chat_ids: list[int] = config.get("allowed_chat_ids", [])
        self._available: bool = False
        self._on_message: OnMessageCallback | None = None

    async def start(self) -> None:
        logger.warning(
            "Telegram adapter '%s' requires python-telegram-bot — "
            "install with: pip install python-telegram-bot",
            self.name,
        )
        self._available = False

    async def stop(self) -> None:
        if not self._available:
            return

    async def send(self, message: OutboundMessage) -> bool:
        if not self._available:
            logger.warning(
                "Telegram adapter '%s' is not available — "
                "cannot send message (install python-telegram-bot)",
                self.name,
            )
            return False
        return False
