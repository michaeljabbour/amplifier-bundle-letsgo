"""Signal channel adapter using signal-cli subprocess bridge."""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)


class SignalChannel(ChannelAdapter):
    """Signal messaging adapter backed by signal-cli.

    Config keys:
        phone_number: The Signal phone number (e.g., "+15551234567")
        signal_cli_path: Path to signal-cli binary (default: auto-detect)
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._phone: str = config.get("phone_number", "")
        explicit_path = config.get("signal_cli_path")
        # Allow explicit None to mean "not found"
        if explicit_path is None and "signal_cli_path" in config:
            self._cli_path: str | None = None
        else:
            self._cli_path = explicit_path or shutil.which("signal-cli")
        self._process: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        """Start listening for Signal messages via signal-cli daemon."""
        if not self._cli_path:
            logger.warning(
                "signal-cli not found — Signal channel '%s' cannot start",
                self.name,
            )
            return

        try:
            self._process = await asyncio.create_subprocess_exec(
                self._cli_path,
                "-u",
                self._phone,
                "daemon",
                "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._running = True
            logger.info("SignalChannel '%s' started for %s", self.name, self._phone)
            # Start reading messages in background
            asyncio.create_task(self._read_messages())
        except FileNotFoundError:
            logger.error("signal-cli binary not found at %s", self._cli_path)

    async def stop(self) -> None:
        """Stop the signal-cli subprocess."""
        if self._process:
            self._process.terminate()
            await self._process.wait()
            self._process = None
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message via signal-cli."""
        if not self._running or not self._cli_path:
            return False

        args = self._format_outbound(message)
        try:
            proc = await asyncio.create_subprocess_exec(
                self._cli_path,
                "-u",
                self._phone,
                "send",
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode != 0:
                logger.error("signal-cli send failed: %s", stderr.decode())
                return False
            return True
        except (FileNotFoundError, asyncio.TimeoutError):
            logger.exception("Failed to send Signal message")
            return False

    def _format_outbound(self, message: OutboundMessage) -> list[str]:
        """Convert an OutboundMessage to signal-cli send arguments."""
        args: list[str] = []
        if message.thread_id:
            args.extend([message.thread_id])
        args.extend(["-m", message.text])
        return args

    async def _read_messages(self) -> None:
        """Read JSON lines from signal-cli daemon stdout."""
        if not self._process or not self._process.stdout:
            return

        import json

        while self._running:
            try:
                line = await self._process.stdout.readline()
                if not line:
                    break
                data = json.loads(line)
                envelope = data.get("envelope", {})
                data_msg = envelope.get("dataMessage")
                if data_msg and self._on_message:
                    msg = InboundMessage(
                        channel=ChannelType("signal"),
                        channel_name=self.name,
                        sender_id=envelope.get("source", "unknown"),
                        sender_label=envelope.get("sourceName", ""),
                        text=data_msg.get("message", ""),
                        thread_id=envelope.get("source"),
                    )
                    await self._on_message(msg)
            except Exception:
                logger.exception("Error reading Signal message")
