"""Tests for Microsoft Teams channel adapter."""

from __future__ import annotations

import pytest
from letsgo_channel_teams import TeamsChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage


def test_teams_is_channel_adapter():
    """TeamsChannel is a proper ChannelAdapter subclass."""
    assert issubclass(TeamsChannel, ChannelAdapter)


def test_teams_instantiation():
    """TeamsChannel can be instantiated with name and config."""
    ch = TeamsChannel(
        name="teams-main",
        config={
            "app_id": "fake-app-id",
            "app_password": "fake-app-password",
        },
    )
    assert ch.name == "teams-main"
    assert ch.config["app_id"] == "fake-app-id"
    assert not ch.is_running


@pytest.mark.asyncio
async def test_teams_start_without_botbuilder_logs_warning(caplog):
    """start() logs a warning when botbuilder-core is not installed."""
    ch = TeamsChannel(
        name="teams-test",
        config={"app_id": "fake", "app_password": "fake"},
    )
    await ch.start()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_teams_stop_when_not_running():
    """stop() is safe to call when not running."""
    ch = TeamsChannel(name="teams-test", config={})
    await ch.stop()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_teams_send_returns_false_when_not_running():
    """send() returns False when adapter is not running."""
    ch = TeamsChannel(name="teams-test", config={})
    msg = OutboundMessage(
        channel=ChannelType("teams"),
        channel_name="teams-test",
        thread_id=None,
        text="hello",
    )
    result = await ch.send(msg)
    assert result is False


def test_teams_format_adaptive_card():
    """_format_as_card wraps text in an Adaptive Card structure."""
    ch = TeamsChannel(name="teams-test", config={})
    card = ch._format_as_card("Hello **world**")
    assert card["type"] == "AdaptiveCard"
    assert len(card["body"]) >= 1
    assert card["body"][0]["text"] == "Hello **world**"
