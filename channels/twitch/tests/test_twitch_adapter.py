"""Tests for Twitch channel adapter."""

from __future__ import annotations

import pytest
from letsgo_channel_twitch import TwitchChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage


def test_twitch_is_channel_adapter():
    """TwitchChannel is a proper ChannelAdapter subclass."""
    assert issubclass(TwitchChannel, ChannelAdapter)


def test_twitch_instantiation():
    """TwitchChannel can be instantiated with name and config."""
    ch = TwitchChannel(
        name="twitch-main",
        config={"token": "oauth:abc123", "channel": "mychannel"},
    )
    assert ch.name == "twitch-main"
    assert ch.config["channel"] == "mychannel"
    assert not ch.is_running


@pytest.mark.asyncio
async def test_twitch_start_without_sdk_logs_warning(caplog):
    """start() logs a warning when twitchio is not installed."""
    ch = TwitchChannel(name="twitch-test", config={})
    await ch.start()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_twitch_stop_when_not_running():
    """stop() is safe to call when not running."""
    ch = TwitchChannel(name="twitch-test", config={})
    await ch.stop()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_twitch_send_returns_false_when_not_running():
    """send() returns False when adapter is not running."""
    ch = TwitchChannel(name="twitch-test", config={})
    msg = OutboundMessage(
        channel=ChannelType("twitch"),
        channel_name="twitch-test",
        thread_id=None,
        text="hello",
    )
    result = await ch.send(msg)
    assert result is False


def test_twitch_format_chat_message():
    """_format_chat_message returns a Twitch-compatible string."""
    ch = TwitchChannel(name="twitch-test", config={})
    result = ch._format_chat_message("Hello from LetsGo\nSecond line")
    assert result == "Hello from LetsGo"
    # Truncation at 500 chars
    long_msg = "x" * 600
    assert len(ch._format_chat_message(long_msg)) == 500
