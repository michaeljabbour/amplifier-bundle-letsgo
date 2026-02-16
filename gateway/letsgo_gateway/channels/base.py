"""Abstract base class for channel adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Awaitable

from ..models import OutboundMessage, InboundMessage


# Callback type: async function receiving an InboundMessage, returning response text
OnMessageCallback = Callable[[InboundMessage], Awaitable[str]]


class ChannelAdapter(ABC):
    """Base class every channel adapter must implement."""

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        self.name = name
        self.config = config
        self._running = False
        self._on_message: OnMessageCallback | None = None

    def set_on_message(self, callback: OnMessageCallback) -> None:
        """Register the callback invoked when an inbound message arrives."""
        self._on_message = callback

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def send(self, message: OutboundMessage) -> bool: ...

    @property
    def is_running(self) -> bool:
        return self._running
