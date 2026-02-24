# OpenClaw Migration Phase 5: `letsgo-webchat` Satellite Bundle — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a web chat interface and admin dashboard to the LetsGo gateway — a single `WebChatChannel` gateway plugin that serves both a chat UI for messaging and a 6-view admin dashboard for gateway management, on one aiohttp server with URL-prefix separation and bearer token auth for admin routes.

**Architecture:** Single gateway entry-point plugin (`letsgo.channels: webchat`). One aiohttp server serves chat routes (`/chat`, `/chat/ws`) and admin routes (`/admin/`, `/admin/api/*`). Chat WebSocket is bidirectional — clients send messages that route through `daemon._on_message()`, server pushes responses. Admin routes are protected by bearer token middleware (fail-closed: don't mount if no token configured). Admin API endpoints query daemon components in-process (router, auth, cron, heartbeat, channels). Two static HTML SPAs — one for chat (~200 lines), one for the admin dashboard (~900 lines with 6 tabs).

**Tech Stack:** Python 3.11+, pytest + pytest-asyncio (asyncio_mode=auto), hatchling build system, aiohttp for WebSocket server + HTTP routes + admin API, vanilla HTML/CSS/JS for both UIs (no build step).

**Design Document:** `docs/plans/2026-02-24-openclaw-migration-phase5-webchat-design.md`

---

## Conventions Reference

These conventions are derived from the existing codebase. Follow them exactly.

**Channel adapter naming:**
- Directory: `channels/{name}/` (e.g., `channels/webchat/`)
- Package: `letsgo_channel_{name}` (e.g., `letsgo_channel_webchat`)
- PyPI name: `letsgo-channel-{name}`
- Entry point: `{name} = "{package}:{ClassName}"` under `[project.entry-points."letsgo.channels"]`

**Test conventions:**
- Framework: pytest + pytest-asyncio with `asyncio_mode = auto`
- Location: `tests/test_gateway/test_{component}.py` for gateway tests
- Channel adapter tests: `channels/{name}/tests/test_{name}_adapter.py`
- Style: class-based grouping (`class TestSomething:`), `_make_xxx()` helper factories, `@pytest.mark.asyncio` on async tests
- Run gateway tests: `python -m pytest tests/test_gateway/ -v`
- Run channel adapter tests: `PYTHONPATH=channels/webchat:gateway python -m pytest channels/webchat/tests/ -v`

**Channel adapter pattern (from `CanvasChannel` reference):**
```python
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

class SomeChannel(ChannelAdapter):
    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def send(self, message: OutboundMessage) -> bool: ...
```

**ChannelAdapter base class** (`gateway/letsgo_gateway/channels/base.py`):
- Properties: `name`, `config`, `is_running` (bool)
- Methods: `set_on_message(callback)`, abstract `start()`, `stop()`, `send(OutboundMessage) -> bool`
- `_on_message` callback type: `Callable[[InboundMessage], Awaitable[str]]`
- `_running` flag managed by subclass

**Gateway daemon** (`gateway/letsgo_gateway/daemon.py`):
- Public attributes: `auth` (PairingStore), `router` (SessionRouter), `cron` (CronScheduler), `heartbeat` (HeartbeatEngine), `channels` (dict[str, ChannelAdapter]), `voice` (VoiceMiddleware | None)
- Private: `_config` (dict), `_running` (bool)
- `_init_channels()` calls `discover_channels()`, creates adapters with `cls(name=name, config=ch_cfg)`, calls `adapter.set_on_message(self._on_message)`
- `_on_message(InboundMessage) -> str` is the core message handler

**PairingStore API** (`gateway/letsgo_gateway/auth.py`):
- `_key(sender_id, channel) -> str` — returns `"{channel}:{sender_id}"`
- `_senders: dict[str, SenderRecord]` — internal dict keyed by `_key()`
- `request_pairing(sender_id, channel, channel_name, sender_label) -> str` — returns pairing code
- `verify_pairing(sender_id, channel, code) -> bool`
- `is_approved(sender_id, channel) -> bool`
- `block_sender(sender_id, channel) -> None`
- `get_all_approved(channel=None) -> list[SenderRecord]`
- `check_rate_limit(sender_id, channel) -> bool`

**SessionRouter API** (`gateway/letsgo_gateway/router.py`):
- `active_sessions -> dict[str, dict]` — property, returns copy
- `close_session(key) -> bool` — closes by route key
- Session dict keys: `session_id`, `route_key`, `created_at`, `last_active`, `message_count`

**CronScheduler API** (`gateway/letsgo_gateway/cron.py`):
- `list_jobs() -> list[dict]` — each with `name`, `cron`, `recipe`, `context`, `next_run`, `last_run`

**HeartbeatEngine API** (`gateway/letsgo_gateway/heartbeat.py`):
- `history -> list[dict]` — property, execution history
- `last_result(agent_id) -> dict | None`

**Data models** (`gateway/letsgo_gateway/models.py`):
- `ChannelType(str, Enum)` — WEBHOOK, TELEGRAM, DISCORD, SLACK, WHATSAPP + `_missing_()` for plugins
- `AuthStatus(str, Enum)` — PENDING, APPROVED, BLOCKED
- `SenderRecord` — `sender_id`, `channel`, `channel_name`, `status`, `label`, `approved_at`, `last_seen`, `message_count`
- `InboundMessage` — `channel`, `channel_name`, `sender_id`, `sender_label`, `text`, `thread_id`, `attachments`, `timestamp`, `raw`
- `OutboundMessage` — `channel`, `channel_name`, `thread_id`, `text`, `attachments`

**Behavior YAML pattern:**
```yaml
bundle:
  name: behavior-xxx
  version: 1.0.0
  description: ...
context:
  include:
    - namespace:context/xxx-awareness.md
```

**Gateway test pattern (from `test_auth.py`):**
- `_make_store(tmp_path, **overrides) -> PairingStore`
- `tmp_path` fixture for temp directories
- Direct imports from `letsgo_gateway.*`

---

## Task 1: PairingStore Additions (Prerequisite)

**Files:**
- Modify: `gateway/letsgo_gateway/auth.py`
- Test: `tests/test_gateway/test_auth.py`

### Step 1: Write the failing tests

Append these tests to `tests/test_gateway/test_auth.py`:

```python


def test_get_all_senders(tmp_path: Path):
    """get_all_senders returns all senders regardless of status."""
    store = _make_store(tmp_path)

    # Create approved sender
    code = store.request_pairing("alice", ChannelType.WEBHOOK, "main", "Alice")
    store.verify_pairing("alice", ChannelType.WEBHOOK, code)

    # Create blocked sender
    store.block_sender("bob", ChannelType.WEBHOOK)

    # Create pending sender (request pairing but don't verify)
    store.request_pairing("charlie", ChannelType.TELEGRAM, "bot", "Charlie")

    all_senders = store.get_all_senders()
    assert len(all_senders) == 3

    statuses = {s.sender_id: s.status for s in all_senders}
    assert statuses["alice"] == AuthStatus.APPROVED
    assert statuses["bob"] == AuthStatus.BLOCKED
    assert statuses["charlie"] == AuthStatus.PENDING


def test_get_all_senders_filter_by_channel(tmp_path: Path):
    """get_all_senders filters by channel when specified."""
    store = _make_store(tmp_path)
    code1 = store.request_pairing("u1", ChannelType.WEBHOOK, "wh", "U1")
    store.verify_pairing("u1", ChannelType.WEBHOOK, code1)

    code2 = store.request_pairing("u2", ChannelType.TELEGRAM, "tg", "U2")
    store.verify_pairing("u2", ChannelType.TELEGRAM, code2)

    webhook_senders = store.get_all_senders(channel=ChannelType.WEBHOOK)
    assert len(webhook_senders) == 1
    assert webhook_senders[0].sender_id == "u1"


def test_unblock_sender(tmp_path: Path):
    """unblock_sender restores a blocked sender to APPROVED."""
    store = _make_store(tmp_path)

    # Approve then block
    code = store.request_pairing("user1", ChannelType.WEBHOOK, "ch", "User")
    store.verify_pairing("user1", ChannelType.WEBHOOK, code)
    store.block_sender("user1", ChannelType.WEBHOOK)
    assert not store.is_approved("user1", ChannelType.WEBHOOK)

    # Unblock
    store.unblock_sender("user1", ChannelType.WEBHOOK)
    assert store.is_approved("user1", ChannelType.WEBHOOK)

    key = store._key("user1", ChannelType.WEBHOOK)
    assert store._senders[key].status == AuthStatus.APPROVED
```

### Step 2: Run tests to verify they fail

Run: `python -m pytest tests/test_gateway/test_auth.py::test_get_all_senders tests/test_gateway/test_auth.py::test_get_all_senders_filter_by_channel tests/test_gateway/test_auth.py::test_unblock_sender -v`

Expected: 3 FAILED — `AttributeError: 'PairingStore' object has no attribute 'get_all_senders'`

### Step 3: Implement the methods

Add to `gateway/letsgo_gateway/auth.py`, at the end of the `PairingStore` class (after `block_sender`):

```python
    def get_all_senders(
        self, channel: ChannelType | None = None
    ) -> list[SenderRecord]:
        """Return all senders regardless of status, optionally filtered by channel."""
        results = []
        for rec in self._senders.values():
            if channel is not None and rec.channel != channel:
                continue
            results.append(rec)
        return results

    def unblock_sender(self, sender_id: str, channel: ChannelType) -> None:
        """Set a blocked sender's status back to APPROVED."""
        key = self._key(sender_id, channel)
        rec = self._senders.get(key)
        if rec and rec.status == AuthStatus.BLOCKED:
            rec.status = AuthStatus.APPROVED
            self._save()
```

### Step 4: Run tests to verify they pass

Run: `python -m pytest tests/test_gateway/test_auth.py -v`

Expected: All 10 tests pass (7 existing + 3 new).

### Step 5: Verify no regressions

Run: `python -m pytest tests/test_gateway/ -v`

Expected: Same baseline (53+ passed, 3 pre-existing failures in stub channel tests).

### Step 6: Commit

Message: `feat(gateway): add get_all_senders and unblock_sender to PairingStore`

Files: `gateway/letsgo_gateway/auth.py`, `tests/test_gateway/test_auth.py`

---

## Task 2: WebChatChannel Adapter Core

**Files:**
- Create: `channels/webchat/pyproject.toml`
- Create: `channels/webchat/letsgo_channel_webchat/__init__.py`
- Create: `channels/webchat/letsgo_channel_webchat/adapter.py`
- Create: `channels/webchat/tests/__init__.py`
- Create: `channels/webchat/tests/test_webchat_adapter.py`

### Step 1: Create package files

Create `channels/webchat/pyproject.toml`:

```toml
[project]
name = "letsgo-channel-webchat"
version = "0.1.0"
description = "Web chat interface and admin dashboard channel for LetsGo gateway"
requires-python = ">=3.11"
dependencies = [
    "letsgo-gateway",
    "aiohttp>=3.9",
]

[project.entry-points."letsgo.channels"]
webchat = "letsgo_channel_webchat:WebChatChannel"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["letsgo_channel_webchat"]
```

Create `channels/webchat/letsgo_channel_webchat/__init__.py`:

```python
"""Web chat and admin dashboard channel adapter for the LetsGo gateway."""

from .adapter import WebChatChannel

__all__ = ["WebChatChannel"]
```

Create `channels/webchat/tests/__init__.py` (empty file):

```python
```

### Step 2: Write the failing tests

Create `channels/webchat/tests/test_webchat_adapter.py`:

```python
"""Tests for WebChat channel adapter — core lifecycle, chat, and admin."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from letsgo_channel_webchat import WebChatChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_webchat(config: dict[str, Any] | None = None) -> WebChatChannel:
    return WebChatChannel(name="webchat", config=config or {})


def _make_outbound(
    text: str,
    channel_name: str = "webchat",
) -> OutboundMessage:
    return OutboundMessage(
        channel=ChannelType("webchat"),
        channel_name=channel_name,
        thread_id=None,
        text=text,
    )


def _make_mock_daemon() -> MagicMock:
    """Create a mock daemon with all required attributes."""
    daemon = MagicMock()
    daemon._config = {"agents": {}}
    daemon._start_time = 0.0
    daemon._message_count = 0
    daemon.auth = MagicMock()
    daemon.auth.get_all_senders = MagicMock(return_value=[])
    daemon.auth.get_all_approved = MagicMock(return_value=[])
    daemon.auth.block_sender = MagicMock()
    daemon.auth.unblock_sender = MagicMock()
    daemon.router = MagicMock()
    daemon.router.active_sessions = {}
    daemon.router.close_session = MagicMock(return_value=True)
    daemon.cron = MagicMock()
    daemon.cron.list_jobs = MagicMock(return_value=[])
    daemon.heartbeat = MagicMock()
    daemon.heartbeat.history = []
    daemon.channels = {}
    return daemon


# ---------------------------------------------------------------------------
# WebChatChannel — subclass check
# ---------------------------------------------------------------------------


class TestWebChatChannelSubclass:
    """WebChatChannel is a proper ChannelAdapter."""

    def test_is_channel_adapter(self) -> None:
        assert issubclass(WebChatChannel, ChannelAdapter)

    def test_instantiation(self) -> None:
        ch = _make_webchat(config={"host": "0.0.0.0", "port": 9090})
        assert ch.name == "webchat"
        assert ch.config["port"] == 9090
        assert not ch.is_running

    def test_default_config(self) -> None:
        ch = _make_webchat()
        assert ch._host == "localhost"
        assert ch._port == 8090


# ---------------------------------------------------------------------------
# WebChatChannel — lifecycle
# ---------------------------------------------------------------------------


class TestWebChatChannelLifecycle:
    """Start/stop lifecycle management."""

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self) -> None:
        ch = _make_webchat()
        await ch.stop()  # should not raise
        assert not ch.is_running

    @pytest.mark.asyncio
    async def test_stop_after_start(self) -> None:
        ch = _make_webchat(config={"port": 0})
        await ch.start()
        assert ch.is_running
        await ch.stop()
        assert not ch.is_running

    @pytest.mark.asyncio
    async def test_admin_routes_not_mounted_without_token(self) -> None:
        """Admin routes require both admin.enabled=True and admin.token."""
        ch = _make_webchat(config={"port": 0})
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://localhost:{port}/admin/"
                ) as resp:
                    # Should 404 — admin routes not mounted
                    assert resp.status == 404
        finally:
            await ch.stop()


# ---------------------------------------------------------------------------
# WebChatChannel — chat WebSocket
# ---------------------------------------------------------------------------


class TestWebChatChannelChat:
    """Chat WebSocket bidirectional messaging."""

    @pytest.mark.asyncio
    async def test_chat_websocket_connection(self) -> None:
        ch = _make_webchat(config={"port": 0})
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    f"http://localhost:{port}/chat/ws"
                ) as ws:
                    assert not ws.closed
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_chat_send_pushes_to_clients(self) -> None:
        ch = _make_webchat(config={"port": 0})
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    f"http://localhost:{port}/chat/ws"
                ) as ws:
                    msg = _make_outbound(text="Hello from the agent!")
                    await ch.send(msg)

                    data = await asyncio.wait_for(
                        ws.receive_json(), timeout=2
                    )
                    assert data["type"] == "response"
                    assert data["text"] == "Hello from the agent!"
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_chat_inbound_routes_through_callback(self) -> None:
        """Client sends a message -> _on_message callback is invoked."""
        ch = _make_webchat(config={"port": 0})
        callback = AsyncMock(return_value="Echo: hello")
        ch.set_on_message(callback)
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    f"http://localhost:{port}/chat/ws"
                ) as ws:
                    await ws.send_json({
                        "text": "hello",
                        "sender_id": "web-user-1",
                    })

                    data = await asyncio.wait_for(
                        ws.receive_json(), timeout=2
                    )
                    assert data["type"] in ("response", "pairing")
                    callback.assert_called_once()
                    call_msg = callback.call_args[0][0]
                    assert isinstance(call_msg, InboundMessage)
                    assert call_msg.text == "hello"
                    assert call_msg.sender_id == "web-user-1"
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_set_daemon(self) -> None:
        """set_daemon stores reference for admin API access."""
        ch = _make_webchat()
        daemon = _make_mock_daemon()
        ch.set_daemon(daemon)
        assert ch._daemon is daemon
```

### Step 3: Run tests to verify they fail

Run: `PYTHONPATH=channels/webchat:gateway python -m pytest channels/webchat/tests/ -v`

Expected: FAILED — `ModuleNotFoundError: No module named 'letsgo_channel_webchat.adapter'`

### Step 4: Implement the adapter

Create `channels/webchat/letsgo_channel_webchat/adapter.py`:

```python
"""WebChat channel adapter — serves chat UI and admin dashboard."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)


class WebChatChannel(ChannelAdapter):
    """WebChat channel adapter with chat UI and admin dashboard.

    Serves a chat interface at ``/chat`` and an admin dashboard at ``/admin/``
    on a single aiohttp server. Admin routes are protected by bearer token
    middleware and only mount when ``admin.enabled=True`` and ``admin.token``
    is set in config (fail-closed).

    Config keys:
        host: Bind address (default: "localhost")
        port: HTTP port (default: 8090)
        admin.enabled: Enable admin dashboard (default: False)
        admin.token: Bearer token for admin auth (required if admin enabled)
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._host: str = config.get("host", "localhost")
        self._port: int = config.get("port", 8090)
        admin_cfg = config.get("admin", {})
        self._admin_enabled: bool = (
            admin_cfg.get("enabled", False) and bool(admin_cfg.get("token"))
        )
        self._admin_token: str = admin_cfg.get("token", "")
        self._chat_clients: set[Any] = set()
        self._app: Any = None
        self._runner: Any = None
        self._site: Any = None
        self._daemon: Any = None

    def set_daemon(self, daemon: Any) -> None:
        """Store a reference to the gateway daemon for admin API access."""
        self._daemon = daemon

    async def start(self) -> None:
        """Start the aiohttp web server."""
        try:
            import aiohttp.web as web
        except ImportError:
            logger.warning(
                "aiohttp not installed — WebChat channel '%s' cannot start",
                self.name,
            )
            return

        middlewares = []
        if self._admin_enabled:
            from .admin import admin_auth_middleware

            middlewares.append(admin_auth_middleware)

        self._app = web.Application(middlewares=middlewares)

        # Chat routes
        self._app.router.add_get("/chat", self._handle_chat_index)
        self._app.router.add_get("/chat/ws", self._handle_chat_websocket)

        # Admin routes (only if enabled + token configured)
        if self._admin_enabled:
            self._app["admin_token"] = self._admin_token
            from .admin import setup_admin_routes

            setup_admin_routes(self._app, self._daemon)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()
        self._running = True
        logger.info(
            "WebChatChannel '%s' started at http://%s:%s/chat",
            self.name,
            self._host,
            self._port,
        )

    async def stop(self) -> None:
        """Stop the web server and disconnect all clients."""
        for ws in set(self._chat_clients):
            try:
                await ws.close()
            except Exception:
                pass
        self._chat_clients.clear()

        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        self._app = None
        self._site = None
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Push a response to connected chat WebSocket clients."""
        ws_message = json.dumps({
            "type": "response",
            "text": message.text,
        })
        await self._broadcast_chat(ws_message)
        return True

    # -- Internal helpers -----------------------------------------------------

    async def _broadcast_chat(self, message: str) -> None:
        """Send a message to all connected chat WebSocket clients."""
        dead: set[Any] = set()
        for ws in self._chat_clients:
            try:
                await ws.send_str(message)
            except Exception:
                dead.add(ws)
        self._chat_clients -= dead

    # -- HTTP handlers --------------------------------------------------------

    async def _handle_chat_index(self, request: Any) -> Any:
        """Serve the chat web UI."""
        from pathlib import Path

        import aiohttp.web as web

        static_dir = Path(__file__).parent / "static" / "chat"
        index_path = static_dir / "index.html"
        if not index_path.exists():
            return web.Response(text="Chat UI not found", status=404)
        return web.FileResponse(index_path)

    async def _handle_chat_websocket(self, request: Any) -> Any:
        """Handle a bidirectional chat WebSocket connection."""
        import aiohttp.web as web

        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._chat_clients.add(ws)
        logger.debug(
            "Chat WebSocket client connected (%d total)",
            len(self._chat_clients),
        )

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    await self._handle_chat_message(ws, msg.data)
        finally:
            self._chat_clients.discard(ws)
            logger.debug(
                "Chat WebSocket client disconnected (%d remain)",
                len(self._chat_clients),
            )

        return ws

    async def _handle_chat_message(self, ws: Any, data: str) -> None:
        """Process an inbound chat message from a WebSocket client."""
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            await ws.send_json({"type": "error", "text": "Invalid JSON"})
            return

        text = payload.get("text", "")
        sender_id = payload.get("sender_id", f"web-{uuid.uuid4().hex[:8]}")

        if not text:
            return

        if self._on_message is None:
            await ws.send_json({
                "type": "error",
                "text": "No message handler configured",
            })
            return

        inbound = InboundMessage(
            channel=ChannelType("webchat"),
            channel_name=self.name,
            sender_id=sender_id,
            sender_label=sender_id,
            text=text,
        )

        try:
            response = await self._on_message(inbound)
        except Exception:
            logger.exception("Error handling chat message")
            response = "An error occurred processing your message."

        # Determine response type
        msg_type = "response"
        if "pairing code" in response.lower():
            msg_type = "pairing"

        await ws.send_json({"type": msg_type, "text": response})
```

### Step 5: Run tests to verify they pass

Run: `PYTHONPATH=channels/webchat:gateway python -m pytest channels/webchat/tests/ -v`

Expected: All 8 tests pass.

### Step 6: Verify no regressions

Run: `python -m pytest tests/test_gateway/ -v`

Expected: Baseline unchanged.

### Step 7: Commit

Message: `feat(webchat): WebChatChannel adapter with chat WebSocket and lifecycle`

Files: all files under `channels/webchat/`

---

## Task 3: Admin Auth Middleware

**Files:**
- Create: `channels/webchat/letsgo_channel_webchat/admin.py`
- Test: `channels/webchat/tests/test_webchat_adapter.py` (append)

### Step 1: Write the failing tests

Append to `channels/webchat/tests/test_webchat_adapter.py`:

```python


# ---------------------------------------------------------------------------
# Admin auth middleware
# ---------------------------------------------------------------------------


class TestAdminAuthMiddleware:
    """Bearer token middleware for /admin/ routes."""

    @pytest.mark.asyncio
    async def test_valid_token_passes(self) -> None:
        ch = _make_webchat(config={
            "port": 0,
            "admin": {"enabled": True, "token": "test-secret-123"},
        })
        daemon = _make_mock_daemon()
        ch.set_daemon(daemon)
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://localhost:{port}/admin/api/sessions",
                    headers={"Authorization": "Bearer test-secret-123"},
                ) as resp:
                    assert resp.status == 200
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self) -> None:
        ch = _make_webchat(config={
            "port": 0,
            "admin": {"enabled": True, "token": "real-token"},
        })
        daemon = _make_mock_daemon()
        ch.set_daemon(daemon)
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://localhost:{port}/admin/api/sessions",
                    headers={"Authorization": "Bearer wrong-token"},
                ) as resp:
                    assert resp.status == 401
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_missing_token_returns_401(self) -> None:
        ch = _make_webchat(config={
            "port": 0,
            "admin": {"enabled": True, "token": "real-token"},
        })
        daemon = _make_mock_daemon()
        ch.set_daemon(daemon)
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://localhost:{port}/admin/api/sessions",
                ) as resp:
                    assert resp.status == 401
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_non_admin_routes_pass_through(self) -> None:
        """Chat routes should not require auth even when admin is enabled."""
        ch = _make_webchat(config={
            "port": 0,
            "admin": {"enabled": True, "token": "secret"},
        })
        daemon = _make_mock_daemon()
        ch.set_daemon(daemon)
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    f"http://localhost:{port}/chat/ws"
                ) as ws:
                    assert not ws.closed
        finally:
            await ch.stop()
```

### Step 2: Run tests to verify they fail

Run: `PYTHONPATH=channels/webchat:gateway python -m pytest channels/webchat/tests/test_webchat_adapter.py::TestAdminAuthMiddleware -v`

Expected: FAILED — `ModuleNotFoundError: No module named 'letsgo_channel_webchat.admin'`

### Step 3: Implement admin.py

Create `channels/webchat/letsgo_channel_webchat/admin.py`:

```python
"""Admin dashboard API routes and auth middleware."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


def _get_web() -> Any:
    """Lazy import aiohttp.web."""
    import aiohttp.web as web

    return web


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------


def admin_auth_middleware_factory(admin_token: str) -> Any:
    """Create admin auth middleware — unused, using app-level approach."""


async def _admin_auth_middleware_impl(
    request: Any, handler: Any
) -> Any:
    """Bearer token middleware for /admin/ routes."""
    web = _get_web()

    if not request.path.startswith("/admin/"):
        return await handler(request)

    expected = request.app.get("admin_token", "")
    auth_header = request.headers.get("Authorization", "")
    if auth_header == f"Bearer {expected}":
        return await handler(request)

    raise web.HTTPUnauthorized(
        text="Invalid or missing admin token",
        headers={"WWW-Authenticate": "Bearer"},
    )


# aiohttp @web.middleware decorator
try:
    from aiohttp import web

    @web.middleware
    async def admin_auth_middleware(request: Any, handler: Any) -> Any:
        """Bearer token middleware for /admin/ routes."""
        if not request.path.startswith("/admin/"):
            return await handler(request)

        expected = request.app.get("admin_token", "")
        auth_header = request.headers.get("Authorization", "")
        if auth_header == f"Bearer {expected}":
            return await handler(request)

        raise web.HTTPUnauthorized(
            text="Invalid or missing admin token",
            headers={"WWW-Authenticate": "Bearer"},
        )

except ImportError:
    admin_auth_middleware = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Admin API route handlers
# ---------------------------------------------------------------------------


async def _handle_admin_index(request: Any) -> Any:
    """Serve the admin dashboard SPA."""
    from pathlib import Path

    web = _get_web()

    static_dir = Path(__file__).parent / "static" / "admin"
    index_path = static_dir / "index.html"
    if not index_path.exists():
        return web.Response(text="Admin dashboard not found", status=404)
    return web.FileResponse(index_path)


async def _handle_sessions(request: Any) -> Any:
    """GET /admin/api/sessions — list active sessions."""
    web = _get_web()
    daemon = request.app["daemon"]

    sessions = daemon.router.active_sessions
    items = []
    for key, sess in sessions.items():
        items.append({
            "route_key": key,
            "session_id": sess.get("session_id", ""),
            "created_at": sess.get("created_at", ""),
            "message_count": sess.get("message_count", 0),
        })

    return web.json_response({"sessions": items, "count": len(items)})


async def _handle_close_session(request: Any) -> Any:
    """DELETE /admin/api/sessions/{key} — close a session."""
    web = _get_web()
    daemon = request.app["daemon"]
    key = request.match_info["key"]

    closed = daemon.router.close_session(key)
    if closed:
        return web.json_response({"status": "closed", "key": key})
    raise web.HTTPNotFound(text=f"Session not found: {key}")


async def _handle_channels(request: Any) -> Any:
    """GET /admin/api/channels — list channels with status."""
    web = _get_web()
    daemon = request.app["daemon"]

    items = []
    for name, adapter in daemon.channels.items():
        items.append({
            "name": name,
            "type": adapter.config.get("type", name),
            "running": adapter.is_running,
        })

    return web.json_response({"channels": items, "count": len(items)})


async def _handle_senders(request: Any) -> Any:
    """GET /admin/api/senders — list all senders."""
    web = _get_web()
    daemon = request.app["daemon"]

    senders = daemon.auth.get_all_senders()
    items = []
    for s in senders:
        items.append({
            "sender_id": s.sender_id,
            "channel": str(s.channel),
            "channel_name": s.channel_name,
            "status": s.status.value,
            "label": s.label,
            "approved_at": (
                s.approved_at.isoformat() if s.approved_at else None
            ),
            "last_seen": (
                s.last_seen.isoformat() if s.last_seen else None
            ),
            "message_count": s.message_count,
        })

    return web.json_response({"senders": items, "count": len(items)})


async def _handle_block_sender(request: Any) -> Any:
    """POST /admin/api/senders/{id}/block — block a sender."""
    web = _get_web()
    daemon = request.app["daemon"]

    try:
        body = await request.json()
    except Exception:
        body = {}

    sender_id = request.match_info["id"]
    channel_str = body.get("channel", "webchat")

    from letsgo_gateway.models import ChannelType

    channel = ChannelType(channel_str)
    daemon.auth.block_sender(sender_id, channel)

    return web.json_response({
        "status": "blocked",
        "sender_id": sender_id,
        "channel": channel_str,
    })


async def _handle_unblock_sender(request: Any) -> Any:
    """POST /admin/api/senders/{id}/unblock — unblock a sender."""
    web = _get_web()
    daemon = request.app["daemon"]

    try:
        body = await request.json()
    except Exception:
        body = {}

    sender_id = request.match_info["id"]
    channel_str = body.get("channel", "webchat")

    from letsgo_gateway.models import ChannelType

    channel = ChannelType(channel_str)
    daemon.auth.unblock_sender(sender_id, channel)

    return web.json_response({
        "status": "unblocked",
        "sender_id": sender_id,
        "channel": channel_str,
    })


async def _handle_cron(request: Any) -> Any:
    """GET /admin/api/cron — list cron jobs and heartbeat status."""
    web = _get_web()
    daemon = request.app["daemon"]

    jobs = daemon.cron.list_jobs()
    heartbeat_history = daemon.heartbeat.history[-10:]  # last 10

    return web.json_response({
        "jobs": jobs,
        "heartbeat_history": heartbeat_history,
    })


async def _handle_usage(request: Any) -> Any:
    """GET /admin/api/usage — gateway-level metrics."""
    web = _get_web()
    daemon = request.app["daemon"]

    uptime = time.monotonic() - getattr(daemon, "_start_time", time.monotonic())
    all_senders = daemon.auth.get_all_senders()

    approved = sum(1 for s in all_senders if s.status.value == "approved")
    blocked = sum(1 for s in all_senders if s.status.value == "blocked")
    pending = sum(1 for s in all_senders if s.status.value == "pending")
    total_messages = sum(s.message_count for s in all_senders)

    active_sessions = len(daemon.router.active_sessions)
    channel_count = len(daemon.channels)
    running_channels = sum(
        1 for a in daemon.channels.values() if a.is_running
    )

    return web.json_response({
        "uptime_seconds": round(uptime, 1),
        "total_messages": total_messages,
        "active_sessions": active_sessions,
        "senders": {
            "approved": approved,
            "blocked": blocked,
            "pending": pending,
            "total": len(all_senders),
        },
        "channels": {
            "configured": channel_count,
            "running": running_channels,
        },
    })


async def _handle_agents(request: Any) -> Any:
    """GET /admin/api/agents — configured agents from config."""
    web = _get_web()
    daemon = request.app["daemon"]

    agents_config = daemon._config.get("agents", {})
    items = []
    for agent_id, agent_cfg in agents_config.items():
        items.append({
            "id": agent_id,
            "workspace": agent_cfg.get("workspace", ""),
            "heartbeat_channels": agent_cfg.get("heartbeat_channels", []),
        })

    return web.json_response({"agents": items, "count": len(items)})


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def setup_admin_routes(app: Any, daemon: Any) -> None:
    """Register all admin routes on the aiohttp app."""
    app["daemon"] = daemon

    app.router.add_get("/admin/", _handle_admin_index)
    app.router.add_get("/admin/api/sessions", _handle_sessions)
    app.router.add_delete(
        "/admin/api/sessions/{key:.+}", _handle_close_session
    )
    app.router.add_get("/admin/api/channels", _handle_channels)
    app.router.add_get("/admin/api/senders", _handle_senders)
    app.router.add_post(
        "/admin/api/senders/{id}/block", _handle_block_sender
    )
    app.router.add_post(
        "/admin/api/senders/{id}/unblock", _handle_unblock_sender
    )
    app.router.add_get("/admin/api/cron", _handle_cron)
    app.router.add_get("/admin/api/usage", _handle_usage)
    app.router.add_get("/admin/api/agents", _handle_agents)
```

### Step 4: Run tests to verify they pass

Run: `PYTHONPATH=channels/webchat:gateway python -m pytest channels/webchat/tests/ -v`

Expected: All 12 tests pass (8 core + 4 middleware).

### Step 5: Commit

Message: `feat(webchat): admin auth middleware and API route registration`

Files: `channels/webchat/letsgo_channel_webchat/admin.py`, `channels/webchat/tests/test_webchat_adapter.py`

---

## Task 4: Admin API Endpoints Tests

**Files:**
- Test: `channels/webchat/tests/test_webchat_adapter.py` (append)

### Step 1: Write the admin API tests

Append to `channels/webchat/tests/test_webchat_adapter.py`:

```python
from letsgo_gateway.models import AuthStatus, SenderRecord


# ---------------------------------------------------------------------------
# Helpers for admin API tests
# ---------------------------------------------------------------------------


def _make_admin_webchat(
    config_overrides: dict[str, Any] | None = None,
) -> tuple[WebChatChannel, MagicMock]:
    """Create a WebChatChannel with admin enabled and a mock daemon."""
    base_config = {
        "port": 0,
        "admin": {"enabled": True, "token": "test-token"},
    }
    if config_overrides:
        base_config.update(config_overrides)
    ch = _make_webchat(config=base_config)
    daemon = _make_mock_daemon()
    ch.set_daemon(daemon)
    return ch, daemon


async def _admin_get(
    port: int, path: str, token: str = "test-token"
) -> tuple[int, dict[str, Any]]:
    """Make an authenticated GET to the admin API."""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"http://localhost:{port}/admin/api/{path}",
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            data = await resp.json()
            return resp.status, data


async def _admin_post(
    port: int, path: str, body: dict | None = None, token: str = "test-token"
) -> tuple[int, dict[str, Any]]:
    """Make an authenticated POST to the admin API."""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"http://localhost:{port}/admin/api/{path}",
            json=body or {},
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            data = await resp.json()
            return resp.status, data


async def _admin_delete(
    port: int, path: str, token: str = "test-token"
) -> tuple[int, dict[str, Any]]:
    """Make an authenticated DELETE to the admin API."""
    async with aiohttp.ClientSession() as session:
        async with session.delete(
            f"http://localhost:{port}/admin/api/{path}",
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            data = await resp.json()
            return resp.status, data


# ---------------------------------------------------------------------------
# Admin API endpoint tests
# ---------------------------------------------------------------------------


class TestAdminAPISessions:
    """GET /admin/api/sessions and DELETE /admin/api/sessions/{key}."""

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self) -> None:
        ch, daemon = _make_admin_webchat()
        daemon.router.active_sessions = {}
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            status, data = await _admin_get(port, "sessions")
            assert status == 200
            assert data["sessions"] == []
            assert data["count"] == 0
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_list_sessions_with_data(self) -> None:
        ch, daemon = _make_admin_webchat()
        daemon.router.active_sessions = {
            "webchat:user1": {
                "session_id": "gw-session-1",
                "route_key": "webchat:user1",
                "created_at": "2026-01-01T00:00:00+00:00",
                "message_count": 5,
            },
        }
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            status, data = await _admin_get(port, "sessions")
            assert status == 200
            assert data["count"] == 1
            assert data["sessions"][0]["session_id"] == "gw-session-1"
            assert data["sessions"][0]["message_count"] == 5
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_close_session(self) -> None:
        ch, daemon = _make_admin_webchat()
        daemon.router.close_session = MagicMock(return_value=True)
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            status, data = await _admin_delete(
                port, "sessions/webchat:user1"
            )
            assert status == 200
            assert data["status"] == "closed"
            daemon.router.close_session.assert_called_once_with(
                "webchat:user1"
            )
        finally:
            await ch.stop()


class TestAdminAPIChannels:
    """GET /admin/api/channels."""

    @pytest.mark.asyncio
    async def test_list_channels(self) -> None:
        ch, daemon = _make_admin_webchat()
        mock_adapter = MagicMock()
        mock_adapter.config = {"type": "webhook"}
        mock_adapter.is_running = True
        daemon.channels = {"main": mock_adapter}
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            status, data = await _admin_get(port, "channels")
            assert status == 200
            assert data["count"] == 1
            assert data["channels"][0]["name"] == "main"
            assert data["channels"][0]["type"] == "webhook"
            assert data["channels"][0]["running"] is True
        finally:
            await ch.stop()


class TestAdminAPISenders:
    """GET /admin/api/senders, POST block/unblock."""

    @pytest.mark.asyncio
    async def test_list_senders(self) -> None:
        ch, daemon = _make_admin_webchat()
        daemon.auth.get_all_senders = MagicMock(return_value=[
            SenderRecord(
                sender_id="alice",
                channel=ChannelType.WEBHOOK,
                channel_name="main",
                status=AuthStatus.APPROVED,
                label="Alice",
                message_count=10,
            ),
        ])
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            status, data = await _admin_get(port, "senders")
            assert status == 200
            assert data["count"] == 1
            assert data["senders"][0]["sender_id"] == "alice"
            assert data["senders"][0]["status"] == "approved"
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_block_sender(self) -> None:
        ch, daemon = _make_admin_webchat()
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            status, data = await _admin_post(
                port,
                "senders/user1/block",
                body={"channel": "webchat"},
            )
            assert status == 200
            assert data["status"] == "blocked"
            daemon.auth.block_sender.assert_called_once()
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_unblock_sender(self) -> None:
        ch, daemon = _make_admin_webchat()
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            status, data = await _admin_post(
                port,
                "senders/user1/unblock",
                body={"channel": "webchat"},
            )
            assert status == 200
            assert data["status"] == "unblocked"
            daemon.auth.unblock_sender.assert_called_once()
        finally:
            await ch.stop()


class TestAdminAPICron:
    """GET /admin/api/cron."""

    @pytest.mark.asyncio
    async def test_list_cron_jobs(self) -> None:
        ch, daemon = _make_admin_webchat()
        daemon.cron.list_jobs = MagicMock(return_value=[
            {
                "name": "heartbeat",
                "cron": "@hourly",
                "recipe": "__heartbeat__",
                "context": {},
                "next_run": "at minute 00 every hour",
                "last_run": None,
            },
        ])
        daemon.heartbeat.history = []
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            status, data = await _admin_get(port, "cron")
            assert status == 200
            assert len(data["jobs"]) == 1
            assert data["jobs"][0]["name"] == "heartbeat"
        finally:
            await ch.stop()


class TestAdminAPIUsage:
    """GET /admin/api/usage."""

    @pytest.mark.asyncio
    async def test_usage_metrics(self) -> None:
        ch, daemon = _make_admin_webchat()
        daemon._start_time = 0.0  # Will make uptime = time.monotonic()
        daemon.auth.get_all_senders = MagicMock(return_value=[
            SenderRecord(
                sender_id="u1",
                channel=ChannelType.WEBHOOK,
                channel_name="wh",
                status=AuthStatus.APPROVED,
                message_count=42,
            ),
            SenderRecord(
                sender_id="u2",
                channel=ChannelType.WEBHOOK,
                channel_name="wh",
                status=AuthStatus.BLOCKED,
                message_count=3,
            ),
        ])
        daemon.router.active_sessions = {"k1": {}, "k2": {}}
        mock_ch = MagicMock()
        mock_ch.is_running = True
        daemon.channels = {"wh": mock_ch}
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            status, data = await _admin_get(port, "usage")
            assert status == 200
            assert data["total_messages"] == 45
            assert data["active_sessions"] == 2
            assert data["senders"]["approved"] == 1
            assert data["senders"]["blocked"] == 1
            assert data["channels"]["configured"] == 1
            assert data["channels"]["running"] == 1
        finally:
            await ch.stop()


class TestAdminAPIAgents:
    """GET /admin/api/agents."""

    @pytest.mark.asyncio
    async def test_list_agents(self) -> None:
        ch, daemon = _make_admin_webchat()
        daemon._config = {
            "agents": {
                "jesse": {
                    "workspace": "~/dev/project",
                    "heartbeat_channels": ["webhook"],
                },
            },
        }
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            status, data = await _admin_get(port, "agents")
            assert status == 200
            assert data["count"] == 1
            assert data["agents"][0]["id"] == "jesse"
        finally:
            await ch.stop()
```

### Step 2: Run tests to verify they pass

Run: `PYTHONPATH=channels/webchat:gateway python -m pytest channels/webchat/tests/ -v`

Expected: All 22 tests pass (8 core + 4 middleware + 10 API endpoints).

### Step 3: Commit

Message: `test(webchat): admin API endpoint tests for all 9 routes`

Files: `channels/webchat/tests/test_webchat_adapter.py`

---

## Task 5: Chat UI — `static/chat/index.html`

**Files:**
- Create: `channels/webchat/letsgo_channel_webchat/static/chat/index.html`

### Step 1: Create the chat interface

Create `channels/webchat/letsgo_channel_webchat/static/chat/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LetsGo Chat</title>
<style>
  :root {
    --bg: #f8f9fa;
    --surface: #ffffff;
    --primary: #0d6efd;
    --primary-hover: #0b5ed7;
    --text: #212529;
    --text-secondary: #6c757d;
    --border: #dee2e6;
    --success: #198754;
    --warning: #ffc107;
    --danger: #dc3545;
    --msg-user: #e3f2fd;
    --msg-bot: #f0f0f0;
    --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: var(--font);
    background: var(--bg);
    color: var(--text);
    height: 100vh;
    display: flex;
    flex-direction: column;
  }
  #header {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 12px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  #header h1 { font-size: 18px; font-weight: 600; }
  #connection-status {
    width: 10px; height: 10px; border-radius: 50%;
    background: var(--danger);
  }
  #connection-status.connected { background: var(--success); }
  #messages {
    flex: 1;
    overflow-y: auto;
    padding: 16px 20px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .message {
    max-width: 75%;
    padding: 10px 14px;
    border-radius: 12px;
    font-size: 14px;
    line-height: 1.5;
    word-wrap: break-word;
  }
  .message.user {
    align-self: flex-end;
    background: var(--msg-user);
    border-bottom-right-radius: 4px;
  }
  .message.bot {
    align-self: flex-start;
    background: var(--msg-bot);
    border-bottom-left-radius: 4px;
  }
  .message.pairing {
    align-self: flex-start;
    background: #fff3cd;
    border: 1px solid var(--warning);
    border-bottom-left-radius: 4px;
  }
  .message.error {
    align-self: center;
    background: #f8d7da;
    border: 1px solid var(--danger);
    color: var(--danger);
    font-size: 13px;
  }
  .message .time {
    font-size: 11px;
    color: var(--text-secondary);
    margin-top: 4px;
  }
  #input-area {
    background: var(--surface);
    border-top: 1px solid var(--border);
    padding: 12px 20px;
    display: flex;
    gap: 8px;
  }
  #message-input {
    flex: 1;
    padding: 10px 14px;
    border: 1px solid var(--border);
    border-radius: 8px;
    font-size: 14px;
    font-family: var(--font);
    outline: none;
    resize: none;
  }
  #message-input:focus { border-color: var(--primary); }
  #send-btn {
    padding: 10px 20px;
    background: var(--primary);
    color: white;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
  }
  #send-btn:hover { background: var(--primary-hover); }
  #send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  #sender-bar {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 8px 20px;
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--text-secondary);
  }
  #sender-id-input {
    padding: 4px 8px;
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 13px;
    width: 180px;
  }
  #empty-state {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-secondary);
    font-size: 15px;
  }
</style>
</head>
<body>

<div id="header">
  <h1>LetsGo Chat</h1>
  <div id="connection-status" title="Disconnected"></div>
</div>

<div id="sender-bar">
  <label for="sender-id-input">Your ID:</label>
  <input type="text" id="sender-id-input" placeholder="web-user-1">
</div>

<div id="messages">
  <div id="empty-state">Send a message to start chatting...</div>
</div>

<div id="input-area">
  <textarea id="message-input" rows="1" placeholder="Type a message..."></textarea>
  <button id="send-btn" disabled>Send</button>
</div>

<script>
(function() {
  const messagesEl = document.getElementById('messages');
  const inputEl = document.getElementById('message-input');
  const sendBtn = document.getElementById('send-btn');
  const statusEl = document.getElementById('connection-status');
  const senderInput = document.getElementById('sender-id-input');
  const emptyState = document.getElementById('empty-state');

  let ws = null;
  let reconnectDelay = 1000;
  const MAX_DELAY = 30000;

  // Generate default sender ID
  senderInput.value = 'web-' + Math.random().toString(36).substr(2, 8);

  function getSenderId() {
    return senderInput.value.trim() || 'web-anonymous';
  }

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${proto}//${location.host}/chat/ws`);

    ws.onopen = function() {
      statusEl.className = 'connected';
      statusEl.title = 'Connected';
      sendBtn.disabled = false;
      reconnectDelay = 1000;
    };

    ws.onmessage = function(event) {
      const data = JSON.parse(event.data);
      addMessage(data.text, data.type || 'response');
    };

    ws.onclose = function() {
      statusEl.className = '';
      statusEl.title = 'Disconnected';
      sendBtn.disabled = true;
      setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, MAX_DELAY);
    };

    ws.onerror = function() {
      ws.close();
    };
  }

  function addMessage(text, type) {
    if (emptyState) emptyState.remove();

    const div = document.createElement('div');
    div.className = 'message ' + (type === 'user' ? 'user' : type === 'pairing' ? 'pairing' : type === 'error' ? 'error' : 'bot');
    div.textContent = text;

    const timeEl = document.createElement('div');
    timeEl.className = 'time';
    timeEl.textContent = new Date().toLocaleTimeString();
    div.appendChild(timeEl);

    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function sendMessage() {
    const text = inputEl.value.trim();
    if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;

    addMessage(text, 'user');
    ws.send(JSON.stringify({ text: text, sender_id: getSenderId() }));
    inputEl.value = '';
    inputEl.style.height = 'auto';
  }

  sendBtn.addEventListener('click', sendMessage);

  inputEl.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Auto-resize textarea
  inputEl.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 120) + 'px';
  });

  connect();
})();
</script>
</body>
</html>
```

### Step 2: Verify the file exists

Run: `wc -l channels/webchat/letsgo_channel_webchat/static/chat/index.html`

Expected: ~210 lines.

### Step 3: Commit

Message: `feat(webchat): chat web UI with WebSocket messaging`

Files: `channels/webchat/letsgo_channel_webchat/static/chat/index.html`

---

## Task 6: Admin Dashboard UI — `static/admin/index.html`

**Files:**
- Create: `channels/webchat/letsgo_channel_webchat/static/admin/index.html`

### Step 1: Create the admin dashboard SPA

Create `channels/webchat/letsgo_channel_webchat/static/admin/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LetsGo Admin Dashboard</title>
<style>
  :root {
    --bg: #f4f5f7;
    --surface: #ffffff;
    --primary: #0d6efd;
    --primary-hover: #0b5ed7;
    --text: #1a1a2e;
    --text-secondary: #6c757d;
    --border: #e0e0e0;
    --success: #198754;
    --warning: #ffc107;
    --danger: #dc3545;
    --info: #0dcaf0;
    --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    --sidebar-w: 200px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: var(--font);
    background: var(--bg);
    color: var(--text);
    height: 100vh;
    display: flex;
    flex-direction: column;
  }
  /* Top bar */
  #topbar {
    background: var(--text);
    color: white;
    padding: 10px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 14px;
  }
  #topbar h1 { font-size: 16px; font-weight: 600; }
  #topbar .status {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  #topbar .status .dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--success);
  }
  #topbar .status .dot.error { background: var(--danger); }

  /* Layout */
  #layout {
    flex: 1;
    display: flex;
    overflow: hidden;
  }

  /* Tab navigation */
  #tabs {
    width: var(--sidebar-w);
    background: var(--surface);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    padding: 8px 0;
  }
  .tab {
    padding: 10px 16px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
    color: var(--text-secondary);
    border-left: 3px solid transparent;
    transition: all 0.15s;
  }
  .tab:hover { background: var(--bg); color: var(--text); }
  .tab.active {
    color: var(--primary);
    border-left-color: var(--primary);
    background: #f0f6ff;
  }
  .tab .badge {
    float: right;
    background: var(--bg);
    padding: 1px 8px;
    border-radius: 10px;
    font-size: 11px;
    color: var(--text-secondary);
  }

  /* Main content */
  #main {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
  }

  /* Panel (tab content) */
  .panel { display: none; }
  .panel.active { display: block; }
  .panel h2 { font-size: 18px; margin-bottom: 16px; }

  /* Tables */
  table {
    width: 100%;
    border-collapse: collapse;
    background: var(--surface);
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }
  th, td {
    text-align: left;
    padding: 10px 14px;
    font-size: 13px;
    border-bottom: 1px solid var(--border);
  }
  th {
    background: var(--bg);
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    font-size: 11px;
    letter-spacing: 0.5px;
  }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #fafbfc; }

  /* Badges */
  .status-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
  }
  .status-badge.approved { background: #d1e7dd; color: #0f5132; }
  .status-badge.blocked { background: #f8d7da; color: #842029; }
  .status-badge.pending { background: #fff3cd; color: #664d03; }
  .status-badge.running { background: #d1e7dd; color: #0f5132; }
  .status-badge.stopped { background: #f8d7da; color: #842029; }

  /* Action buttons */
  .btn {
    padding: 4px 12px;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 12px;
    font-weight: 500;
  }
  .btn-danger { background: var(--danger); color: white; }
  .btn-danger:hover { background: #bb2d3b; }
  .btn-success { background: var(--success); color: white; }
  .btn-success:hover { background: #157347; }
  .btn-secondary { background: #6c757d; color: white; }
  .btn-secondary:hover { background: #5c636a; }

  /* Stat cards */
  .stat-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px;
    margin-bottom: 20px;
  }
  .stat-card {
    background: var(--surface);
    padding: 16px;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }
  .stat-card .label {
    font-size: 11px;
    text-transform: uppercase;
    color: var(--text-secondary);
    letter-spacing: 0.5px;
    margin-bottom: 4px;
  }
  .stat-card .value {
    font-size: 24px;
    font-weight: 700;
  }
  .stat-card .sub {
    font-size: 12px;
    color: var(--text-secondary);
    margin-top: 2px;
  }

  /* Empty states */
  .empty {
    text-align: center;
    padding: 40px;
    color: var(--text-secondary);
    font-size: 14px;
  }

  /* Token prompt */
  #token-overlay {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
  }
  #token-overlay.hidden { display: none; }
  #token-box {
    background: white;
    padding: 32px;
    border-radius: 12px;
    width: 360px;
    box-shadow: 0 8px 30px rgba(0,0,0,0.2);
  }
  #token-box h2 { font-size: 18px; margin-bottom: 12px; }
  #token-box p { font-size: 13px; color: var(--text-secondary); margin-bottom: 16px; }
  #token-box input {
    width: 100%;
    padding: 10px;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 14px;
    margin-bottom: 12px;
  }
  #token-box button {
    width: 100%;
    padding: 10px;
    background: var(--primary);
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 14px;
    cursor: pointer;
  }
  #token-box button:hover { background: var(--primary-hover); }
  #token-error {
    color: var(--danger);
    font-size: 12px;
    margin-top: 8px;
    display: none;
  }

  /* Refresh indicator */
  #refresh-indicator {
    font-size: 11px;
    color: var(--text-secondary);
  }
</style>
</head>
<body>

<!-- Token prompt overlay -->
<div id="token-overlay">
  <div id="token-box">
    <h2>Admin Authentication</h2>
    <p>Enter the admin token from your gateway config.</p>
    <input type="password" id="token-input" placeholder="Bearer token">
    <button id="token-submit">Connect</button>
    <div id="token-error">Invalid token. Please try again.</div>
  </div>
</div>

<!-- Top bar -->
<div id="topbar">
  <h1>LetsGo Admin</h1>
  <div class="status">
    <span id="refresh-indicator">Refreshing...</span>
    <div class="dot" id="api-status"></div>
  </div>
</div>

<!-- Layout -->
<div id="layout">
  <!-- Sidebar tabs -->
  <div id="tabs">
    <div class="tab active" data-panel="sessions">Sessions <span class="badge" id="badge-sessions">0</span></div>
    <div class="tab" data-panel="channels">Channels <span class="badge" id="badge-channels">0</span></div>
    <div class="tab" data-panel="senders">Senders <span class="badge" id="badge-senders">0</span></div>
    <div class="tab" data-panel="cron">Cron <span class="badge" id="badge-cron">0</span></div>
    <div class="tab" data-panel="usage">Usage</div>
    <div class="tab" data-panel="agents">Agents <span class="badge" id="badge-agents">0</span></div>
  </div>

  <!-- Main content panels -->
  <div id="main">

    <!-- Sessions Panel -->
    <div class="panel active" id="panel-sessions">
      <h2>Active Sessions</h2>
      <div id="sessions-content"><div class="empty">Loading...</div></div>
    </div>

    <!-- Channels Panel -->
    <div class="panel" id="panel-channels">
      <h2>Channels</h2>
      <div id="channels-content"><div class="empty">Loading...</div></div>
    </div>

    <!-- Senders Panel -->
    <div class="panel" id="panel-senders">
      <h2>Senders</h2>
      <div id="senders-content"><div class="empty">Loading...</div></div>
    </div>

    <!-- Cron Panel -->
    <div class="panel" id="panel-cron">
      <h2>Cron Jobs &amp; Heartbeat</h2>
      <div id="cron-content"><div class="empty">Loading...</div></div>
    </div>

    <!-- Usage Panel -->
    <div class="panel" id="panel-usage">
      <h2>Usage Metrics</h2>
      <div id="usage-content"><div class="empty">Loading...</div></div>
    </div>

    <!-- Agents Panel -->
    <div class="panel" id="panel-agents">
      <h2>Agents</h2>
      <div id="agents-content"><div class="empty">Loading...</div></div>
    </div>

  </div>
</div>

<script>
(function() {
  let TOKEN = localStorage.getItem('letsgo_admin_token') || '';
  let refreshInterval = null;

  // ---- Token management ----
  const overlay = document.getElementById('token-overlay');
  const tokenInput = document.getElementById('token-input');
  const tokenSubmit = document.getElementById('token-submit');
  const tokenError = document.getElementById('token-error');

  if (TOKEN) {
    overlay.classList.add('hidden');
    startDashboard();
  }

  tokenSubmit.addEventListener('click', async function() {
    const t = tokenInput.value.trim();
    if (!t) return;
    TOKEN = t;
    try {
      const resp = await apiFetch('sessions');
      if (resp.ok) {
        localStorage.setItem('letsgo_admin_token', TOKEN);
        overlay.classList.add('hidden');
        tokenError.style.display = 'none';
        startDashboard();
      } else {
        tokenError.style.display = 'block';
        TOKEN = '';
      }
    } catch(e) {
      tokenError.style.display = 'block';
      TOKEN = '';
    }
  });

  tokenInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') tokenSubmit.click();
  });

  // ---- API helpers ----
  function apiFetch(path, opts) {
    opts = opts || {};
    opts.headers = opts.headers || {};
    opts.headers['Authorization'] = 'Bearer ' + TOKEN;
    return fetch('/admin/api/' + path, opts);
  }

  async function apiGet(path) {
    const resp = await apiFetch(path);
    if (!resp.ok) throw new Error('API error: ' + resp.status);
    return resp.json();
  }

  async function apiPost(path, body) {
    const resp = await apiFetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
    return resp.json();
  }

  async function apiDelete(path) {
    const resp = await apiFetch(path, { method: 'DELETE' });
    return resp.json();
  }

  // ---- Tab switching ----
  document.querySelectorAll('.tab').forEach(function(tab) {
    tab.addEventListener('click', function() {
      document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
      document.querySelectorAll('.panel').forEach(function(p) { p.classList.remove('active'); });
      tab.classList.add('active');
      document.getElementById('panel-' + tab.dataset.panel).classList.add('active');
    });
  });

  // ---- Rendering functions ----

  function renderSessions(data) {
    const el = document.getElementById('sessions-content');
    document.getElementById('badge-sessions').textContent = data.count;
    if (!data.sessions.length) {
      el.innerHTML = '<div class="empty">No active sessions</div>';
      return;
    }
    let html = '<table><thead><tr><th>Session ID</th><th>Route Key</th><th>Created</th><th>Messages</th><th>Actions</th></tr></thead><tbody>';
    data.sessions.forEach(function(s) {
      html += '<tr>';
      html += '<td>' + esc(s.session_id) + '</td>';
      html += '<td>' + esc(s.route_key) + '</td>';
      html += '<td>' + formatDate(s.created_at) + '</td>';
      html += '<td>' + s.message_count + '</td>';
      html += '<td><button class="btn btn-danger" onclick="closeSession(\'' + esc(s.route_key) + '\')">Close</button></td>';
      html += '</tr>';
    });
    html += '</tbody></table>';
    el.innerHTML = html;
  }

  function renderChannels(data) {
    const el = document.getElementById('channels-content');
    document.getElementById('badge-channels').textContent = data.count;
    if (!data.channels.length) {
      el.innerHTML = '<div class="empty">No channels configured</div>';
      return;
    }
    let html = '<table><thead><tr><th>Name</th><th>Type</th><th>Status</th></tr></thead><tbody>';
    data.channels.forEach(function(c) {
      const status = c.running ? 'running' : 'stopped';
      html += '<tr>';
      html += '<td>' + esc(c.name) + '</td>';
      html += '<td>' + esc(c.type) + '</td>';
      html += '<td><span class="status-badge ' + status + '">' + status + '</span></td>';
      html += '</tr>';
    });
    html += '</tbody></table>';
    el.innerHTML = html;
  }

  function renderSenders(data) {
    const el = document.getElementById('senders-content');
    document.getElementById('badge-senders').textContent = data.count;
    if (!data.senders.length) {
      el.innerHTML = '<div class="empty">No senders registered</div>';
      return;
    }
    let html = '<table><thead><tr><th>Sender ID</th><th>Channel</th><th>Status</th><th>Messages</th><th>Last Seen</th><th>Actions</th></tr></thead><tbody>';
    data.senders.forEach(function(s) {
      html += '<tr>';
      html += '<td>' + esc(s.sender_id) + '</td>';
      html += '<td>' + esc(s.channel) + '</td>';
      html += '<td><span class="status-badge ' + s.status + '">' + s.status + '</span></td>';
      html += '<td>' + s.message_count + '</td>';
      html += '<td>' + formatDate(s.last_seen) + '</td>';
      html += '<td>';
      if (s.status === 'approved') {
        html += '<button class="btn btn-danger" onclick="blockSender(\'' + esc(s.sender_id) + '\',\'' + esc(s.channel) + '\')">Block</button>';
      } else if (s.status === 'blocked') {
        html += '<button class="btn btn-success" onclick="unblockSender(\'' + esc(s.sender_id) + '\',\'' + esc(s.channel) + '\')">Unblock</button>';
      }
      html += '</td>';
      html += '</tr>';
    });
    html += '</tbody></table>';
    el.innerHTML = html;
  }

  function renderCron(data) {
    const el = document.getElementById('cron-content');
    document.getElementById('badge-cron').textContent = data.jobs.length;
    let html = '';
    if (data.jobs.length) {
      html += '<h3 style="font-size:14px;margin-bottom:8px;">Scheduled Jobs</h3>';
      html += '<table><thead><tr><th>Name</th><th>Schedule</th><th>Recipe</th><th>Next Run</th><th>Last Run</th></tr></thead><tbody>';
      data.jobs.forEach(function(j) {
        html += '<tr>';
        html += '<td>' + esc(j.name) + '</td>';
        html += '<td><code>' + esc(j.cron) + '</code></td>';
        html += '<td>' + esc(j.recipe) + '</td>';
        html += '<td>' + esc(j.next_run) + '</td>';
        html += '<td>' + formatDate(j.last_run) + '</td>';
        html += '</tr>';
      });
      html += '</tbody></table>';
    } else {
      html += '<div class="empty">No cron jobs configured</div>';
    }

    if (data.heartbeat_history && data.heartbeat_history.length) {
      html += '<h3 style="font-size:14px;margin:16px 0 8px;">Recent Heartbeats</h3>';
      html += '<table><thead><tr><th>Agent</th><th>Status</th><th>Time</th><th>Duration</th></tr></thead><tbody>';
      data.heartbeat_history.forEach(function(h) {
        html += '<tr>';
        html += '<td>' + esc(h.agent_id || '') + '</td>';
        html += '<td><span class="status-badge ' + (h.status === 'completed' ? 'approved' : 'blocked') + '">' + esc(h.status) + '</span></td>';
        html += '<td>' + formatDate(h.timestamp) + '</td>';
        html += '<td>' + (h.duration_ms || 0) + 'ms</td>';
        html += '</tr>';
      });
      html += '</tbody></table>';
    }

    el.innerHTML = html;
  }

  function renderUsage(data) {
    const el = document.getElementById('usage-content');
    let html = '<div class="stat-grid">';

    html += statCard('Uptime', formatUptime(data.uptime_seconds), '');
    html += statCard('Total Messages', data.total_messages, 'across all senders');
    html += statCard('Active Sessions', data.active_sessions, '');
    html += statCard('Senders', data.senders.total,
      data.senders.approved + ' approved, ' + data.senders.blocked + ' blocked, ' + data.senders.pending + ' pending');
    html += statCard('Channels', data.channels.running + '/' + data.channels.configured, 'running / configured');

    html += '</div>';
    el.innerHTML = html;
  }

  function renderAgents(data) {
    const el = document.getElementById('agents-content');
    document.getElementById('badge-agents').textContent = data.count;
    if (!data.agents.length) {
      el.innerHTML = '<div class="empty">No agents configured</div>';
      return;
    }
    let html = '<table><thead><tr><th>Agent ID</th><th>Workspace</th><th>Heartbeat Channels</th></tr></thead><tbody>';
    data.agents.forEach(function(a) {
      html += '<tr>';
      html += '<td>' + esc(a.id) + '</td>';
      html += '<td><code>' + esc(a.workspace) + '</code></td>';
      html += '<td>' + esc((a.heartbeat_channels || []).join(', ') || 'none') + '</td>';
      html += '</tr>';
    });
    html += '</tbody></table>';
    el.innerHTML = html;
  }

  // ---- Helper functions ----

  function statCard(label, value, sub) {
    return '<div class="stat-card"><div class="label">' + label + '</div><div class="value">' + value + '</div>' + (sub ? '<div class="sub">' + sub + '</div>' : '') + '</div>';
  }

  function esc(s) {
    if (s == null) return '';
    const d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
  }

  function formatDate(s) {
    if (!s) return '-';
    try {
      const d = new Date(s);
      return d.toLocaleString();
    } catch(e) { return s; }
  }

  function formatUptime(seconds) {
    if (!seconds) return '0s';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return h + 'h ' + m + 'm';
    if (m > 0) return m + 'm ' + s + 's';
    return s + 's';
  }

  // ---- Global action functions ----

  window.closeSession = async function(key) {
    if (!confirm('Close session ' + key + '?')) return;
    await apiDelete('sessions/' + encodeURIComponent(key));
    refreshAll();
  };

  window.blockSender = async function(senderId, channel) {
    if (!confirm('Block sender ' + senderId + '?')) return;
    await apiPost('senders/' + encodeURIComponent(senderId) + '/block', { channel: channel });
    refreshAll();
  };

  window.unblockSender = async function(senderId, channel) {
    await apiPost('senders/' + encodeURIComponent(senderId) + '/unblock', { channel: channel });
    refreshAll();
  };

  // ---- Data refresh ----

  async function refreshAll() {
    const indicator = document.getElementById('refresh-indicator');
    const statusDot = document.getElementById('api-status');
    indicator.textContent = 'Refreshing...';

    try {
      const [sessions, channels, senders, cron, usage, agents] = await Promise.all([
        apiGet('sessions'),
        apiGet('channels'),
        apiGet('senders'),
        apiGet('cron'),
        apiGet('usage'),
        apiGet('agents'),
      ]);
      renderSessions(sessions);
      renderChannels(channels);
      renderSenders(senders);
      renderCron(cron);
      renderUsage(usage);
      renderAgents(agents);
      statusDot.className = 'dot';
      indicator.textContent = 'Updated ' + new Date().toLocaleTimeString();
    } catch(e) {
      statusDot.className = 'dot error';
      indicator.textContent = 'Error: ' + e.message;
    }
  }

  function startDashboard() {
    refreshAll();
    refreshInterval = setInterval(refreshAll, 5000);
  }

})();
</script>
</body>
</html>
```

### Step 2: Verify the file exists

Run: `wc -l channels/webchat/letsgo_channel_webchat/static/admin/index.html`

Expected: ~500-600 lines (compact but complete).

### Step 3: Commit

Message: `feat(webchat): admin dashboard SPA with 6-tab interface`

Files: `channels/webchat/letsgo_channel_webchat/static/admin/index.html`

---

## Task 7: Satellite Bundle Structure

**Files:**
- Create: `webchat/bundle.md`
- Create: `webchat/behaviors/webchat-capabilities.yaml`
- Create: `webchat/context/webchat-awareness.md`
- Create: `webchat/agents/admin-assistant.md`

### Step 1: Create bundle.md

Create `webchat/bundle.md`:

```markdown
---
name: letsgo-webchat
version: 0.1.0
description: Web chat interface and admin dashboard for the LetsGo gateway
author: letsgo
tags:
  - webchat
  - admin
  - dashboard
  - chat
