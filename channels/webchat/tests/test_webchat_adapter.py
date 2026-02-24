"""Tests for WebChatChannel adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp.test_utils import TestClient, TestServer
from letsgo_channel_webchat import WebChatChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import AuthStatus, ChannelType, OutboundMessage, SenderRecord

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_channel(**overrides) -> WebChatChannel:
    config = {
        "host": "localhost",
        "port": 0,  # OS-assigned port for tests
        **overrides,
    }
    return WebChatChannel("webchat", config)


# ---------------------------------------------------------------------------
# TestWebChatChannelSubclass
# ---------------------------------------------------------------------------


class TestWebChatChannelSubclass:
    """WebChatChannel inherits from ChannelAdapter correctly."""

    def test_is_channel_adapter(self):
        """WebChatChannel is a subclass of ChannelAdapter."""
        assert issubclass(WebChatChannel, ChannelAdapter)

    def test_instantiation(self):
        """Can instantiate with name and config dict."""
        ch = _make_channel()
        assert ch.name == "webchat"
        assert ch.is_running is False

    def test_default_config(self):
        """Default host/port come from config; admin defaults to disabled."""
        ch = _make_channel()
        assert ch.config["host"] == "localhost"
        assert ch.config["port"] == 0
        # admin not enabled by default
        assert ch.config.get("admin", {}).get("enabled") is not True


# ---------------------------------------------------------------------------
# TestWebChatChannelLifecycle
# ---------------------------------------------------------------------------


class TestWebChatChannelLifecycle:
    """Start / stop lifecycle."""

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self):
        """Stopping a channel that hasn't started is a no-op."""
        ch = _make_channel()
        await ch.stop()  # should not raise
        assert ch.is_running is False

    @pytest.mark.asyncio
    async def test_stop_after_start(self):
        """Channel can be started and then stopped cleanly."""
        ch = _make_channel()
        await ch.start()
        assert ch.is_running is True
        await ch.stop()
        assert ch.is_running is False

    @pytest.mark.asyncio
    async def test_admin_routes_not_mounted_without_token(self):
        """Without admin.enabled + admin.token, no /admin/ routes exist."""
        ch = _make_channel()
        await ch.start()
        try:
            # Build a test client against the internal app
            async with TestClient(TestServer(ch._app)) as client:
                resp = await client.get("/admin/sessions")
                assert resp.status == 404
        finally:
            await ch.stop()


# ---------------------------------------------------------------------------
# TestWebChatChannelChat
# ---------------------------------------------------------------------------


class TestWebChatChannelChat:
    """Chat WebSocket and send behaviour."""

    @pytest.mark.asyncio
    async def test_websocket_connection(self):
        """A client can connect to /chat/ws."""
        ch = _make_channel()
        callback = AsyncMock(return_value="pong")
        ch.set_on_message(callback)
        await ch.start()
        try:
            async with TestClient(TestServer(ch._app)) as client:
                ws = await client.ws_connect("/chat/ws")
                await ws.send_json({"text": "ping", "sender_id": "u1"})
                resp = await ws.receive_json()
                assert resp["text"] == "pong"
                await ws.close()
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_send_pushes_to_clients(self):
        """send() broadcasts an OutboundMessage to connected WS clients."""
        ch = _make_channel()
        callback = AsyncMock(return_value="ignored")
        ch.set_on_message(callback)
        await ch.start()
        try:
            async with TestClient(TestServer(ch._app)) as client:
                ws = await client.ws_connect("/chat/ws")
                msg = OutboundMessage(
                    channel=ChannelType("webchat"),
                    channel_name="webchat",
                    thread_id=None,
                    text="hello from server",
                )
                result = await ch.send(msg)
                assert result is True

                resp = await ws.receive_json()
                assert resp["text"] == "hello from server"
                await ws.close()
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_inbound_routes_through_callback(self):
        """Inbound WS message triggers the _on_message callback."""
        ch = _make_channel()
        callback = AsyncMock(return_value="reply")
        ch.set_on_message(callback)
        await ch.start()
        try:
            async with TestClient(TestServer(ch._app)) as client:
                ws = await client.ws_connect("/chat/ws")
                await ws.send_json({"text": "hello", "sender_id": "u2"})
                await ws.receive_json()  # consume reply
                await ws.close()

            assert callback.call_count == 1
            inbound = callback.call_args[0][0]
            assert inbound.text == "hello"
            assert inbound.sender_id == "u2"
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_set_daemon(self):
        """set_daemon stores the daemon reference for admin API."""
        ch = _make_channel()
        daemon = MagicMock()
        ch.set_daemon(daemon)
        assert ch._daemon is daemon


