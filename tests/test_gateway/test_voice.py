"""Tests for gateway voice middleware -- inbound transcription."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from letsgo_gateway.models import ChannelType, InboundMessage
from letsgo_gateway.voice import (
    AUDIO_EXTENSIONS,
    VoiceMiddleware,
    detect_audio_attachments,
    transcribe_voice_messages,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_message(
    text: str = "hello",
    attachments: list[dict[str, Any]] | None = None,
) -> InboundMessage:
    return InboundMessage(
        channel=ChannelType.TELEGRAM,
        channel_name="test-tg",
        sender_id="user1",
        sender_label="User One",
        text=text,
        attachments=attachments or [],
    )


def _make_audio_file(tmp_path: Path, name: str = "voice.ogg") -> Path:
    audio = tmp_path / name
    audio.write_bytes(b"\x00" * 100)
    return audio


# ---------------------------------------------------------------------------
# detect_audio_attachments
# ---------------------------------------------------------------------------


class TestDetectAudioAttachments:
    """detect_audio_attachments finds audio files in attachments."""

    def test_finds_ogg_attachment(self, tmp_path: Path) -> None:
        audio = _make_audio_file(tmp_path, "voice.ogg")
        msg = _make_message(attachments=[{"type": "file", "path": str(audio)}])
        paths = detect_audio_attachments(msg)
        assert paths == [str(audio)]

    def test_finds_mp3_attachment(self, tmp_path: Path) -> None:
        audio = _make_audio_file(tmp_path, "song.mp3")
        msg = _make_message(attachments=[{"type": "file", "path": str(audio)}])
        paths = detect_audio_attachments(msg)
        assert paths == [str(audio)]

    def test_finds_multiple_audio_files(self, tmp_path: Path) -> None:
        a1 = _make_audio_file(tmp_path, "voice.ogg")
        a2 = _make_audio_file(tmp_path, "note.wav")
        msg = _make_message(
            attachments=[
                {"type": "file", "path": str(a1)},
                {"type": "file", "path": str(a2)},
            ]
        )
        paths = detect_audio_attachments(msg)
        assert len(paths) == 2

    def test_ignores_non_audio_files(self, tmp_path: Path) -> None:
        doc = tmp_path / "readme.txt"
        doc.write_text("hello")
        msg = _make_message(attachments=[{"type": "file", "path": str(doc)}])
        paths = detect_audio_attachments(msg)
        assert paths == []

    def test_ignores_missing_path_key(self) -> None:
        msg = _make_message(attachments=[{"type": "file"}])
        paths = detect_audio_attachments(msg)
        assert paths == []

    def test_empty_attachments(self) -> None:
        msg = _make_message(attachments=[])
        paths = detect_audio_attachments(msg)
        assert paths == []

    def test_audio_extensions_constant(self) -> None:
        """Ensure AUDIO_EXTENSIONS covers the expected formats."""
        for ext in (".ogg", ".mp3", ".wav", ".m4a", ".opus", ".flac", ".webm"):
            assert ext in AUDIO_EXTENSIONS


# ---------------------------------------------------------------------------
# transcribe_voice_messages
# ---------------------------------------------------------------------------


class TestTranscribeVoiceMessages:
    """transcribe_voice_messages prepends transcription to message text."""

    @pytest.mark.asyncio
    async def test_prepends_transcription(self, tmp_path: Path) -> None:
        audio = _make_audio_file(tmp_path)
        msg = _make_message(
            text=f"[file: {audio}]",
            attachments=[{"type": "file", "path": str(audio)}],
        )

        mock_provider = AsyncMock()
        mock_provider.transcribe = AsyncMock(return_value="hello world")

        result = await transcribe_voice_messages(msg, mock_provider)

        assert '[Voice message transcription: "hello world"]' in result.text
        mock_provider.transcribe.assert_awaited_once_with(str(audio))

    @pytest.mark.asyncio
    async def test_no_audio_passthrough(self) -> None:
        msg = _make_message(text="just text", attachments=[])

        mock_provider = AsyncMock()
        result = await transcribe_voice_messages(msg, mock_provider)

        assert result.text == "just text"
        mock_provider.transcribe.assert_not_awaited()


# ---------------------------------------------------------------------------
# VoiceMiddleware -- inbound
# ---------------------------------------------------------------------------


class TestVoiceMiddlewareInbound:
    """VoiceMiddleware.process_inbound handles voice transcription."""

    @pytest.mark.asyncio
    async def test_process_inbound_with_audio(self, tmp_path: Path) -> None:
        audio = _make_audio_file(tmp_path)
        msg = _make_message(
            text=f"[file: {audio}]",
            attachments=[{"type": "file", "path": str(audio)}],
        )

        mock_provider = AsyncMock()
        mock_provider.transcribe = AsyncMock(return_value="transcribed")

        middleware = VoiceMiddleware(
            config={"enabled": True, "transcription": {"provider": "whisper-api"}}
        )

        with patch.object(middleware, "_transcription", mock_provider):
            result = await middleware.process_inbound(msg)

        assert '[Voice message transcription: "transcribed"]' in result.text

    @pytest.mark.asyncio
    async def test_process_inbound_text_only_passthrough(self) -> None:
        msg = _make_message(text="just text")

        middleware = VoiceMiddleware(config={"enabled": True})
        result = await middleware.process_inbound(msg)

        assert result.text == "just text"

    @pytest.mark.asyncio
    async def test_process_inbound_disabled_passthrough(self, tmp_path: Path) -> None:
        audio = _make_audio_file(tmp_path)
        msg = _make_message(attachments=[{"type": "file", "path": str(audio)}])

        middleware = VoiceMiddleware(config={"enabled": False})
        result = await middleware.process_inbound(msg)

        # Should pass through unchanged
        assert result is msg