includes: []
behaviors:
  - ./behaviors/webchat-capabilities.yaml
---

# letsgo-webchat

Web chat interface for messaging and a 6-view admin dashboard for gateway management. Requires the `letsgo-channel-webchat` gateway plugin package (`pip install letsgo-channel-webchat`).
```

### Step 2: Create behavior YAML

Create `webchat/behaviors/webchat-capabilities.yaml`:

```yaml
bundle:
  name: behavior-webchat-capabilities
  version: 1.0.0
  description: WebChat and admin dashboard capabilities for the LetsGo gateway

context:
  include:
    - letsgo-webchat:context/webchat-awareness.md
```

### Step 3: Create context document

Create `webchat/context/webchat-awareness.md`:

```markdown
# WebChat Awareness

You have access to a web chat interface and admin dashboard via the `letsgo-webchat` satellite bundle.

## Web Chat Interface

The gateway serves a web chat UI at `http://{host}:{port}/chat` (default: `http://localhost:8090/chat`). Users can chat with you directly through their browser using WebSocket for real-time bidirectional messaging. The pairing flow works the same as other channels — first-time senders receive a pairing code.

## Admin Dashboard

An admin dashboard is available at `http://{host}:{port}/admin/` when `admin.enabled` is `true` in the gateway config. It provides 6 views:

- **Sessions** — Active sessions with route keys, message counts, and the ability to close sessions
- **Channels** — Configured channel adapters and their running status
- **Senders** — All registered senders with approval status, message counts, block/unblock actions
- **Cron/Heartbeat** — Scheduled jobs and recent heartbeat execution history
- **Usage** — Gateway-level metrics: uptime, total messages, sender counts, channel status
- **Agents** — Configured agents with workspaces and heartbeat channel assignments

The admin dashboard requires a bearer token (configured in `admin.token` in the gateway config). If the token is not configured, admin routes are not mounted (fail-closed security).

## When to Mention

- When users ask about monitoring or managing the gateway
- When troubleshooting channel or session issues (direct them to the dashboard)
- When users need to block/unblock senders or close sessions
- When setting up the gateway (mention webchat as a channel option)
```

### Step 4: Create admin assistant agent

Create `webchat/agents/admin-assistant.md`:

```markdown
# Admin Assistant

Gateway administration specialist. Helps users understand and manage their LetsGo gateway through the admin dashboard.

## When to Use

- Interpreting dashboard metrics and session data
- Helping users manage senders (block, unblock, review)
- Troubleshooting channel connectivity issues
- Explaining cron job schedules and heartbeat results
- Reviewing usage patterns and suggesting optimizations