# ---------------------------------------------------------------------------
# TestAdminAuthMiddleware
# ---------------------------------------------------------------------------

_ADMIN_TOKEN = "test-secret-token"


def _make_admin_channel(**overrides) -> WebChatChannel:
    """Create a channel with admin enabled and a token."""
    config = {
        "host": "localhost",
        "port": 0,
        "admin": {"enabled": True, "token": _ADMIN_TOKEN},
        **overrides,
    }
    ch = WebChatChannel("webchat", config)
    # Provide a minimal daemon mock so admin handlers don't crash
    daemon = MagicMock()
    daemon.session_manager.list_sessions.return_value = []
    ch.set_daemon(daemon)
    return ch


class TestAdminAuthMiddleware:
    """Bearer-token auth middleware for /admin/ routes."""

    @pytest.mark.asyncio
    async def test_valid_token_passes(self):
        """A valid Bearer token gets 200 on admin endpoints."""
        ch = _make_admin_channel()
        await ch.start()
        try:
            async with TestClient(TestServer(ch._app)) as client:
                resp = await client.get(
                    "/admin/sessions",
                    headers={"Authorization": f"Bearer {_ADMIN_TOKEN}"},
                )
                assert resp.status == 200
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self):
        """A wrong Bearer token gets 401."""
        ch = _make_admin_channel()
        await ch.start()
        try:
            async with TestClient(TestServer(ch._app)) as client:
                resp = await client.get(
                    "/admin/sessions",
                    headers={"Authorization": "Bearer wrong-token"},
                )
                assert resp.status == 401
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_missing_token_returns_401(self):
        """No Authorization header gets 401."""
        ch = _make_admin_channel()
        await ch.start()
        try:
            async with TestClient(TestServer(ch._app)) as client:
                resp = await client.get("/admin/sessions")
                assert resp.status == 401
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_non_admin_routes_pass_through(self):
        """Chat WS endpoint works without auth — middleware only guards /admin/."""
        ch = _make_admin_channel()
        callback = AsyncMock(return_value="ok")
        ch.set_on_message(callback)
        await ch.start()
        try:
            async with TestClient(TestServer(ch._app)) as client:
                ws = await client.ws_connect("/chat/ws")
                await ws.send_json({"text": "hi", "sender_id": "u1"})
                resp = await ws.receive_json()
                assert resp["text"] == "ok"
                await ws.close()
        finally:
            await ch.stop()


# ---------------------------------------------------------------------------
# Helpers for admin API endpoint tests
# ---------------------------------------------------------------------------


def _make_admin_webchat() -> tuple[WebChatChannel, MagicMock]:
    """Create a WebChatChannel with admin enabled and a comprehensive mock daemon."""
    config = {
        "host": "localhost",
        "port": 0,
        "admin": {"enabled": True, "token": _ADMIN_TOKEN},
    }
    ch = WebChatChannel("webchat", config)
    daemon = MagicMock()
    # Sensible defaults for all admin API handlers
    daemon.router.active_sessions.return_value = {}
    daemon.router.close_session.return_value = True
    daemon.channels = {}
    daemon.auth.get_all_senders.return_value = []
    daemon.cron._jobs = {}
    daemon._config = {"agents": {}}
    ch.set_daemon(daemon)
    return ch, daemon


