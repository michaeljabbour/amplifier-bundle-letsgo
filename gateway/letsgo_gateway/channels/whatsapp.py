"""WhatsApp channel adapter using whatsapp-web.js via a Node.js bridge.

Spawns a Node.js subprocess running whatsapp_bridge.js which handles
the WhatsApp Web connection (QR code auth, message events, media).
Communication is via JSON lines on stdin/stdout.

Config keys:
    session_dir: Session persistence directory (default ``~/.letsgo/whatsapp-session/``)
    files_dir: Media download directory (default ``~/.letsgo/whatsapp-files/``)
    qr_file: QR code save path (default ``~/.letsgo/whatsapp_qr.txt``)
    node_path: Path to node binary (default: found via ``shutil.which``)
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any

from ..models import ChannelType, InboundMessage, OutboundMessage
from .base import ChannelAdapter

logger = logging.getLogger(__name__)

_BRIDGE_SCRIPT = Path(__file__).parent / "whatsapp_bridge.js"
_MAX_TEXT_LENGTH = 4000


class WhatsAppChannel(ChannelAdapter):
    """WhatsApp adapter backed by whatsapp-web.js.

    Spawns a Node.js child process that handles the WhatsApp Web protocol.
    Authentication is via QR code scan — no API keys or business accounts
    required.

    Config:
        session_dir (str): Session persistence path.
        files_dir (str): Downloaded media path.
        qr_file (str): QR code text file path.
        node_path (str): Explicit path to ``node`` binary.
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)

        home = Path.home() / ".letsgo"
        self._session_dir = config.get("session_dir", str(home / "whatsapp-session"))
        self._files_dir = config.get("files_dir", str(home / "whatsapp-files"))
        self._qr_file = config.get("qr_file", str(home / "whatsapp_qr.txt"))
        self._node_path = config.get("node_path", shutil.which("node"))

        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()

    # ---- lifecycle ----

    async def start(self) -> None:
        if not self._node_path:
            logger.error(
                "WhatsApp adapter '%s': node not found. "
                "Install Node.js and ensure 'node' is on PATH.",
                self.name,
            )
            return

        if not _BRIDGE_SCRIPT.exists():
            logger.error(
                "WhatsApp bridge script not found at %s", _BRIDGE_SCRIPT
            )
            return

        # Check that npm deps are installed
        pkg_dir = _BRIDGE_SCRIPT.parent
        if not (pkg_dir / "node_modules" / "whatsapp-web.js").exists():
            logger.error(
                "WhatsApp adapter '%s': node_modules not found. "
                "Run 'npm install' in %s",
                self.name,
                pkg_dir,
            )
            return

        env = {
            "HOME": str(Path.home()),
            "PATH": str(Path(self._node_path).parent) + ":/usr/bin:/bin",
            "WHATSAPP_SESSION_DIR": self._session_dir,
            "WHATSAPP_FILES_DIR": self._files_dir,
            "WHATSAPP_QR_FILE": self._qr_file,
        }

        self._process = await asyncio.create_subprocess_exec(
            self._node_path,
            str(_BRIDGE_SCRIPT),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        self._running = True
        self._reader_task = asyncio.create_task(self._read_stdout())
        asyncio.create_task(self._read_stderr())

        logger.info(
            "WhatsAppChannel '%s' started (pid=%s, session=%s)",
            self.name,
            self._process.pid,
            self._session_dir,
        )

    async def stop(self) -> None:
        self._running = False

        if self._process and self._process.stdin:
            try:
                self._write_cmd({"type": "shutdown"})
                await asyncio.wait_for(self._process.wait(), timeout=10)
            except (asyncio.TimeoutError, ProcessLookupError):
                self._process.kill()
            except Exception:
                logger.exception("Error during WhatsApp bridge shutdown")

        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        self._process = None
        self._reader_task = None
        logger.info("WhatsAppChannel '%s' stopped", self.name)

    # ---- bridge communication ----

    def _write_cmd(self, cmd: dict[str, Any]) -> None:
        """Send a JSON-line command to the bridge's stdin."""
        if self._process and self._process.stdin:
            line = json.dumps(cmd) + "\n"
            self._process.stdin.write(line.encode())

    async def _read_stdout(self) -> None:
        """Read JSON lines from bridge stdout and dispatch."""
        assert self._process and self._process.stdout
        while self._running:
            try:
                raw = await self._process.stdout.readline()
                if not raw:
                    break
                line = raw.decode().strip()
                if not line:
                    continue
                msg = json.loads(line)
                await self._handle_bridge_event(msg)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from bridge: %s", raw[:200])
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error reading from WhatsApp bridge")

        # Process exited
        if self._running:
            logger.warning("WhatsApp bridge process exited unexpectedly")
            self._running = False

    async def _read_stderr(self) -> None:
        """Forward bridge stderr to Python logging."""
        assert self._process and self._process.stderr
        while self._running:
            try:
                raw = await self._process.stderr.readline()
                if not raw:
                    break
                line = raw.decode().strip()
                if line:
                    logger.info("[whatsapp-bridge] %s", line)
            except asyncio.CancelledError:
                break
            except Exception:
                break

    async def _handle_bridge_event(self, event: dict[str, Any]) -> None:
        """Dispatch an event from the bridge."""
        event_type = event.get("type", "")
        data = event.get("data", {})

        if event_type == "qr":
            logger.info(
                "WhatsApp QR code generated — scan with your phone "
                "(also saved to %s)",
                self._qr_file,
            )

        elif event_type == "ready":
            phone = data.get("phone", "unknown")
            logger.info("WhatsApp connected as %s", phone)
            self._ready.set()

        elif event_type == "message":
            await self._handle_inbound(data)

        elif event_type == "disconnect":
            reason = data.get("reason", "unknown")
            logger.warning("WhatsApp disconnected: %s", reason)
            self._ready.clear()

        elif event_type == "error":
            logger.error("WhatsApp bridge error: %s", data.get("message", ""))

    # ---- inbound messages ----

    async def _handle_inbound(self, data: dict[str, Any]) -> None:
        """Convert a bridge message event to InboundMessage and dispatch."""
        sender_id = data.get("from", "")
        sender_label = data.get("sender", "")
        text = data.get("text", "")
        files = data.get("files", [])

        attachments = [{"type": "file", "path": f} for f in files]

        message = InboundMessage(
            channel=ChannelType.WHATSAPP,
            channel_name=self.name,
            sender_id=sender_id,
            sender_label=sender_label,
            text=text,
            thread_id=sender_id,
            attachments=attachments,
            raw=data,
        )

        if not self._on_message:
            return

        try:
            response_text = await self._on_message(message)
            if response_text:
                outbound = OutboundMessage(
                    channel=ChannelType.WHATSAPP,
                    channel_name=self.name,
                    thread_id=sender_id,
                    text=response_text,
                )
                await self.send(outbound)
        except Exception:
            logger.exception(
                "Error processing WhatsApp message from '%s'", sender_id
            )

    # ---- outbound ----

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message via WhatsApp."""
        if not self._process or not self._process.stdin:
            logger.warning(
                "WhatsApp adapter '%s' not running — cannot send", self.name
            )
            return False

        to = message.thread_id or ""

        # Send file attachments
        file_paths = [a.get("path", "") for a in message.attachments if a.get("path")]

        # Handle long text — save as .md file and attach
        text = message.text or ""
        if len(text) > _MAX_TEXT_LENGTH:
            md_path = Path(self._files_dir) / f"response_{id(message)}.md"
            md_path.write_text(text)
            file_paths.append(str(md_path))
            text = text[:_MAX_TEXT_LENGTH] + "\n\n(full response attached as file)"

        self._write_cmd({
            "type": "send",
            "data": {"to": to, "text": text, "files": file_paths},
        })
        return True

    # ---- helpers ----

    @staticmethod
    def _split_text(text: str, max_len: int = _MAX_TEXT_LENGTH) -> list[str]:
        """Split text into chunks. Prefers paragraph, then sentence, then hard."""
        if len(text) <= max_len:
            return [text]

        chunks: list[str] = []
        remaining = text

        while len(remaining) > max_len:
            split_at = remaining.rfind("\n\n", 0, max_len)
            if split_at > 0:
                chunks.append(remaining[:split_at])
                remaining = remaining[split_at + 2:]
                continue

            for sep in (". ", "! ", "? ", ".\n"):
                split_at = remaining.rfind(sep, 0, max_len)
                if split_at > 0:
                    chunks.append(remaining[: split_at + 1])
                    remaining = remaining[split_at + 1:].lstrip()
                    break
            else:
                chunks.append(remaining[:max_len])
                remaining = remaining[max_len:]

        if remaining:
            chunks.append(remaining)

        return chunks
