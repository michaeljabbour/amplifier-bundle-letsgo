"""TTS provider abstraction — edge-tts, ElevenLabs, and OpenAI."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import edge_tts

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ABC
# ---------------------------------------------------------------------------


class TTSProvider(ABC):
    """Abstract base for text-to-speech synthesis."""

    @abstractmethod
    async def synthesize(
        self, text: str, output_path: str, voice: str | None = None
    ) -> str:
        """Synthesize *text* to audio at *output_path*. Returns the output path."""


# ---------------------------------------------------------------------------
# edge-tts (free, no API key)
# ---------------------------------------------------------------------------


class EdgeTTSProvider(TTSProvider):
    """Uses the ``edge-tts`` library for free TTS via Microsoft Edge."""

    def __init__(self, voice: str = "en-US-AriaNeural") -> None:
        self._voice = voice

    async def synthesize(
        self, text: str, output_path: str, voice: str | None = None
    ) -> str:
        effective_voice = voice or self._voice
        logger.info("Synthesizing via edge-tts (voice=%s)", effective_voice)

        communicate = edge_tts.Communicate(text, voice=effective_voice)
        await communicate.save(output_path)
        return output_path


# ---------------------------------------------------------------------------
# ElevenLabs
# ---------------------------------------------------------------------------


class ElevenLabsProvider(TTSProvider):
    """Calls the ElevenLabs TTS API."""

    ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"

    def __init__(self, api_key: str, voice_id: str = "21m00Tcm4TlvDq8ikWAM") -> None:
        self._api_key = api_key
        self._voice_id = voice_id

    async def synthesize(
        self, text: str, output_path: str, voice: str | None = None
    ) -> str:
        import aiohttp

        effective_voice_id = voice or self._voice_id
        url = f"{self.ELEVENLABS_API_URL}/{effective_voice_id}"
        logger.info("Synthesizing via ElevenLabs (voice=%s)", effective_voice_id)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                headers={
                    "xi-api-key": self._api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": "eleven_monolingual_v1",
                },
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    msg = f"ElevenLabs API error ({resp.status}): {body}"
                    raise RuntimeError(msg)
                audio_bytes = await resp.read()

        Path(output_path).write_bytes(audio_bytes)
        return output_path


# ---------------------------------------------------------------------------
# OpenAI TTS
# ---------------------------------------------------------------------------


class OpenAITTSProvider(TTSProvider):
    """Calls the OpenAI TTS API."""

    OPENAI_TTS_URL = "https://api.openai.com/v1/audio/speech"

    def __init__(
        self, api_key: str, voice: str = "alloy", model: str = "tts-1"
    ) -> None:
        self._api_key = api_key
        self._voice = voice
        self._model = model

    async def synthesize(
        self, text: str, output_path: str, voice: str | None = None
    ) -> str:
        import aiohttp

        effective_voice = voice or self._voice
        logger.info("Synthesizing via OpenAI TTS (voice=%s)", effective_voice)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.OPENAI_TTS_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "input": text,
                    "voice": effective_voice,
                },
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    msg = f"OpenAI TTS API error ({resp.status}): {body}"
                    raise RuntimeError(msg)
                audio_bytes = await resp.read()

        Path(output_path).write_bytes(audio_bytes)
        return output_path


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_tts_provider(config: dict[str, Any]) -> TTSProvider:
    """Create a TTS provider from config.

    Config keys:
        provider: "edge-tts" (default), "elevenlabs", or "openai-tts"
        api_key:  Required for elevenlabs and openai-tts
        voice:    Voice name/ID (provider-specific defaults)
        model:    Model name (openai-tts only, default: "tts-1")
    """
    provider_name = config.get("provider", "edge-tts")

    if provider_name == "edge-tts":
        voice = config.get("voice", "en-US-AriaNeural")
        return EdgeTTSProvider(voice=voice)

    if provider_name == "elevenlabs":
        api_key = config.get("api_key", "")
        voice_id = config.get("voice", "21m00Tcm4TlvDq8ikWAM")
        return ElevenLabsProvider(api_key=api_key, voice_id=voice_id)

    if provider_name == "openai-tts":
        api_key = config.get("api_key", "")
        voice = config.get("voice", "alloy")
        model = config.get("model", "tts-1")
        return OpenAITTSProvider(api_key=api_key, voice=voice, model=model)

    msg = f"Unknown TTS provider: '{provider_name}'"
    raise ValueError(msg)