# ---------------------------------------------------------------------------
# TestAdminAPISessions
# ---------------------------------------------------------------------------


class TestAdminAPISessions:
    """GET /admin/sessions and DELETE /admin/sessions?id=..."""

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self):
        """Empty active_sessions returns an empty list."""
        ch, _daemon = _make_admin_webchat()
        await ch.start()
        try:
            async with TestClient(TestServer(ch._app)) as client:
                resp = await client.get(
                    "/admin/sessions",
                    headers={"Authorization": f"Bearer {_ADMIN_TOKEN}"},
                )
                assert resp.status == 200
                data = await resp.json()
                assert data["sessions"] == []
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_list_sessions_with_data(self):
        """Sessions are returned with their details."""
        ch, daemon = _make_admin_webchat()
        daemon.router.active_sessions.return_value = {
            "webchat:user1": {
                "session_id": "gw-session-1",
                "route_key": "webchat:user1",
                "created_at": "2026-01-01T00:00:00",
                "message_count": 5,
            },
        }
        await ch.start()
        try:
            async with TestClient(TestServer(ch._app)) as client:
                resp = await client.get(
                    "/admin/sessions",
                    headers={"Authorization": f"Bearer {_ADMIN_TOKEN}"},
                )
                assert resp.status == 200
                data = await resp.json()
                assert len(data["sessions"]) == 1
                assert data["sessions"][0]["session_id"] == "gw-session-1"
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_close_session(self):
        """DELETE /admin/sessions?id=... closes the session."""
        ch, daemon = _make_admin_webchat()
        await ch.start()
        try:
            async with TestClient(TestServer(ch._app)) as client:
                resp = await client.delete(
                    "/admin/sessions?id=webchat:user1",
                    headers={"Authorization": f"Bearer {_ADMIN_TOKEN}"},
                )
                assert resp.status == 200
                data = await resp.json()
                assert data["closed"] is True
                daemon.router.close_session.assert_called_once_with("webchat:user1")
        finally:
            await ch.stop()


# ---------------------------------------------------------------------------
# TestAdminAPIChannels
# ---------------------------------------------------------------------------


class TestAdminAPIChannels:
    """GET /admin/channels."""

    @pytest.mark.asyncio
    async def test_list_channels(self):
        """Channels are returned with name, type, and running status."""
        ch, daemon = _make_admin_webchat()
        mock_adapter = MagicMock()
        mock_adapter.config = {"type": "webhook"}
        mock_adapter.is_running = True
        daemon.channels = {"main": mock_adapter}
        await ch.start()
        try:
            async with TestClient(TestServer(ch._app)) as client:
                resp = await client.get(
                    "/admin/channels",
                    headers={"Authorization": f"Bearer {_ADMIN_TOKEN}"},
                )
                assert resp.status == 200
                data = await resp.json()
                assert len(data["channels"]) == 1
                assert data["channels"][0]["name"] == "main"
                assert data["channels"][0]["type"] == "webhook"
                assert data["channels"][0]["running"] is True
        finally:
            await ch.stop()


# ---------------------------------------------------------------------------
# TestAdminAPISenders
# ---------------------------------------------------------------------------


