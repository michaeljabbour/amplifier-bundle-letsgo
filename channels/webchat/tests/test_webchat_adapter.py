"""Tests for WebChatChannel adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp.test_utils import TestClient, TestServer
from letsgo_channel_webchat import WebChatChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage

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