## Capabilities

- Read and interpret admin API data (sessions, channels, senders, cron, usage, agents)
- Guide users through admin dashboard features
- Help configure webchat channel settings
- Explain pairing flow and sender management
```

### Step 5: Verify files exist

Run: `find webchat/ -type f | sort`

Expected:
```
webchat/agents/admin-assistant.md
webchat/behaviors/webchat-capabilities.yaml
webchat/bundle.md
webchat/context/webchat-awareness.md
```

### Step 6: Commit

Message: `feat(webchat): satellite bundle structure — bundle.md, behaviors, context, agent`

Files: all files under `webchat/`

---

## Task 8: Update Setup Wizard Recipe

**Files:**
- Modify: `recipes/setup-wizard.yaml`

### Step 1: Add configure-webchat step

In `recipes/setup-wizard.yaml`, add a new step after the `configure-browser` step (line 245) and before the `approval:` section of the `satellite-setup` stage:

```yaml
      - id: configure-webchat
        agent: self
        prompt: >
          If webchat was selected in {{satellite_config}}:

          1. **WebChat channel setup:**
             - Ask: What port should the webchat server use? (default: 8090)
             - Ask: Bind to localhost only or all interfaces? (default: localhost)
             - Note: Chat will be at http://{host}:{port}/chat
             - Note: Admin dashboard at http://{host}:{port}/admin/

          2. **Admin dashboard setup:**
             - Ask: Enable admin dashboard? (recommended: yes)
             - If yes: Generate a random admin token or let user provide one
             - Store token via secrets tool as "webchat/admin/token" (category: api_key)

          3. **Install webchat channel package:**
             - Run: pip install letsgo-channel-webchat

          4. **Update gateway config:**
             - Add webchat channel to ~/.letsgo/gateway/config.yaml:
               channels:
                 webchat:
                   type: webchat
                   host: "<chosen-host>"
                   port: <chosen-port>
                   admin:
                     enabled: true
                     token: "<stored-token>"

          If webchat was NOT selected, skip this step entirely and report "WebChat: skipped".
        output: webchat_config
        timeout: 180
