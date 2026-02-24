# OpenClaw Migration Phase 2: `letsgo-voice` Satellite Bundle — Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Add voice capabilities to the LetsGo gateway — auto-transcribe inbound audio messages to text (gateway middleware), optionally synthesize TTS on outbound responses (gateway post-processing), and provide an explicit `media_pipeline` tool the agent can call for on-demand transcription/TTS.

**Architecture:** Two voice paths operate at the gateway level (NOT as Amplifier hooks). Inbound: before routing to the Amplifier session, gateway middleware detects audio attachments and transcribes them to text, prepending the transcription to the message. Outbound: after the agent responds, optionally synthesize TTS audio and include it in the response files. A third path — the `tool-media-pipeline` Amplifier tool module — lets the agent explicitly request transcription or TTS when needed (e.g., "transcribe this podcast").

**Tech Stack:** Python 3.11+, pytest + pytest-asyncio (asyncio_mode=auto), hatchling build system, aiohttp for HTTP API calls, edge-tts for free TTS, OpenAI Whisper API / local whisper CLI for transcription.

**Design Document:** `docs/plans/2026-02-23-openclaw-migration-design.md`

---

## Conventions Reference

These conventions are derived from the existing codebase. Follow them exactly.

**Module naming:**
- Directory: `modules/{type}-{name}/` (e.g., `modules/tool-media-pipeline/`)
- Package: `amplifier_module_{type}_{name}` (hyphens → underscores)
- PyPI name: `amplifier-module-{type}-{name}`
- Entry point: `{type}-{name} = "{package}:mount"` under `[project.entry-points."amplifier.modules"]`

**Test conventions:**
- Framework: pytest + pytest-asyncio with `asyncio_mode = auto`
- Location: `tests/test_{module_name_underscored}.py` for modules, `tests/test_gateway/test_{component}.py` for gateway
- Style: class-based grouping (`class TestSomething:`), `_make_xxx()` helper factories, `@pytest.mark.asyncio` on async tests
- Fixtures: `mock_coordinator` and `tmp_dir` from `tests/conftest.py`
- Run command: `python -m pytest tests/path/to/test.py -v`

**Tool protocol (from `tool-secrets` reference):**
- Properties: `name` → str, `description` → str, `input_schema` → dict (JSON Schema)
- Method: `async def execute(self, input: dict) -> ToolResult`
- Import: `from amplifier_core.models import ToolResult`

**Mount pattern (tool):**
```python
__amplifier_module_type__ = "tool"
async def mount(coordinator, config=None):
    tool = SomeTool(...)
    await coordinator.mount("tools", tool, name="tool-xxx")
    coordinator.register_capability("xxx.yyy", tool)
```

**Behavior YAML pattern:**
```yaml
bundle:
  name: behavior-xxx
  version: 1.0.0
  description: ...
tools:
  - module: tool-xxx
    source: ../modules/tool-xxx
    config: {}
context:
  include:
    - namespace:context/xxx-awareness.md
```

**Gateway test pattern (from `test_daemon.py`):**
- `_make_daemon(tmp_path, **config_overrides) -> GatewayDaemon`
- `_make_message(sender_id, text, channel, channel_name) -> InboundMessage`
- Direct import: `from letsgo_gateway.daemon import GatewayDaemon`

---

## Task 1: Transcription Provider Abstraction

**Files:**
- Create: `modules/tool-media-pipeline/pyproject.toml`
- Create: `modules/tool-media-pipeline/amplifier_module_tool_media_pipeline/__init__.py` (stub only — completed in Task 3)
- Create: `modules/tool-media-pipeline/amplifier_module_tool_media_pipeline/transcribe.py`
- Test: `tests/test_tool_media_pipeline.py`

### Step 1: Create pyproject.toml

Create `modules/tool-media-pipeline/pyproject.toml`:

```toml
[project]
name = "amplifier-module-tool-media-pipeline"
version = "0.1.0"
description = "Audio transcription and text-to-speech tool for Amplifier"
requires-python = ">=3.11"
dependencies = []

[project.entry-points."amplifier.modules"]
tool-media-pipeline = "amplifier_module_tool_media_pipeline:mount"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["amplifier_module_tool_media_pipeline"]
```

### Step 2: Create stub `__init__.py`

Create `modules/tool-media-pipeline/amplifier_module_tool_media_pipeline/__init__.py`:

```python
"""Audio transcription and text-to-speech tool for Amplifier."""

from __future__ import annotations

from typing import Any

__amplifier_module_type__ = "tool"


async def mount(
    coordinator: Any,
    config: dict[str, Any] | None = None,
) -> None:
    """Mount placeholder — completed in Task 3."""
    raise NotImplementedError("Mount not yet implemented")
```

### Step 3: Register module in conftest.py

Edit `tests/conftest.py` — add the new module to `_MODULE_DIRS` list. Insert after the `tool-memory-store` line:

```python
    _BUNDLE_ROOT / "modules" / "tool-media-pipeline",
```

The full `_MODULE_DIRS` list should now end with:

