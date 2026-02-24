"""Microsoft Teams channel adapter using botbuilder-core."""

from __future__ import annotations

import logging
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

# Graceful degradation
_HAS_BOTBUILDER = False
try:
    from botbuilder.core import (
        BotFrameworkAdapter,
        BotFrameworkAdapterSettings,
    )
    from botbuilder.schema import Activity

    _HAS_BOTBUILDER = True
except ImportError:
    pass


class TeamsChannel(ChannelAdapter):
    """Microsoft Teams adapter using Bot Framework.

    Config keys:
        app_id: Microsoft App ID from Azure Bot registration
        app_password: Microsoft App Password
        host: Bind address for the webhook server (default: "127.0.0.1")
        port: Bind port (default: 3978)
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._app_id: str = config.get("app_id", "")
        self._app_password: str = config.get("app_password", "")
        self._host: str = config.get("host", "127.0.0.1")
        self._port: int = int(config.get("port", 3978))
        self._adapter: Any = None  # BotFrameworkAdapter when available
        self._runner: Any = None  # aiohttp AppRunner

    async def start(self) -> None:
        """Start the Teams bot webhook server."""
        if not _HAS_BOTBUILDER:
            logger.warning(
                "botbuilder-core not installed — Teams channel '%s' cannot start. "
                "Install with: pip install letsgo-channel-teams[botbuilder]",
                self.name,
            )
            return

        try:
            settings = BotFrameworkAdapterSettings(self._app_id, self._app_password)
            self._adapter = BotFrameworkAdapter(settings)

            # Set up aiohttp web server for Bot Framework messages
            from aiohttp import web

            app = web.Application()
            app.router.add_post("/api/messages", self._handle_messages)
            self._runner = web.AppRunner(app)
            await self._runner.setup()
            site = web.TCPSite(self._runner, self._host, self._port)
            await site.start()

            self._running = True
            logger.info(
                "TeamsChannel '%s' listening on %s:%s",
                self.name,
                self._host,
                self._port,
            )
        except Exception:
            logger.exception("Failed to start Teams channel '%s'", self.name)

    async def stop(self) -> None:
        """Stop the Teams bot webhook server."""
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        self._adapter = None
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message via Teams Bot Framework."""
        if not self._running or not self._adapter:
            return False

        # Teams messages are typically sent as replies via TurnContext,
        # which is handled during the on_turn callback flow.
        # For proactive messages, we'd need a conversation reference.
        logger.warning(
            "Proactive Teams messaging not yet implemented for '%s'", self.name
        )
        return False

    def _format_as_card(self, text: str) -> dict[str, Any]:
        """Wrap text in an Adaptive Card structure for Teams.

        Returns:
            Adaptive Card JSON dict.
        """
        return {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.4",
            "body": [
                {
                    "type": "TextBlock",
                    "text": text,
                    "wrap": True,
                }
            ],
        }

    async def _handle_messages(self, request: Any) -> Any:
        """Handle incoming Bot Framework messages."""
        from aiohttp import web

        if not self._adapter:
            return web.Response(status=503)

        body = await request.json()

        async def _on_turn(turn_context: Any) -> None:
            if turn_context.activity.type == "message":
                if self._on_message:
                    msg = InboundMessage(
                        channel=ChannelType("teams"),
                        channel_name=self.name,
                        sender_id=turn_context.activity.from_property.id,
                        sender_label=turn_context.activity.from_property.name or "",
                        text=turn_context.activity.text or "",
                        thread_id=turn_context.activity.conversation.id,
                    )
                    response_text = await self._on_message(msg)
                    if response_text:
                        await turn_context.send_activity(response_text)

        try:
            auth_header = request.headers.get("Authorization", "")
            activity = Activity().deserialize(body)
            await self._adapter.process_activity(activity, auth_header, _on_turn)
            return web.Response(status=200)
        except Exception:
            logger.exception("Error processing Teams message")
            return web.Response(status=500)
