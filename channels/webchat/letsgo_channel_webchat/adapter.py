"""WebChatChannel adapter — web chat interface for LetsGo gateway."""

from __future__ import annotations

import json
import logging
from typing import Any

from aiohttp import WSMsgType, web
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)


class WebChatChannel(ChannelAdapter):
    """Web chat channel with WebSocket-based chat and optional admin dashboard."""

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._host: str = config.get("host", "localhost")
        self._port: int = config.get("port", 8090)
        self._ws_clients: set[web.WebSocketResponse] = set()
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._daemon: Any = None

    # ---- public API ----

    def set_daemon(self, daemon: Any) -> None:
        """Store a daemon reference for the admin API."""
        self._daemon = daemon

    async def start(self) -> None:
        """Create the aiohttp app with /chat and /chat/ws routes."""
        self._app = web.Application()
        self._app.router.add_get("/chat/ws", self._handle_chat_websocket)

        # Only mount admin routes if admin is enabled AND token is set
        admin_cfg = self.config.get("admin", {})
        if admin_cfg.get("enabled") and admin_cfg.get("token"):
            from .admin import setup_admin_routes

            setup_admin_routes(self._app, self._daemon, admin_cfg["token"])

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._running = True

    async def stop(self) -> None:
        """Close WebSocket clients and clean up the runner."""
        if not self._running:
            return

        # Close all connected WebSocket clients
        for ws in set(self._ws_clients):
            await ws.close()
        self._ws_clients.clear()

        if self._runner:
            await self._runner.cleanup()
            self._runner = None

        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Broadcast an outbound message to all connected chat WS clients."""
        if not self._ws_clients:
            return True

        payload = json.dumps({"text": message.text})
        closed = set()
        for ws in self._ws_clients:
            try:
                await ws.send_str(payload)
            except Exception:
                closed.add(ws)

        self._ws_clients -= closed
        return True

    # ---- WebSocket handler ----

    async def _handle_chat_websocket(
        self, request: web.Request
    ) -> web.WebSocketResponse:
        """Bidirectional WebSocket for chat messages."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._ws_clients.add(ws)

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except json.JSONDecodeError:
                        continue

                    inbound = InboundMessage(
                        channel=ChannelType("webchat"),
                        channel_name=self.name,
                        sender_id=data.get("sender_id", "anonymous"),
                        sender_label=data.get("sender_id", "anonymous"),
                        text=data.get("text", ""),
                    )

                    if self._on_message:
                        reply_text = await self._on_message(inbound)
                        await ws.send_json({"text": reply_text})
                elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                    break
        finally:
            self._ws_clients.discard(ws)

        return ws
