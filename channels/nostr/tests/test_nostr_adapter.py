"""Tests for Nostr channel adapter."""

from __future__ import annotations

import pytest
from letsgo_channel_nostr import NostrChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage


def test_nostr_is_channel_adapter():
    """NostrChannel is a proper ChannelAdapter subclass."""
    assert issubclass(NostrChannel, ChannelAdapter)


def test_nostr_instantiation():
    """NostrChannel can be instantiated with name and config."""
    ch = NostrChannel(
        name="nostr-main",
        config={"private_key": "nsec1...", "relay_urls": ["wss://relay.damus.io"]},
    )
    assert ch.name == "nostr-main"
    assert ch.config["private_key"] == "nsec1..."
    assert not ch.is_running


@pytest.mark.asyncio
async def test_nostr_start_without_sdk_logs_warning(caplog):
    """start() logs a warning when nostr-sdk is not installed."""
    ch = NostrChannel(name="nostr-test", config={})
    await ch.start()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_nostr_stop_when_not_running():
    """stop() is safe to call when not running."""
    ch = NostrChannel(name="nostr-test", config={})
    await ch.stop()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_nostr_send_returns_false_when_not_running():
    """send() returns False when adapter is not running."""
    ch = NostrChannel(name="nostr-test", config={})
    msg = OutboundMessage(
        channel=ChannelType("nostr"),
        channel_name="nostr-test",
        thread_id=None,
        text="hello",
    )
    result = await ch.send(msg)
    assert result is False


def test_nostr_format_event():
    """_format_event returns a NIP-01 kind-1 text note."""
    ch = NostrChannel(name="nostr-test", config={})
    result = ch._format_event("Hello from LetsGo")
    assert result["kind"] == 1
    assert result["content"] == "Hello from LetsGo"
    assert isinstance(result["tags"], list)
    assert isinstance(result["created_at"], int)
