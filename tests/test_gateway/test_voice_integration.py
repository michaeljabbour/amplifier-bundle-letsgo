"""Integration tests for the full voice pipeline through the gateway daemon."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from letsgo_gateway.daemon import GatewayDaemon
from letsgo_gateway.models import ChannelType, InboundMessage
from letsgo_gateway.voice import VoiceMiddleware

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_daemon(tmp_path: Path, **config_overrides) -> GatewayDaemon:
    config = {
        "auth": {
            "pairing_db_path": str(tmp_path / "pairing.json"),
            "max_messages_per_minute": 60,
            "code_ttl_seconds": 300,
        },
        "channels": {},
        "cron": {
            "log_path": str(tmp_path / "cron.jsonl"),
        },
        "files_dir": str(tmp_path / "files"),
        **config_overrides,
    }
    return GatewayDaemon(config=config)


def _make_message(
    sender_id: str = "user1",
    text: str = "hello",
    channel: ChannelType = ChannelType.WEBHOOK,
    channel_name: str = "main",
    attachments: list[dict[str, Any]] | None = None,
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        channel_name=channel_name,
        sender_id=sender_id,
        sender_label=sender_id,
        text=text,
        attachments=attachments or [],
    )


def _make_audio_file(tmp_path: Path, name: str = "voice.ogg") -> Path:
    audio = tmp_path / name
    audio.write_bytes(b"\x00" * 100)
    return audio


def _approve_sender(daemon: GatewayDaemon, sender_id: str) -> None:
    """Pre-approve a sender for testing."""
    code = daemon.auth.request_pairing(
        sender_id, ChannelType.WEBHOOK, "main", sender_id
    )
    daemon.auth.verify_pairing(sender_id, ChannelType.WEBHOOK, code)


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestVoicePipelineInboundIntegration:
    """End-to-end: audio attachment -> transcription -> message with text."""

    @pytest.mark.asyncio
    async def test_audio_message_gets_transcription(self, tmp_path: Path) -> None:
        """Audio attachment -> VoiceMiddleware transcribes -> text."""
        audio = _make_audio_file(tmp_path)

        mock_provider = AsyncMock()
        mock_provider.transcribe = AsyncMock(return_value="hello from voice message")

        middleware = VoiceMiddleware(
            config={"enabled": True, "transcription": {"provider": "whisper-api"}}
        )

        with patch.object(middleware, "_transcription", mock_provider):
            msg = _make_message(
                text=f"[file: {audio}]",
                attachments=[{"type": "file", "path": str(audio)}],
            )
            result = await middleware.process_inbound(msg)

        assert (
            '[Voice message transcription: "hello from voice message"]' in result.text
        )
        assert f"[file: {audio}]" in result.text

    @pytest.mark.asyncio
    async def test_mixed_audio_and_text(self, tmp_path: Path) -> None:
        """Audio file alongside regular text gets transcription prepended."""
        audio = _make_audio_file(tmp_path)

        mock_provider = AsyncMock()
        mock_provider.transcribe = AsyncMock(return_value="voice part")

        middleware = VoiceMiddleware(
            config={"enabled": True, "transcription": {"provider": "whisper-api"}}
        )

        with patch.object(middleware, "_transcription", mock_provider):
            msg = _make_message(
                text=f"also some text [file: {audio}]",
                attachments=[{"type": "file", "path": str(audio)}],
            )
            result = await middleware.process_inbound(msg)

        assert '[Voice message transcription: "voice part"]' in result.text
        assert "also some text" in result.text


class TestVoicePipelineOutboundIntegration:
    """End-to-end: session response -> TTS synthesis -> audio file in outbound."""

    @pytest.mark.asyncio
    async def test_tts_produces_audio_file(self, tmp_path: Path) -> None:
        """Full flow: response text -> VoiceMiddleware synthesizes -> audio file."""
        files_dir = tmp_path / "files"
        msg = _make_message()

        mock_provider = AsyncMock()
        mock_provider.synthesize = AsyncMock(return_value=None)

        middleware = VoiceMiddleware(
            config={"enabled": True, "tts": {"enabled": True, "provider": "edge-tts"}}
        )

        with patch.object(middleware, "_tts", mock_provider):
            text, files = await middleware.process_outbound(
                "Agent response text", msg, files_dir
            )

        assert text == "Agent response text"
        assert len(files) == 1
        assert files[0].name == "tts_response.mp3"


class TestDaemonVoiceIntegration:
    """Daemon._on_message with voice middleware active/inactive."""

    def test_daemon_creates_voice_middleware_when_configured(
        self, tmp_path: Path
    ) -> None:
        daemon = _make_daemon(
            tmp_path,
            voice={"enabled": True, "transcription": {"provider": "whisper-api"}},
        )
        assert daemon.voice is not None
        assert isinstance(daemon.voice, VoiceMiddleware)

    def test_daemon_no_voice_middleware_by_default(self, tmp_path: Path) -> None:
        daemon = _make_daemon(tmp_path)
        assert daemon.voice is None

    def test_daemon_no_voice_middleware_when_disabled(self, tmp_path: Path) -> None:
        daemon = _make_daemon(tmp_path, voice={"enabled": False})
        assert daemon.voice is None

    @pytest.mark.asyncio
    async def test_on_message_with_voice_middleware(self, tmp_path: Path) -> None:
        """When voice middleware is active, _on_message calls process_inbound."""
        daemon = _make_daemon(
            tmp_path,
            voice={"enabled": True, "transcription": {"provider": "whisper-api"}},
        )
        _approve_sender(daemon, "user1")

        # Mock the voice middleware's process_inbound
        mock_inbound = AsyncMock(side_effect=lambda msg: msg)
        daemon.voice.process_inbound = mock_inbound  # type: ignore[union-attr]

        # Mock process_outbound to return passthrough
        mock_outbound = AsyncMock(return_value=("response", []))
        daemon.voice.process_outbound = mock_outbound  # type: ignore[union-attr]

        msg = _make_message(sender_id="user1", text="test voice")
        await daemon._on_message(msg)

        mock_inbound.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_on_message_without_voice_passthrough(self, tmp_path: Path) -> None:
        """When voice middleware is None, _on_message works normally."""
        daemon = _make_daemon(tmp_path)
        assert daemon.voice is None

        _approve_sender(daemon, "user1")
        msg = _make_message(sender_id="user1", text="test no voice")

        # Should not raise -- voice middleware is None, skipped
        response = await daemon._on_message(msg)
        assert isinstance(response, str)
