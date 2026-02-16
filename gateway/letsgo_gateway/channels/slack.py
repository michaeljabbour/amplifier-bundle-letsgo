"""Slack channel adapter (stub).

TODO: Implement full Slack bot integration.

Config keys:
    bot_token: Slack Bot User OAuth Token (xoxb-...)
    signing_secret: Slack app signing secret for request verification
"""

from __future__ import annotations

from typing import Any

from ..models import OutboundMessage
from .base import ChannelAdapter


class SlackChannel(ChannelAdapter):
    """Slack adapter — requires ``slack-sdk``.

    Config:
        bot_token (str): Slack bot OAuth token.
        signing_secret (str): Slack signing secret.
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._bot_token: str = config.get("bot_token", "")
        self._signing_secret: str = config.get("signing_secret", "")

    async def start(self) -> None:
        raise NotImplementedError(
            "Slack adapter requires slack-sdk. "
            "Install with: pip install slack-sdk"
        )

    async def stop(self) -> None:
        raise NotImplementedError(
            "Slack adapter requires slack-sdk. "
            "Install with: pip install slack-sdk"
        )

    async def send(self, message: OutboundMessage) -> bool:
        raise NotImplementedError(
            "Slack adapter requires slack-sdk. "
            "Install with: pip install slack-sdk"
        )