```python
    _BUNDLE_ROOT / "modules" / "tool-memory-store",
    _BUNDLE_ROOT / "modules" / "tool-media-pipeline",
    # Gateway package lives under gateway/
    _BUNDLE_ROOT / "gateway",
]
```

### Step 4: Write failing tests for transcription providers

Create `tests/test_tool_media_pipeline.py`:

```python
"""Tests for tool-media-pipeline module — transcription providers."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amplifier_module_tool_media_pipeline.transcribe import (
    LocalWhisperProvider,
    TranscriptionProvider,
    WhisperAPIProvider,
    create_transcription_provider,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_audio_file(tmp_path: Path, name: str = "voice.ogg") -> Path:
    """Create a dummy audio file for testing."""
    audio = tmp_path / name
    audio.write_bytes(b"\x00" * 100)  # dummy content
    return audio


# ---------------------------------------------------------------------------
# TranscriptionProvider ABC
# ---------------------------------------------------------------------------


class TestTranscriptionProviderABC:
    """TranscriptionProvider enforces the interface contract."""

    def test_cannot_instantiate_abc(self) -> None:
        with pytest.raises(TypeError):
            TranscriptionProvider()  # type: ignore[abstract]

    def test_subclass_must_implement_transcribe(self) -> None:
        class Incomplete(TranscriptionProvider):
            pass

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestCreateTranscriptionProvider:
    """Factory creates the correct provider from config."""

    def test_creates_whisper_api_provider(self) -> None:
        provider = create_transcription_provider(
            {"provider": "whisper-api", "api_key": "sk-test"}
        )
        assert isinstance(provider, WhisperAPIProvider)

    def test_creates_local_whisper_provider(self) -> None:
        provider = create_transcription_provider({"provider": "local-whisper"})
        assert isinstance(provider, LocalWhisperProvider)

    def test_defaults_to_whisper_api(self) -> None:
        provider = create_transcription_provider({"api_key": "sk-test"})
        assert isinstance(provider, WhisperAPIProvider)

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown transcription provider"):
            create_transcription_provider({"provider": "nonexistent"})


# ---------------------------------------------------------------------------
# WhisperAPIProvider
# ---------------------------------------------------------------------------


class TestWhisperAPIProvider:
    """WhisperAPIProvider formats the request correctly."""

    @pytest.mark.asyncio
    async def test_transcribe_calls_api(self, tmp_path: Path) -> None:
        audio = _make_audio_file(tmp_path)
        provider = WhisperAPIProvider(api_key="sk-test-key", model="whisper-1")

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"text": "hello world"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await provider.transcribe(str(audio))

        assert result == "hello world"
        # Verify the API was called with correct URL
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert "api.openai.com" in call_args[0][0]
        assert "transcriptions" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_transcribe_api_error_raises(self, tmp_path: Path) -> None:
        audio = _make_audio_file(tmp_path)
        provider = WhisperAPIProvider(api_key="sk-bad", model="whisper-1")

        mock_response = MagicMock()
        mock_response.status = 401
        mock_response.text = AsyncMock(return_value="Unauthorized")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(RuntimeError, match="Whisper API error"):
                await provider.transcribe(str(audio))


# ---------------------------------------------------------------------------
# LocalWhisperProvider
# ---------------------------------------------------------------------------


class TestLocalWhisperProvider:
    """LocalWhisperProvider builds the correct command."""

    @pytest.mark.asyncio
    async def test_transcribe_builds_command(self, tmp_path: Path) -> None:
        audio = _make_audio_file(tmp_path)
        provider = LocalWhisperProvider(model="base")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"transcribed text output", b"")
        )
        mock_proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ) as mock_exec:
            result = await provider.transcribe(str(audio))

        assert result == "transcribed text output"
        # Verify command includes whisper, the audio path, and model
        call_args = mock_exec.call_args[0]
        assert "whisper" in call_args[0]
        assert str(audio) in call_args
        assert "--model" in call_args
        assert "base" in call_args

    @pytest.mark.asyncio
    async def test_transcribe_nonzero_exit_raises(self, tmp_path: Path) -> None:
        audio = _make_audio_file(tmp_path)
        provider = LocalWhisperProvider(model="base")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error occurred"))
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(RuntimeError, match="Whisper CLI failed"):
                await provider.transcribe(str(audio))
```

### Step 5: Run tests to verify they fail

Run: `python -m pytest tests/test_tool_media_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'amplifier_module_tool_media_pipeline.transcribe'`

### Step 6: Implement transcription providers

Create `modules/tool-media-pipeline/amplifier_module_tool_media_pipeline/transcribe.py`:

```python
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
```

### Step 7: Run tests to verify they pass

Run: `python -m pytest tests/test_tool_media_pipeline.py -v`
Expected: all 9 tests PASS

### Step 8: Commit

```
git add modules/tool-media-pipeline/ tests/test_tool_media_pipeline.py tests/conftest.py
git commit -m "feat(voice): transcription provider abstraction with Whisper API and local CLI"
```

---

## Task 2: TTS Provider Abstraction

**Files:**
- Create: `modules/tool-media-pipeline/amplifier_module_tool_media_pipeline/synthesize.py`
- Modify: `tests/test_tool_media_pipeline.py` (append TTS tests)

