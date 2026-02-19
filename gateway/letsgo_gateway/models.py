"""Data models shared across the gateway."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class ChannelType(str, Enum):
    WEBHOOK = "webhook"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    WHATSAPP = "whatsapp"


class AuthStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    BLOCKED = "blocked"


@dataclass
class InboundMessage:
    channel: ChannelType
    channel_name: str
    sender_id: str
    sender_label: str
    text: str
    thread_id: str | None = None
    attachments: list[dict[str, Any]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutboundMessage:
    channel: ChannelType
    channel_name: str
    thread_id: str | None
    text: str
    attachments: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PairingRequest:
    channel: ChannelType
    channel_name: str
    sender_id: str
    sender_label: str
    code: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None


@dataclass
class SenderRecord:
    sender_id: str
    channel: ChannelType
    channel_name: str
    status: AuthStatus = AuthStatus.PENDING
    label: str = ""
    approved_at: datetime | None = None
    last_seen: datetime | None = None
    message_count: int = 0
