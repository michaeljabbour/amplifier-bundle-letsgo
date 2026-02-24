"""Tests for tool-media-pipeline module — transcription & TTS providers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from amplifier_module_tool_media_pipeline.synthesize import (
    EdgeTTSProvider,
    ElevenLabsProvider,
    OpenAITTSProvider,
    TTSProvider,
    create_tts_provider,
)
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


# ===========================================================================
# TTS Provider Tests
# ===========================================================================


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
        provider = create_tts_provider({"provider": "elevenlabs", "api_key": "el-test"})
        assert isinstance(provider, ElevenLabsProvider)

    def test_creates_openai_tts_provider(self) -> None:
        provider = create_tts_provider({"provider": "openai-tts", "api_key": "sk-test"})
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
