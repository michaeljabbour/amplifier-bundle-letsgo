"""Slack channel adapter.

Supports two inbound modes:
- **Socket Mode** (preferred): real-time via WebSocket when ``app_token`` is configured.
- **HTTP Events API**: traditional webhook with request signature verification.

Gracefully degrades when ``slack-sdk`` is not installed.

Config keys:
    bot_token: Slack Bot User OAuth Token (xoxb-...)
    signing_secret: Slack app signing secret for request verification
    app_token: Slack App-Level Token for Socket Mode (xapp-...) -- optional
    files_dir: Path for downloaded files (default: ~/.letsgo/gateway/files)
    max_message_length: Message split threshold (default: 4000)
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..models import ChannelType, InboundMessage, OutboundMessage
from .base import ChannelAdapter

if TYPE_CHECKING:
    from slack_sdk.socket_mode.aiohttp import SocketModeClient
    from slack_sdk.socket_mode.request import SocketModeRequest
    from slack_sdk.web.async_client import AsyncWebClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Graceful import -- sets _HAS_SLACK so the class can degrade cleanly.
# ---------------------------------------------------------------------------
_HAS_SLACK = False
try:
    from slack_sdk.socket_mode.aiohttp import (  # noqa: F811
        SocketModeClient as _SocketModeClient,
    )
    from slack_sdk.socket_mode.async_handler import AsyncSocketModeHandler
    from slack_sdk.socket_mode.response import SocketModeResponse
    from slack_sdk.web.async_client import (  # noqa: F811
        AsyncWebClient as _AsyncWebClient,
    )

    _HAS_SLACK = True
except ImportError:  # pragma: no cover
    _AsyncWebClient = None
    _SocketModeClient = None
    AsyncSocketModeHandler = None
    SocketModeResponse = None  # type: ignore[assignment,misc]

_DEFAULT_FILES_DIR = os.path.expanduser("~/.letsgo/gateway/files")
_DEFAULT_MAX_LEN = 4000
_SIGNATURE_VERSION = "v0"


class SlackChannel(ChannelAdapter):
    """Slack adapter -- requires ``slack-sdk``.

    When the dependency is missing the adapter loads without error but all
    operations are no-ops.  Install the real dependency to enable it::

        pip install slack-sdk aiohttp

    Config:
        bot_token (str): Slack bot OAuth token (xoxb-...).
        signing_secret (str): Slack signing secret.
        app_token (str): Slack app-level token (xapp-...) for Socket Mode.
        files_dir (str): Directory for downloaded attachments.
        max_message_length (int): Max chars per message chunk (default 4000).
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._bot_token: str = config.get("bot_token", "")
        self._signing_secret: str = config.get("signing_secret", "")
        self._app_token: str = config.get("app_token", "")
        self._files_dir: Path = Path(config.get("files_dir", _DEFAULT_FILES_DIR))
        self._max_len: int = int(config.get("max_message_length", _DEFAULT_MAX_LEN))

        self._available: bool = _HAS_SLACK
        self._client: AsyncWebClient | None = None
        self._socket_handler: Any = None
        self._bot_user_id: str | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if not self._available:
            logger.warning(
                "Slack adapter '%s' requires slack-sdk -- "
                "install with: pip install slack-sdk aiohttp",
                self.name,
            )
            return

        if not self._bot_token:
            logger.error("Slack adapter '%s': bot_token is required", self.name)
            self._available = False
            return

        self._files_dir.mkdir(parents=True, exist_ok=True)
        self._client = _AsyncWebClient(token=self._bot_token)  # type: ignore[misc]

        # Resolve our own bot user-id so we can ignore self-messages.
        try:
            auth = await self._client.auth_test()  # type: ignore[union-attr]
            self._bot_user_id = auth.get("user_id")
            logger.info(
                "Slack adapter '%s' authenticated as user %s",
                self.name,
                self._bot_user_id,
            )
        except Exception:
            logger.exception("Slack adapter '%s': auth_test failed", self.name)
            self._available = False
            return

        # Socket Mode (preferred) vs HTTP fallback.
        if self._app_token:
            await self._start_socket_mode()
        else:
            logger.info(
                "Slack adapter '%s': no app_token -- using HTTP Events API "
                "mode.  Call handle_http_event() from your web server.",
                self.name,
            )

        self._running = True
        logger.info("Slack adapter '%s' started", self.name)

    async def stop(self) -> None:
        if not self._available:
            return
        if self._socket_handler is not None:
            try:
                await self._socket_handler.close_async()
            except Exception:
                logger.debug("Error closing socket handler", exc_info=True)
            self._socket_handler = None
        self._client = None
        self._running = False
        logger.info("Slack adapter '%s' stopped", self.name)

    # ------------------------------------------------------------------
    # Socket Mode
    # ------------------------------------------------------------------

    async def _start_socket_mode(self) -> None:
        """Connect via Socket Mode for real-time event delivery."""
        socket_client = _SocketModeClient(  # type: ignore[misc]
            app_token=self._app_token,
            web_client=self._client,
        )
        self._socket_handler = AsyncSocketModeHandler(  # type: ignore[misc]
            app=socket_client,
        )
        socket_client.socket_mode_request_listeners.append(self._on_socket_request)
        # start_async launches in the background and returns immediately.
        await self._socket_handler.start_async()
        logger.info("Slack adapter '%s': Socket Mode connected", self.name)

    async def _on_socket_request(
        self,
        client: SocketModeClient,
        req: SocketModeRequest,
    ) -> None:
        """Handle a single Socket Mode envelope."""
        # Always acknowledge immediately to prevent retries.
        response = SocketModeResponse(envelope_id=req.envelope_id)  # type: ignore[misc]
        await client.send_socket_mode_response(response)

        if req.type != "events_api":
            return

        event = (req.payload or {}).get("event", {})
        await self._process_event(event)

    # ------------------------------------------------------------------
    # HTTP Events API (fallback)
    # ------------------------------------------------------------------

    async def handle_http_event(
        self,
        body: bytes,
        timestamp: str,
        signature: str,
    ) -> dict[str, Any]:
        """Process an HTTP Events API request.

        Parameters:
            body: Raw request body bytes.
            timestamp: Value of ``X-Slack-Request-Timestamp`` header.
            signature: Value of ``X-Slack-Signature`` header.

        Returns a dict suitable for JSON response (may contain
        ``{"challenge": ...}`` for URL verification).
        """
        import json as _json

        if not self.verify_signature(body, timestamp, signature):
            return {"error": "invalid signature"}

        try:
            payload = _json.loads(body)
        except _json.JSONDecodeError:
            return {"error": "invalid JSON"}

        # URL verification handshake.
        if payload.get("type") == "url_verification":
            return {"challenge": payload["challenge"]}

        event = payload.get("event", {})
        if event:
            # Fire-and-forget so we respond to Slack within 3 s.
            asyncio.create_task(self._process_event(event))

        return {"ok": True}

    def verify_signature(self, body: bytes, timestamp: str, signature: str) -> bool:
        """Validate Slack request signature (HMAC-SHA256).

        See https://api.slack.com/authentication/verifying-requests-from-slack
        """
        if not self._signing_secret:
            return True  # no secret configured -- accept all

        # Reject requests older than 5 minutes (replay protection).
        try:
            if abs(time.time() - float(timestamp)) > 300:
                logger.warning("Slack signature timestamp too old")
                return False
        except (ValueError, TypeError):
            return False

        sig_basestring = f"{_SIGNATURE_VERSION}:{timestamp}:{body.decode('utf-8')}"
        computed = (
            f"{_SIGNATURE_VERSION}="
            + hmac.new(
                self._signing_secret.encode(),
                sig_basestring.encode(),
                hashlib.sha256,
            ).hexdigest()
        )
        return hmac.compare_digest(computed, signature)

    # ------------------------------------------------------------------
    # Shared event processing
    # ------------------------------------------------------------------

    async def _process_event(self, event: dict[str, Any]) -> None:
        """Normalize a Slack event and invoke the on_message callback."""
        if event.get("type") != "message":
            return

        # Skip bot messages, message_changed / message_deleted, etc.
        if event.get("subtype"):
            return

        # Skip messages from ourselves.
        user = event.get("user", "")
        if user == self._bot_user_id:
            return

        # DM-only: channel_type "im" indicates a direct message.
        if event.get("channel_type") != "im":
            return

        text = event.get("text", "")
        channel_id = event.get("channel", "")
        thread_ts = event.get("thread_ts") or event.get("ts", "")

        # Handle file attachments.
        attachments = await self._download_files(event.get("files", []))

        message = InboundMessage(
            channel=ChannelType.SLACK,
            channel_name=self.name,
            sender_id=user,
            sender_label=event.get("user_profile", {}).get("display_name", user),
            text=text,
            thread_id=thread_ts,
            attachments=attachments,
            raw={**event, "_channel_id": channel_id},
        )

        if self._on_message:
            try:
                response_text = await self._on_message(message)
                if response_text:
                    await self.send(
                        OutboundMessage(
                            channel=ChannelType.SLACK,
                            channel_name=self.name,
                            thread_id=thread_ts,
                            text=response_text,
                        )
                    )
            except Exception:
                logger.exception(
                    "Slack adapter '%s': error in message callback",
                    self.name,
                )

    # ------------------------------------------------------------------
    # File handling
    # ------------------------------------------------------------------

    async def _download_files(
        self, files: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Download Slack-hosted files and return attachment metadata."""
        if not files or not self._client:
            return []

        attachments: list[dict[str, Any]] = []
        for f in files:
            url = f.get("url_private_download") or f.get("url_private", "")
            if not url:
                continue
            filename = f.get("name", f.get("id", "unknown"))
            dest = self._files_dir / filename
            try:
                import aiohttp as _aiohttp

                headers = {"Authorization": f"Bearer {self._bot_token}"}
                async with _aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers) as resp:
                        if resp.status == 200:
                            dest.write_bytes(await resp.read())
                            attachments.append(
                                {
                                    "type": f.get("filetype", "file"),
                                    "filename": filename,
                                    "path": str(dest),
                                    "mimetype": f.get("mimetype", ""),
                                    "size": f.get("size", 0),
                                }
                            )
                            logger.debug("Downloaded %s -> %s", filename, dest)
                        else:
                            logger.warning(
                                "Failed to download %s: HTTP %s",
                                filename,
                                resp.status,
                            )
            except Exception:
                logger.exception("Error downloading file %s", filename)

        return attachments

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message (or multiple chunks) to a Slack channel/DM."""
        if not self._available or not self._client:
            logger.warning(
                "Slack adapter '%s' is not available -- cannot send message",
                self.name,
            )
            return False

        # Resolve target channel.  The _channel_id stashed during inbound
        # processing is the most reliable source; thread_id is the fallback.
        channel_id = (
            (
                message.raw.get("_channel_id", "")  # type: ignore[union-attr]
                if isinstance(getattr(message, "raw", None), dict)
                else ""
            )
            or message.thread_id
            or ""
        )

        if not channel_id:
            logger.error("Slack adapter '%s': no channel_id to send to", self.name)
            return False

        chunks = self._split_text(message.text, self._max_len)
        thread_ts = message.thread_id if message.thread_id else None

        try:
            for chunk in chunks:
                await self._client.chat_postMessage(
                    channel=channel_id,
                    text=chunk,
                    thread_ts=thread_ts,
                )

            # Upload file attachments via files_upload_v2.
            for att in message.attachments:
                filepath = att.get("path", "")
                if filepath and os.path.isfile(filepath):
                    await self._client.files_upload_v2(
                        channel=channel_id,
                        file=filepath,
                        filename=att.get("filename", os.path.basename(filepath)),
                        thread_ts=thread_ts,
                    )

            return True
        except Exception:
            logger.exception("Slack adapter '%s': failed to send message", self.name)
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _split_text(text: str, max_len: int) -> list[str]:
        """Split *text* into chunks of at most *max_len* characters.

        Tries to break on newlines first, then on spaces, and only
        hard-splits as a last resort.
        """
        if not text:
            return [""]
        if len(text) <= max_len:
            return [text]

        chunks: list[str] = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break

            # Try to find a newline break point.
            cut = text.rfind("\n", 0, max_len)
            if cut <= 0:
                # Try a space.
                cut = text.rfind(" ", 0, max_len)
            if cut <= 0:
                # Hard split.
                cut = max_len

            chunks.append(text[:cut])
            text = text[cut:].lstrip("\n")

        return chunks
