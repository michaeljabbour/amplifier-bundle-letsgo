"""Tests for gateway channel adapters."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from letsgo_gateway.channels.webhook import WebhookChannel
from letsgo_gateway.channels.telegram import TelegramChannel
from letsgo_gateway.channels.discord import DiscordChannel
from letsgo_gateway.channels.slack import SlackChannel
from letsgo_gateway.channels.whatsapp import WhatsAppChannel
from letsgo_gateway.models import ChannelType, OutboundMessage


# ---------------------------------------------------------------------------
# Webhook tests
# ---------------------------------------------------------------------------


def test_webhook_normalize_message():
    """WebhookChannel.normalize_message produces a correct InboundMessage."""
    data = {
        "sender_id": "u42",
        "sender_label": "Alice",
        "text": "Hello gateway",
        "thread_id": "t-1",
        "attachments": [{"url": "https://example.com/file.png"}],
    }
    msg = WebhookChannel.normalize_message("my-hook", data)

    assert msg.channel == ChannelType.WEBHOOK
    assert msg.channel_name == "my-hook"
    assert msg.sender_id == "u42"
    assert msg.sender_label == "Alice"
    assert msg.text == "Hello gateway"
    assert msg.thread_id == "t-1"
    assert len(msg.attachments) == 1
    assert msg.raw == data


def test_webhook_hmac_validation():
    """HMAC signature validation works correctly."""
    secret = "my-secret-key"
    ch = WebhookChannel("test", {"shared_secret": secret})

    body = b'{"text": "hello"}'
    valid_sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert ch.verify_signature(body, valid_sig)
    assert not ch.verify_signature(body, "bad-signature")
    assert not ch.verify_signature(b"different body", valid_sig)


def test_webhook_hmac_skipped_without_secret():
    """Without a shared_secret, signature validation always passes."""
    ch = WebhookChannel("test", {})
    assert ch.verify_signature(b"anything", "anything")


# ---------------------------------------------------------------------------
# Stub adapter tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_telegram_stub_raises():
    """Telegram adapter raises NotImplementedError."""
    adapter = TelegramChannel("tg", {"bot_token": "fake"})
    with pytest.raises(NotImplementedError, match="python-telegram-bot"):
        await adapter.start()
    with pytest.raises(NotImplementedError, match="python-telegram-bot"):
        await adapter.stop()
    with pytest.raises(NotImplementedError, match="python-telegram-bot"):
        await adapter.send(
            OutboundMessage(ChannelType.TELEGRAM, "tg", None, "hi")
        )


@pytest.mark.asyncio
async def test_discord_stub_raises():
    """Discord adapter raises NotImplementedError."""
    adapter = DiscordChannel("dc", {"bot_token": "fake"})
    with pytest.raises(NotImplementedError, match="discord.py"):
        await adapter.start()
    with pytest.raises(NotImplementedError, match="discord.py"):
        await adapter.send(
            OutboundMessage(ChannelType.DISCORD, "dc", None, "hi")
        )


@pytest.mark.asyncio
async def test_slack_stub_raises():
    """Slack adapter raises NotImplementedError."""
    adapter = SlackChannel("sl", {"bot_token": "fake"})
    with pytest.raises(NotImplementedError, match="slack-sdk"):
        await adapter.start()
    with pytest.raises(NotImplementedError, match="slack-sdk"):
        await adapter.send(
            OutboundMessage(ChannelType.SLACK, "sl", None, "hi")
        )


# ---------------------------------------------------------------------------
# WhatsApp tests
# ---------------------------------------------------------------------------


def _make_whatsapp_channel(**overrides: object) -> WhatsAppChannel:
    """Create a WhatsAppChannel with test defaults."""
    config: dict = {**overrides}
    return WhatsAppChannel("wa-test", config)


def _bridge_message_data(
    sender: str = "15551234567@c.us",
    text: str = "Hello there",
    files: list | None = None,
) -> dict:
    """Build bridge message data (the 'data' field from a bridge event)."""
    return {
        "id": "test_123",
        "from": sender,
        "sender": "Test User",
        "text": text,
        "files": files or [],
        "timestamp": 1700000000,
        "messageType": "chat",
    }


@pytest.mark.asyncio
async def test_whatsapp_handle_inbound_creates_message():
    """Bridge message event produces a correct InboundMessage."""
    ch = _make_whatsapp_channel()
    received = []

    async def capture(msg):
        received.append(msg)
        return None

    ch.set_on_message(capture)
    await ch._handle_inbound(_bridge_message_data())

    assert len(received) == 1
    msg = received[0]
    assert msg.channel == ChannelType.WHATSAPP
    assert msg.sender_id == "15551234567@c.us"
    assert msg.sender_label == "Test User"
    assert msg.text == "Hello there"
    assert msg.thread_id == "15551234567@c.us"


@pytest.mark.asyncio
async def test_whatsapp_handle_inbound_with_files():
    """Bridge message with files populates attachments."""
    ch = _make_whatsapp_channel()
    received = []

    async def capture(msg):
        received.append(msg)
        return None

    ch.set_on_message(capture)
    await ch._handle_inbound(_bridge_message_data(files=["/tmp/photo.jpg"]))

    assert len(received) == 1
    assert len(received[0].attachments) == 1
    assert received[0].attachments[0]["path"] == "/tmp/photo.jpg"


@pytest.mark.asyncio
async def test_whatsapp_handle_inbound_no_callback():
    """No crash when _on_message is not set."""
    ch = _make_whatsapp_channel()
    # Should not raise
    await ch._handle_inbound(_bridge_message_data())


@pytest.mark.asyncio
async def test_whatsapp_bridge_event_dispatch():
    """_handle_bridge_event dispatches message events."""
    ch = _make_whatsapp_channel()
    received = []

    async def capture(msg):
        received.append(msg)
        return None

    ch.set_on_message(capture)
    event = {"type": "message", "data": _bridge_message_data()}
    await ch._handle_bridge_event(event)

    assert len(received) == 1


@pytest.mark.asyncio
async def test_whatsapp_bridge_event_ready():
    """Ready event sets the _ready flag."""
    ch = _make_whatsapp_channel()
    assert not ch._ready.is_set()

    await ch._handle_bridge_event({"type": "ready", "data": {"phone": "15551234567"}})

    assert ch._ready.is_set()


@pytest.mark.asyncio
async def test_whatsapp_bridge_event_disconnect_clears_ready():
    """Disconnect event clears the _ready flag."""
    ch = _make_whatsapp_channel()
    ch._ready.set()

    await ch._handle_bridge_event({"type": "disconnect", "data": {"reason": "logout"}})

    assert not ch._ready.is_set()


@pytest.mark.asyncio
async def test_whatsapp_node_not_found():
    """start() logs error and stays not-running when node is not on PATH."""
    ch = _make_whatsapp_channel(node_path=None)
    await ch.start()
    assert not ch._running


def test_whatsapp_split_text_short():
    """Short text returns a single chunk."""
    assert WhatsAppChannel._split_text("short text") == ["short text"]


def test_whatsapp_split_text_at_paragraph():
    """Long text splits at paragraph boundary when possible."""
    para1 = "a" * 3000
    para2 = "b" * 3000
    text = para1 + "\n\n" + para2

    chunks = WhatsAppChannel._split_text(text)

    assert len(chunks) == 2
    assert chunks[0] == para1
    assert chunks[1] == para2


def test_whatsapp_split_text_hard():
    """Text with no natural breaks hard-splits at 4000."""
    text = "a" * 5000

    chunks = WhatsAppChannel._split_text(text)

    assert len(chunks) == 2
    assert len(chunks[0]) == 4000
    assert len(chunks[1]) == 1000
