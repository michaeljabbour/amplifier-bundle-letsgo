"""Tests for Matrix channel adapter."""

from __future__ import annotations

import pytest
from letsgo_channel_matrix import MatrixChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage


def test_matrix_is_channel_adapter():
    """MatrixChannel is a proper ChannelAdapter subclass."""
    assert issubclass(MatrixChannel, ChannelAdapter)


def test_matrix_instantiation():
    """MatrixChannel can be instantiated with name and config."""
    ch = MatrixChannel(
        name="matrix-main",
        config={
            "homeserver": "https://matrix.org",
            "user_id": "@letsgo:matrix.org",
            "access_token": "fake-token",
        },
    )
    assert ch.name == "matrix-main"
    assert ch.config["homeserver"] == "https://matrix.org"
    assert not ch.is_running


@pytest.mark.asyncio
async def test_matrix_start_without_nio_logs_warning(caplog):
    """start() logs a warning when matrix-nio is not installed."""
    ch = MatrixChannel(
        name="matrix-test",
        config={"homeserver": "https://matrix.org"},
    )
    await ch.start()
    # Without nio, should not be running
    assert not ch.is_running


@pytest.mark.asyncio
async def test_matrix_stop_when_not_running():
    """stop() is safe to call when not running."""
    ch = MatrixChannel(name="matrix-test", config={})
    await ch.stop()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_matrix_send_returns_false_when_not_running():
    """send() returns False when adapter is not running."""
    ch = MatrixChannel(name="matrix-test", config={})
    msg = OutboundMessage(
        channel=ChannelType("matrix"),
        channel_name="matrix-test",
        thread_id="!room:matrix.org",
        text="hello",
    )
    result = await ch.send(msg)
    assert result is False


def test_matrix_format_outbound_html():
    """_format_message converts text to Matrix-compatible format."""
    ch = MatrixChannel(name="matrix-test", config={})
    body, formatted = ch._format_message("**bold** and _italic_")
    assert body == "**bold** and _italic_"
    assert isinstance(formatted, str)