### Step 1: Write failing tests for TTS providers

Append to `tests/test_tool_media_pipeline.py`:

```python
from amplifier_module_tool_media_pipeline.synthesize import (
    EdgeTTSProvider,
    ElevenLabsProvider,
    OpenAITTSProvider,
    TTSProvider,
    create_tts_provider,
)


# ---------------------------------------------------------------------------
# TTSProvider ABC
# ---------------------------------------------------------------------------


class TestTTSProviderABC:
    """TTSProvider enforces the interface contract."""

    def test_cannot_instantiate_abc(self) -> None:
        with pytest.raises(TypeError):
            TTSProvider()  # type: ignore[abstract]

    def test_subclass_must_implement_synthesize(self) -> None:
        class Incomplete(TTSProvider):
            pass

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# TTS Factory
# ---------------------------------------------------------------------------


class TestCreateTTSProvider:
    """Factory creates the correct TTS provider from config."""

    def test_creates_edge_tts_provider(self) -> None:
        provider = create_tts_provider({"provider": "edge-tts"})
        assert isinstance(provider, EdgeTTSProvider)

    def test_creates_elevenlabs_provider(self) -> None:
        provider = create_tts_provider(
            {"provider": "elevenlabs", "api_key": "el-test"}
        )
        assert isinstance(provider, ElevenLabsProvider)

    def test_creates_openai_tts_provider(self) -> None:
        provider = create_tts_provider(
            {"provider": "openai-tts", "api_key": "sk-test"}
        )
        assert isinstance(provider, OpenAITTSProvider)

    def test_defaults_to_edge_tts(self) -> None:
        provider = create_tts_provider({})
        assert isinstance(provider, EdgeTTSProvider)

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown TTS provider"):
            create_tts_provider({"provider": "nonexistent"})


# ---------------------------------------------------------------------------
# EdgeTTSProvider
# ---------------------------------------------------------------------------


class TestEdgeTTSProvider:
    """EdgeTTSProvider calls edge-tts correctly."""

    @pytest.mark.asyncio
    async def test_synthesize_creates_file(self, tmp_path: Path) -> None:
        output = tmp_path / "output.mp3"
        provider = EdgeTTSProvider(voice="en-US-AriaNeural")

        mock_communicate = MagicMock()
        mock_communicate.save = AsyncMock()

        with patch(
            "amplifier_module_tool_media_pipeline.synthesize.edge_tts.Communicate",
            return_value=mock_communicate,
        ) as mock_cls:
            result = await provider.synthesize("Hello world", str(output))

        assert result == str(output)
        mock_cls.assert_called_once_with("Hello world", voice="en-US-AriaNeural")
        mock_communicate.save.assert_awaited_once_with(str(output))


# ---------------------------------------------------------------------------
# ElevenLabsProvider
# ---------------------------------------------------------------------------


class TestElevenLabsProvider:
    """ElevenLabsProvider formats the API request correctly."""

    @pytest.mark.asyncio
    async def test_synthesize_calls_api(self, tmp_path: Path) -> None:
        output = tmp_path / "output.mp3"
        provider = ElevenLabsProvider(
            api_key="el-test-key", voice_id="21m00Tcm4TlvDq8ikWAM"
        )

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=b"\xff\xfb\x90\x00")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await provider.synthesize("Hello world", str(output))

        assert result == str(output)
        assert output.read_bytes() == b"\xff\xfb\x90\x00"

        call_args = mock_session.post.call_args
        assert "api.elevenlabs.io" in call_args[0][0]


# ---------------------------------------------------------------------------
# OpenAITTSProvider
# ---------------------------------------------------------------------------


class TestOpenAITTSProvider:
    """OpenAITTSProvider formats the API request correctly."""

    @pytest.mark.asyncio
    async def test_synthesize_calls_api(self, tmp_path: Path) -> None:
        output = tmp_path / "output.mp3"
        provider = OpenAITTSProvider(api_key="sk-test-key", voice="alloy")

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=b"\xff\xfb\x90\x00")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await provider.synthesize("Hello world", str(output))

        assert result == str(output)
        assert output.read_bytes() == b"\xff\xfb\x90\x00"

        call_args = mock_session.post.call_args
        assert "api.openai.com" in call_args[0][0]
        assert "speech" in call_args[0][0]
```

### Step 2: Run tests to verify they fail

Run: `python -m pytest tests/test_tool_media_pipeline.py::TestTTSProviderABC -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'amplifier_module_tool_media_pipeline.synthesize'`

### Step 3: Implement TTS providers

Create `modules/tool-media-pipeline/amplifier_module_tool_media_pipeline/synthesize.py`:

```python
"""TTS provider abstraction — edge-tts, ElevenLabs, and OpenAI."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

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
        import edge_tts

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

    def __init__(
        self, api_key: str, voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    ) -> None:
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
```

### Step 4: Run tests to verify they pass

Run: `python -m pytest tests/test_tool_media_pipeline.py -v`
Expected: all 21 tests PASS (9 transcription + 12 TTS)

### Step 5: Commit

