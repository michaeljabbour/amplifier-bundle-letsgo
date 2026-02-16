"""Tests for gateway daemon."""

from __future__ import annotations

from pathlib import Path

import pytest

from letsgo_gateway.daemon import GatewayDaemon
from letsgo_gateway.models import ChannelType, InboundMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_daemon(tmp_path: Path, **config_overrides) -> GatewayDaemon:
    config = {
        "auth": {
            "pairing_db_path": str(tmp_path / "pairing.json"),
            "max_messages_per_minute": 60,
            "code_ttl_seconds": 300,
        },
        "channels": {},
        "cron": {
            "log_path": str(tmp_path / "cron.jsonl"),
        },
        **config_overrides,
    }
    return GatewayDaemon(config=config)


def _make_message(
    sender_id: str = "user1",
    text: str = "hello",
    channel: ChannelType = ChannelType.WEBHOOK,
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


def test_daemon_creates_components(tmp_path: Path):
    """Daemon initializes all sub-components."""
    d = _make_daemon(tmp_path)
    assert d.auth is not None
    assert d.router is not None
    assert d.cron is not None
    assert isinstance(d.channels, dict)


@pytest.mark.asyncio
async def test_on_message_unapproved_sends_pairing(tmp_path: Path):
    """Unapproved sender receives a pairing code."""
    d = _make_daemon(tmp_path)
    msg = _make_message(sender_id="new_user", text="hi there")

    response = await d._on_message(msg)
    assert "pairing code" in response.lower() or "code" in response.lower()
    # A 6-char code should be somewhere in the response
    words = response.split()
    codes = [w.strip(".") for w in words if len(w.strip(".")) == 6 and w.strip(".").isalnum()]
    assert len(codes) >= 1


@pytest.mark.asyncio
async def test_on_message_approved_routes(tmp_path: Path):
    """Approved sender messages are routed to a session."""
    d = _make_daemon(tmp_path)

    # Pre-approve the sender
    code = d.auth.request_pairing("approved_user", ChannelType.WEBHOOK, "main", "AU")
    d.auth.verify_pairing("approved_user", ChannelType.WEBHOOK, code)

    msg = _make_message(sender_id="approved_user", text="do something")
    response = await d._on_message(msg)

    # Should come from the router stub
    assert "session" in response.lower() or "received" in response.lower()


@pytest.mark.asyncio
async def test_pairing_flow_complete(tmp_path: Path):
    """Full pairing flow through the daemon: first message → code → verify → route."""
    d = _make_daemon(tmp_path)

    # Step 1: First message from unknown sender → get pairing code
    msg1 = _make_message(sender_id="flow_user", text="hello")
    resp1 = await d._on_message(msg1)
    assert "code" in resp1.lower()

    # Extract the 6-char code from the response
    words = resp1.replace(".", " ").replace(":", " ").split()
    code = None
    for w in words:
        if len(w) == 6 and w.isalnum() and w == w.upper():
            code = w
            break
    assert code is not None, f"No pairing code found in: {resp1}"

    # Step 2: Reply with the code → pairing succeeds
    msg2 = _make_message(sender_id="flow_user", text=code)
    resp2 = await d._on_message(msg2)
    assert "successful" in resp2.lower() or "connected" in resp2.lower()

    # Step 3: Now approved — messages route to session
    msg3 = _make_message(sender_id="flow_user", text="real work now")
    resp3 = await d._on_message(msg3)
    assert "session" in resp3.lower() or "received" in resp3.lower()
