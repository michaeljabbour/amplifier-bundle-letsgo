"""Tests for Canvas channel adapter — core lifecycle and state management."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp
import pytest
from letsgo_channel_canvas import CanvasChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_canvas(config: dict[str, Any] | None = None) -> CanvasChannel:
    return CanvasChannel(name="canvas", config=config or {})


def _make_outbound(
    text: str,
    channel_name: str = "canvas",
) -> OutboundMessage:
    return OutboundMessage(
        channel=ChannelType("canvas"),
        channel_name=channel_name,
        thread_id=None,
        text=text,
    )


def _make_envelope(
    content_type: str = "html",
    content: str = "<p>hello</p>",
    content_id: str | None = None,
    title: str | None = None,
) -> str:
    envelope: dict[str, Any] = {
        "content_type": content_type,
        "content": content,
    }
    if content_id is not None:
        envelope["id"] = content_id
    if title is not None:
        envelope["title"] = title
    return json.dumps(envelope)


# ---------------------------------------------------------------------------
# CanvasChannel — subclass check
# ---------------------------------------------------------------------------


class TestCanvasChannelSubclass:
    """CanvasChannel is a proper ChannelAdapter."""

    def test_is_channel_adapter(self) -> None:
        assert issubclass(CanvasChannel, ChannelAdapter)

    def test_instantiation(self) -> None:
        ch = _make_canvas(config={"host": "0.0.0.0", "port": 9090})
        assert ch.name == "canvas"
        assert ch.config["port"] == 9090
        assert not ch.is_running


# ---------------------------------------------------------------------------
# CanvasChannel — lifecycle
# ---------------------------------------------------------------------------


class TestCanvasChannelLifecycle:
    """Start/stop lifecycle management."""

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self) -> None:
        ch = _make_canvas()
        await ch.stop()  # should not raise
        assert not ch.is_running

    @pytest.mark.asyncio
    async def test_stop_after_start(self) -> None:
        ch = _make_canvas(config={"port": 0})  # port 0 = OS picks free port
        await ch.start()
        assert ch.is_running
        await ch.stop()
        assert not ch.is_running


# ---------------------------------------------------------------------------
# CanvasChannel — send and state management
# ---------------------------------------------------------------------------


class TestCanvasChannelSend:
    """send() parses JSON envelope and manages canvas state."""

    @pytest.mark.asyncio
    async def test_send_parses_json_envelope(self) -> None:
        ch = _make_canvas()
        envelope = _make_envelope(
            content_type="chart",
            content='{"$schema": "vega-lite"}',
            content_id="chart-1",
            title="My Chart",
        )
        msg = _make_outbound(text=envelope)
        result = await ch.send(msg)

        assert result is True
        state = ch.get_state()
        assert "chart-1" in state
        assert state["chart-1"]["content_type"] == "chart"
        assert state["chart-1"]["title"] == "My Chart"

    @pytest.mark.asyncio
    async def test_send_with_invalid_json(self) -> None:
        ch = _make_canvas()
        msg = _make_outbound(text="not json at all")
        result = await ch.send(msg)

        # Gracefully handled — returns True but stores as raw text
        assert result is True

    @pytest.mark.asyncio
    async def test_send_updates_existing_item(self) -> None:
        ch = _make_canvas()

        # First push
        envelope1 = _make_envelope(
            content_type="html", content="<p>v1</p>", content_id="item-1"
        )
        await ch.send(_make_outbound(text=envelope1))
        assert ch.get_state()["item-1"]["content"] == "<p>v1</p>"

        # Update same ID
        envelope2 = _make_envelope(
            content_type="html", content="<p>v2</p>", content_id="item-1"
        )
        await ch.send(_make_outbound(text=envelope2))
        assert ch.get_state()["item-1"]["content"] == "<p>v2</p>"

        # Only one item in state
        assert len(ch.get_state()) == 1

    @pytest.mark.asyncio
    async def test_send_without_id_auto_generates(self) -> None:
        ch = _make_canvas()
        envelope = _make_envelope(content_type="code", content="print('hi')")
        await ch.send(_make_outbound(text=envelope))

        state = ch.get_state()
        assert len(state) == 1
        # Auto-generated ID should exist
        item_id = next(iter(state))
        assert len(item_id) > 0
        assert state[item_id]["content_type"] == "code"

    @pytest.mark.asyncio
    async def test_get_state_returns_copy(self) -> None:
        ch = _make_canvas()
        envelope = _make_envelope(
            content_type="svg", content="<svg></svg>", content_id="svg-1"
        )
        await ch.send(_make_outbound(text=envelope))

        state1 = ch.get_state()
        state2 = ch.get_state()
        assert state1 == state2
        # Modifying returned state doesn't affect internal
        state1.pop("svg-1")
        assert "svg-1" in ch.get_state()

    @pytest.mark.asyncio
    async def test_state_ordering_newest_first(self) -> None:
        ch = _make_canvas()

        for i in range(3):
            envelope = _make_envelope(
                content_type="html",
                content=f"<p>item {i}</p>",
                content_id=f"item-{i}",
            )
            await ch.send(_make_outbound(text=envelope))

        state = ch.get_state()
        ids = list(state.keys())
        # Newest first
        assert ids == ["item-2", "item-1", "item-0"]


# ---------------------------------------------------------------------------
# CanvasChannel — WebSocket transport
# ---------------------------------------------------------------------------


class TestCanvasChannelWebSocket:
    """WebSocket transport for real-time canvas updates."""

    @pytest.mark.asyncio
    async def test_websocket_connection_accepted(self) -> None:
        ch = _make_canvas(config={"port": 0})
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    f"http://localhost:{port}/canvas/ws"
                ) as ws:
                    assert not ws.closed
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_websocket_receives_pushed_content(self) -> None:
        ch = _make_canvas(config={"port": 0})
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    f"http://localhost:{port}/canvas/ws"
                ) as ws:
                    # Push content
                    envelope = _make_envelope(
                        content_type="html",
                        content="<p>hello</p>",
                        content_id="ws-test-1",
                        title="Test",
                    )
                    await ch.send(_make_outbound(text=envelope))

                    # Receive WebSocket message
                    msg = await asyncio.wait_for(ws.receive_json(), timeout=2)
                    assert msg["type"] == "update"
                    assert msg["id"] == "ws-test-1"
                    assert msg["content_type"] == "html"
                    assert msg["content"] == "<p>hello</p>"
                    assert msg["title"] == "Test"
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_multiple_clients_receive_same_update(self) -> None:
        ch = _make_canvas(config={"port": 0})
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            async with aiohttp.ClientSession() as session:
                ws1 = await session.ws_connect(f"http://localhost:{port}/canvas/ws")
                ws2 = await session.ws_connect(f"http://localhost:{port}/canvas/ws")

                envelope = _make_envelope(
                    content_type="svg",
                    content="<svg></svg>",
                    content_id="multi-test",
                )
                await ch.send(_make_outbound(text=envelope))

                msg1 = await asyncio.wait_for(ws1.receive_json(), timeout=2)
                msg2 = await asyncio.wait_for(ws2.receive_json(), timeout=2)

                assert msg1["id"] == "multi-test"
                assert msg2["id"] == "multi-test"

                await ws1.close()
                await ws2.close()
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_disconnected_clients_cleaned_up(self) -> None:
        ch = _make_canvas(config={"port": 0})
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            async with aiohttp.ClientSession() as session:
                ws = await session.ws_connect(f"http://localhost:{port}/canvas/ws")
                assert len(ch._ws_clients) == 1

                await ws.close()
                # Allow cleanup to happen
                await asyncio.sleep(0.1)

                # Push content — should clean up dead client
                envelope = _make_envelope(
                    content_type="html", content="<p>after close</p>"
                )
                await ch.send(_make_outbound(text=envelope))

                assert len(ch._ws_clients) == 0
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_state_endpoint_returns_current_items(self) -> None:
        ch = _make_canvas(config={"port": 0})
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]

            # Push two items
            for i in range(2):
                envelope = _make_envelope(
                    content_type="markdown",
                    content=f"# Item {i}",
                    content_id=f"state-{i}",
                )
                await ch.send(_make_outbound(text=envelope))

            # Fetch state
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:{port}/canvas/state") as resp:
                    assert resp.status == 200
                    data = await resp.json()
                    assert len(data["items"]) == 2
                    # Newest first
                    assert data["items"][0]["id"] == "state-1"
                    assert data["items"][1]["id"] == "state-0"
        finally:
            await ch.stop()
