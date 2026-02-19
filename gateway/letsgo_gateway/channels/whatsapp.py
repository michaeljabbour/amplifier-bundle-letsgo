"""WhatsApp Cloud API channel adapter.

Uses the Meta Graph API for sending messages and an aiohttp webhook
server for receiving inbound messages.

Config keys:
    phone_number_id: Meta phone number ID (required)
    access_token: Meta access token (required)
    verify_token: Webhook verification token (required)
    app_secret: For X-Hub-Signature-256 verification (optional)
    webhook_path: Path for webhook endpoint (default ``"/whatsapp"``)
    api_version: Graph API version (default ``"v21.0"``)
    host: Bind address (default ``"0.0.0.0"``)
    port: Bind port (default ``8081``)
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from typing import Any

from ..models import ChannelType, InboundMessage, OutboundMessage
from .base import ChannelAdapter

logger = logging.getLogger(__name__)

try:
    import aiohttp
    from aiohttp import web

    _HAS_AIOHTTP = True
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore[assignment]
    web = None  # type: ignore[assignment]
    _HAS_AIOHTTP = False

_GRAPH_API_BASE = "https://graph.facebook.com"
_MAX_TEXT_LENGTH = 4096


class WhatsAppChannel(ChannelAdapter):
    """WhatsApp Cloud API adapter.

    Requires ``aiohttp`` (a core gateway dependency).  If the import
    somehow fails the adapter loads without error but all operations
    are no-ops.

    Config:
        phone_number_id (str): Meta phone number ID.
        access_token (str): Meta access token.
        verify_token (str): Webhook verification token.
        app_secret (str | None): Optional app secret for signature verification.
        webhook_path (str): Webhook URL path (default ``"/whatsapp"``).
        api_version (str): Graph API version (default ``"v21.0"``).
        host (str): Bind address (default ``"0.0.0.0"``).
        port (int): Bind port (default ``8081``).
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._phone_number_id: str = config.get("phone_number_id", "")
        self._access_token: str = config.get("access_token", "")
        self._verify_token: str = config.get("verify_token", "")
        self._app_secret: str | None = config.get("app_secret")
        self._webhook_path: str = config.get("webhook_path", "/whatsapp")
        self._api_version: str = config.get("api_version", "v21.0")
        self._host: str = config.get("host", "0.0.0.0")
        self._port: int = int(config.get("port", 8081))

        self._available: bool = _HAS_AIOHTTP
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._http_session: aiohttp.ClientSession | None = None
        self._pending_tasks: set[asyncio.Task[None]] = set()

    # ---- lifecycle ----

    async def start(self) -> None:
        if not self._available:
            logger.warning(
                "WhatsApp adapter '%s' requires aiohttp — "
                "install with: pip install aiohttp",
                self.name,
            )
            return

        self._app = web.Application()
        self._app.router.add_get(self._webhook_path, self._handle_verify)
        self._app.router.add_post(self._webhook_path, self._handle_webhook)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()

        self._http_session = aiohttp.ClientSession()
        self._running = True
        logger.info(
            "WhatsAppChannel '%s' listening on %s:%s%s",
            self.name,
            self._host,
            self._port,
            self._webhook_path,
        )

    async def stop(self) -> None:
        if not self._available:
            return

        # Cancel pending background tasks
        for task in self._pending_tasks:
            task.cancel()
        if self._pending_tasks:
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)
        self._pending_tasks.clear()

        if self._http_session:
            await self._http_session.close()
            self._http_session = None

        if self._runner:
            await self._runner.cleanup()
            self._runner = None

        self._running = False
        logger.info("WhatsAppChannel '%s' stopped", self.name)

    # ---- inbound: webhook verification ----

    async def _handle_verify(self, request: web.Request) -> web.Response:
        """Handle GET webhook verification from Meta."""
        mode = request.query.get("hub.mode", "")
        token = request.query.get("hub.verify_token", "")
        challenge = request.query.get("hub.challenge", "")

        if mode == "subscribe" and token == self._verify_token:
            logger.info("WhatsApp webhook verified for '%s'", self.name)
            return web.Response(text=challenge, content_type="text/plain")

        logger.warning(
            "WhatsApp webhook verification failed for '%s' "
            "(mode=%s, token_match=%s)",
            self.name,
            mode,
            token == self._verify_token,
        )
        return web.Response(status=403, text="Verification failed")

    # ---- inbound: message webhook ----

    def _verify_payload_signature(self, body: bytes, signature: str) -> bool:
        """Validate X-Hub-Signature-256 header."""
        if not self._app_secret:
            return True
        expected = hmac.new(
            self._app_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)

    async def _handle_webhook(self, request: web.Request) -> web.Response:
        """Handle POST inbound messages from WhatsApp Cloud API.

        Returns 200 immediately and processes messages as background tasks.
        """
        body = await request.read()

        # Signature check
        if self._app_secret:
            sig = request.headers.get("X-Hub-Signature-256", "")
            if not self._verify_payload_signature(body, sig):
                return web.Response(status=403, text="Invalid signature")

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return web.Response(status=400, text="Invalid JSON")

        # Extract messages and process in the background
        messages = self._extract_messages(data)
        for msg in messages:
            task = asyncio.create_task(self._process_inbound(msg))
            self._pending_tasks.add(task)
            task.add_done_callback(self._pending_tasks.discard)

        # Must respond within 5 seconds
        return web.Response(status=200, text="OK")

    def _extract_messages(self, data: dict[str, Any]) -> list[InboundMessage]:
        """Parse WhatsApp Cloud API payload into InboundMessages."""
        messages: list[InboundMessage] = []

        if data.get("object") != "whatsapp_business_account":
            return messages

        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                contacts = {
                    c.get("wa_id", ""): c.get("profile", {}).get("name", "")
                    for c in value.get("contacts", [])
                }
                for msg in value.get("messages", []):
                    sender_id = msg.get("from", "")
                    sender_label = contacts.get(sender_id, "")
                    msg_type = msg.get("type", "text")

                    text = ""
                    attachments: list[dict[str, Any]] = []

                    if msg_type == "text":
                        text = msg.get("text", {}).get("body", "")
                    elif msg_type in ("image", "document", "audio", "video"):
                        media_info = msg.get(msg_type, {})
                        attachments.append({
                            "type": msg_type,
                            "media_id": media_info.get("id", ""),
                            "mime_type": media_info.get("mime_type", ""),
                            "caption": media_info.get("caption", ""),
                        })
                        text = media_info.get("caption", "")

                    messages.append(InboundMessage(
                        channel=ChannelType.WHATSAPP,
                        channel_name=self.name,
                        sender_id=sender_id,
                        sender_label=sender_label,
                        text=text,
                        thread_id=sender_id,
                        attachments=attachments,
                        raw=msg,
                    ))

        return messages

    async def _process_inbound(self, message: InboundMessage) -> None:
        """Process a single inbound message via the registered callback."""
        if not self._on_message:
            return
        try:
            response_text = await self._on_message(message)
            if response_text:
                outbound = OutboundMessage(
                    channel=ChannelType.WHATSAPP,
                    channel_name=self.name,
                    thread_id=message.thread_id,
                    text=response_text,
                )
                await self.send(outbound)
        except Exception:
            logger.exception(
                "Error processing WhatsApp message from '%s'",
                message.sender_id,
            )

    # ---- outbound ----

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message via WhatsApp Cloud API."""
        if not self._available:
            logger.warning(
                "WhatsApp adapter '%s' is not available — "
                "cannot send message (aiohttp not installed)",
                self.name,
            )
            return False

        if not self._http_session:
            self._http_session = aiohttp.ClientSession()

        thread_id = message.thread_id or ""
        success = True

        # Send attachments first
        for att in message.attachments:
            media_type = att.get("type", "document")
            url = att.get("url", "")
            if url and media_type in ("image", "document", "audio", "video"):
                if not await self._send_media(thread_id, media_type, url):
                    success = False

        # Send text (split if too long)
        if message.text:
            for chunk in self._split_text(message.text):
                if not await self._send_message(thread_id, chunk):
                    success = False

        return success

    async def _send_message(self, to: str, text: str) -> bool:
        """POST a text message to the WhatsApp Graph API."""
        url = (
            f"{_GRAPH_API_BASE}/{self._api_version}"
            f"/{self._phone_number_id}/messages"
        )
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }
        try:
            async with self._http_session.post(
                url, headers=headers, json=payload
            ) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    logger.error(
                        "WhatsApp API error %s: %s", resp.status, body
                    )
                    return False
                return True
        except aiohttp.ClientError:
            logger.exception("Failed to send WhatsApp message")
            return False

    async def _send_media(
        self, to: str, media_type: str, media_url: str
    ) -> bool:
        """Send a media message via the WhatsApp Graph API."""
        url = (
            f"{_GRAPH_API_BASE}/{self._api_version}"
            f"/{self._phone_number_id}/messages"
        )
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": media_type,
            media_type: {"link": media_url},
        }
        try:
            async with self._http_session.post(
                url, headers=headers, json=payload
            ) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    logger.error(
                        "WhatsApp media send error %s: %s", resp.status, body
                    )
                    return False
                return True
        except aiohttp.ClientError:
            logger.exception("Failed to send WhatsApp media")
            return False

    async def _download_media(self, media_id: str) -> bytes | None:
        """Download media content from WhatsApp via the Graph API.

        Two-step process:
        1. GET media metadata to obtain the download URL.
        2. GET the download URL for the actual file bytes.
        """
        if not self._http_session:
            return None

        headers = {"Authorization": f"Bearer {self._access_token}"}

        # Step 1: Get the download URL
        meta_url = f"{_GRAPH_API_BASE}/{self._api_version}/{media_id}"
        try:
            async with self._http_session.get(
                meta_url, headers=headers
            ) as resp:
                if resp.status >= 400:
                    logger.error(
                        "Failed to get media URL for %s", media_id
                    )
                    return None
                meta = await resp.json()
                download_url = meta.get("url")
                if not download_url:
                    return None
        except aiohttp.ClientError:
            logger.exception(
                "Failed to fetch media metadata for %s", media_id
            )
            return None

        # Step 2: Download the actual file
        try:
            async with self._http_session.get(
                download_url, headers=headers
            ) as resp:
                if resp.status >= 400:
                    logger.error("Failed to download media %s", media_id)
                    return None
                return await resp.read()
        except aiohttp.ClientError:
            logger.exception("Failed to download media %s", media_id)
            return None

    # ---- helpers ----

    @staticmethod
    def _split_text(text: str) -> list[str]:
        """Split text into chunks of at most 4096 characters.

        Prefers splitting at paragraph boundaries (double newline), then
        sentence boundaries, falling back to a hard split.
        """
        if len(text) <= _MAX_TEXT_LENGTH:
            return [text]

        chunks: list[str] = []
        remaining = text

        while len(remaining) > _MAX_TEXT_LENGTH:
            # Try paragraph boundary
            split_at = remaining.rfind("\n\n", 0, _MAX_TEXT_LENGTH)
            if split_at > 0:
                chunks.append(remaining[:split_at])
                remaining = remaining[split_at + 2:]
                continue

            # Try sentence boundary
            for sep in (". ", "! ", "? ", ".\n"):
                split_at = remaining.rfind(sep, 0, _MAX_TEXT_LENGTH)
                if split_at > 0:
                    # Include the punctuation mark, skip the separator
                    chunks.append(remaining[: split_at + 1])
                    remaining = remaining[split_at + 1 :].lstrip()
                    break
            else:
                # Hard split
                chunks.append(remaining[:_MAX_TEXT_LENGTH])
                remaining = remaining[_MAX_TEXT_LENGTH:]

        if remaining:
            chunks.append(remaining)

        return chunks
