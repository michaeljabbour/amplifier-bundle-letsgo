"""Canvas channel adapter — serves a visual workspace web UI via WebSocket."""

from __future__ import annotations

import json
import logging
import uuid
from collections import OrderedDict
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import OutboundMessage

logger = logging.getLogger(__name__)


class CanvasChannel(ChannelAdapter):
    """Canvas visual workspace channel adapter.

    Serves a web UI at ``http://{host}:{port}/canvas`` with a WebSocket
    connection for real-time content updates.

    Config keys:
        host: Bind address (default: "localhost")
        port: HTTP port (default: 8080)
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._host: str = config.get("host", "localhost")
        self._port: int = config.get("port", 8080)
        # Ordered dict — newest items first (insert at beginning)
        self._canvas_state: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._ws_clients: set[Any] = set()
        self._app: Any = None
        self._runner: Any = None
        self._site: Any = None

    async def start(self) -> None:
        """Start the aiohttp web server for the canvas UI."""
        try:
            import aiohttp.web as web
        except ImportError:
            logger.warning(
                "aiohttp not installed — Canvas channel '%s' cannot start",
                self.name,
            )
            return

        self._app = web.Application()
        self._app.router.add_get("/canvas", self._handle_index)
        self._app.router.add_get("/canvas/state", self._handle_state)
        self._app.router.add_get("/canvas/ws", self._handle_websocket)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()
        self._running = True
        logger.info(
            "CanvasChannel '%s' started at http://%s:%s/canvas",
            self.name,
            self._host,
            self._port,
        )

    async def stop(self) -> None:
        """Stop the web server and disconnect all WebSocket clients."""
        # Close all WebSocket connections
        for ws in set(self._ws_clients):
            try:
                await ws.close()
            except Exception:
                pass
        self._ws_clients.clear()

        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        self._app = None
        self._site = None
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Parse JSON envelope from message text and update canvas state."""
        try:
            item = self._parse_envelope(message.text)
        except Exception:
            logger.exception("Failed to parse canvas envelope")
            # Store as raw text fallback
            item = {
                "id": str(uuid.uuid4())[:8],
                "content_type": "text",
                "content": message.text,
                "title": None,
            }

        item_id = item["id"]

        # Update or insert into ordered state (newest first)
        if item_id in self._canvas_state:
            # Remove and re-insert at beginning to maintain order
            del self._canvas_state[item_id]
        self._canvas_state[item_id] = {
            "content_type": item["content_type"],
            "content": item["content"],
            "title": item.get("title"),
        }
        self._canvas_state.move_to_end(item_id, last=False)

        # Broadcast to WebSocket clients
        ws_message = json.dumps(
            {
                "type": "update",
                "id": item_id,
                "content_type": item["content_type"],
                "content": item["content"],
                "title": item.get("title"),
            }
        )
        await self._broadcast(ws_message)

        return True

    def get_state(self) -> dict[str, dict[str, Any]]:
        """Return a copy of the current canvas state (newest first)."""
        return dict(self._canvas_state)

    # -- Internal helpers -----------------------------------------------------

    def _parse_envelope(self, text: str) -> dict[str, Any]:
        """Parse a JSON envelope from message text."""
        data = json.loads(text)
        return {
            "id": data.get("id") or str(uuid.uuid4())[:8],
            "content_type": data.get("content_type", "text"),
            "content": data.get("content", ""),
            "title": data.get("title"),
        }

    async def _broadcast(self, message: str) -> None:
        """Send a message to all connected WebSocket clients."""
        dead: set[Any] = set()
        for ws in self._ws_clients:
            try:
                await ws.send_str(message)
            except Exception:
                dead.add(ws)
        self._ws_clients -= dead

    # -- HTTP handlers --------------------------------------------------------

    async def _handle_index(self, request: Any) -> Any:
        """Serve the canvas web UI."""
        from pathlib import Path

        import aiohttp.web as web

        static_dir = Path(__file__).parent / "static"
        index_path = static_dir / "index.html"
        if not index_path.exists():
            return web.Response(text="Canvas UI not found", status=404)
        return web.FileResponse(index_path)

    async def _handle_state(self, request: Any) -> Any:
        """Return current canvas state as JSON."""
        import aiohttp.web as web

        # Return items list ordered newest first
        items = []
        for item_id, item in self._canvas_state.items():
            items.append(
                {
                    "id": item_id,
                    "content_type": item["content_type"],
                    "content": item["content"],
                    "title": item.get("title"),
                }
            )
        return web.json_response({"items": items})

    async def _handle_websocket(self, request: Any) -> Any:
        """Handle a WebSocket connection for real-time canvas updates."""
        import aiohttp.web as web

        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._ws_clients.add(ws)
        logger.debug(
            "Canvas WebSocket client connected (%d total)", len(self._ws_clients)
        )

        try:
            async for _msg in ws:
                # Client → server messages (future: forms, user input)
                pass
        finally:
            self._ws_clients.discard(ws)
            logger.debug(
                "Canvas WebSocket client disconnected (%d remain)",
                len(self._ws_clients),
            )

        return ws
