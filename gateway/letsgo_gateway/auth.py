"""Authentication and pairing middleware for the gateway."""

from __future__ import annotations

import json
import os
import secrets
import string
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .models import AuthStatus, ChannelType, PairingRequest, SenderRecord


def generate_pairing_code() -> str:
    """Generate a 6-character alphanumeric pairing code."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(6))


class PairingStore:
    """Persistent pairing and sender auth store backed by a JSON file."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        default_path = Path("~/.letsgo/gateway/pairing.json").expanduser()
        self._db_path = Path(config.get("pairing_db_path", str(default_path)))
        self._max_messages_per_minute: int = config.get("max_messages_per_minute", 10)
        self._code_ttl_seconds: int = config.get("code_ttl_seconds", 300)

        # In-memory state
        self._pairing_requests: dict[str, PairingRequest] = {}
        self._senders: dict[str, SenderRecord] = {}
        self._rate_limits: dict[str, list[float]] = {}

        self._load()

    # ---- key helpers ----

    @staticmethod
    def _key(sender_id: str, channel: ChannelType | str) -> str:
        ch = channel.value if isinstance(channel, ChannelType) else channel
        return f"{ch}:{sender_id}"

    # ---- persistence ----

    def _load(self) -> None:
        if not self._db_path.exists():
            return
        try:
            data = json.loads(self._db_path.read_text())
        except (json.JSONDecodeError, OSError):
            return

        for key, rec in data.get("senders", {}).items():
            self._senders[key] = SenderRecord(
                sender_id=rec["sender_id"],
                channel=ChannelType(rec["channel"]),
                channel_name=rec.get("channel_name", ""),
                status=AuthStatus(rec["status"]),
                label=rec.get("label", ""),
                approved_at=(
                    datetime.fromisoformat(rec["approved_at"])
                    if rec.get("approved_at")
                    else None
                ),
                last_seen=(
                    datetime.fromisoformat(rec["last_seen"])
                    if rec.get("last_seen")
                    else None
                ),
                message_count=rec.get("message_count", 0),
            )

        for key, pr in data.get("pairing_requests", {}).items():
            self._pairing_requests[key] = PairingRequest(
                channel=ChannelType(pr["channel"]),
                channel_name=pr.get("channel_name", ""),
                sender_id=pr["sender_id"],
                sender_label=pr.get("sender_label", ""),
                code=pr["code"],
                created_at=datetime.fromisoformat(pr["created_at"]),
                expires_at=(
                    datetime.fromisoformat(pr["expires_at"])
                    if pr.get("expires_at")
                    else None
                ),
            )

    def _save(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        senders_data: dict[str, Any] = {}
        for key, rec in self._senders.items():
            senders_data[key] = {
                "sender_id": rec.sender_id,
                "channel": rec.channel.value,
                "channel_name": rec.channel_name,
                "status": rec.status.value,
                "label": rec.label,
                "approved_at": (
                    rec.approved_at.isoformat() if rec.approved_at else None
                ),
                "last_seen": (rec.last_seen.isoformat() if rec.last_seen else None),
                "message_count": rec.message_count,
            }

        pairing_data: dict[str, Any] = {}
        for key, pr in self._pairing_requests.items():
            pairing_data[key] = {
                "channel": pr.channel.value,
                "channel_name": pr.channel_name,
                "sender_id": pr.sender_id,
                "sender_label": pr.sender_label,
                "code": pr.code,
                "created_at": pr.created_at.isoformat(),
                "expires_at": (pr.expires_at.isoformat() if pr.expires_at else None),
            }

        payload = json.dumps(
            {"senders": senders_data, "pairing_requests": pairing_data},
            indent=2,
        )

        # Atomic write: temp file + rename
        fd, tmp = tempfile.mkstemp(dir=str(self._db_path.parent), suffix=".tmp")
        try:
            os.write(fd, payload.encode())
            os.close(fd)
            os.replace(tmp, str(self._db_path))
        except Exception:
            os.close(fd) if not os.get_inheritable(fd) else None
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # ---- pairing API ----

    def request_pairing(
        self,
        sender_id: str,
        channel: ChannelType,
        channel_name: str,
        sender_label: str,
    ) -> str:
        """Create a pairing request and return the code."""
        code = generate_pairing_code()
        key = self._key(sender_id, channel)
        now = datetime.now(UTC)
        pr = PairingRequest(
            channel=channel,
            channel_name=channel_name,
            sender_id=sender_id,
            sender_label=sender_label,
            code=code,
            created_at=now,
            expires_at=now + timedelta(seconds=self._code_ttl_seconds),
        )
        self._pairing_requests[key] = pr

        # Ensure a sender record exists
        if key not in self._senders:
            self._senders[key] = SenderRecord(
                sender_id=sender_id,
                channel=channel,
                channel_name=channel_name,
                status=AuthStatus.PENDING,
                label=sender_label,
            )

        self._save()
        return code

    def verify_pairing(self, sender_id: str, channel: ChannelType, code: str) -> bool:
        """Validate a pairing code and promote sender to approved."""
        key = self._key(sender_id, channel)
        pr = self._pairing_requests.get(key)
        if pr is None:
            return False
        if pr.code != code:
            return False
        if pr.expires_at and datetime.now(UTC) > pr.expires_at:
            # Expired
            del self._pairing_requests[key]
            self._save()
            return False

        # Approve
        now = datetime.now(UTC)
        rec = self._senders.get(key)
        if rec:
            rec.status = AuthStatus.APPROVED
            rec.approved_at = now
        else:
            self._senders[key] = SenderRecord(
                sender_id=sender_id,
                channel=channel,
                channel_name=pr.channel_name,
                status=AuthStatus.APPROVED,
                label=pr.sender_label,
                approved_at=now,
            )

        del self._pairing_requests[key]
        self._save()
        return True

    def is_approved(self, sender_id: str, channel: ChannelType) -> bool:
        """Check if a sender is approved."""
        key = self._key(sender_id, channel)
        rec = self._senders.get(key)
        return rec is not None and rec.status == AuthStatus.APPROVED

    def has_pending_pairing(self, sender_id: str, channel: ChannelType) -> bool:
        """Check if a sender has a pending (non-expired) pairing request."""
        key = self._key(sender_id, channel)
        pr = self._pairing_requests.get(key)
        if pr is None:
            return False
        if pr.expires_at and datetime.now(UTC) > pr.expires_at:
            del self._pairing_requests[key]
            return False
        return True

    def check_rate_limit(self, sender_id: str, channel: ChannelType) -> bool:
        """Return True if the sender is within rate limits, False if exceeded."""
        key = self._key(sender_id, channel)
        now = time.monotonic()
        window = self._rate_limits.get(key, [])

        # Sliding window: keep only timestamps within the last 60 seconds
        cutoff = now - 60.0
        window = [t for t in window if t > cutoff]
        self._rate_limits[key] = window

        if len(window) >= self._max_messages_per_minute:
            return False

        window.append(now)
        self._rate_limits[key] = window

        # Update sender record
        rec = self._senders.get(key)
        if rec:
            rec.last_seen = datetime.now(UTC)
            rec.message_count += 1

        return True

    def get_all_approved(
        self, channel: ChannelType | None = None
    ) -> list[SenderRecord]:
        """List all approved senders, optionally filtered by channel."""
        results = []
        for rec in self._senders.values():
            if rec.status != AuthStatus.APPROVED:
                continue
            if channel is not None and rec.channel != channel:
                continue
            results.append(rec)
        return results

    def block_sender(self, sender_id: str, channel: ChannelType) -> None:
        """Block a sender."""
        key = self._key(sender_id, channel)
        rec = self._senders.get(key)
        if rec:
            rec.status = AuthStatus.BLOCKED
        else:
            self._senders[key] = SenderRecord(
                sender_id=sender_id,
                channel=channel,
                channel_name="",
                status=AuthStatus.BLOCKED,
            )
        # Remove any pending pairing
        self._pairing_requests.pop(key, None)
        self._save()

    def unblock_sender(self, sender_id: str, channel: ChannelType) -> None:
        """Restore a blocked sender to approved status."""
        key = self._key(sender_id, channel)
        rec = self._senders.get(key)
        if rec and rec.status == AuthStatus.BLOCKED:
            rec.status = AuthStatus.APPROVED
            self._save()

    def get_all_senders(self, channel: ChannelType | None = None) -> list[SenderRecord]:
        """List all senders regardless of status, optionally filtered by channel."""
        results = []
        for rec in self._senders.values():
            if channel is not None and rec.channel != channel:
                continue
            results.append(rec)
        return results
