"""Main gateway daemon — orchestrates channels, auth, routing, and cron."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from .auth import PairingStore
from .channels.base import ChannelAdapter
from .channels.registry import discover_channels
from .cron import CronScheduler
from .files import extract_send_files, handle_long_response, resolve_files_dir
from .heartbeat import HeartbeatEngine
from .models import ChannelType, InboundMessage, OutboundMessage
from .router import SessionRouter
from .voice import VoiceMiddleware

logger = logging.getLogger(__name__)


def _load_config(config_path: str) -> dict[str, Any]:
    """Load YAML config, falling back to empty dict if missing."""
    path = Path(config_path).expanduser()
    if not path.exists():
        logger.warning("Config file not found: %s — using defaults", path)
        return {}
    try:
        import yaml  # optional dependency

        return yaml.safe_load(path.read_text()) or {}
    except ImportError:
        # Fall back to JSON if PyYAML is not installed
        return json.loads(path.read_text())


class GatewayDaemon:
    """Top-level gateway daemon that orchestrates all components."""

    def __init__(
        self,
        config_path: str = "~/.letsgo/gateway/config.yaml",
        config: dict[str, Any] | None = None,
    ) -> None:
        self._config: dict[str, Any] = (
            config if config is not None else _load_config(config_path)
        )
        self._files_dir = resolve_files_dir(self._config)
        self.auth = PairingStore(self._config.get("auth", {}))
        self.router = SessionRouter(
            session_factory=self._create_session,
        )
        self.heartbeat = HeartbeatEngine(
            agents_config=self._config.get("agents", {}),
            default_channels=self._config.get("heartbeat", {}).get(
                "default_channels", []
            ),
            response_router=self._route_heartbeat_response,
        )
        self.cron = CronScheduler(
            self._config.get("cron", {}),
            job_executor=self._execute_cron_job,
        )
        self.channels: dict[str, ChannelAdapter] = {}
        self._running = False

        # Voice middleware (optional)
        voice_config = self._config.get("voice", {})
        self.voice: VoiceMiddleware | None = (
            VoiceMiddleware(voice_config)
            if voice_config.get("enabled", False)
            else None
        )

        self._init_channels()

    # ---- session factory ----

    async def _create_session(self, session_id: str, payload: dict[str, Any]) -> str:
        """Create an Amplifier session for a user message.

        This is the injection point where the gateway connects
        to Amplifier's session mechanism. Currently uses a
        subprocess call to ``amplifier run`` as the bridge —
        when amplifier-core's Python API is available, this
        will use PreparedBundle.create_session() directly.
        """
        text = payload.get("text", "")
        sender_id = payload.get("sender_id", "unknown")
        channel = payload.get("channel", "unknown")

        try:
            proc = await asyncio.create_subprocess_exec(
                "amplifier",
                "run",
                "--non-interactive",
                "--json",
                (f"[Gateway message from {sender_id} via {channel}] {text}"),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode == 0 and stdout:
                try:
                    result = json.loads(stdout.decode())
                    return result.get("response", stdout.decode().strip())
                except json.JSONDecodeError:
                    return stdout.decode().strip()
            else:
                logger.warning(
                    "Amplifier session failed (rc=%d): %s",
                    proc.returncode,
                    stderr.decode()[:200],
                )
                return (
                    f"Session {session_id} received your"
                    " message but encountered an error"
                    " processing it."
                )
        except FileNotFoundError:
            logger.warning("amplifier CLI not found — using echo mode")
            return f"Session {session_id} received: {text}"
        except asyncio.TimeoutError:
            logger.warning("Amplifier session timed out after 120s")
            return "I'm still processing your request. Please try again in a moment."

    # ---- cron job executor ----

    async def _execute_cron_job(
        self,
        recipe_path: str,
        context: dict[str, Any],
        automation_profile: dict[str, Any],
    ) -> dict[str, Any]:
        """Route cron jobs to the appropriate executor."""
        if recipe_path == "__heartbeat__":
            results = await self.heartbeat.run_all()
            failed = [r for r in results if r["status"] == "error"]
            return {
                "status": "failed" if failed else "completed",
                "results": results,
            }

        # Regular recipe jobs — execute via amplifier CLI
        try:
            proc = await asyncio.create_subprocess_exec(
                "amplifier",
                "tool",
                "invoke",
                "recipes",
                "operation=execute",
                f"recipe_path={recipe_path}",
                f"context={json.dumps(context)}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            if proc.returncode == 0:
                return {
                    "status": "completed",
                    "output": stdout.decode()[:1000],
                }
            else:
                return {
                    "status": "failed",
                    "error": stderr.decode()[:500],
                }
        except FileNotFoundError:
            logger.warning("amplifier CLI not found — recipe execution unavailable")
            return {
                "status": "skipped",
                "reason": "amplifier CLI not available",
            }
        except asyncio.TimeoutError:
            return {
                "status": "failed",
                "error": "recipe execution timed out (300s)",
            }

    # ---- channel init ----

    def _init_channels(self) -> None:
        """Instantiate channel adapters from config using the registry."""
        available = discover_channels()
        channels_cfg: dict[str, Any] = self._config.get("channels", {})
        for name, ch_cfg in channels_cfg.items():
            ch_type = ch_cfg.get("type", name)
            cls = available.get(ch_type)
            if cls is None:
                logger.warning(
                    "Unknown channel type '%s' — not built-in and no plugin found",
                    ch_type,
                )
                continue

            adapter = cls(name=name, config=ch_cfg)
            adapter.set_on_message(self._on_message)
            self.channels[name] = adapter

    # ---- lifecycle ----

    async def start(self) -> None:
        """Start all components."""
        logger.info("Starting GatewayDaemon")

        # First-run detection
        if not self._config.get("channels"):
            logger.info(
                "No channels configured — run the setup-wizard recipe to get started"
            )

        for name, adapter in self.channels.items():
            try:
                await adapter.start()
                logger.info("Channel '%s' started", name)
            except NotImplementedError as exc:
                logger.warning(
                    "Channel '%s' not available: %s",
                    name,
                    exc,
                )
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
        """Core message handler — auth -> pairing -> route -> respond."""
        sender_id = message.sender_id
        channel = message.channel

        # 1. Check auth
        # BLAST GUARD: reject sends to any non-personal recipient
        _blocked_patterns = ("broadcast", "status", "@g.us", "@newsletter")
        if any(b in sender_id.lower() for b in _blocked_patterns):
            logger.error(
                "BLAST BLOCKED in daemon: refusing to process message "
                "from broadcast/group sender '%s'", sender_id
            )
            return

        if not self.auth.is_approved(sender_id, channel):
            return await self._handle_pairing(message)

        # 2. Rate limit
        if not self.auth.check_rate_limit(sender_id, channel):
            return (
                "Rate limit exceeded. Please wait a moment"
                " before sending another message."
            )

        # 2b. Voice transcription (before routing to session)
        if self.voice is not None:
            message = await self.voice.process_inbound(message)

        # 3. Route to session (await — it's async)
        response = await self.router.route_message(message)

        # 4. Process file exchange on outbound
        response, send_files = extract_send_files(response)
        response, long_file = handle_long_response(response, self._files_dir)

        # 4b. Voice TTS (optional — after session responds)
        if self.voice is not None:
            response, voice_files = await self.voice.process_outbound(
                response, message, self._files_dir
            )
            send_files.extend(voice_files)

        if long_file:
            send_files.append(long_file)

        # 5. If there are files, send via adapter for
        #    attachment support (fire-and-forget)
        if send_files:
            await self._send_response_with_files(message, response, send_files)

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
        return (
            f"Welcome! Your pairing code is: {code}."
            " Please reply with this code to connect."
        )

    async def _send_response(self, message: InboundMessage, text: str) -> None:
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

    async def _send_response_with_files(
        self,
        message: InboundMessage,
        text: str,
        files: list[Path],
    ) -> None:
        """Send a response with file attachments."""
        channel_name = message.channel_name
        adapter = self.channels.get(channel_name)
        if not adapter:
            logger.warning("No adapter for channel '%s'", channel_name)
            return

        attachments = [{"type": "file", "path": str(f)} for f in files]
        outbound = OutboundMessage(
            channel=message.channel,
            channel_name=channel_name,
            thread_id=message.thread_id,
            text=text,
            attachments=attachments,
        )
        await adapter.send(outbound)

    # ---- proactive outbound ----

    async def send_to_channel(
        self,
        channel_name: str,
        sender_id: str,
        text: str,
    ) -> bool:
        """Send a proactive message to a user via a channel."""
        adapter = self.channels.get(channel_name)
        if not adapter:
            logger.warning("No adapter for channel '%s'", channel_name)
            return False

        # Resolve channel type from adapter
        ch_type = ChannelType.WEBHOOK
        for ct in ChannelType:
            if ct.value == adapter.config.get("type", ""):
                ch_type = ct
                break

        outbound = OutboundMessage(
            channel=ch_type,
            channel_name=channel_name,
            thread_id=sender_id,
            text=text,
        )
        try:
            await adapter.send(outbound)
            return True
        except Exception:
            logger.exception(
                "Failed to send proactive message to %s via %s",
                sender_id,
                channel_name,
            )
            return False

    async def _route_heartbeat_response(
        self,
        agent_id: str,
        response: str,
        channels: list[str],
    ) -> None:
        """Route a heartbeat response to designated channels."""
        for ch_name in channels:
            await self.send_to_channel(ch_name, agent_id, response)
