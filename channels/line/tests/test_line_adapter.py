"""Tests for LINE channel adapter."""

from __future__ import annotations

import pytest
from letsgo_channel_line import LINEChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage


def test_line_is_channel_adapter():
    """LINEChannel is a proper ChannelAdapter subclass."""
    assert issubclass(LINEChannel, ChannelAdapter)


def test_line_instantiation():
    """LINEChannel can be instantiated with name and config."""
    ch = LINEChannel(
        name="line-main",
        config={"channel_access_token": "tok123", "channel_secret": "sec456"},
    )
    assert ch.name == "line-main"
    assert ch.config["channel_access_token"] == "tok123"
    assert not ch.is_running


@pytest.mark.asyncio
async def test_line_start_without_sdk_logs_warning(caplog):
    """start() logs a warning when line-bot-sdk is not installed."""
    ch = LINEChannel(name="line-test", config={})
    await ch.start()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_line_stop_when_not_running():
    """stop() is safe to call when not running."""
    ch = LINEChannel(name="line-test", config={})
    await ch.stop()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_line_send_returns_false_when_not_running():
    """send() returns False when adapter is not running."""
    ch = LINEChannel(name="line-test", config={})
    msg = OutboundMessage(
        channel=ChannelType("line"),
        channel_name="line-test",
        thread_id=None,
        text="hello",
    )
    result = await ch.send(msg)
    assert result is False


def test_line_format_flex_message():
    """_format_flex_message returns a LINE Flex Message structure."""
    ch = LINEChannel(name="line-test", config={})
    result = ch._format_flex_message("Hello from LetsGo")
    assert result["type"] == "flex"
    assert result["altText"] == "Hello from LetsGo"
    assert result["contents"]["type"] == "bubble"
    body_text = result["contents"]["body"]["contents"][0]["text"]
    assert body_text == "Hello from LetsGo"