```
git add modules/tool-media-pipeline/amplifier_module_tool_media_pipeline/synthesize.py tests/test_tool_media_pipeline.py
git commit -m "feat(voice): TTS provider abstraction with edge-tts, ElevenLabs, and OpenAI"
```

---

## Task 3: MediaPipelineTool — Amplifier Tool Module

**Files:**
- Modify: `modules/tool-media-pipeline/amplifier_module_tool_media_pipeline/__init__.py` (replace stub)
- Modify: `tests/test_tool_media_pipeline.py` (append tool + mount tests)

### Step 1: Write failing tests for the tool and mount

Append to `tests/test_tool_media_pipeline.py`:

```python
from amplifier_module_tool_media_pipeline import MediaPipelineTool, mount


# ---------------------------------------------------------------------------
# MediaPipelineTool
# ---------------------------------------------------------------------------


class TestMediaPipelineTool:
    """MediaPipelineTool exposes transcribe and synthesize actions."""

    def _make_tool(self) -> MediaPipelineTool:
        return MediaPipelineTool(config={})

    def test_name(self) -> None:
        tool = self._make_tool()
        assert tool.name == "media_pipeline"

    def test_description_not_empty(self) -> None:
        tool = self._make_tool()
        assert len(tool.description) > 20

    def test_input_schema_has_action(self) -> None:
        tool = self._make_tool()
        schema = tool.input_schema
        assert "action" in schema["properties"]
        assert "transcribe" in schema["properties"]["action"]["enum"]
        assert "synthesize" in schema["properties"]["action"]["enum"]

    @pytest.mark.asyncio
    async def test_execute_transcribe(self, tmp_path: Path) -> None:
        audio = _make_audio_file(tmp_path)
        tool = MediaPipelineTool(
            config={"transcription": {"provider": "whisper-api", "api_key": "sk-test"}}
        )

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"text": "transcribed text"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await tool.execute(
                {"action": "transcribe", "audio_path": str(audio)}
            )

        assert result.success is True
        assert result.output["text"] == "transcribed text"

    @pytest.mark.asyncio
    async def test_execute_synthesize(self, tmp_path: Path) -> None:
        output = tmp_path / "output.mp3"
        tool = MediaPipelineTool(
            config={"tts": {"provider": "edge-tts"}}
        )

        mock_communicate = MagicMock()
        mock_communicate.save = AsyncMock()

        with patch(
            "amplifier_module_tool_media_pipeline.synthesize.edge_tts.Communicate",
            return_value=mock_communicate,
        ):
            result = await tool.execute(
                {"action": "synthesize", "text": "hello", "output_path": str(output)}
            )

        assert result.success is True
        assert result.output["audio_path"] == str(output)

    @pytest.mark.asyncio
    async def test_execute_unknown_action(self) -> None:
        tool = self._make_tool()
        result = await tool.execute({"action": "unknown"})
        assert result.success is False
        assert "Unknown action" in result.error["message"]

    @pytest.mark.asyncio
    async def test_execute_missing_action(self) -> None:
        tool = self._make_tool()
        result = await tool.execute({})
        assert result.success is False


# ---------------------------------------------------------------------------
# Mount
# ---------------------------------------------------------------------------


class TestMount:
    """mount() registers the tool and capability."""

    @pytest.mark.asyncio
    async def test_mount_registers_tool_and_capability(
        self, mock_coordinator: Any
    ) -> None:
        await mount(mock_coordinator, config={})

        # Check tool was mounted
        assert len(mock_coordinator.mounts) == 1
        m = mock_coordinator.mounts[0]
        assert m["category"] == "tools"
        assert m["name"] == "tool-media-pipeline"
        assert isinstance(m["obj"], MediaPipelineTool)

        # Check capability was registered
        assert "media.pipeline" in mock_coordinator.capabilities
```

### Step 2: Run tests to verify they fail

Run: `python -m pytest tests/test_tool_media_pipeline.py::TestMediaPipelineTool -v`
Expected: FAIL — `ImportError: cannot import name 'MediaPipelineTool' from 'amplifier_module_tool_media_pipeline'`

### Step 3: Replace the stub `__init__.py` with full implementation

Replace `modules/tool-media-pipeline/amplifier_module_tool_media_pipeline/__init__.py` with:

```python
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
                    "description": (
                        "Path to audio file (required for 'transcribe')."
                    ),
                },
                "text": {
                    "type": "string",
                    "description": (
                        "Text to synthesize (required for 'synthesize')."
                    ),
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
                error={"message": "Parameter 'output_path' is required for synthesize."},
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
```

### Step 4: Run tests to verify they pass

Run: `python -m pytest tests/test_tool_media_pipeline.py -v`
Expected: all 29 tests PASS (9 transcription + 12 TTS + 8 tool/mount)

### Step 5: Commit

```
git add modules/tool-media-pipeline/amplifier_module_tool_media_pipeline/__init__.py tests/test_tool_media_pipeline.py
git commit -m "feat(voice): MediaPipelineTool with transcribe and synthesize actions"
```

---

## Task 4: Gateway Voice Middleware — Inbound Transcription

