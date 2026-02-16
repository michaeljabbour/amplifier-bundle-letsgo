"""Tests for gateway session router."""

from __future__ import annotations

import time

import pytest

from letsgo_gateway.models import ChannelType, InboundMessage
from letsgo_gateway.router import SessionRouter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_message(
    sender_id: str = "user1",
    channel: ChannelType = ChannelType.WEBHOOK,
    text: str = "hello",
    channel_name: str = "main",
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        channel_name=channel_name,
        sender_id=sender_id,
        sender_label=sender_id,
        text=text,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_route_key_format():
    """Route key is channel:sender_id."""
    router = SessionRouter()
    msg = _make_message(sender_id="alice", channel=ChannelType.TELEGRAM)
    assert router.route_key(msg) == "telegram:alice"


def test_get_or_create_session():
    """First call creates, second returns same session."""
    router = SessionRouter()
    s1 = router.get_or_create_session("webhook:u1")
    s2 = router.get_or_create_session("webhook:u1")
    assert s1["session_id"] == s2["session_id"]
    assert s2["message_count"] == 2  # incremented on second call


def test_close_session():
    """Closing removes the session."""
    router = SessionRouter()
    router.get_or_create_session("webhook:u1")
    assert router.close_session("webhook:u1")
    assert not router.close_session("webhook:u1")  # already gone
    assert "webhook:u1" not in router.active_sessions


def test_close_stale_sessions():
    """Sessions idle longer than threshold are closed."""
    router = SessionRouter()
    session = router.get_or_create_session("webhook:stale")
    # Backdate last_active to make it stale
    session["last_active"] = time.monotonic() - 3600
    closed = router.close_stale_sessions(max_idle_seconds=60)
    assert "webhook:stale" in closed
    assert "webhook:stale" not in router.active_sessions


def test_dm_scoping_isolation():
    """Different senders get independent sessions."""
    router = SessionRouter()
    msg_a = _make_message(sender_id="alice")
    msg_b = _make_message(sender_id="bob")

    resp_a = router.route_message(msg_a)
    resp_b = router.route_message(msg_b)

    assert resp_a != resp_b
    assert len(router.active_sessions) == 2

    # Verify different session IDs
    key_a = router.route_key(msg_a)
    key_b = router.route_key(msg_b)
    assert (
        router.active_sessions[key_a]["session_id"]
        != router.active_sessions[key_b]["session_id"]
    )
