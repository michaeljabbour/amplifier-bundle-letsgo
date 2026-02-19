"""Main gateway daemon — orchestrates channels, auth, routing, and cron."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .auth import PairingStore
from .channels.base import ChannelAdapter
from .channels.webhook import WebhookChannel
from .channels.whatsapp import WhatsAppChannel
from .cron import CronScheduler
from .models import ChannelType, InboundMessage, OutboundMessage
from .heartbeat import HeartbeatEngine
from .router import SessionRouter

logger = logging.getLogger(__name__)

# Channel type -> adapter class mapping
_CHANNEL_CLASSES: dict[str, type[ChannelAdapter]] = {
    "webhook": WebhookChannel,
    "whatsapp": WhatsAppChannel,
}

# Lazy imports for stub channels to avoid requiring their deps at import time
_STUB_CHANNELS = {"telegram", "discord", "slack"}


def _load_config(config_path: str) -> dict[str, Any]:
    """Load YAML config, falling back to empty dict if file is missing."""
    path = Path(config_path).expanduser()
    if not path.exists():
        logger.warning("Config file not found: %s — using defaults", path)
        return {}
    try:
        import yaml  # optional dependency

        return yaml.safe_load(path.read_text()) or {}
    except ImportError:
        # Fall back to JSON if PyYAML is not installed
        import json

        return json.loads(path.read_text())


class GatewayDaemon:
    """Top-level gateway daemon that orchestrates all components."""

    def __init__(
        self,
        config_path: str = "~/.letsgo/gateway/config.yaml",
        config: dict[str, Any] | None = None,
    ) -> None:
        self._config: dict[str, Any] = config if config is not None else _load_config(config_path)
        self.auth = PairingStore(self._config.get("auth", {}))
        self.router = SessionRouter()
        self.heartbeat = HeartbeatEngine(
            agents_config=self._config.get("agents", {}),
            default_channels=self._config.get("heartbeat", {}).get("default_channels", []),
        )
        self.cron = CronScheduler(
            self._config.get("cron", {}),
            job_executor=self._execute_cron_job,
        )
        self.channels: dict[str, ChannelAdapter] = {}
        self._running = False

        self._init_channels()

    async def _execute_cron_job(
        self, recipe_path: str, context: dict, automation_profile: dict
    ) -> dict[str, Any]:
        """Route cron jobs to the appropriate executor."""
        if recipe_path == "__heartbeat__":
            results = await self.heartbeat.run_all()
            failed = [r for r in results if r["status"] == "error"]
            return {
                "status": "failed" if failed else "completed",
                "results": results,
            }

        # Regular recipe jobs — stub for future wiring
        logger.info(
            "Recipe job '%s' triggered (recipe runner not yet wired)", recipe_path
        )
        return {"status": "completed", "note": "recipe runner not yet wired"}

    def _init_channels(self) -> None:
        """Instantiate channel adapters from config."""
        channels_cfg: dict[str, Any] = self._config.get("channels", {})
        for name, ch_cfg in channels_cfg.items():
            ch_type = ch_cfg.get("type", name)
            if ch_type in _STUB_CHANNELS:
                # Import lazily
                from .channels.telegram import TelegramChannel
                from .channels.discord import DiscordChannel
                from .channels.slack import SlackChannel

                stub_map: dict[str, type[ChannelAdapter]] = {
                    "telegram": TelegramChannel,
                    "discord": DiscordChannel,
                    "slack": SlackChannel,
                }
                cls = stub_map[ch_type]
            elif ch_type in _CHANNEL_CLASSES:
                cls = _CHANNEL_CLASSES[ch_type]
            else:
                logger.warning("Unknown channel type: %s", ch_type)
                continue

            adapter = cls(name=name, config=ch_cfg)
            adapter.set_on_message(self._on_message)
            self.channels[name] = adapter

    # ---- lifecycle ----

    async def start(self) -> None:
        """Start all components."""
        logger.info("Starting GatewayDaemon")
        for name, adapter in self.channels.items():
            try:
                await adapter.start()
                logger.info("Channel '%s' started", name)
            except NotImplementedError as exc:
                logger.warning("Channel '%s' not available: %s", name, exc)
            except Exception:
                logger.exception("Failed to start channel '%s'", name)

        await self.cron.start()
        self._running = True
        logger.info("GatewayDaemon started")

    async def stop(self) -> None:
        """Gracefully shut down all components."""
        logger.info("Stopping GatewayDaemon")
        self._running = False

        for name, adapter in self.channels.items():
            try:
                await adapter.stop()
            except NotImplementedError:
                pass
            except Exception:
                logger.exception("Error stopping channel '%s'", name)

        await self.cron.stop()

        # Close stale sessions
        self.router.close_stale_sessions(0)
        logger.info("GatewayDaemon stopped")

    # ---- message handling ----

    async def _on_message(self, message: InboundMessage) -> str:
        """Core message handler — auth → pairing → route → respond."""
        sender_id = message.sender_id
        channel = message.channel

        # 1. Check auth
        if not self.auth.is_approved(sender_id, channel):
            return await self._handle_pairing(message)

        # 2. Rate limit
        if not self.auth.check_rate_limit(sender_id, channel):
            return "Rate limit exceeded. Please wait a moment before sending another message."

        # 3. Route to session
        response = self.router.route_message(message)

        return response

    async def _handle_pairing(self, message: InboundMessage) -> str:
        """Handle pairing flow for unapproved senders."""
        sender_id = message.sender_id
        channel = message.channel

        # Check if sender is blocked
        key = self.auth._key(sender_id, channel)
        rec = self.auth._senders.get(key)
        if rec and rec.status.value == "blocked":
            return "Your access has been blocked."

        # Check if text matches a pending pairing code
        if self.auth.has_pending_pairing(sender_id, channel):
            code = message.text.strip().upper()
            if self.auth.verify_pairing(sender_id, channel, code):
                return "Pairing successful! You are now connected."
            return "Invalid or expired code. Please try again or request a new code."

        # No pending pairing — create one
        code = self.auth.request_pairing(
            sender_id=sender_id,
            channel=channel,
            channel_name=message.channel_name,
            sender_label=message.sender_label,
        )
        return f"Welcome! Your pairing code is: {code}. Please reply with this code to connect."

    async def _send_response(
        self, message: InboundMessage, text: str
    ) -> None:
        """Send a response back via the appropriate channel adapter."""
        channel_name = message.channel_name
        adapter = self.channels.get(channel_name)
        if not adapter:
            logger.warning("No adapter for channel '%s'", channel_name)
            return

        outbound = OutboundMessage(
            channel=message.channel,
            channel_name=channel_name,
            thread_id=message.thread_id,
            text=text,
        )
        await adapter.send(outbound)
