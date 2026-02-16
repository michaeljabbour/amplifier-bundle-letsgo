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