**Files:**
- Create: `gateway/letsgo_gateway/voice.py`
- Modify: `gateway/letsgo_gateway/daemon.py` (import + wire middleware)
- Test: `tests/test_gateway/test_voice.py`

### Step 1: Write failing tests for voice middleware

Create `tests/test_gateway/test_voice.py`:

```python
"""Tests for gateway voice middleware — inbound transcription."""

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
        msg = _make_message(
            attachments=[{"type": "file", "path": str(audio)}]
        )
        paths = detect_audio_attachments(msg)
        assert paths == [str(audio)]

    def test_finds_mp3_attachment(self, tmp_path: Path) -> None:
        audio = _make_audio_file(tmp_path, "song.mp3")
        msg = _make_message(
            attachments=[{"type": "file", "path": str(audio)}]
        )
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
        msg = _make_message(
            attachments=[{"type": "file", "path": str(doc)}]
        )
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
# VoiceMiddleware — inbound
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
    async def test_process_inbound_disabled_passthrough(
        self, tmp_path: Path
    ) -> None:
        audio = _make_audio_file(tmp_path)
        msg = _make_message(
            attachments=[{"type": "file", "path": str(audio)}]
        )

        middleware = VoiceMiddleware(config={"enabled": False})
        result = await middleware.process_inbound(msg)

        # Should pass through unchanged
        assert result is msg
```

### Step 2: Run tests to verify they fail

Run: `python -m pytest tests/test_gateway/test_voice.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'letsgo_gateway.voice'`

### Step 3: Implement `voice.py`

Create `gateway/letsgo_gateway/voice.py`:

```python
"""Gateway voice middleware — auto-transcribe inbound, optional TTS outbound.

This is gateway-level middleware, NOT an Amplifier hook. It operates on
InboundMessage objects before they reach the Amplifier session, and on
response text after the session responds.

Inbound: detects audio attachments → transcribes → prepends transcription
Outbound: optionally synthesizes TTS → returns audio file path
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

from .models import InboundMessage

logger = logging.getLogger(__name__)

# Superset of the per-channel _AUDIO_EXTS — covers all known audio formats
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
    prefix_parts = [
        f'[Voice message transcription: "{t}"]' for t in transcriptions
    ]
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
        """Process inbound message — transcribe audio if present."""
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
        """Process outbound response — optionally synthesize TTS.

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
            logger.exception("TTS synthesis failed — sending text only")
            return text, []
```

### Step 4: Run tests to verify they pass

Run: `python -m pytest tests/test_gateway/test_voice.py -v`
Expected: all 10 tests PASS

### Step 5: Wire middleware into daemon.py

Edit `gateway/letsgo_gateway/daemon.py`.

**Add import** — after the existing imports (after line 18 `from .router import SessionRouter`), add:

```python
from .voice import VoiceMiddleware
```

**Add initialization** — inside `__init__`, after `self._running = False` (line 66) and before `self._init_channels()` (line 68), add:

```python
        # Voice middleware (optional)
        voice_config = self._config.get("voice", {})
        self.voice: VoiceMiddleware | None = (
            VoiceMiddleware(voice_config)
            if voice_config.get("enabled", False)
            else None
        )
```

**Add inbound processing** — inside `_on_message`, after the rate limit check (after line 257 `"Rate limit exceeded..."`) and before `# 3. Route to session`, add:

```python
        # 2b. Voice transcription (before routing to session)
        if self.voice is not None:
            message = await self.voice.process_inbound(message)
```

**Add outbound processing** — inside `_on_message`, after `response, long_file = handle_long_response(...)` (after line 264) and before `if long_file:`, add:

```python
        # 4b. Voice TTS (optional — after session responds)
        if self.voice is not None:
            response, voice_files = await self.voice.process_outbound(
                response, message, self._files_dir
            )
            send_files.extend(voice_files)
```

### Step 6: Run daemon tests to verify nothing broke

Run: `python -m pytest tests/test_gateway/test_daemon.py -v`
Expected: all existing daemon tests PASS (voice middleware is None when no config present)

### Step 7: Commit

```
git add gateway/letsgo_gateway/voice.py gateway/letsgo_gateway/daemon.py tests/test_gateway/test_voice.py
git commit -m "feat(voice): gateway voice middleware — auto-transcribe inbound audio"
```

---

## Task 5: Gateway TTS Post-Processing — Outbound

**Files:**
- Modify: `tests/test_gateway/test_voice.py` (append outbound TTS tests)

This task extends the tests for `VoiceMiddleware.process_outbound()` which was already implemented in Task 4. The implementation is done — we just need to verify the outbound path with tests.

### Step 1: Write tests for outbound TTS processing

Append to `tests/test_gateway/test_voice.py`:

