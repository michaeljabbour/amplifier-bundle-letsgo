"""Audio transcription and text-to-speech tool for Amplifier.

Provides a ``media_pipeline`` tool with two actions:
- ``transcribe``: Convert audio file to text
- ``synthesize``: Convert text to audio file

Also usable programmatically via the ``media.pipeline`` capability.
"""

from __future__ import annotations

import logging
from typing import Any

from amplifier_core.models import ToolResult  # type: ignore[import-not-found]

from .synthesize import TTSProvider, create_tts_provider
from .transcribe import TranscriptionProvider, create_transcription_provider

__amplifier_module_type__ = "tool"

logger = logging.getLogger(__name__)


class MediaPipelineTool:
    """Amplifier tool for audio transcription and text-to-speech.

    The agent can call this tool explicitly for on-demand media processing
    (e.g., "transcribe this podcast", "read this aloud").
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._transcription: TranscriptionProvider | None = None
        self._tts: TTSProvider | None = None

    def _get_transcription_provider(self) -> TranscriptionProvider:
        """Lazy-init transcription provider."""
        if self._transcription is None:
            self._transcription = create_transcription_provider(
                self._config.get("transcription", {})
            )
        return self._transcription

    def _get_tts_provider(self) -> TTSProvider:
        """Lazy-init TTS provider."""
        if self._tts is None:
            self._tts = create_tts_provider(self._config.get("tts", {}))
        return self._tts

    # -- Amplifier Tool protocol ----------------------------------------------

    @property
    def name(self) -> str:
        return "media_pipeline"

    @property
    def description(self) -> str:
        return (
            "Audio transcription and text-to-speech synthesis. "
            "Use 'transcribe' to convert an audio file to text, "
            "or 'synthesize' to convert text to an audio file."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["transcribe", "synthesize"],
                    "description": "The action to perform.",
                },
                "audio_path": {
                    "type": "string",
                    "description": ("Path to audio file (required for 'transcribe')."),
                },
                "text": {
                    "type": "string",
                    "description": ("Text to synthesize (required for 'synthesize')."),
                },
                "output_path": {
                    "type": "string",
                    "description": (
                        "Output file path for synthesized audio "
                        "(required for 'synthesize')."
                    ),
                },
                "voice": {
                    "type": "string",
                    "description": (
                        "Voice name/ID for TTS (optional, provider-specific)."
                    ),
                },
            },
            "required": ["action"],
        }

    async def execute(self, input: dict[str, Any]) -> ToolResult:  # noqa: A002
        """Dispatch to the requested action."""
        action = input.get("action", "")

        try:
            if action == "transcribe":
                return await self._transcribe(input)
            if action == "synthesize":
                return await self._synthesize(input)
            if not action:
                return ToolResult(
                    success=False,
                    error={"message": "Parameter 'action' is required."},
                )
            return ToolResult(
                success=False,
                error={"message": f"Unknown action: '{action}'"},
            )
        except Exception as exc:
            logger.exception("media_pipeline error")
            return ToolResult(
                success=False,
                error={"message": str(exc)},
            )

    # -- action handlers ------------------------------------------------------

    async def _transcribe(self, input: dict[str, Any]) -> ToolResult:
        audio_path = input.get("audio_path")
        if not audio_path:
            return ToolResult(
                success=False,
                error={"message": "Parameter 'audio_path' is required for transcribe."},
            )

        provider = self._get_transcription_provider()
        text = await provider.transcribe(audio_path)

        return ToolResult(
            success=True,
            output={"text": text, "audio_path": audio_path},
        )

    async def _synthesize(self, input: dict[str, Any]) -> ToolResult:
        text = input.get("text")
        output_path = input.get("output_path")
        if not text:
            return ToolResult(
                success=False,
                error={"message": "Parameter 'text' is required for synthesize."},
            )
        if not output_path:
            return ToolResult(
                success=False,
                error={
                    "message": "Parameter 'output_path' is required for synthesize.",
                },
            )

        voice = input.get("voice")
        provider = self._get_tts_provider()
        result_path = await provider.synthesize(text, output_path, voice=voice)

        return ToolResult(
            success=True,
            output={"audio_path": result_path, "text_length": len(text)},
        )


# ---------------------------------------------------------------------------
# Module mount point
# ---------------------------------------------------------------------------


async def mount(
    coordinator: Any,
    config: dict[str, Any] | None = None,
) -> None:
    """Mount the media pipeline tool into the Amplifier coordinator.

    Configuration keys (all optional):
        transcription:
            provider: "whisper-api" or "local-whisper"
            api_key:  Whisper API key (for whisper-api)
            model:    Model name
        tts:
            provider: "edge-tts", "elevenlabs", or "openai-tts"
            api_key:  API key (for elevenlabs and openai-tts)
            voice:    Voice name/ID
    """
    config = config or {}
    tool = MediaPipelineTool(config=config)

    await coordinator.mount("tools", tool, name="tool-media-pipeline")
    coordinator.register_capability("media.pipeline", tool)

    logger.info("tool-media-pipeline mounted")