class TestAdminAPISenders:
    """GET /admin/senders, POST block/unblock."""

    @pytest.mark.asyncio
    async def test_list_senders(self):
        """Senders are returned with their details."""
        ch, daemon = _make_admin_webchat()
        daemon.auth.get_all_senders.return_value = [
            SenderRecord(
                sender_id="alice",
                channel=ChannelType.WEBHOOK,
                channel_name="main",
                status=AuthStatus.APPROVED,
                label="Alice",
                message_count=10,
            ),
        ]
        await ch.start()
        try:
            async with TestClient(TestServer(ch._app)) as client:
                resp = await client.get(
                    "/admin/senders",
                    headers={"Authorization": f"Bearer {_ADMIN_TOKEN}"},
                )
                assert resp.status == 200
                data = await resp.json()
                assert len(data["senders"]) == 1
                assert data["senders"][0]["sender_id"] == "alice"
                assert data["senders"][0]["status"] == "approved"
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_block_sender(self):
        """POST /admin/senders/block blocks a sender."""
        ch, daemon = _make_admin_webchat()
        await ch.start()
        try:
            async with TestClient(TestServer(ch._app)) as client:
                resp = await client.post(
                    "/admin/senders/block",
                    json={"sender_id": "user1", "channel": "webchat"},
                    headers={"Authorization": f"Bearer {_ADMIN_TOKEN}"},
                )
                assert resp.status == 200
                data = await resp.json()
                assert data["blocked"] is True
                daemon.auth.block_sender.assert_called_once()
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_unblock_sender(self):
        """POST /admin/senders/unblock unblocks a sender."""
        ch, daemon = _make_admin_webchat()
        await ch.start()
        try:
            async with TestClient(TestServer(ch._app)) as client:
                resp = await client.post(
                    "/admin/senders/unblock",
                    json={"sender_id": "user1", "channel": "webchat"},
                    headers={"Authorization": f"Bearer {_ADMIN_TOKEN}"},
                )
                assert resp.status == 200
                data = await resp.json()
                assert data["unblocked"] is True
                daemon.auth.unblock_sender.assert_called_once()
        finally:
            await ch.stop()


# ---------------------------------------------------------------------------
# TestAdminAPICron
# ---------------------------------------------------------------------------


class TestAdminAPICron:
    """GET /admin/cron."""

    @pytest.mark.asyncio
    async def test_list_cron_jobs(self):
        """Cron jobs are returned from daemon.cron._jobs."""
        ch, daemon = _make_admin_webchat()
        daemon.cron._jobs = {
            "heartbeat": {
                "cron": "@hourly",
                "recipe": "__heartbeat__",
            },
        }
        await ch.start()
        try:
            async with TestClient(TestServer(ch._app)) as client:
                resp = await client.get(
                    "/admin/cron",
                    headers={"Authorization": f"Bearer {_ADMIN_TOKEN}"},
                )
                assert resp.status == 200
                data = await resp.json()
                assert len(data["jobs"]) == 1
                assert data["jobs"][0]["name"] == "heartbeat"
        finally:
            await ch.stop()


# ---------------------------------------------------------------------------
# TestAdminAPIUsage
# ---------------------------------------------------------------------------


class TestAdminAPIUsage:
    """GET /admin/usage."""

    @pytest.mark.asyncio
    async def test_usage_metrics(self):
        """Usage metrics aggregate sender and session data."""
        ch, daemon = _make_admin_webchat()
        daemon.auth.get_all_senders.return_value = [
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
        ]
        daemon.router.active_sessions.return_value = {"k1": {}, "k2": {}}
        await ch.start()
        try:
            async with TestClient(TestServer(ch._app)) as client:
                resp = await client.get(
                    "/admin/usage",
                    headers={"Authorization": f"Bearer {_ADMIN_TOKEN}"},
                )
                assert resp.status == 200
                data = await resp.json()
                assert data["total_messages"] == 45
                assert data["active_sessions"] == 2
                assert data["total_senders"] == 2
        finally:
            await ch.stop()


# ---------------------------------------------------------------------------
# TestAdminAPIAgents
# ---------------------------------------------------------------------------


class TestAdminAPIAgents:
    """GET /admin/agents."""

    @pytest.mark.asyncio
    async def test_list_agents(self):
        """Agents config is returned from daemon._config."""
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
            async with TestClient(TestServer(ch._app)) as client:
                resp = await client.get(
                    "/admin/agents",
                    headers={"Authorization": f"Bearer {_ADMIN_TOKEN}"},
                )
                assert resp.status == 200
                data = await resp.json()
                assert "jesse" in data["agents"]
        finally:
            await ch.stop()
