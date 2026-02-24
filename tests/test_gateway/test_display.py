"""Tests for GatewayDisplaySystem."""

from __future__ import annotations

from typing import Any

import pytest
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.display import GatewayDisplaySystem
from letsgo_gateway.models import OutboundMessage


class FakeChannel(ChannelAdapter):
    """Minimal channel adapter for testing."""

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(name, config or {})
        self.sent: list[OutboundMessage] = []

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        self.sent.append(message)
        return True


@pytest.mark.asyncio
async def test_display_routes_to_canvas_channel():
    """When a canvas channel exists, display routes content to it."""
    canvas = FakeChannel("canvas")
    chat = FakeChannel("general")
    channels = {"canvas": canvas, "general": chat}

    ds = GatewayDisplaySystem(channels)
    await ds.display("# Hello World", metadata={"content_type": "markdown"})

    assert len(canvas.sent) == 1
    assert canvas.sent[0].text == "# Hello World"
    # Chat channel should NOT receive the display content
    assert len(chat.sent) == 0


@pytest.mark.asyncio
async def test_display_fallback_to_chat():
    """Without a canvas channel, display falls back to chat channels."""
    chat = FakeChannel("general")
    channels = {"general": chat}

    ds = GatewayDisplaySystem(channels)
    await ds.display("Some content")

    assert len(chat.sent) == 1
    assert chat.sent[0].text == "Some content"


@pytest.mark.asyncio
async def test_display_with_no_channels():
    """Display with no channels does not crash."""
    ds = GatewayDisplaySystem({})
    # Should not raise
    await ds.display("orphaned content")


@pytest.mark.asyncio
async def test_display_updates_canvas_state():
    """Display updates internal canvas state tracking."""
    canvas = FakeChannel("canvas")
    ds = GatewayDisplaySystem({"canvas": canvas})

    await ds.display(
        "<svg>...</svg>", metadata={"content_type": "svg", "id": "chart-1"}
    )

    assert ds.canvas_state.get("chart-1") == {
        "content_type": "svg",
        "content": "<svg>...</svg>",
    }


@pytest.mark.asyncio
async def test_display_without_metadata():
    """Display works when metadata is None."""
    chat = FakeChannel("general")
    ds = GatewayDisplaySystem({"general": chat})

    await ds.display("plain text")

    assert len(chat.sent) == 1
    assert chat.sent[0].text == "plain text"