```

Also update the approval prompt of `satellite-setup` to include `{{webchat_config}}`.

### Step 2: Validate YAML

Run: `python -c "import yaml; yaml.safe_load(open('recipes/setup-wizard.yaml')); print('Valid YAML')"`

Expected: `Valid YAML`

### Step 3: Commit

Message: `feat(webchat): add webchat configuration step to setup-wizard recipe`

Files: `recipes/setup-wizard.yaml`

---

## Task 9: Integration Tests — Full WebChat Pipeline

**Files:**
- Create: `tests/test_gateway/test_webchat_integration.py`

### Step 1: Write integration tests

Create `tests/test_gateway/test_webchat_integration.py`:

```python
"""Integration tests — WebChat channel through the gateway daemon."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from letsgo_gateway.daemon import GatewayDaemon
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_daemon(tmp_path: Path, **config_overrides: Any) -> GatewayDaemon:
    """Create a GatewayDaemon with given config overrides."""
    config = {
        "channels": {},
        "auth": {"pairing_db_path": str(tmp_path / "pairing.json")},
        "cron": {"log_path": str(tmp_path / "cron.jsonl")},
        "files_dir": str(tmp_path / "files"),
        **config_overrides,
    }
    return GatewayDaemon(config=config)


class FakeWebChatChannel:
    """Fake webchat channel that records sent messages."""

    def __init__(self, name: str = "webchat") -> None:
        self.name = name
        self.config: dict[str, Any] = {"type": "webchat"}
        self._running = True
        self._on_message = None
        self.sent: list[OutboundMessage] = []

    @property
    def is_running(self) -> bool:
        return self._running

    def set_on_message(self, callback: Any) -> None:
        self._on_message = callback

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        self.sent.append(message)
        return True


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestWebChatDaemonIntegration:
    """WebChat channel integration with the gateway daemon."""

    @pytest.mark.asyncio
    async def test_daemon_discovers_webchat_channel(
        self, tmp_path: Path
    ) -> None:
        """When webchat plugin is in registry, daemon can create it."""
        fake_cls = MagicMock(side_effect=lambda name, config: FakeWebChatChannel(name))

        with patch(
            "letsgo_gateway.daemon.discover_channels",
            return_value={"webchat": fake_cls},
        ):
            daemon = _make_daemon(
                tmp_path,
                channels={"webchat": {"type": "webchat"}},
            )

        assert "webchat" in daemon.channels

    @pytest.mark.asyncio
    async def test_daemon_without_webchat_works(
        self, tmp_path: Path
    ) -> None:
        """Daemon works normally without a webchat channel."""
        daemon = _make_daemon(tmp_path)
        assert "webchat" not in daemon.channels

    @pytest.mark.asyncio
    async def test_webchat_inbound_routes_through_daemon(
        self, tmp_path: Path
    ) -> None:
        """Message from webchat channel routes through daemon._on_message."""
        daemon = _make_daemon(tmp_path)

        # Simulate inbound from webchat
        msg = InboundMessage(
            channel=ChannelType("webchat"),
            channel_name="webchat",
            sender_id="web-user-1",
            sender_label="web-user-1",
            text="hello",
        )

        # First message from unapproved sender -> pairing
        response = await daemon._on_message(msg)
        assert "pairing code" in response.lower()

    @pytest.mark.asyncio
    async def test_webchat_outbound_to_fake_channel(
        self, tmp_path: Path
    ) -> None:
        """Daemon sends outbound through webchat adapter."""
        fake = FakeWebChatChannel()
        daemon = _make_daemon(tmp_path)
        daemon.channels["webchat"] = fake

        outbound = OutboundMessage(
            channel=ChannelType("webchat"),
            channel_name="webchat",
            thread_id=None,
            text="Hello from the agent!",
        )

        await fake.send(outbound)
        assert len(fake.sent) == 1
        assert fake.sent[0].text == "Hello from the agent!"
```

### Step 2: Run integration tests

Run: `python -m pytest tests/test_gateway/test_webchat_integration.py -v`

Expected: All 4 tests pass.

### Step 3: Run full test suite

Run: `python -m pytest tests/test_gateway/ -v`

Expected: Baseline + 4 new (57+ passed, 3 pre-existing failures).

### Step 4: Commit

Message: `test(webchat): integration tests for WebChat channel through gateway`

Files: `tests/test_gateway/test_webchat_integration.py`

---

## Task 10: Final Verification and Cleanup

### Step 1: Run full test suite

Run: `python -m pytest tests/ -v`

Expected: All tests pass (except 3 pre-existing failures in stub channel tests).

### Step 2: Run webchat channel adapter tests

Run: `PYTHONPATH=channels/webchat:gateway python -m pytest channels/webchat/tests/ -v`

Expected: All 22 tests pass.

### Step 3: Validate all YAML files

Run:
```bash
python -c "import yaml; yaml.safe_load(open('recipes/setup-wizard.yaml')); print('setup-wizard: OK')"
python -c "import yaml; yaml.safe_load(open('webchat/behaviors/webchat-capabilities.yaml')); print('behavior: OK')"
```

Expected: Both valid.

### Step 4: Show git log

Run: `git log --oneline feat/openclaw-migration-phase5-webchat...`

Expected: ~9 commits covering all tasks.

---

## Summary

| Task | What Ships | Tests | Commit Message |
|------|-----------|-------|----------------|
| 1 | `get_all_senders()` + `unblock_sender()` on PairingStore | 3 | `feat(gateway): add get_all_senders and unblock_sender to PairingStore` |
| 2 | WebChatChannel adapter (lifecycle, chat WS, send) | 8 | `feat(webchat): WebChatChannel adapter with chat WebSocket and lifecycle` |
| 3 | Admin auth middleware + route registration | 4 | `feat(webchat): admin auth middleware and API route registration` |
| 4 | Admin API endpoint tests (9 endpoints) | 10 | `test(webchat): admin API endpoint tests for all 9 routes` |
| 5 | Chat UI (`static/chat/index.html`) | 0 | `feat(webchat): chat web UI with WebSocket messaging` |
| 6 | Admin dashboard (`static/admin/index.html`) | 0 | `feat(webchat): admin dashboard SPA with 6-tab interface` |
| 7 | Satellite bundle (bundle.md, behavior, context, agent) | 0 | `feat(webchat): satellite bundle structure` |
| 8 | Setup wizard recipe update | 0 | `feat(webchat): add webchat configuration step to setup-wizard recipe` |
| 9 | Integration tests (daemon wiring) | 4 | `test(webchat): integration tests for WebChat channel through gateway` |
| 10 | Final verification | 0 | (verification only) |
| **Total** | | **~29** | |
