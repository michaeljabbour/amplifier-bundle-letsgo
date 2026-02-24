"""Transcription provider abstraction — Whisper API and local CLI."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

WHISPER_API_URL = "https://api.openai.com/v1/audio/transcriptions"


# ---------------------------------------------------------------------------
# ABC
# ---------------------------------------------------------------------------


class TranscriptionProvider(ABC):
    """Abstract base for audio-to-text transcription."""

    @abstractmethod
    async def transcribe(self, audio_path: str) -> str:
        """Transcribe audio file at *audio_path* and return text."""


# ---------------------------------------------------------------------------
# OpenAI Whisper API
# ---------------------------------------------------------------------------


class WhisperAPIProvider(TranscriptionProvider):
    """Calls the OpenAI Whisper API for transcription."""

    def __init__(self, api_key: str, model: str = "whisper-1") -> None:
        self._api_key = api_key
        self._model = model

    async def transcribe(self, audio_path: str) -> str:
        import aiohttp

        path = Path(audio_path)
        logger.info("Transcribing via Whisper API: %s", path.name)

        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field(
                "file",
                open(path, "rb"),  # noqa: SIM115
                filename=path.name,
                content_type="application/octet-stream",
            )
            data.add_field("model", self._model)

            async with session.post(
                WHISPER_API_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                data=data,
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    msg = f"Whisper API error ({resp.status}): {body}"
                    raise RuntimeError(msg)
                result = await resp.json()
                return result["text"]


# ---------------------------------------------------------------------------
# Local Whisper CLI
# ---------------------------------------------------------------------------


class LocalWhisperProvider(TranscriptionProvider):
    """Shells out to the local ``whisper`` CLI for transcription."""

    def __init__(self, model: str = "base") -> None:
        self._model = model

    async def transcribe(self, audio_path: str) -> str:
        logger.info("Transcribing via local whisper: %s", Path(audio_path).name)

        proc = await asyncio.create_subprocess_exec(
            "whisper",
            audio_path,
            "--model",
            self._model,
            "--output_format",
            "txt",
            "--output_dir",
            str(Path(audio_path).parent),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            msg = f"Whisper CLI failed (rc={proc.returncode}): {stderr.decode()}"
            raise RuntimeError(msg)

        # whisper CLI writes a .txt file next to the audio; read it if present
        txt_path = Path(audio_path).with_suffix(".txt")
        if txt_path.exists():
            return txt_path.read_text(encoding="utf-8").strip()

        # Fallback: return stdout
        return stdout.decode("utf-8").strip()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_transcription_provider(config: dict[str, Any]) -> TranscriptionProvider:
    """Create a transcription provider from config.

    Config keys:
        provider: "whisper-api" (default) or "local-whisper"
        api_key:  Required for whisper-api
        model:    Whisper model name (default: "whisper-1" for API, "base" for local)
    """
    provider_name = config.get("provider", "whisper-api")

    if provider_name == "whisper-api":
        api_key = config.get("api_key", "")
        model = config.get("model", "whisper-1")
        return WhisperAPIProvider(api_key=api_key, model=model)

    if provider_name == "local-whisper":
        model = config.get("model", "base")
        return LocalWhisperProvider(model=model)

    msg = f"Unknown transcription provider: '{provider_name}'"
    raise ValueError(msg)
