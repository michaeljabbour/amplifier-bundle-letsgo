"""Tests for tool-canvas module — canvas visual workspace."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from amplifier_module_tool_canvas import CanvasPushTool, mount

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool(config: dict[str, Any] | None = None) -> CanvasPushTool:
    return CanvasPushTool(config=config or {})


def _make_coordinator_with_display() -> MagicMock:
    """MockCoordinator that has a display capability registered."""
    coord = MagicMock()
    display_fn = AsyncMock()
    coord.get_capability = MagicMock(return_value=display_fn)
    return coord


def _make_coordinator_without_display() -> MagicMock:
    """MockCoordinator with no display capability."""
    coord = MagicMock()
    coord.get_capability = MagicMock(return_value=None)
    return coord


# ---------------------------------------------------------------------------
# CanvasPushTool — protocol compliance
# ---------------------------------------------------------------------------


class TestCanvasPushToolProtocol:
    """CanvasPushTool implements the Amplifier tool protocol."""

    def test_name(self) -> None:
        tool = _make_tool()
        assert tool.name == "canvas_push"

    def test_description_not_empty(self) -> None:
        tool = _make_tool()
        assert len(tool.description) > 20

    def test_input_schema_has_content_type(self) -> None:
        tool = _make_tool()
        schema = tool.input_schema
        assert "content_type" in schema["properties"]
        assert set(schema["properties"]["content_type"]["enum"]) == {
            "chart",
            "html",
            "svg",
            "markdown",
            "code",
            "table",
        }

    def test_input_schema_has_content(self) -> None:
        tool = _make_tool()
        schema = tool.input_schema
        assert "content" in schema["properties"]

    def test_input_schema_has_optional_id(self) -> None:
        tool = _make_tool()
        schema = tool.input_schema
        assert "id" in schema["properties"]
        assert "id" not in schema.get("required", [])

    def test_input_schema_has_optional_title(self) -> None:
        tool = _make_tool()
        schema = tool.input_schema
        assert "title" in schema["properties"]
        assert "title" not in schema.get("required", [])

    def test_input_schema_required_fields(self) -> None:
        tool = _make_tool()
        schema = tool.input_schema
        assert "content_type" in schema["required"]
        assert "content" in schema["required"]


# ---------------------------------------------------------------------------
# CanvasPushTool — execute
# ---------------------------------------------------------------------------


class TestCanvasPushToolExecute:
    """CanvasPushTool.execute dispatches to the display capability."""

    @pytest.mark.asyncio
    async def test_execute_pushes_json_envelope(self) -> None:
        tool = _make_tool()
        coord = _make_coordinator_with_display()
        tool._coordinator = coord

        result = await tool.execute(
            {
                "content_type": "chart",
                "content": '{"$schema": "https://vega-lite.github.io/schema"}',
                "id": "chart-1",
                "title": "Revenue",
            }
        )

        assert result.success is True
        assert result.output["id"] == "chart-1"
        assert result.output["content_type"] == "chart"

        # Verify display was called with JSON envelope
        display_fn = coord.get_capability("display")
        display_fn.assert_awaited_once()
        call_args = display_fn.call_args
        envelope = json.loads(call_args[0][0])
        assert envelope["content_type"] == "chart"
        assert envelope["id"] == "chart-1"
        assert envelope["title"] == "Revenue"

    @pytest.mark.asyncio
    async def test_execute_without_optional_fields(self) -> None:
        tool = _make_tool()
        coord = _make_coordinator_with_display()
        tool._coordinator = coord

        result = await tool.execute(
            {
                "content_type": "markdown",
                "content": "# Hello World",
            }
        )

        assert result.success is True
        assert result.output["content_type"] == "markdown"

        display_fn = coord.get_capability("display")
        display_fn.assert_awaited_once()
        call_args = display_fn.call_args
        envelope = json.loads(call_args[0][0])
        assert "id" not in envelope or envelope["id"] is None
        assert envelope["content_type"] == "markdown"

    @pytest.mark.asyncio
    async def test_execute_missing_display_capability(self) -> None:
        tool = _make_tool()
        coord = _make_coordinator_without_display()
        tool._coordinator = coord

        result = await tool.execute({"content_type": "html", "content": "<p>hello</p>"})

        assert result.success is False
        assert "display" in result.error["message"].lower()

    @pytest.mark.asyncio
    async def test_execute_missing_content_type(self) -> None:
        tool = _make_tool()
        coord = _make_coordinator_with_display()
        tool._coordinator = coord

        result = await tool.execute({"content": "some content"})

        assert result.success is False
        assert "content_type" in result.error["message"]

    @pytest.mark.asyncio
    async def test_execute_missing_content(self) -> None:
        tool = _make_tool()
        coord = _make_coordinator_with_display()
        tool._coordinator = coord

        result = await tool.execute({"content_type": "html"})

        assert result.success is False
        assert "content" in result.error["message"]

    @pytest.mark.asyncio
    async def test_execute_invalid_content_type(self) -> None:
        tool = _make_tool()
        coord = _make_coordinator_with_display()
        tool._coordinator = coord

        result = await tool.execute({"content_type": "video", "content": "stuff"})

        assert result.success is False
        assert "content_type" in result.error["message"]

    @pytest.mark.asyncio
    async def test_execute_display_error_handled_gracefully(self) -> None:
        tool = _make_tool()
        coord = MagicMock()
        display_fn = AsyncMock(side_effect=RuntimeError("Display broke"))
        coord.get_capability = MagicMock(return_value=display_fn)
        tool._coordinator = coord

        result = await tool.execute({"content_type": "html", "content": "<p>test</p>"})

        assert result.success is False
        assert "Display broke" in result.error["message"]

    @pytest.mark.asyncio
    async def test_execute_generates_id_when_omitted(self) -> None:
        tool = _make_tool()
        coord = _make_coordinator_with_display()
        tool._coordinator = coord

        result = await tool.execute(
            {"content_type": "code", "content": "print('hello')"}
        )

        assert result.success is True
        # Should still return a content_type in output
        assert result.output["content_type"] == "code"


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
        assert m["name"] == "tool-canvas"
        assert isinstance(m["obj"], CanvasPushTool)

        # Check capability was registered
        assert "canvas.push" in mock_coordinator.capabilities

    @pytest.mark.asyncio
    async def test_mount_stores_coordinator_ref(self, mock_coordinator: Any) -> None:
        await mount(mock_coordinator, config={})

        tool = mock_coordinator.mounts[0]["obj"]
        assert tool._coordinator is mock_coordinator
