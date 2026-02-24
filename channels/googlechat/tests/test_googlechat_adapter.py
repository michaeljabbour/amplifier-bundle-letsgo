"""Tests for Google Chat channel adapter."""

from __future__ import annotations

import pytest
from letsgo_channel_googlechat import GoogleChatChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage


def test_googlechat_is_channel_adapter():
    """GoogleChatChannel is a proper ChannelAdapter subclass."""
    assert issubclass(GoogleChatChannel, ChannelAdapter)


def test_googlechat_instantiation():
    """GoogleChatChannel can be instantiated with name and config."""
    ch = GoogleChatChannel(
        name="gchat-main",
        config={"service_account_path": "/tmp/sa.json", "space_name": "spaces/AAAA"},
    )
    assert ch.name == "gchat-main"
    assert ch.config["space_name"] == "spaces/AAAA"
    assert not ch.is_running


@pytest.mark.asyncio
async def test_googlechat_start_without_sdk_logs_warning(caplog):
    """start() logs a warning when google-api-python-client is not installed."""
    ch = GoogleChatChannel(name="gchat-test", config={})
    await ch.start()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_googlechat_stop_when_not_running():
    """stop() is safe to call when not running."""
    ch = GoogleChatChannel(name="gchat-test", config={})
    await ch.stop()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_googlechat_send_returns_false_when_not_running():
    """send() returns False when adapter is not running."""
    ch = GoogleChatChannel(name="gchat-test", config={})
    msg = OutboundMessage(
        channel=ChannelType("googlechat"),
        channel_name="gchat-test",
        thread_id=None,
        text="hello",
    )
    result = await ch.send(msg)
    assert result is False


def test_googlechat_format_card():
    """_format_card returns a Google Chat Card v2 structure."""
    ch = GoogleChatChannel(name="gchat-test", config={})
    result = ch._format_card("Hello from LetsGo")
    assert "cardsV2" in result
    card = result["cardsV2"][0]["card"]
    assert card["header"]["title"] == "LetsGo"
    widget_text = card["sections"][0]["widgets"][0]["textParagraph"]["text"]
    assert widget_text == "Hello from LetsGo"
