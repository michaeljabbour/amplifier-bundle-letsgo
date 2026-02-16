"""Session routing for the gateway."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from .models import InboundMessage


class SessionRouter:
    """Routes inbound messages to sessions, one session per sender+channel."""

    def __init__(
        self,
        session_factory: Callable[[str, dict], Awaitable[str]] | None = None,
    ) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._session_counter: int = 0
        self._session_factory = session_factory

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

    async def route_message(self, message: InboundMessage) -> str:
        """Route a message and return the session response.

        If a *session_factory* callback is configured, delegates to the real
        Amplifier session.  Otherwise falls back to the stub echo response.
        """
        key = self.route_key(message)
        session = self.get_or_create_session(key)

        if self._session_factory is not None:
            response = await self._session_factory(
                session["session_id"],
                {
                    "text": message.text,
                    "sender_id": message.sender_id,
                    "channel": message.channel.value,
                },
            )
            return response

        # Stub: actual AmplifierSession creation requires the full framework
        return f"Session {session['session_id']} received: {message.text}"

    async def route_message_with_response(
        self, message: InboundMessage
    ) -> dict[str, Any]:
        """Route a message and return a full response dict.

        Returns:
            Dict with ``session_id``, ``response``, ``route_key``, and
            ``message_count``.
        """
        key = self.route_key(message)
        session = self.get_or_create_session(key)
        response = await self.route_message(message)
        return {
            "session_id": session["session_id"],
            "response": response,
            "route_key": key,
            "message_count": session["message_count"],
        }

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
