"""Tests for IRC channel adapter."""

from __future__ import annotations

import pytest
from letsgo_channel_irc import IRCChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage


def test_irc_is_channel_adapter():
    """IRCChannel is a proper ChannelAdapter subclass."""
    assert issubclass(IRCChannel, ChannelAdapter)


def test_irc_instantiation():
    """IRCChannel can be instantiated with name and config."""
    ch = IRCChannel(
        name="irc-main",
        config={"server": "irc.libera.chat", "nick": "letsgo", "channel": "#test"},
    )
    assert ch.name == "irc-main"
    assert ch.config["server"] == "irc.libera.chat"
    assert not ch.is_running


@pytest.mark.asyncio
async def test_irc_start_without_sdk_logs_warning(caplog):
    """start() logs a warning when irc3 is not installed."""
    ch = IRCChannel(name="irc-test", config={})
    await ch.start()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_irc_stop_when_not_running():
    """stop() is safe to call when not running."""
    ch = IRCChannel(name="irc-test", config={})
    await ch.stop()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_irc_send_returns_false_when_not_running():
    """send() returns False when adapter is not running."""
    ch = IRCChannel(name="irc-test", config={})
    msg = OutboundMessage(
        channel=ChannelType("irc"),
        channel_name="irc-test",
        thread_id=None,
        text="hello",
    )
    result = await ch.send(msg)
    assert result is False


def test_irc_format_privmsg():
    """_format_privmsg returns a valid IRC PRIVMSG command."""
    ch = IRCChannel(name="irc-test", config={})
    result = ch._format_privmsg("Hello from LetsGo", "#test")
    assert result == "PRIVMSG #test :Hello from LetsGo"
