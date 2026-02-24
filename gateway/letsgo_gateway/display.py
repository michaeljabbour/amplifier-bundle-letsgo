"""Gateway DisplaySystem — routes content to canvas or chat channels."""

from __future__ import annotations

import logging
from typing import Any

from .channels.base import ChannelAdapter
from .models import ChannelType, OutboundMessage

logger = logging.getLogger(__name__)

# Channel names that are treated as canvas surfaces
_CANVAS_CHANNEL_NAMES = {"canvas", "webchat-canvas"}


class GatewayDisplaySystem:
    """Routes display content to the appropriate channel surface.

    If a canvas channel is connected, content goes there.
    Otherwise, content is formatted and sent to chat channels as fallback.
    """

    def __init__(self, channels: dict[str, ChannelAdapter]) -> None:
        self._channels = channels
        self._canvas_state: dict[str, dict[str, Any]] = {}

    @property
    def canvas_state(self) -> dict[str, dict[str, Any]]:
        """Current canvas content state, keyed by content ID."""
        return self._canvas_state

    async def display(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Display content on the best available surface.

        Args:
            content: The content to display (markdown, SVG, HTML, etc.).
            metadata: Optional metadata including ``content_type`` and ``id``.
        """
        if not self._channels:
            logger.debug("DisplaySystem: no channels available, dropping content")
            return

        meta = metadata or {}
        content_type = meta.get("content_type", "text")
        content_id = meta.get("id")

        # Try canvas channel first
        canvas = self._find_canvas_channel()
        if canvas is not None:
            msg = OutboundMessage(
                channel=ChannelType(canvas.name),
                channel_name=canvas.name,
                thread_id=None,
                text=content,
            )
            await canvas.send(msg)

            # Track canvas state
            if content_id:
                self._canvas_state[content_id] = {
                    "content_type": content_type,
                    "content": content,
                }
            return

        # Fallback: send to first available chat channel
        for name, channel in self._channels.items():
            msg = OutboundMessage(
                channel=ChannelType(name),
                channel_name=name,
                thread_id=None,
                text=content,
            )
            await channel.send(msg)
            return  # Send to first channel only

    def _find_canvas_channel(self) -> ChannelAdapter | None:
        """Find a canvas-type channel if one is connected."""
        for name, channel in self._channels.items():
            if name in _CANVAS_CHANNEL_NAMES:
                return channel
        return None
