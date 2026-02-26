"""Abstract base class for channel adapters."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Awaitable

from ..models import OutboundMessage, InboundMessage

logger = logging.getLogger(__name__)

# Callback type: async function receiving an InboundMessage, returning response text
OnMessageCallback = Callable[[InboundMessage], Awaitable[str]]


class ChannelAdapter(ABC):
    """Base class every channel adapter must implement.

    Supports a ``dry_run`` mode where outbound sends are logged but never
    delivered.  Enable via ``config["dry_run"] = True`` before going live
    on any new channel.  Review the log for unexpected outbound before
    switching to real sends.
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        self.name = name
        self.config = config
        self._running = False
        self._on_message: OnMessageCallback | None = None
        self._dry_run: bool = config.get("dry_run", False)

    def set_on_message(self, callback: OnMessageCallback) -> None:
        """Register the callback invoked when an inbound message arrives."""
        self._on_message = callback

    async def safe_send(self, message: OutboundMessage) -> bool:
        """Send with dry-run guard.

        Call ``safe_send()`` from the daemon instead of ``send()`` directly
        to ensure the dry-run guard is always applied.
        """
        if self._dry_run:
            logger.info(
                "[DRY RUN] %s would send to '%s': %s",
                self.name,
                message.thread_id or "(no thread)",
                message.text[:200],
            )
            return True
        return await self.send(message)

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def send(self, message: OutboundMessage) -> bool: ...

    @property
    def is_running(self) -> bool:
        return self._running