```python
# ---------------------------------------------------------------------------
# VoiceMiddleware — outbound TTS
# ---------------------------------------------------------------------------


class TestVoiceMiddlewareOutbound:
    """VoiceMiddleware.process_outbound handles TTS synthesis."""

    @pytest.mark.asyncio
    async def test_tts_creates_audio_file(self, tmp_path: Path) -> None:
        msg = _make_message(text="original")
        files_dir = tmp_path / "files"

        mock_provider = AsyncMock()
        mock_provider.synthesize = AsyncMock(return_value=str(files_dir / "tts_response.mp3"))

        middleware = VoiceMiddleware(
            config={"enabled": True, "tts": {"enabled": True, "provider": "edge-tts"}}
        )

        with patch.object(middleware, "_tts", mock_provider):
            text, files = await middleware.process_outbound(
                "Hello world", msg, files_dir
            )

        assert text == "Hello world"
        assert len(files) == 1
        assert files[0].name == "tts_response.mp3"
        mock_provider.synthesize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_tts_disabled_passthrough(self, tmp_path: Path) -> None:
        msg = _make_message()
        files_dir = tmp_path / "files"

        middleware = VoiceMiddleware(
            config={"enabled": True, "tts": {"enabled": False}}
        )
        text, files = await middleware.process_outbound(
            "Hello world", msg, files_dir
        )

        assert text == "Hello world"
        assert files == []

    @pytest.mark.asyncio
    async def test_middleware_disabled_passthrough(self, tmp_path: Path) -> None:
        msg = _make_message()
        files_dir = tmp_path / "files"

        middleware = VoiceMiddleware(config={"enabled": False})
        text, files = await middleware.process_outbound(
            "Hello world", msg, files_dir
        )

        assert text == "Hello world"
        assert files == []

    @pytest.mark.asyncio
    async def test_tts_error_graceful_degradation(self, tmp_path: Path) -> None:
        msg = _make_message()
        files_dir = tmp_path / "files"

        mock_provider = AsyncMock()
        mock_provider.synthesize = AsyncMock(side_effect=RuntimeError("API error"))

        middleware = VoiceMiddleware(
            config={"enabled": True, "tts": {"enabled": True}}
        )

        with patch.object(middleware, "_tts", mock_provider):
            text, files = await middleware.process_outbound(
                "Hello world", msg, files_dir
            )

        # Should gracefully degrade — return text with no files
        assert text == "Hello world"
        assert files == []

    @pytest.mark.asyncio
    async def test_tts_no_tts_config_passthrough(self, tmp_path: Path) -> None:
        msg = _make_message()
        files_dir = tmp_path / "files"

        middleware = VoiceMiddleware(config={"enabled": True})
        text, files = await middleware.process_outbound(
            "Hello world", msg, files_dir
        )

        assert text == "Hello world"
        assert files == []
```

### Step 2: Run tests to verify they pass

Run: `python -m pytest tests/test_gateway/test_voice.py -v`
Expected: all 15 tests PASS (10 inbound + 5 outbound)

### Step 3: Commit

```
git add tests/test_gateway/test_voice.py
git commit -m "test(voice): outbound TTS processing tests for VoiceMiddleware"
```

---

## Task 6: Satellite Bundle Structure

**Files:**
- Create: `voice/bundle.md`
- Create: `voice/behaviors/voice-capabilities.yaml`
- Create: `voice/context/voice-awareness.md`
- Create: `voice/agents/voice-specialist.md`
- Create: `voice/skills/voice-config/SKILL.md`

No tests for bundle structure — validated by Amplifier's bundle loader at runtime.

### Step 1: Create bundle.md

Create `voice/bundle.md`:

```markdown
---
bundle:
  name: letsgo-voice
  version: 0.1.0
  description: Voice message transcription and TTS for LetsGo channels
includes:
  - bundle: letsgo-voice:behaviors/voice-capabilities
---

# LetsGo Voice

Voice capabilities for the LetsGo gateway — auto-transcribe inbound audio messages and optionally synthesize text-to-speech responses.

@letsgo-voice:context/voice-awareness.md
```

### Step 2: Create behavior YAML

Create `voice/behaviors/voice-capabilities.yaml`:

```yaml
bundle:
  name: behavior-voice-capabilities
  version: 1.0.0
  description: Voice transcription and TTS capabilities for LetsGo

tools:
  - module: tool-media-pipeline
    source: ../modules/tool-media-pipeline
    config:
      transcription:
        provider: "whisper-api"
      tts:
        provider: "edge-tts"
        voice: "en-US-AriaNeural"

context:
  include:
    - letsgo-voice:context/voice-awareness.md
```

### Step 3: Create voice awareness context

Create `voice/context/voice-awareness.md`:

```markdown
# Voice Capabilities

You have access to voice processing capabilities through the LetsGo gateway.

## Automatic Voice Transcription

When users send voice messages through any channel (Telegram, WhatsApp, Discord, etc.), their audio is automatically transcribed to text before reaching you. You'll see transcriptions formatted as:

```
[Voice message transcription: "the transcribed text"]
```

Treat these transcriptions as the user's actual message. Respond naturally in text — the gateway may optionally convert your response to audio.

## Explicit Media Pipeline Tool

You can also use the `media_pipeline` tool explicitly for on-demand audio processing:

- **Transcribe**: Convert any audio file to text
  - Action: `transcribe`, provide `audio_path`
- **Synthesize**: Convert text to audio
  - Action: `synthesize`, provide `text` and `output_path`

Use explicit transcription for tasks like "transcribe this podcast" or "what does this audio say". Use explicit synthesis for "read this aloud" or "create an audio version".

## Voice Providers

Transcription providers: OpenAI Whisper API, local Whisper CLI
TTS providers: edge-tts (free), ElevenLabs, OpenAI TTS
```

