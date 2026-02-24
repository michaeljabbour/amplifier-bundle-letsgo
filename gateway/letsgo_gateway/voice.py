"""Gateway voice middleware -- auto-transcribe inbound, optional TTS outbound.

This is gateway-level middleware, NOT an Amplifier hook. It operates on
InboundMessage objects before they reach the Amplifier session, and on
response text after the session responds.

Inbound: detects audio attachments -> transcribes -> prepends transcription
Outbound: optionally synthesizes TTS -> returns audio file path
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

from .models import InboundMessage

logger = logging.getLogger(__name__)

# Superset of the per-channel _AUDIO_EXTS -- covers all known audio formats
AUDIO_EXTENSIONS: frozenset[str] = frozenset(
    {".ogg", ".mp3", ".wav", ".m4a", ".opus", ".flac", ".webm"}
)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def detect_audio_attachments(message: InboundMessage) -> list[str]:
    """Return paths of audio file attachments from *message*."""
    audio_paths: list[str] = []
    for att in message.attachments:
        path_str = att.get("path")
        if not path_str:
            continue
        ext = Path(path_str).suffix.lower()
        if ext in AUDIO_EXTENSIONS:
            audio_paths.append(path_str)
    return audio_paths


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------


async def transcribe_voice_messages(
    message: InboundMessage,
    provider: Any,
) -> InboundMessage:
    """Transcribe audio attachments and prepend transcription to message text.

    Returns a new InboundMessage with transcription prepended. If no audio
    attachments are found, returns the original message unchanged.
    """
    audio_paths = detect_audio_attachments(message)
    if not audio_paths:
        return message

    transcriptions: list[str] = []
    for audio_path in audio_paths:
        try:
            text = await provider.transcribe(audio_path)
            transcriptions.append(text)
            logger.info("Transcribed %s: %d chars", Path(audio_path).name, len(text))
        except Exception:
            logger.exception("Failed to transcribe %s", audio_path)

    if not transcriptions:
        return message

    # Prepend transcription(s) to the message text
    prefix_parts = [f'[Voice message transcription: "{t}"]' for t in transcriptions]
    prefix = "\n".join(prefix_parts)
    new_text = f"{prefix}\n{message.text}" if message.text else prefix

    return replace(message, text=new_text)


# ---------------------------------------------------------------------------
# VoiceMiddleware
# ---------------------------------------------------------------------------


class VoiceMiddleware:
    """Gateway middleware for voice message processing.

    Handles two directions:
    - Inbound: auto-transcribe audio attachments
    - Outbound: optionally synthesize TTS audio
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._enabled = config.get("enabled", False)
        self._transcription: Any | None = None
        self._tts: Any | None = None

    def _get_transcription_provider(self) -> Any:
        """Lazy-init transcription provider."""
        if self._transcription is None:
            from amplifier_module_tool_media_pipeline.transcribe import (
                create_transcription_provider,
            )

            self._transcription = create_transcription_provider(
                self._config.get("transcription", {})
            )
        return self._transcription

    def _get_tts_provider(self) -> Any:
        """Lazy-init TTS provider."""
        if self._tts is None:
            from amplifier_module_tool_media_pipeline.synthesize import (
                create_tts_provider,
            )

            self._tts = create_tts_provider(self._config.get("tts", {}))
        return self._tts

    async def process_inbound(self, message: InboundMessage) -> InboundMessage:
        """Process inbound message -- transcribe audio if present."""
        if not self._enabled:
            return message

        audio_paths = detect_audio_attachments(message)
        if not audio_paths:
            return message

        provider = self._get_transcription_provider()
        return await transcribe_voice_messages(message, provider)

    async def process_outbound(
        self,
        text: str,
        message: InboundMessage,
        files_dir: Path,
    ) -> tuple[str, list[Path]]:
        """Process outbound response -- optionally synthesize TTS.

        Returns (response_text, list_of_audio_files_to_send).
        If TTS is disabled, returns (text, []).
        """
        if not self._enabled:
            return text, []

        tts_config = self._config.get("tts", {})
        if not tts_config.get("enabled", False):
            return text, []

        # Synthesize TTS
        try:
            provider = self._get_tts_provider()
            files_dir.mkdir(parents=True, exist_ok=True)
            output_path = files_dir / "tts_response.mp3"
            await provider.synthesize(text, str(output_path))
            logger.info("TTS synthesized: %s", output_path)
            return text, [output_path]
        except Exception:
            logger.exception("TTS synthesis failed -- sending text only")
            return text, []
