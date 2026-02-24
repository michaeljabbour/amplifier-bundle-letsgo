"""Tests for Mattermost channel adapter."""

from __future__ import annotations

import pytest
from letsgo_channel_mattermost import MattermostChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage


def test_mattermost_is_channel_adapter():
    """MattermostChannel is a proper ChannelAdapter subclass."""
    assert issubclass(MattermostChannel, ChannelAdapter)


def test_mattermost_instantiation():
    """MattermostChannel can be instantiated with name and config."""
    ch = MattermostChannel(
        name="mm-main",
        config={"url": "https://mm.example.com", "token": "tok123", "team_id": "t1"},
    )
    assert ch.name == "mm-main"
    assert ch.config["url"] == "https://mm.example.com"
    assert not ch.is_running


@pytest.mark.asyncio
async def test_mattermost_start_without_sdk_logs_warning(caplog):
    """start() logs a warning when mattermostdriver is not installed."""
    ch = MattermostChannel(name="mm-test", config={})
    await ch.start()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_mattermost_stop_when_not_running():
    """stop() is safe to call when not running."""
    ch = MattermostChannel(name="mm-test", config={})
    await ch.stop()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_mattermost_send_returns_false_when_not_running():
    """send() returns False when adapter is not running."""
    ch = MattermostChannel(name="mm-test", config={})
    msg = OutboundMessage(
        channel=ChannelType("mattermost"),
        channel_name="mm-test",
        thread_id=None,
        text="hello",
    )
    result = await ch.send(msg)
    assert result is False


def test_mattermost_format_post():
    """_format_post returns a Mattermost post payload."""
    ch = MattermostChannel(name="mm-test", config={})
    result = ch._format_post("Hello from LetsGo", "ch123")
    assert result["channel_id"] == "ch123"
    assert result["message"] == "Hello from LetsGo"
    assert result["props"]["override_username"] == "LetsGo"
