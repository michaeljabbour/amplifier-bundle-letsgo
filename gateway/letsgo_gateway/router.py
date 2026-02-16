"""Session routing for the gateway."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from .models import InboundMessage


class SessionRouter:
    """Routes inbound messages to sessions, one session per sender+channel."""

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._session_counter: int = 0

    def route_key(self, message: InboundMessage) -> str:
        """Derive a route key from the message: ``{channel}:{sender_id}``."""
        return f"{message.channel.value}:{message.sender_id}"

    def get_or_create_session(self, key: str) -> dict[str, Any]:
        """Return the existing session for *key*, or create a new one."""
        if key in self._sessions:
            session = self._sessions[key]
            session["last_active"] = time.monotonic()
            session["message_count"] += 1
            return session

        self._session_counter += 1
        session: dict[str, Any] = {
            "session_id": f"gw-session-{self._session_counter}",
            "route_key": key,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_active": time.monotonic(),
            "message_count": 1,
        }
        self._sessions[key] = session
        return session

    def route_message(self, message: InboundMessage) -> str:
        """Route a message and return the session response (stub)."""
        key = self.route_key(message)
        session = self.get_or_create_session(key)
        # Stub: actual AmplifierSession creation requires the full framework
        return f"Session {session['session_id']} received: {message.text}"

    def close_session(self, key: str) -> bool:
        """Close a session by route key. Returns True if it existed."""
        return self._sessions.pop(key, None) is not None

    def close_stale_sessions(self, max_idle_seconds: float) -> list[str]:
        """Close sessions idle longer than *max_idle_seconds*. Returns closed keys."""
        now = time.monotonic()
        stale = [
            key
            for key, sess in self._sessions.items()
            if (now - sess["last_active"]) > max_idle_seconds
        ]
        for key in stale:
            del self._sessions[key]
        return stale

    @property
    def active_sessions(self) -> dict[str, dict[str, Any]]:
        """Return a copy of active sessions."""
        return dict(self._sessions)
