"""Integration test: end-to-end plugin channel discovery and usage."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.channels.registry import discover_channels
from letsgo_gateway.daemon import GatewayDaemon
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

# ---------------------------------------------------------------------------
# Fake plugin channel
# ---------------------------------------------------------------------------


class FakePluginChannel(ChannelAdapter):
    """A fake channel adapter that simulates a plugin channel."""

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self.started = False
        self.stopped = False
        self.sent_messages: list[OutboundMessage] = []

    async def start(self) -> None:
        self.started = True
        self._running = True

    async def stop(self) -> None:
        self.stopped = True
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        self.sent_messages.append(message)
        return True


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _mock_entry_point(name: str, cls: type) -> MagicMock:
    """Create a mock entry point that loads the given class."""
    ep = MagicMock()
    ep.name = name
    ep.load.return_value = cls
    return ep


def test_plugin_discovered_via_entry_point():
    """A plugin channel registered via entry point is discovered."""
    mock_ep = _mock_entry_point("fakechat", FakePluginChannel)

    with patch(
        "letsgo_gateway.channels.registry.entry_points",
        return_value=[mock_ep],
    ):
        channels = discover_channels()

    assert "fakechat" in channels
    assert channels["fakechat"] is FakePluginChannel


def test_daemon_initializes_plugin_channel(tmp_path: Path):
    """Daemon creates a plugin channel instance from registry discovery."""
    mock_ep = _mock_entry_point("fakechat", FakePluginChannel)

    config = {
        "auth": {
            "pairing_db_path": str(tmp_path / "pairing.json"),
            "max_messages_per_minute": 60,
            "code_ttl_seconds": 300,
        },
        "channels": {
            "my-fakechat": {"type": "fakechat", "api_key": "test123"},
        },
        "cron": {
            "log_path": str(tmp_path / "cron.jsonl"),
        },
    }

    with patch(
        "letsgo_gateway.channels.registry.entry_points",
        return_value=[mock_ep],
    ):
        daemon = GatewayDaemon(config=config)

    assert "my-fakechat" in daemon.channels
    adapter = daemon.channels["my-fakechat"]
    assert isinstance(adapter, FakePluginChannel)
    assert adapter.name == "my-fakechat"
    assert adapter.config["api_key"] == "test123"


@pytest.mark.asyncio
async def test_plugin_channel_send_receive(tmp_path: Path):
    """Full flow: discover plugin -> init daemon -> send message."""
    mock_ep = _mock_entry_point("fakechat", FakePluginChannel)

    config = {
        "auth": {
            "pairing_db_path": str(tmp_path / "pairing.json"),
            "max_messages_per_minute": 60,
            "code_ttl_seconds": 300,
        },
        "channels": {
            "my-fakechat": {"type": "fakechat"},
        },
        "cron": {
            "log_path": str(tmp_path / "cron.jsonl"),
        },
    }

    with patch(
        "letsgo_gateway.channels.registry.entry_points",
        return_value=[mock_ep],
    ):
        daemon = GatewayDaemon(config=config)

    adapter: FakePluginChannel = daemon.channels["my-fakechat"]

    # Verify send works
    msg = OutboundMessage(
        channel=ChannelType("fakechat"),
        channel_name="my-fakechat",
        thread_id=None,
        text="Hello from integration test",
    )
    await adapter.start()
    result = await adapter.send(msg)

    assert result is True
    assert len(adapter.sent_messages) == 1
    assert adapter.sent_messages[0].text == "Hello from integration test"


@pytest.mark.asyncio
async def test_plugin_channel_receives_inbound(tmp_path: Path):
    """Plugin channel can trigger on_message callback from daemon."""
    mock_ep = _mock_entry_point("fakechat", FakePluginChannel)

    config = {
        "auth": {
            "pairing_db_path": str(tmp_path / "pairing.json"),
            "max_messages_per_minute": 60,
            "code_ttl_seconds": 300,
        },
        "channels": {
            "my-fakechat": {"type": "fakechat"},
        },
        "cron": {
            "log_path": str(tmp_path / "cron.jsonl"),
        },
    }

    with patch(
        "letsgo_gateway.channels.registry.entry_points",
        return_value=[mock_ep],
    ):
        daemon = GatewayDaemon(config=config)

    adapter: FakePluginChannel = daemon.channels["my-fakechat"]

    # The daemon should have set on_message callback
    assert adapter._on_message is not None

    # Simulate an inbound message through the callback
    msg = InboundMessage(
        channel=ChannelType("fakechat"),
        channel_name="my-fakechat",
        sender_id="test-user",
        sender_label="Test User",
        text="hello from plugin",
    )
    response = await adapter._on_message(msg)
    # Daemon routes to its _on_message handler (pairing/routing logic)
    assert isinstance(response, str)


def test_custom_channel_type_in_messages():
    """Plugin channels can use custom ChannelType strings in messages."""
    msg = InboundMessage(
        channel=ChannelType("fakechat"),
        channel_name="my-fakechat",
        sender_id="u1",
        sender_label="User",
        text="test",
    )
    assert msg.channel == "fakechat"
    assert isinstance(msg.channel, ChannelType)

    out = OutboundMessage(
        channel=ChannelType("fakechat"),
        channel_name="my-fakechat",
        thread_id=None,
        text="reply",
    )
    assert out.channel == "fakechat"
