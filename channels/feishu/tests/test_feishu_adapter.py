"""Tests for Feishu channel adapter."""

from __future__ import annotations

import pytest
from letsgo_channel_feishu import FeishuChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage


def test_feishu_is_channel_adapter():
    """FeishuChannel is a proper ChannelAdapter subclass."""
    assert issubclass(FeishuChannel, ChannelAdapter)


def test_feishu_instantiation():
    """FeishuChannel can be instantiated with name and config."""
    ch = FeishuChannel(
        name="feishu-main",
        config={"app_id": "cli_abc123", "app_secret": "secret456"},
    )
    assert ch.name == "feishu-main"
    assert ch.config["app_id"] == "cli_abc123"
    assert not ch.is_running


@pytest.mark.asyncio
async def test_feishu_start_without_sdk_logs_warning(caplog):
    """start() logs a warning when feishu-sdk is not installed."""
    ch = FeishuChannel(name="feishu-test", config={})
    await ch.start()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_feishu_stop_when_not_running():
    """stop() is safe to call when not running."""
    ch = FeishuChannel(name="feishu-test", config={})
    await ch.stop()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_feishu_send_returns_false_when_not_running():
    """send() returns False when adapter is not running."""
    ch = FeishuChannel(name="feishu-test", config={})
    msg = OutboundMessage(
        channel=ChannelType("feishu"),
        channel_name="feishu-test",
        thread_id=None,
        text="hello",
    )
    result = await ch.send(msg)
    assert result is False


def test_feishu_format_interactive_card():
    """_format_interactive_card returns a Feishu card structure."""
    ch = FeishuChannel(name="feishu-test", config={})
    result = ch._format_interactive_card("Hello from LetsGo")
    assert result["msg_type"] == "interactive"
    assert result["card"]["header"]["title"]["content"] == "LetsGo"
    element = result["card"]["elements"][0]
    assert element["tag"] == "markdown"
    assert element["content"] == "Hello from LetsGo"
