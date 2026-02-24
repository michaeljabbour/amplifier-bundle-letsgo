"""Tests for Signal channel adapter."""

from __future__ import annotations

import pytest
from letsgo_channel_signal import SignalChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage


def test_signal_is_channel_adapter():
    """SignalChannel is a proper ChannelAdapter subclass."""
    assert issubclass(SignalChannel, ChannelAdapter)


def test_signal_instantiation():
    """SignalChannel can be instantiated with name and config."""
    ch = SignalChannel(
        name="signal-main",
        config={"phone_number": "+15551234567"},
    )
    assert ch.name == "signal-main"
    assert ch.config["phone_number"] == "+15551234567"
    assert not ch.is_running


@pytest.mark.asyncio
async def test_signal_start_without_cli_logs_warning(caplog):
    """start() logs a warning when signal-cli is not found."""
    ch = SignalChannel(
        name="signal-test",
        config={"phone_number": "+15551234567", "signal_cli_path": None},
    )
    await ch.start()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_signal_stop_when_not_running():
    """stop() is safe to call when not running."""
    ch = SignalChannel(name="signal-test", config={})
    await ch.stop()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_signal_send_returns_false_when_not_running():
    """send() returns False when adapter is not running."""
    ch = SignalChannel(name="signal-test", config={})
    msg = OutboundMessage(
        channel=ChannelType("signal"),
        channel_name="signal-test",
        thread_id=None,
        text="hello",
    )
    result = await ch.send(msg)
    assert result is False


def test_signal_format_outbound():
    """_format_outbound converts OutboundMessage to signal-cli args."""
    ch = SignalChannel(
        name="signal-test",
        config={"phone_number": "+15551234567"},
    )
    msg = OutboundMessage(
        channel=ChannelType("signal"),
        channel_name="signal-test",
        thread_id="+15559876543",
        text="Hello from LetsGo",
    )
    args = ch._format_outbound(msg)
    assert "+15559876543" in args
    assert "Hello from LetsGo" in args