### Step 4: Create voice specialist agent

Create `voice/agents/voice-specialist.md`:

```markdown
---
meta:
  name: voice-specialist
  description: |
    Specialist agent for voice-related workflows — transcription quality review,
    TTS voice selection, audio format conversion, and voice pipeline configuration.

    Use PROACTIVELY when:
    - User needs help choosing voice providers or TTS voices
    - Audio transcription quality needs review or correction
    - Voice pipeline configuration or troubleshooting
    - Batch audio processing tasks

    Examples:
    <example>
    user: 'The transcription of my meeting recording seems wrong'
    assistant: 'I'll use the voice-specialist to review and correct the transcription.'
    </example>
tools:
  - media_pipeline
---

# Voice Specialist

You are a specialist in voice and audio processing workflows. You help users with:

1. **Transcription review** — Check and correct auto-transcribed voice messages
2. **TTS configuration** — Help users choose the right voice and provider
3. **Batch processing** — Handle multiple audio files efficiently
4. **Troubleshooting** — Debug voice pipeline issues

Always use the `media_pipeline` tool for audio operations. When reviewing transcriptions, pay attention to proper nouns, technical terms, and context that the automatic transcription might have missed.
```

### Step 5: Create voice config skill

Create `voice/skills/voice-config/SKILL.md`:

```markdown
---
skill:
  name: voice-config
  version: 1.0.0
  description: Guide for configuring voice transcription and TTS providers
  tags:
    - voice
    - configuration
    - setup
---

# Voice Configuration Guide

## Gateway Voice Middleware

Add a `voice` section to `~/.letsgo/gateway/config.yaml`:

```yaml
voice:
  enabled: true
  transcription:
    provider: "whisper-api"    # Options: "whisper-api", "local-whisper"
    api_key: "<stored-in-secrets>"
    model: "whisper-1"
  tts:
    enabled: false              # TTS is opt-in
    provider: "edge-tts"        # Options: "edge-tts", "elevenlabs", "openai-tts"
    voice: "en-US-AriaNeural"   # Provider-specific voice name
```

## Provider Setup

### Transcription: OpenAI Whisper API (Recommended)
1. Get API key from https://platform.openai.com/api-keys
2. Store: `secrets set_secret voice/whisper/api_key <key> api_key`
3. Set `transcription.provider: "whisper-api"` in config

### Transcription: Local Whisper (Free, requires GPU)
1. Install: `pip install openai-whisper`
2. Set `transcription.provider: "local-whisper"` in config
3. Model options: tiny, base, small, medium, large

### TTS: edge-tts (Free, No API Key)
1. Install: `pip install edge-tts`
2. Set `tts.provider: "edge-tts"` in config
3. Voices: en-US-AriaNeural, en-US-GuyNeural, en-GB-SoniaNeural, etc.

### TTS: ElevenLabs (High Quality)
1. Get API key from https://elevenlabs.io
2. Store: `secrets set_secret voice/elevenlabs/api_key <key> api_key`
3. Set `tts.provider: "elevenlabs"` in config

### TTS: OpenAI TTS
1. Uses same API key as Whisper (if using OpenAI for both)
2. Set `tts.provider: "openai-tts"` in config
3. Voices: alloy, echo, fable, onyx, nova, shimmer
```

### Step 6: Commit

```
git add voice/
git commit -m "feat(voice): satellite bundle structure — bundle.md, behaviors, context, agent, skill"
```

---

## Task 7: Update Onboarding Recipe for Voice

**Files:**
- Modify: `recipes/setup-wizard.yaml` (extend satellite-setup stage)

### Step 1: Read current satellite-setup step

The satellite-setup stage is at line 123-168 in `recipes/setup-wizard.yaml`. The `select-satellites` step already mentions voice (lines 131-134):

```yaml
          **Voice** (amplifier-bundle-letsgo-voice)
          - Transcribe inbound voice messages
          - Text-to-speech responses
          - Works across all channels with voice support
```

### Step 2: Add voice configuration step to satellite-setup stage

Edit `recipes/setup-wizard.yaml` — add a new step after `select-satellites` (insert before the `approval:` block of the `satellite-setup` stage). Insert between the `select-satellites` step's `timeout: 300` (line 159) and the `approval:` block (line 161):

```yaml
      - id: configure-voice
        agent: self
        prompt: >
          If voice was selected in {{satellite_config}}:

          1. **Transcription provider setup:**
             - Ask: OpenAI Whisper API (recommended, cloud) or local Whisper (free, needs GPU)?
             - If Whisper API: collect API key, store via secrets tool as
               "voice/whisper/api_key" (category: api_key)
             - If local: verify `whisper` CLI is installed

          2. **TTS setup (optional):**
             - Ask: Enable text-to-speech responses? (default: no)
             - If yes, ask provider: edge-tts (free, no key), ElevenLabs (high quality),
               or OpenAI TTS
             - If ElevenLabs: collect API key, store as "voice/elevenlabs/api_key"
             - If OpenAI TTS: can reuse existing OpenAI key if available
             - Choose voice (list top 3 options for selected provider)

          3. **Update gateway config:**
             - Add voice section to ~/.letsgo/gateway/config.yaml with the
               chosen providers and settings
             - Voice config schema:
               voice:
                 enabled: true
                 transcription:
                   provider: "whisper-api" or "local-whisper"
                 tts:
                   enabled: true/false
                   provider: "edge-tts" / "elevenlabs" / "openai-tts"
                   voice: "<chosen-voice>"

          If voice was NOT selected, skip this step entirely and report "Voice: skipped".
        output: voice_config
        timeout: 300
```

