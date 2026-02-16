"""Webhook channel adapter using aiohttp."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

import aiohttp
from aiohttp import web

from ..models import ChannelType, InboundMessage, OutboundMessage
from .base import ChannelAdapter

logger = logging.getLogger(__name__)


class WebhookChannel(ChannelAdapter):
    """HTTP webhook adapter.

    Config keys:
        host: Bind address (default ``"127.0.0.1"``)
        port: Bind port (default ``8080``)
        shared_secret: Optional HMAC secret for signature validation
        response_url: Optional URL to POST responses to
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._host: str = config.get("host", "127.0.0.1")
        self._port: int = int(config.get("port", 8080))
        self._shared_secret: str | None = config.get("shared_secret")
        self._response_url: str | None = config.get("response_url")
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._http_session: aiohttp.ClientSession | None = None

    # ---- lifecycle ----

    async def start(self) -> None:
        self._app = web.Application()
        self._app.router.add_post("/webhook/{channel_name}", self._handle_post)
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        self._running = True
        logger.info(
            "WebhookChannel '%s' listening on %s:%s",
            self.name, self._host, self._port,
        )

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
        if self._http_session:
            await self._http_session.close()
        self._running = False

    # ---- inbound ----

    def verify_signature(self, body: bytes, signature: str) -> bool:
        """Validate HMAC-SHA256 signature."""
        if not self._shared_secret:
            return True
        expected = hmac.new(
            self._shared_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    @staticmethod
    def normalize_message(
        channel_name: str, data: dict[str, Any]
    ) -> InboundMessage:
        """Convert raw webhook JSON into an InboundMessage."""
        return InboundMessage(
            channel=ChannelType.WEBHOOK,
            channel_name=channel_name,
            sender_id=str(data.get("sender_id", "unknown")),
            sender_label=str(data.get("sender_label", "")),
            text=str(data.get("text", "")),
            thread_id=data.get("thread_id"),
            attachments=data.get("attachments", []),
            raw=data,
        )

    async def _handle_post(self, request: web.Request) -> web.Response:
        channel_name = request.match_info["channel_name"]
        body = await request.read()

        # Signature check
        if self._shared_secret:
            sig = request.headers.get("X-Signature", "")
            if not self.verify_signature(body, sig):
                return web.json_response(
                    {"error": "invalid signature"}, status=401
                )

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return web.json_response(
                {"error": "invalid JSON"}, status=400
            )

        message = self.normalize_message(channel_name, data)

        if self._on_message:
            response_text = await self._on_message(message)
            return web.json_response({"response": response_text})

        return web.json_response({"status": "received"})

    # ---- outbound ----

    async def send(self, message: OutboundMessage) -> bool:
        """POST a response to the configured response_url."""
        if not self._response_url:
            logger.warning("No response_url configured for WebhookChannel '%s'", self.name)
            return False

        if not self._http_session:
            self._http_session = aiohttp.ClientSession()

        payload = {
            "channel_name": message.channel_name,
            "thread_id": message.thread_id,
            "text": message.text,
            "attachments": message.attachments,
        }
        try:
            async with self._http_session.post(
                self._response_url, json=payload
            ) as resp:
                return resp.status < 400
        except aiohttp.ClientError:
            logger.exception("Failed to send via webhook")
            return False
