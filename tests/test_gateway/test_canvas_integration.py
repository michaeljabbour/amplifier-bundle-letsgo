"""Integration tests — full canvas pipeline from tool-canvas to CanvasChannel."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from letsgo_gateway.daemon import GatewayDaemon
from letsgo_gateway.display import GatewayDisplaySystem
from letsgo_gateway.models import OutboundMessage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_daemon(tmp_path: Path, **config_overrides: Any) -> GatewayDaemon:
    """Create a GatewayDaemon with given config overrides."""
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


class FakeCanvasChannel:
    """Fake canvas channel that records sent messages."""

    def __init__(
        self, name: str = "canvas", config: dict[str, Any] | None = None
    ) -> None:
        self.name = name
        self.config: dict[str, Any] = config or {}
        self._running = True
        self._on_message = None
        self.sent: list[OutboundMessage] = []

    @property
    def is_running(self) -> bool:
        return self._running

    def set_on_message(self, callback: Any) -> None:
        self._on_message = callback

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        self.sent.append(message)
        return True


class FakeChatChannel:
    """Fake chat channel for fallback testing."""

    def __init__(self, name: str = "webhook") -> None:
        self.name = name
        self.config: dict[str, Any] = {}
        self._running = True
        self._on_message = None
        self.sent: list[OutboundMessage] = []

    @property
    def is_running(self) -> bool:
        return self._running

    def set_on_message(self, callback: Any) -> None:
        self._on_message = callback

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        self.sent.append(message)
        return True


# ---------------------------------------------------------------------------
# tool-canvas -> DisplaySystem -> CanvasChannel
# ---------------------------------------------------------------------------


class TestToolToDisplay:
    """tool-canvas execute -> DisplaySystem routes to canvas channel."""

    @pytest.mark.asyncio
    async def test_display_routes_to_canvas_channel(self) -> None:
        """Content pushed via DisplaySystem reaches the canvas channel."""
        canvas = FakeCanvasChannel()
        display = GatewayDisplaySystem(channels={"canvas": canvas})

        envelope = json.dumps(
            {
                "content_type": "chart",
                "content": '{"$schema": "vega-lite"}',
                "id": "test-chart",
                "title": "Test",
            }
        )

        await display.display(
            envelope, metadata={"content_type": "chart", "id": "test-chart"}
        )

        assert len(canvas.sent) == 1
        msg = canvas.sent[0]
        parsed = json.loads(msg.text)
        assert parsed["content_type"] == "chart"
        assert parsed["id"] == "test-chart"

    @pytest.mark.asyncio
    async def test_display_fallback_to_chat(self) -> None:
        """Without a canvas channel, content falls back to chat."""
        chat = FakeChatChannel()
        display = GatewayDisplaySystem(channels={"webhook": chat})

        envelope = json.dumps({"content_type": "html", "content": "<p>hello</p>"})

        await display.display(envelope, metadata={"content_type": "html"})

        assert len(chat.sent) == 1
        assert "<p>hello</p>" in chat.sent[0].text

    @pytest.mark.asyncio
    async def test_display_tracks_canvas_state(self) -> None:
        """DisplaySystem tracks canvas state when content has an ID."""
        canvas = FakeCanvasChannel()
        display = GatewayDisplaySystem(channels={"canvas": canvas})

        envelope = json.dumps(
            {"content_type": "svg", "content": "<svg></svg>", "id": "svg-1"}
        )
        await display.display(envelope, metadata={"content_type": "svg", "id": "svg-1"})

        assert "svg-1" in display.canvas_state
        assert display.canvas_state["svg-1"]["content_type"] == "svg"

    @pytest.mark.asyncio
    async def test_display_with_no_channels(self) -> None:
        """DisplaySystem with no channels doesn't crash."""
        display = GatewayDisplaySystem(channels={})
        envelope = json.dumps({"content_type": "markdown", "content": "# Hello"})
        # Should not raise
        await display.display(envelope, metadata={"content_type": "markdown"})


# ---------------------------------------------------------------------------
# tool-canvas capability wiring
# ---------------------------------------------------------------------------


class TestCanvasToolCapability:
    """tool-canvas mount registers capability correctly."""

    @pytest.mark.asyncio
    async def test_mount_registers_display_queryable_capability(
        self, mock_coordinator: Any
    ) -> None:
        from amplifier_module_tool_canvas import mount

        await mount(mock_coordinator, config={})

        # Tool is mounted
        assert len(mock_coordinator.mounts) == 1
        assert mock_coordinator.mounts[0]["name"] == "tool-canvas"

        # canvas.push capability is registered
        assert "canvas.push" in mock_coordinator.capabilities

    @pytest.mark.asyncio
    async def test_tool_queries_display_capability_on_execute(self) -> None:
        from amplifier_module_tool_canvas import CanvasPushTool

        tool = CanvasPushTool(config={})
        display_fn = AsyncMock()
        coord = MagicMock()
        coord.get_capability = MagicMock(return_value=display_fn)
        tool._coordinator = coord

        await tool.execute({"content_type": "html", "content": "<p>test</p>"})

        # Verify get_capability was called
        coord.get_capability.assert_called_with("display")
        display_fn.assert_awaited_once()


# ---------------------------------------------------------------------------
# Daemon with canvas channel configured
# ---------------------------------------------------------------------------


class TestDaemonCanvasIntegration:
    """GatewayDaemon with canvas channel configuration."""

    def test_daemon_discovers_canvas_channel(self, tmp_path: Path) -> None:
        """When canvas channel is in the registry, daemon can create it."""
        with patch(
            "letsgo_gateway.daemon.discover_channels",
            return_value={"canvas": FakeCanvasChannel},
        ):
            daemon = _make_daemon(
                tmp_path,
                channels={"canvas": {"type": "canvas"}},
            )
            assert "canvas" in daemon.channels

    def test_daemon_without_canvas_works(self, tmp_path: Path) -> None:
        """Daemon works fine without any canvas channel."""
        daemon = _make_daemon(tmp_path)
        assert "canvas" not in daemon.channels