### Step 3: Validate the recipe

Run: `amplifier recipe validate recipes/setup-wizard.yaml`
Expected: validation passes with no errors

### Step 4: Commit

```
git add recipes/setup-wizard.yaml
git commit -m "feat(voice): add voice configuration step to setup-wizard recipe"
```

---

## Task 8: Integration Test — Full Voice Pipeline

**Files:**
- Create: `tests/test_gateway/test_voice_integration.py`

### Step 1: Write integration tests

Create `tests/test_gateway/test_voice_integration.py`:

```python
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
    """End-to-end: audio attachment → transcription → message with text."""

    @pytest.mark.asyncio
    async def test_audio_message_gets_transcription(self, tmp_path: Path) -> None:
        """Full flow: audio attachment → VoiceMiddleware transcribes → text in message."""
        audio = _make_audio_file(tmp_path)

        mock_provider = AsyncMock()
        mock_provider.transcribe = AsyncMock(
            return_value="hello from voice message"
        )

        middleware = VoiceMiddleware(
            config={"enabled": True, "transcription": {"provider": "whisper-api"}}
        )

        with patch.object(middleware, "_transcription", mock_provider):
            msg = _make_message(
                text=f"[file: {audio}]",
                attachments=[{"type": "file", "path": str(audio)}],
            )
            result = await middleware.process_inbound(msg)

        assert '[Voice message transcription: "hello from voice message"]' in result.text
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
    """End-to-end: session response → TTS synthesis → audio file in outbound."""

    @pytest.mark.asyncio
    async def test_tts_produces_audio_file(self, tmp_path: Path) -> None:
        """Full flow: response text → VoiceMiddleware synthesizes → audio file."""
        files_dir = tmp_path / "files"
        msg = _make_message()

        mock_provider = AsyncMock()
        mock_provider.synthesize = AsyncMock(
            return_value=str(files_dir / "tts_response.mp3")
        )

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
    async def test_on_message_without_voice_passthrough(
        self, tmp_path: Path
    ) -> None:
        """When voice middleware is None, _on_message works normally."""
        daemon = _make_daemon(tmp_path)
        assert daemon.voice is None

        _approve_sender(daemon, "user1")
        msg = _make_message(sender_id="user1", text="test no voice")

        # Should not raise — voice middleware is None, skipped
        response = await daemon._on_message(msg)
        assert isinstance(response, str)
```

### Step 2: Run integration tests

Run: `python -m pytest tests/test_gateway/test_voice_integration.py -v`
Expected: all 8 tests PASS

### Step 3: Run the complete test suite

Run: `python -m pytest tests/ -v`
Expected: all tests PASS (existing ~285 + new ~37 voice tests)

### Step 4: Commit

```
git add tests/test_gateway/test_voice_integration.py
git commit -m "test(voice): integration tests for full voice pipeline through gateway"
```

---

## Summary

| Task | What | Files Created | Files Modified | Tests |
|------|------|---------------|----------------|-------|
| 1 | Transcription providers | `transcribe.py`, `pyproject.toml`, stub `__init__.py` | `conftest.py` | 9 |
| 2 | TTS providers | `synthesize.py` | `test_tool_media_pipeline.py` | 12 |
| 3 | MediaPipelineTool | — | `__init__.py`, `test_tool_media_pipeline.py` | 8 |
| 4 | Inbound voice middleware | `voice.py` | `daemon.py` | 10 |
| 5 | Outbound TTS tests | — | `test_voice.py` | 5 |
| 6 | Satellite bundle | `bundle.md`, behavior, context, agent, skill | — | 0 |
| 7 | Recipe update | — | `setup-wizard.yaml` | 0 (validate) |
| 8 | Integration tests | `test_voice_integration.py` | — | 8 |
| **Total** | | **~13 new files** | **~4 modified** | **~52 tests** |

### Commit sequence
1. `feat(voice): transcription provider abstraction with Whisper API and local CLI`
2. `feat(voice): TTS provider abstraction with edge-tts, ElevenLabs, and OpenAI`
3. `feat(voice): MediaPipelineTool with transcribe and synthesize actions`
4. `feat(voice): gateway voice middleware — auto-transcribe inbound audio`
5. `test(voice): outbound TTS processing tests for VoiceMiddleware`
6. `feat(voice): satellite bundle structure — bundle.md, behaviors, context, agent, skill`
7. `feat(voice): add voice configuration step to setup-wizard recipe`
8. `test(voice): integration tests for full voice pipeline through gateway`
