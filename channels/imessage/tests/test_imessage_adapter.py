"""Tests for iMessage channel adapter."""

from __future__ import annotations

import pytest
from letsgo_channel_imessage import IMessageChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage


def test_imessage_is_channel_adapter():
    """IMessageChannel is a proper ChannelAdapter subclass."""
    assert issubclass(IMessageChannel, ChannelAdapter)


def test_imessage_instantiation():
    """IMessageChannel can be instantiated with name and config."""
    ch = IMessageChannel(
        name="imessage-main",
        config={"apple_id": "user@icloud.com"},
    )
    assert ch.name == "imessage-main"
    assert ch.config["apple_id"] == "user@icloud.com"
    assert not ch.is_running


@pytest.mark.asyncio
async def test_imessage_start_without_osascript_logs_warning(caplog):
    """start() logs a warning when osascript is unavailable."""
    ch = IMessageChannel(name="imessage-test", config={})
    # Force osascript to None regardless of platform
    ch._osascript = None
    await ch.start()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_imessage_stop_when_not_running():
    """stop() is safe to call when not running."""
    ch = IMessageChannel(name="imessage-test", config={})
    await ch.stop()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_imessage_send_returns_false_when_not_running():
    """send() returns False when adapter is not running."""
    ch = IMessageChannel(name="imessage-test", config={})
    msg = OutboundMessage(
        channel=ChannelType("imessage"),
        channel_name="imessage-test",
        thread_id=None,
        text="hello",
    )
    result = await ch.send(msg)
    assert result is False


def test_imessage_format_applescript():
    """_format_applescript returns a valid AppleScript command."""
    ch = IMessageChannel(name="imessage-test", config={})
    script = ch._format_applescript("Hello from LetsGo", "+15551234567")
    assert 'tell application "Messages"' in script
    assert "+15551234567" in script
    assert "Hello from LetsGo" in script
    assert "send" in script
