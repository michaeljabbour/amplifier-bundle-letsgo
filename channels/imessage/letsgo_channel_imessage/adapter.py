"""iMessage channel adapter using AppleScript subprocess bridge (macOS only)."""

from __future__ import annotations

import asyncio
import logging
import platform
import shutil
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

_IS_MACOS = platform.system() == "Darwin"


class IMessageChannel(ChannelAdapter):
    """iMessage adapter using osascript (AppleScript) on macOS.

    Config keys:
        apple_id: The Apple ID or phone number to send from
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._apple_id: str = config.get("apple_id", "")
        self._osascript: str | None = shutil.which("osascript") if _IS_MACOS else None

    async def start(self) -> None:
        """Start the iMessage adapter."""
        if not _IS_MACOS:
            logger.warning(
                "iMessage channel '%s' cannot start — macOS required (current: %s)",
                self.name,
                platform.system(),
            )
            return

        if not self._osascript:
            logger.warning(
                "osascript not found — iMessage channel '%s' cannot start",
                self.name,
            )
            return

        self._running = True
        logger.info("IMessageChannel '%s' started for %s", self.name, self._apple_id)

    async def stop(self) -> None:
        """Stop the iMessage adapter."""
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message via iMessage (osascript)."""
        if not self._running or not self._osascript:
            return False

        recipient = message.thread_id or self._apple_id
        if not recipient:
            logger.error("No recipient for iMessage send")
            return False

        script = self._format_applescript(message.text, recipient)
        try:
            proc = await asyncio.create_subprocess_exec(
                self._osascript,
                "-e",
                script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            if proc.returncode != 0:
                logger.error("osascript failed: %s", stderr.decode())
                return False
            return True
        except (FileNotFoundError, asyncio.TimeoutError):
            logger.exception("Failed to send iMessage")
            return False

    def _format_applescript(self, text: str, recipient: str) -> str:
        """Build an AppleScript command to send an iMessage.

        Args:
            text: Message text to send.
            recipient: Phone number or Apple ID of the recipient.

        Returns:
            AppleScript source string for osascript -e.
        """
        # Escape quotes in text for AppleScript string literals
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return (
            f'tell application "Messages"\n'
            f'    set targetService to 1st service whose service type = iMessage\n'
            f'    set targetBuddy to buddy "{recipient}" of targetService\n'
            f'    send "{escaped}" to targetBuddy\n'
            f"end tell"
        )
