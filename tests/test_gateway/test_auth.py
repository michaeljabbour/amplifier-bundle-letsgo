"""Tests for gateway authentication and pairing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from letsgo_gateway.auth import PairingStore, generate_pairing_code
from letsgo_gateway.models import AuthStatus, ChannelType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store(tmp_path: Path, **overrides) -> PairingStore:
    config = {
        "pairing_db_path": str(tmp_path / "pairing.json"),
        "max_messages_per_minute": overrides.pop("max_messages_per_minute", 10),
        "code_ttl_seconds": overrides.pop("code_ttl_seconds", 300),
        **overrides,
    }
    return PairingStore(config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_generate_pairing_code_format():
    """Pairing code is 6 alphanumeric characters."""
    for _ in range(20):
        code = generate_pairing_code()
        assert len(code) == 6
        assert code.isalnum()
        assert code == code.upper()  # all uppercase


def test_request_and_verify_pairing(tmp_path: Path):
    """Full pairing flow: request → verify → approved."""
    store = _make_store(tmp_path)
    code = store.request_pairing(
        sender_id="user1",
        channel=ChannelType.WEBHOOK,
        channel_name="main",
        sender_label="User One",
    )
    assert len(code) == 6

    # Not yet approved
    assert not store.is_approved("user1", ChannelType.WEBHOOK)

    # Verify with correct code
    assert store.verify_pairing("user1", ChannelType.WEBHOOK, code)
    assert store.is_approved("user1", ChannelType.WEBHOOK)


def test_expired_code_rejected(tmp_path: Path):
    """An expired pairing code is rejected."""
    store = _make_store(tmp_path, code_ttl_seconds=1)
    code = store.request_pairing(
        sender_id="user2",
        channel=ChannelType.TELEGRAM,
        channel_name="bot",
        sender_label="User Two",
    )

    # Manually expire the code
    key = store._key("user2", ChannelType.TELEGRAM)
    pr = store._pairing_requests[key]
    pr.expires_at = datetime.now(UTC) - timedelta(seconds=10)

    assert not store.verify_pairing("user2", ChannelType.TELEGRAM, code)
    assert not store.is_approved("user2", ChannelType.TELEGRAM)


def test_is_approved_after_pairing(tmp_path: Path):
    """After pairing, is_approved returns True consistently."""
    store = _make_store(tmp_path)
    code = store.request_pairing("u3", ChannelType.DISCORD, "srv", "U3")
    store.verify_pairing("u3", ChannelType.DISCORD, code)

    assert store.is_approved("u3", ChannelType.DISCORD)
    # Different channel — not approved
    assert not store.is_approved("u3", ChannelType.SLACK)


def test_rate_limit_enforced(tmp_path: Path):
    """Rate limiter blocks after max_messages_per_minute."""
    store = _make_store(tmp_path, max_messages_per_minute=3)

    # Approve sender first
    code = store.request_pairing("rl_user", ChannelType.WEBHOOK, "ch", "RL")
    store.verify_pairing("rl_user", ChannelType.WEBHOOK, code)

    # First 3 should pass
    assert store.check_rate_limit("rl_user", ChannelType.WEBHOOK)
    assert store.check_rate_limit("rl_user", ChannelType.WEBHOOK)
    assert store.check_rate_limit("rl_user", ChannelType.WEBHOOK)

    # 4th should be blocked
    assert not store.check_rate_limit("rl_user", ChannelType.WEBHOOK)


def test_block_sender(tmp_path: Path):
    """Blocking a sender changes their status and removes pairing."""
    store = _make_store(tmp_path)
    code = store.request_pairing("bad", ChannelType.WEBHOOK, "ch", "Bad")
    store.verify_pairing("bad", ChannelType.WEBHOOK, code)
    assert store.is_approved("bad", ChannelType.WEBHOOK)

    store.block_sender("bad", ChannelType.WEBHOOK)
    assert not store.is_approved("bad", ChannelType.WEBHOOK)

    key = store._key("bad", ChannelType.WEBHOOK)
    assert store._senders[key].status == AuthStatus.BLOCKED


def test_persistence(tmp_path: Path):
    """Data survives a store reload from disk."""
    store = _make_store(tmp_path)
    code = store.request_pairing("persist", ChannelType.SLACK, "ws", "P")
    store.verify_pairing("persist", ChannelType.SLACK, code)
    assert store.is_approved("persist", ChannelType.SLACK)

    # Reload from same file
    store2 = _make_store(tmp_path)
    assert store2.is_approved("persist", ChannelType.SLACK)
    approved = store2.get_all_approved(ChannelType.SLACK)
    assert len(approved) == 1
    assert approved[0].sender_id == "persist"


# ---------------------------------------------------------------------------
# get_all_senders / unblock_sender
# ---------------------------------------------------------------------------


def test_get_all_senders_returns_every_status(tmp_path: Path):
    """get_all_senders returns pending, approved, AND blocked senders."""
    store = _make_store(tmp_path)

    # Create one approved sender
    code = store.request_pairing("a1", ChannelType.WEBHOOK, "ch", "A1")
    store.verify_pairing("a1", ChannelType.WEBHOOK, code)

    # Create one pending sender (request but don't verify)
    store.request_pairing("a2", ChannelType.TELEGRAM, "ch", "A2")

    # Create one blocked sender
    code = store.request_pairing("a3", ChannelType.DISCORD, "ch", "A3")
    store.verify_pairing("a3", ChannelType.DISCORD, code)
    store.block_sender("a3", ChannelType.DISCORD)

    all_senders = store.get_all_senders()
    assert len(all_senders) == 3
    statuses = {r.status for r in all_senders}
    assert statuses == {AuthStatus.APPROVED, AuthStatus.PENDING, AuthStatus.BLOCKED}


def test_get_all_senders_filtered_by_channel(tmp_path: Path):
    """get_all_senders(channel=...) returns only senders on that channel."""
    store = _make_store(tmp_path)

    code = store.request_pairing("b1", ChannelType.WEBHOOK, "ch", "B1")
    store.verify_pairing("b1", ChannelType.WEBHOOK, code)

    code = store.request_pairing("b2", ChannelType.SLACK, "ch", "B2")
    store.verify_pairing("b2", ChannelType.SLACK, code)

    webhook_senders = store.get_all_senders(channel=ChannelType.WEBHOOK)
    assert len(webhook_senders) == 1
    assert webhook_senders[0].sender_id == "b1"


def test_unblock_sender_restores_to_approved(tmp_path: Path):
    """unblock_sender changes status from BLOCKED back to APPROVED."""
    store = _make_store(tmp_path)

    code = store.request_pairing("c1", ChannelType.WEBHOOK, "ch", "C1")
    store.verify_pairing("c1", ChannelType.WEBHOOK, code)
    store.block_sender("c1", ChannelType.WEBHOOK)

    key = store._key("c1", ChannelType.WEBHOOK)
    assert store._senders[key].status == AuthStatus.BLOCKED

    store.unblock_sender("c1", ChannelType.WEBHOOK)
    assert store._senders[key].status == AuthStatus.APPROVED
    assert store.is_approved("c1", ChannelType.WEBHOOK)
