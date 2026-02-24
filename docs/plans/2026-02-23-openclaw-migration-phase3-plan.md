# OpenClaw Migration Phase 3: `letsgo-canvas` Satellite Bundle — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a visual workspace to the LetsGo gateway — agents push rich content (charts, HTML, SVG, markdown, code, tables) to a multi-panel web UI served by a new `CanvasChannel` gateway plugin, routed through the existing `DisplaySystem` shipped in Phase 0.

**Architecture:** Three-layer design validated by Amplifier experts. Layer 1: `tool-canvas` (Amplifier tool module) wraps content as a JSON envelope and calls the `display` capability. Layer 2: `GatewayDisplaySystem` (already built) routes to canvas-named channels or falls back to chat. Layer 3: `CanvasChannel` (gateway entry-point plugin) parses the JSON envelope, maintains in-memory state, serves a WebSocket-powered web UI at `localhost:8080/canvas`, and pushes real-time updates to connected browsers.

**Tech Stack:** Python 3.11+, pytest + pytest-asyncio (asyncio_mode=auto), hatchling build system, aiohttp for WebSocket server + HTTP routes, vanilla HTML/CSS/JS for the web UI (no build step), CDN-loaded vega-embed + marked + highlight.js for content rendering.

**Design Document:** `docs/plans/2026-02-23-openclaw-migration-phase3-canvas-design.md`

---

## Conventions Reference

These conventions are derived from the existing codebase. Follow them exactly.

**Module naming:**
- Directory: `modules/{type}-{name}/` (e.g., `modules/tool-canvas/`)
- Package: `amplifier_module_{type}_{name}` (hyphens → underscores)
- PyPI name: `amplifier-module-{type}-{name}`
- Entry point: `{type}-{name} = "{package}:mount"` under `[project.entry-points."amplifier.modules"]`

**Channel adapter naming:**
- Directory: `channels/{name}/` (e.g., `channels/canvas/`)
- Package: `letsgo_channel_{name}` (e.g., `letsgo_channel_canvas`)
- PyPI name: `letsgo-channel-{name}`
- Entry point: `{name} = "{package}:{ClassName}"` under `[project.entry-points."letsgo.channels"]`

**Test conventions:**
- Framework: pytest + pytest-asyncio with `asyncio_mode = auto`
- Location: `tests/test_{module_name_underscored}.py` for modules, `tests/test_gateway/test_{component}.py` for gateway
- Style: class-based grouping (`class TestSomething:`), `_make_xxx()` helper factories, `@pytest.mark.asyncio` on async tests
- Fixtures: `mock_coordinator` and `tmp_dir` from `tests/conftest.py`
- Run command: `python -m pytest tests/path/to/test.py -v`
- Channel adapter tests run with: `PYTHONPATH=channels/canvas:gateway python -m pytest channels/canvas/tests/ -v`

**Tool protocol (from `tool-media-pipeline` reference):**
- Properties: `name` → str, `description` → str, `input_schema` → dict (JSON Schema)
- Method: `async def execute(self, input: dict) -> ToolResult`
- Import: `from amplifier_core.models import ToolResult  # type: ignore[import-not-found]`
- Module type marker: `__amplifier_module_type__ = "tool"`

**Mount pattern (tool):**
```python
__amplifier_module_type__ = "tool"
async def mount(coordinator, config=None):
    tool = SomeTool(...)
    await coordinator.mount("tools", tool, name="tool-xxx")
    coordinator.register_capability("xxx.yyy", tool)
```

**Channel adapter pattern (from `SignalChannel` reference):**
```python
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

class SomeChannel(ChannelAdapter):
    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def send(self, message: OutboundMessage) -> bool: ...
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

**Wire format — JSON envelope in `OutboundMessage.text`:**
```json
{
  "content_type": "chart",
  "content": "<vega-lite-spec-or-html-or-svg>",
  "id": "chart-1",
  "title": "Monthly Revenue"
}
```

Fields: `content_type` (required, one of: chart/html/svg/markdown/code/table), `content` (required), `id` (optional — stable ID for update-in-place), `title` (optional — display title for sidebar).

---

## Task 1: `tool-canvas` — Amplifier Tool Module

**Files:**
- Create: `modules/tool-canvas/pyproject.toml`
- Create: `modules/tool-canvas/amplifier_module_tool_canvas/__init__.py`
- Test: `tests/test_tool_canvas.py`
- Modify: `tests/conftest.py` (add module to `_MODULE_DIRS`)

### Step 1: Create pyproject.toml

Create `modules/tool-canvas/pyproject.toml`:

```toml
[project]
name = "amplifier-module-tool-canvas"
version = "0.1.0"
description = "Canvas visual workspace tool for Amplifier — push charts, HTML, SVG, markdown, code, and tables"
requires-python = ">=3.11"
dependencies = []

[project.entry-points."amplifier.modules"]
tool-canvas = "amplifier_module_tool_canvas:mount"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["amplifier_module_tool_canvas"]
```

### Step 2: Create stub `__init__.py`

Create `modules/tool-canvas/amplifier_module_tool_canvas/__init__.py`:

```python
"""Canvas visual workspace tool for Amplifier.

Provides a ``canvas_push`` tool that lets the agent push rich visual content
(charts, HTML, SVG, markdown, code, tables) to a canvas web UI.
"""

from __future__ import annotations

from typing import Any

__amplifier_module_type__ = "tool"


async def mount(
    coordinator: Any,
    config: dict[str, Any] | None = None,
) -> None:
    """Mount placeholder — completed in Step 5."""
    raise NotImplementedError("Mount not yet implemented")
```

### Step 3: Register module in conftest.py

Edit `tests/conftest.py` — add the new module to `_MODULE_DIRS` list. Insert after the `tool-media-pipeline` line:

```python
    _BUNDLE_ROOT / "modules" / "tool-canvas",
```

The full `_MODULE_DIRS` list should now end with:

```python
    _BUNDLE_ROOT / "modules" / "tool-media-pipeline",
    _BUNDLE_ROOT / "modules" / "tool-canvas",
    # Gateway package lives under gateway/
    _BUNDLE_ROOT / "gateway",
]
```

### Step 4: Write failing tests

Create `tests/test_tool_canvas.py`:

```python
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

        result = await tool.execute(
            {"content_type": "html", "content": "<p>hello</p>"}
        )

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

        result = await tool.execute(
            {"content_type": "video", "content": "stuff"}
        )

        assert result.success is False
        assert "content_type" in result.error["message"]

    @pytest.mark.asyncio
    async def test_execute_display_error_handled_gracefully(self) -> None:
        tool = _make_tool()
        coord = MagicMock()
        display_fn = AsyncMock(side_effect=RuntimeError("Display broke"))
        coord.get_capability = MagicMock(return_value=display_fn)
        tool._coordinator = coord

        result = await tool.execute(
            {"content_type": "html", "content": "<p>test</p>"}
        )

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
    async def test_mount_stores_coordinator_ref(
        self, mock_coordinator: Any
    ) -> None:
        await mount(mock_coordinator, config={})

        tool = mock_coordinator.mounts[0]["obj"]
        assert tool._coordinator is mock_coordinator
```

### Step 5: Run tests to verify they fail

Run: `python -m pytest tests/test_tool_canvas.py -v`
Expected: FAIL — `ImportError: cannot import name 'CanvasPushTool' from 'amplifier_module_tool_canvas'`

### Step 6: Implement tool-canvas

Replace `modules/tool-canvas/amplifier_module_tool_canvas/__init__.py` with:

```python
"""Canvas visual workspace tool for Amplifier.

Provides a ``canvas_push`` tool that lets the agent push rich visual content
(charts, HTML, SVG, markdown, code, tables) to a canvas web UI via the
gateway's DisplaySystem.

Also usable programmatically via the ``canvas.push`` capability.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from amplifier_core.models import ToolResult  # type: ignore[import-not-found]

__amplifier_module_type__ = "tool"

logger = logging.getLogger(__name__)

_VALID_CONTENT_TYPES = frozenset(
    {"chart", "html", "svg", "markdown", "code", "table"}
)


class CanvasPushTool:
    """Amplifier tool for pushing visual content to the canvas.

    The agent calls this tool to display charts, HTML, SVG, markdown,
    code blocks, or tables on the canvas web UI.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._coordinator: Any = None

    # -- Amplifier Tool protocol ----------------------------------------------

    @property
    def name(self) -> str:
        return "canvas_push"

    @property
    def description(self) -> str:
        return (
            "Push visual content to the canvas workspace. "
            "Supports chart (Vega-Lite), html, svg, markdown, code, and table. "
            "Content appears in a multi-panel web UI at localhost:8080/canvas."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content_type": {
                    "type": "string",
                    "enum": sorted(_VALID_CONTENT_TYPES),
                    "description": "Type of content to display.",
                },
                "content": {
                    "type": "string",
                    "description": (
                        "The content to display (Vega-Lite JSON, HTML, SVG, "
                        "markdown text, code, or JSON array for tables)."
                    ),
                },
                "id": {
                    "type": "string",
                    "description": (
                        "Stable identifier for update-in-place. "
                        "Same ID replaces previous content."
                    ),
                },
                "title": {
                    "type": "string",
                    "description": "Display title shown in the canvas sidebar.",
                },
            },
            "required": ["content_type", "content"],
        }

    async def execute(self, input: dict[str, Any]) -> ToolResult:  # noqa: A002
        """Push content to the canvas via the display capability."""
        content_type = input.get("content_type", "")
        content = input.get("content", "")

        # Validate required fields
        if not content_type:
            return ToolResult(
                success=False,
                error={"message": "Parameter 'content_type' is required."},
            )
        if not content:
            return ToolResult(
                success=False,
                error={"message": "Parameter 'content' is required."},
            )
        if content_type not in _VALID_CONTENT_TYPES:
            return ToolResult(
                success=False,
                error={
                    "message": (
                        f"Invalid content_type '{content_type}'. "
                        f"Must be one of: {', '.join(sorted(_VALID_CONTENT_TYPES))}"
                    ),
                },
            )

        try:
            return await self._push(input, content_type, content)
        except Exception as exc:
            logger.exception("canvas_push error")
            return ToolResult(
                success=False,
                error={"message": str(exc)},
            )

    async def _push(
        self,
        input: dict[str, Any],
        content_type: str,
        content: str,
    ) -> ToolResult:
        """Build JSON envelope and call the display capability."""
        # Lazy-query display capability on every call (per capability contracts)
        display = (
            self._coordinator.get_capability("display")
            if self._coordinator
            else None
        )
        if display is None:
            return ToolResult(
                success=False,
                error={
                    "message": (
                        "Display capability not available. "
                        "letsgo-canvas requires amplifier-bundle-letsgo (core). "
                        "Add it to your root bundle's includes."
                    ),
                },
            )

        content_id = input.get("id")
        title = input.get("title")

        # Build JSON envelope
        envelope: dict[str, Any] = {
            "content_type": content_type,
            "content": content,
        }
        if content_id:
            envelope["id"] = content_id
        if title:
            envelope["title"] = title

        metadata: dict[str, Any] = {"content_type": content_type}
        if content_id:
            metadata["id"] = content_id

        await display(json.dumps(envelope), metadata)

        output: dict[str, Any] = {"content_type": content_type}
        if content_id:
            output["id"] = content_id

        return ToolResult(success=True, output=output)


# ---------------------------------------------------------------------------
# Module mount point
# ---------------------------------------------------------------------------


async def mount(
    coordinator: Any,
    config: dict[str, Any] | None = None,
) -> None:
    """Mount the canvas push tool into the Amplifier coordinator.

    Configuration keys (all optional):
        (none currently — the tool delegates to DisplaySystem)
    """
    config = config or {}
    tool = CanvasPushTool(config=config)
    tool._coordinator = coordinator

    await coordinator.mount("tools", tool, name="tool-canvas")
    coordinator.register_capability("canvas.push", tool)

    logger.info("tool-canvas mounted")
```

### Step 7: Run tests to verify they pass

Run: `python -m pytest tests/test_tool_canvas.py -v`
Expected: all 13 tests PASS

### Step 8: Run full suite for regressions

Run: `python -m pytest tests/ -v`
Expected: no new failures

### Step 9: Commit

```
git add modules/tool-canvas/ tests/test_tool_canvas.py tests/conftest.py
git commit -m "feat(canvas): tool-canvas module with canvas_push action and display capability"
```

---

## Task 2: `CanvasChannel` — Adapter Core

**Files:**
- Create: `channels/canvas/pyproject.toml`
- Create: `channels/canvas/letsgo_channel_canvas/__init__.py`
- Create: `channels/canvas/letsgo_channel_canvas/adapter.py`
- Create: `channels/canvas/tests/__init__.py`
- Create: `channels/canvas/tests/test_canvas_adapter.py`

### Step 1: Create pyproject.toml

Create `channels/canvas/pyproject.toml`:

```toml
[project]
name = "letsgo-channel-canvas"
version = "0.1.0"
description = "Canvas visual workspace channel adapter for LetsGo gateway"
requires-python = ">=3.11"
dependencies = [
    "letsgo-gateway",
    "aiohttp>=3.9",
]

[project.entry-points."letsgo.channels"]
canvas = "letsgo_channel_canvas:CanvasChannel"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["letsgo_channel_canvas"]
```

### Step 2: Create package files

Create `channels/canvas/letsgo_channel_canvas/__init__.py`:

```python
"""Canvas channel adapter for the LetsGo gateway."""

from .adapter import CanvasChannel

__all__ = ["CanvasChannel"]
```

Create `channels/canvas/tests/__init__.py` (empty file):

```python
```

### Step 3: Write failing tests

Create `channels/canvas/tests/test_canvas_adapter.py`:

```python
"""Tests for Canvas channel adapter — core lifecycle and state management."""

from __future__ import annotations

import json
from typing import Any

import pytest
from letsgo_channel_canvas import CanvasChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_canvas(config: dict[str, Any] | None = None) -> CanvasChannel:
    return CanvasChannel(name="canvas", config=config or {})


def _make_outbound(
    text: str,
    channel_name: str = "canvas",
) -> OutboundMessage:
    return OutboundMessage(
        channel=ChannelType("canvas"),
        channel_name=channel_name,
        thread_id=None,
        text=text,
    )


def _make_envelope(
    content_type: str = "html",
    content: str = "<p>hello</p>",
    content_id: str | None = None,
    title: str | None = None,
) -> str:
    envelope: dict[str, Any] = {
        "content_type": content_type,
        "content": content,
    }
    if content_id is not None:
        envelope["id"] = content_id
    if title is not None:
        envelope["title"] = title
    return json.dumps(envelope)


# ---------------------------------------------------------------------------
# CanvasChannel — subclass check
# ---------------------------------------------------------------------------


class TestCanvasChannelSubclass:
    """CanvasChannel is a proper ChannelAdapter."""

    def test_is_channel_adapter(self) -> None:
        assert issubclass(CanvasChannel, ChannelAdapter)

    def test_instantiation(self) -> None:
        ch = _make_canvas(config={"host": "0.0.0.0", "port": 9090})
        assert ch.name == "canvas"
        assert ch.config["port"] == 9090
        assert not ch.is_running


# ---------------------------------------------------------------------------
# CanvasChannel — lifecycle
# ---------------------------------------------------------------------------


class TestCanvasChannelLifecycle:
    """Start/stop lifecycle management."""

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self) -> None:
        ch = _make_canvas()
        await ch.stop()  # should not raise
        assert not ch.is_running

    @pytest.mark.asyncio
    async def test_stop_after_start(self) -> None:
        ch = _make_canvas(config={"port": 0})  # port 0 = OS picks free port
        await ch.start()
        assert ch.is_running
        await ch.stop()
        assert not ch.is_running


# ---------------------------------------------------------------------------
# CanvasChannel — send and state management
# ---------------------------------------------------------------------------


class TestCanvasChannelSend:
    """send() parses JSON envelope and manages canvas state."""

    @pytest.mark.asyncio
    async def test_send_parses_json_envelope(self) -> None:
        ch = _make_canvas()
        envelope = _make_envelope(
            content_type="chart",
            content='{"$schema": "vega-lite"}',
            content_id="chart-1",
            title="My Chart",
        )
        msg = _make_outbound(text=envelope)
        result = await ch.send(msg)

        assert result is True
        state = ch.get_state()
        assert "chart-1" in state
        assert state["chart-1"]["content_type"] == "chart"
        assert state["chart-1"]["title"] == "My Chart"

    @pytest.mark.asyncio
    async def test_send_with_invalid_json(self) -> None:
        ch = _make_canvas()
        msg = _make_outbound(text="not json at all")
        result = await ch.send(msg)

        # Gracefully handled — returns True but stores as raw text
        assert result is True

    @pytest.mark.asyncio
    async def test_send_updates_existing_item(self) -> None:
        ch = _make_canvas()

        # First push
        envelope1 = _make_envelope(
            content_type="html", content="<p>v1</p>", content_id="item-1"
        )
        await ch.send(_make_outbound(text=envelope1))
        assert ch.get_state()["item-1"]["content"] == "<p>v1</p>"

        # Update same ID
        envelope2 = _make_envelope(
            content_type="html", content="<p>v2</p>", content_id="item-1"
        )
        await ch.send(_make_outbound(text=envelope2))
        assert ch.get_state()["item-1"]["content"] == "<p>v2</p>"

        # Only one item in state
        assert len(ch.get_state()) == 1

    @pytest.mark.asyncio
    async def test_send_without_id_auto_generates(self) -> None:
        ch = _make_canvas()
        envelope = _make_envelope(content_type="code", content="print('hi')")
        await ch.send(_make_outbound(text=envelope))

        state = ch.get_state()
        assert len(state) == 1
        # Auto-generated ID should exist
        item_id = next(iter(state))
        assert len(item_id) > 0
        assert state[item_id]["content_type"] == "code"

    @pytest.mark.asyncio
    async def test_get_state_returns_copy(self) -> None:
        ch = _make_canvas()
        envelope = _make_envelope(
            content_type="svg", content="<svg></svg>", content_id="svg-1"
        )
        await ch.send(_make_outbound(text=envelope))

        state1 = ch.get_state()
        state2 = ch.get_state()
        assert state1 == state2
        # Modifying returned state doesn't affect internal
        state1.pop("svg-1")
        assert "svg-1" in ch.get_state()

    @pytest.mark.asyncio
    async def test_state_ordering_newest_first(self) -> None:
        ch = _make_canvas()

        for i in range(3):
            envelope = _make_envelope(
                content_type="html",
                content=f"<p>item {i}</p>",
                content_id=f"item-{i}",
            )
            await ch.send(_make_outbound(text=envelope))

        state = ch.get_state()
        ids = list(state.keys())
        # Newest first
        assert ids == ["item-2", "item-1", "item-0"]
```

### Step 4: Run tests to verify they fail

Run: `PYTHONPATH=channels/canvas:gateway python -m pytest channels/canvas/tests/test_canvas_adapter.py -v`
Expected: FAIL — `ImportError: cannot import name 'CanvasChannel'` (adapter.py doesn't exist yet)

### Step 5: Implement adapter core

Create `channels/canvas/letsgo_channel_canvas/adapter.py`:

```python
"""Canvas channel adapter — serves a visual workspace web UI via WebSocket."""

from __future__ import annotations

import json
import logging
import uuid
from collections import OrderedDict
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import OutboundMessage

logger = logging.getLogger(__name__)


class CanvasChannel(ChannelAdapter):
    """Canvas visual workspace channel adapter.

    Serves a web UI at ``http://{host}:{port}/canvas`` with a WebSocket
    connection for real-time content updates.

    Config keys:
        host: Bind address (default: "localhost")
        port: HTTP port (default: 8080)
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._host: str = config.get("host", "localhost")
        self._port: int = config.get("port", 8080)
        # Ordered dict — newest items first (insert at beginning)
        self._canvas_state: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._ws_clients: set[Any] = set()
        self._app: Any = None
        self._runner: Any = None
        self._site: Any = None

    async def start(self) -> None:
        """Start the aiohttp web server for the canvas UI."""
        try:
            import aiohttp.web as web
        except ImportError:
            logger.warning(
                "aiohttp not installed — Canvas channel '%s' cannot start",
                self.name,
            )
            return

        self._app = web.Application()
        self._app.router.add_get("/canvas", self._handle_index)
        self._app.router.add_get("/canvas/state", self._handle_state)
        self._app.router.add_get("/canvas/ws", self._handle_websocket)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()
        self._running = True
        logger.info(
            "CanvasChannel '%s' started at http://%s:%s/canvas",
            self.name,
            self._host,
            self._port,
        )

    async def stop(self) -> None:
        """Stop the web server and disconnect all WebSocket clients."""
        # Close all WebSocket connections
        for ws in set(self._ws_clients):
            try:
                await ws.close()
            except Exception:
                pass
        self._ws_clients.clear()

        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        self._app = None
        self._site = None
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Parse JSON envelope from message text and update canvas state."""
        try:
            item = self._parse_envelope(message.text)
        except Exception:
            logger.exception("Failed to parse canvas envelope")
            # Store as raw text fallback
            item = {
                "id": str(uuid.uuid4())[:8],
                "content_type": "text",
                "content": message.text,
                "title": None,
            }

        item_id = item["id"]

        # Update or insert into ordered state (newest first)
        if item_id in self._canvas_state:
            # Remove and re-insert at beginning to maintain order
            del self._canvas_state[item_id]
        self._canvas_state[item_id] = {
            "content_type": item["content_type"],
            "content": item["content"],
            "title": item.get("title"),
        }
        self._canvas_state.move_to_end(item_id, last=False)

        # Broadcast to WebSocket clients
        ws_message = json.dumps(
            {
                "type": "update",
                "id": item_id,
                "content_type": item["content_type"],
                "content": item["content"],
                "title": item.get("title"),
            }
        )
        await self._broadcast(ws_message)

        return True

    def get_state(self) -> dict[str, dict[str, Any]]:
        """Return a copy of the current canvas state (newest first)."""
        return dict(self._canvas_state)

    # -- Internal helpers -----------------------------------------------------

    def _parse_envelope(self, text: str) -> dict[str, Any]:
        """Parse a JSON envelope from message text."""
        data = json.loads(text)
        return {
            "id": data.get("id") or str(uuid.uuid4())[:8],
            "content_type": data.get("content_type", "text"),
            "content": data.get("content", ""),
            "title": data.get("title"),
        }

    async def _broadcast(self, message: str) -> None:
        """Send a message to all connected WebSocket clients."""
        dead: set[Any] = set()
        for ws in self._ws_clients:
            try:
                await ws.send_str(message)
            except Exception:
                dead.add(ws)
        self._ws_clients -= dead

    # -- HTTP handlers --------------------------------------------------------

    async def _handle_index(self, request: Any) -> Any:
        """Serve the canvas web UI."""
        import aiohttp.web as web
        from pathlib import Path

        static_dir = Path(__file__).parent / "static"
        index_path = static_dir / "index.html"
        if not index_path.exists():
            return web.Response(text="Canvas UI not found", status=404)
        return web.FileResponse(index_path)

    async def _handle_state(self, request: Any) -> Any:
        """Return current canvas state as JSON."""
        import aiohttp.web as web

        # Return items list ordered newest first
        items = []
        for item_id, item in self._canvas_state.items():
            items.append(
                {
                    "id": item_id,
                    "content_type": item["content_type"],
                    "content": item["content"],
                    "title": item.get("title"),
                }
            )
        return web.json_response({"items": items})

    async def _handle_websocket(self, request: Any) -> Any:
        """Handle a WebSocket connection for real-time canvas updates."""
        import aiohttp.web as web

        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._ws_clients.add(ws)
        logger.debug("Canvas WebSocket client connected (%d total)", len(self._ws_clients))

        try:
            async for msg in ws:
                # Client → server messages (future: forms, user input)
                pass
        finally:
            self._ws_clients.discard(ws)
            logger.debug(
                "Canvas WebSocket client disconnected (%d remain)",
                len(self._ws_clients),
            )

        return ws
```

### Step 6: Run tests to verify they pass

Run: `PYTHONPATH=channels/canvas:gateway python -m pytest channels/canvas/tests/test_canvas_adapter.py -v`
Expected: all 10 tests PASS

### Step 7: Commit

```
git add channels/canvas/
git commit -m "feat(canvas): CanvasChannel adapter with JSON envelope parsing and state management"
```

---

## Task 3: `CanvasChannel` — WebSocket Transport

**Files:**
- Modify: `channels/canvas/tests/test_canvas_adapter.py` (append WebSocket tests)
- (adapter.py already has WebSocket support from Task 2 — these tests verify it)

### Step 1: Write WebSocket transport tests

Append to `channels/canvas/tests/test_canvas_adapter.py`:

```python
import asyncio

import aiohttp


# ---------------------------------------------------------------------------
# CanvasChannel — WebSocket transport
# ---------------------------------------------------------------------------


class TestCanvasChannelWebSocket:
    """WebSocket transport for real-time canvas updates."""

    @pytest.mark.asyncio
    async def test_websocket_connection_accepted(self) -> None:
        ch = _make_canvas(config={"port": 0})
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    f"http://localhost:{port}/canvas/ws"
                ) as ws:
                    assert not ws.closed
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_websocket_receives_pushed_content(self) -> None:
        ch = _make_canvas(config={"port": 0})
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    f"http://localhost:{port}/canvas/ws"
                ) as ws:
                    # Push content
                    envelope = _make_envelope(
                        content_type="html",
                        content="<p>hello</p>",
                        content_id="ws-test-1",
                        title="Test",
                    )
                    await ch.send(_make_outbound(text=envelope))

                    # Receive WebSocket message
                    msg = await asyncio.wait_for(ws.receive_json(), timeout=2)
                    assert msg["type"] == "update"
                    assert msg["id"] == "ws-test-1"
                    assert msg["content_type"] == "html"
                    assert msg["content"] == "<p>hello</p>"
                    assert msg["title"] == "Test"
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_multiple_clients_receive_same_update(self) -> None:
        ch = _make_canvas(config={"port": 0})
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            async with aiohttp.ClientSession() as session:
                ws1 = await session.ws_connect(
                    f"http://localhost:{port}/canvas/ws"
                )
                ws2 = await session.ws_connect(
                    f"http://localhost:{port}/canvas/ws"
                )

                envelope = _make_envelope(
                    content_type="svg",
                    content="<svg></svg>",
                    content_id="multi-test",
                )
                await ch.send(_make_outbound(text=envelope))

                msg1 = await asyncio.wait_for(ws1.receive_json(), timeout=2)
                msg2 = await asyncio.wait_for(ws2.receive_json(), timeout=2)

                assert msg1["id"] == "multi-test"
                assert msg2["id"] == "multi-test"

                await ws1.close()
                await ws2.close()
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_disconnected_clients_cleaned_up(self) -> None:
        ch = _make_canvas(config={"port": 0})
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]
            async with aiohttp.ClientSession() as session:
                ws = await session.ws_connect(
                    f"http://localhost:{port}/canvas/ws"
                )
                assert len(ch._ws_clients) == 1

                await ws.close()
                # Allow cleanup to happen
                await asyncio.sleep(0.1)

                # Push content — should clean up dead client
                envelope = _make_envelope(content_type="html", content="<p>after close</p>")
                await ch.send(_make_outbound(text=envelope))

                assert len(ch._ws_clients) == 0
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_state_endpoint_returns_current_items(self) -> None:
        ch = _make_canvas(config={"port": 0})
        await ch.start()
        try:
            port = ch._site._server.sockets[0].getsockname()[1]

            # Push two items
            for i in range(2):
                envelope = _make_envelope(
                    content_type="markdown",
                    content=f"# Item {i}",
                    content_id=f"state-{i}",
                )
                await ch.send(_make_outbound(text=envelope))

            # Fetch state
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://localhost:{port}/canvas/state"
                ) as resp:
                    assert resp.status == 200
                    data = await resp.json()
                    assert len(data["items"]) == 2
                    # Newest first
                    assert data["items"][0]["id"] == "state-1"
                    assert data["items"][1]["id"] == "state-0"
        finally:
            await ch.stop()
```

### Step 2: Run tests to verify they pass

Run: `PYTHONPATH=channels/canvas:gateway python -m pytest channels/canvas/tests/test_canvas_adapter.py -v`
Expected: all 15 tests PASS (10 core + 5 WebSocket)

### Step 3: Commit

```
git add channels/canvas/tests/test_canvas_adapter.py
git commit -m "test(canvas): WebSocket transport tests for CanvasChannel"
```

---

## Task 4: Canvas Web UI — Static HTML/JS

**Files:**
- Create: `channels/canvas/letsgo_channel_canvas/static/index.html`

No unit tests — validated by the integration test in Task 7 and manual browser testing.

### Step 1: Create static directory

```bash
mkdir -p channels/canvas/letsgo_channel_canvas/static
```

### Step 2: Create the canvas web UI

Create `channels/canvas/letsgo_channel_canvas/static/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LetsGo Canvas</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css">
<style>
  :root {
    --sidebar-width: 260px;
    --bg: #f8f9fa;
    --bg-sidebar: #ffffff;
    --bg-main: #ffffff;
    --border: #dee2e6;
    --text: #212529;
    --text-secondary: #6c757d;
    --accent: #0d6efd;
    --accent-bg: #e7f1ff;
    --badge-chart: #198754;
    --badge-html: #dc3545;
    --badge-svg: #6f42c1;
    --badge-markdown: #0dcaf0;
    --badge-code: #fd7e14;
    --badge-table: #20c997;
    --flash: rgba(13, 110, 253, 0.15);
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    height: 100vh;
    display: flex;
    overflow: hidden;
  }

  /* -- Sidebar ------------------------------------------------------------ */
  #sidebar {
    width: var(--sidebar-width);
    min-width: var(--sidebar-width);
    background: var(--bg-sidebar);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    height: 100vh;
  }
  #sidebar-header {
    padding: 16px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  #sidebar-header h1 {
    font-size: 16px;
    font-weight: 600;
  }
  #connection-status {
    width: 10px; height: 10px;
    border-radius: 50%;
    background: #dc3545;
    transition: background 0.3s;
  }
  #connection-status.connected { background: #198754; }
  #item-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
  }
  .item-entry {
    padding: 10px 12px;
    border-radius: 6px;
    cursor: pointer;
    margin-bottom: 4px;
    display: flex;
    align-items: center;
    gap: 8px;
    transition: background 0.15s;
  }
  .item-entry:hover { background: var(--bg); }
  .item-entry.selected { background: var(--accent-bg); }
  .item-entry.flash {
    animation: flash-update 0.6s ease-out;
  }
  @keyframes flash-update {
    0% { background: var(--flash); }
    100% { background: transparent; }
  }
  .item-badge {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    padding: 2px 6px;
    border-radius: 3px;
    color: #fff;
    white-space: nowrap;
  }
  .badge-chart { background: var(--badge-chart); }
  .badge-html { background: var(--badge-html); }
  .badge-svg { background: var(--badge-svg); }
  .badge-markdown { background: var(--badge-markdown); color: #000; }
  .badge-code { background: var(--badge-code); }
  .badge-table { background: var(--badge-table); }
  .badge-text { background: var(--text-secondary); }
  .item-title {
    font-size: 13px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
  }
  #empty-sidebar {
    padding: 24px 16px;
    text-align: center;
    color: var(--text-secondary);
    font-size: 13px;
  }

  /* -- Main panel --------------------------------------------------------- */
  #main {
    flex: 1;
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }
  #main-header {
    padding: 12px 20px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-main);
    display: flex;
    align-items: center;
    gap: 10px;
    min-height: 48px;
  }
  #main-header h2 {
    font-size: 14px;
    font-weight: 600;
    flex: 1;
  }
  #main-header .badge-type {
    font-size: 11px;
    color: var(--text-secondary);
  }
  #content-area {
    flex: 1;
    overflow: auto;
    padding: 20px;
    background: var(--bg-main);
  }
  #empty-content {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--text-secondary);
    font-size: 15px;
  }

  /* -- Content renderers -------------------------------------------------- */
  #content-area iframe {
    width: 100%;
    min-height: 400px;
    border: 1px solid var(--border);
    border-radius: 4px;
  }
  #content-area pre {
    background: #f6f8fa;
    padding: 16px;
    border-radius: 6px;
    overflow-x: auto;
    font-size: 13px;
    line-height: 1.5;
  }
  #content-area table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  #content-area th, #content-area td {
    text-align: left;
    padding: 8px 12px;
    border-bottom: 1px solid var(--border);
  }
  #content-area th {
    background: var(--bg);
    font-weight: 600;
    position: sticky;
    top: 0;
  }
  .markdown-body { line-height: 1.6; font-size: 14px; }
  .markdown-body h1 { font-size: 1.8em; margin: 0.5em 0 0.3em; }
  .markdown-body h2 { font-size: 1.4em; margin: 0.5em 0 0.3em; }
  .markdown-body h3 { font-size: 1.2em; margin: 0.5em 0 0.3em; }
  .markdown-body p { margin: 0.5em 0; }
  .markdown-body code {
    background: #f0f0f0; padding: 2px 5px; border-radius: 3px; font-size: 0.9em;
  }
  .markdown-body pre code { background: none; padding: 0; }
  .markdown-body ul, .markdown-body ol { margin: 0.5em 0; padding-left: 2em; }
  .markdown-body blockquote {
    border-left: 3px solid var(--border);
    padding-left: 12px;
    color: var(--text-secondary);
    margin: 0.5em 0;
  }
</style>
</head>
<body>

<!-- Sidebar -->
<div id="sidebar">
  <div id="sidebar-header">
    <h1>Canvas</h1>
    <div id="connection-status" title="Disconnected"></div>
  </div>
  <div id="item-list">
    <div id="empty-sidebar">Waiting for content...</div>
  </div>
</div>

<!-- Main panel -->
<div id="main">
  <div id="main-header">
    <h2 id="selected-title">No item selected</h2>
    <span id="selected-type" class="badge-type"></span>
  </div>
  <div id="content-area">
    <div id="empty-content">Select an item from the sidebar or push content via canvas_push</div>
  </div>
</div>

<!-- CDN dependencies -->
<script src="https://cdn.jsdelivr.net/npm/vega@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-lite@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-embed@6"></script>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>

<script>
(function() {
  'use strict';

  // -- State ----------------------------------------------------------------
  const items = new Map(); // id -> {content_type, content, title}
  const order = [];        // item ids, newest first
  let selectedId = null;
  let ws = null;
  let reconnectDelay = 1000;
  const MAX_RECONNECT = 30000;

  // -- DOM refs -------------------------------------------------------------
  const itemList = document.getElementById('item-list');
  const emptySidebar = document.getElementById('empty-sidebar');
  const contentArea = document.getElementById('content-area');
  const emptyContent = document.getElementById('empty-content');
  const selectedTitle = document.getElementById('selected-title');
  const selectedType = document.getElementById('selected-type');
  const statusDot = document.getElementById('connection-status');

  // -- WebSocket connection -------------------------------------------------
  function connect() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(proto + '//' + location.host + '/canvas/ws');

    ws.onopen = function() {
      statusDot.classList.add('connected');
      statusDot.title = 'Connected';
      reconnectDelay = 1000;
      // Restore state on reconnect
      fetchState();
    };

    ws.onclose = function() {
      statusDot.classList.remove('connected');
      statusDot.title = 'Disconnected — reconnecting...';
      scheduleReconnect();
    };

    ws.onerror = function() {
      ws.close();
    };

    ws.onmessage = function(event) {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'update') {
          handleUpdate(msg);
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };
  }

  function scheduleReconnect() {
    setTimeout(function() {
      reconnectDelay = Math.min(reconnectDelay * 1.5, MAX_RECONNECT);
      connect();
    }, reconnectDelay);
  }

  // -- State recovery -------------------------------------------------------
  function fetchState() {
    fetch('/canvas/state')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.items && data.items.length > 0) {
          // Clear and rebuild
          items.clear();
          order.length = 0;
          data.items.forEach(function(item) {
            items.set(item.id, {
              content_type: item.content_type,
              content: item.content,
              title: item.title
            });
            order.push(item.id);
          });
          renderSidebar();
          if (!selectedId || !items.has(selectedId)) {
            selectItem(order[0]);
          } else {
            renderContent(selectedId);
          }
        }
      })
      .catch(function(e) {
        console.error('Failed to fetch state:', e);
      });
  }

  // -- Update handler -------------------------------------------------------
  function handleUpdate(msg) {
    const id = msg.id;
    const isUpdate = items.has(id);

    items.set(id, {
      content_type: msg.content_type,
      content: msg.content,
      title: msg.title
    });

    // Update order — newest first
    const idx = order.indexOf(id);
    if (idx > -1) order.splice(idx, 1);
    order.unshift(id);

    renderSidebar();

    // Flash updated item
    if (isUpdate) {
      const el = document.querySelector('[data-id="' + id + '"]');
      if (el) {
        el.classList.add('flash');
        setTimeout(function() { el.classList.remove('flash'); }, 600);
      }
    }

    // Auto-select new items (not updates)
    if (!isUpdate) {
      selectItem(id);
    } else if (selectedId === id) {
      renderContent(id);
    }
  }

  // -- Sidebar rendering ----------------------------------------------------
  function renderSidebar() {
    if (order.length === 0) {
      itemList.innerHTML = '';
      itemList.appendChild(emptySidebar);
      return;
    }

    itemList.innerHTML = '';
    order.forEach(function(id) {
      const item = items.get(id);
      const entry = document.createElement('div');
      entry.className = 'item-entry' + (id === selectedId ? ' selected' : '');
      entry.setAttribute('data-id', id);
      entry.onclick = function() { selectItem(id); };

      const badge = document.createElement('span');
      badge.className = 'item-badge badge-' + (item.content_type || 'text');
      badge.textContent = item.content_type || 'text';

      const title = document.createElement('span');
      title.className = 'item-title';
      title.textContent = item.title || id;

      entry.appendChild(badge);
      entry.appendChild(title);
      itemList.appendChild(entry);
    });
  }

  // -- Content selection and rendering --------------------------------------
  function selectItem(id) {
    selectedId = id;
    renderSidebar(); // Update selection highlight
    renderContent(id);
  }

  function renderContent(id) {
    const item = items.get(id);
    if (!item) {
      contentArea.innerHTML = '';
      contentArea.appendChild(emptyContent);
      selectedTitle.textContent = 'No item selected';
      selectedType.textContent = '';
      return;
    }

    selectedTitle.textContent = item.title || id;
    selectedType.textContent = item.content_type;
    contentArea.innerHTML = '';

    switch (item.content_type) {
      case 'chart':
        renderChart(item.content);
        break;
      case 'html':
        renderHTML(item.content);
        break;
      case 'svg':
        renderSVG(item.content);
        break;
      case 'markdown':
        renderMarkdown(item.content);
        break;
      case 'code':
        renderCode(item.content);
        break;
      case 'table':
        renderTable(item.content);
        break;
      default:
        renderText(item.content);
    }
  }

  // -- Renderers ------------------------------------------------------------
  function renderChart(content) {
    var container = document.createElement('div');
    contentArea.appendChild(container);
    try {
      var spec = typeof content === 'string' ? JSON.parse(content) : content;
      vegaEmbed(container, spec, {actions: true, renderer: 'svg'})
        .catch(function(err) {
          container.textContent = 'Chart render error: ' + err.message;
        });
    } catch (e) {
      container.textContent = 'Invalid Vega-Lite spec: ' + e.message;
    }
  }

  function renderHTML(content) {
    var iframe = document.createElement('iframe');
    iframe.sandbox = 'allow-scripts';
    iframe.style.width = '100%';
    iframe.style.minHeight = '400px';
    iframe.style.border = '1px solid var(--border)';
    iframe.style.borderRadius = '4px';
    contentArea.appendChild(iframe);
    iframe.srcdoc = content;
    // Auto-resize iframe to content
    iframe.onload = function() {
      try {
        var h = iframe.contentDocument.body.scrollHeight;
        iframe.style.height = Math.max(h + 20, 200) + 'px';
      } catch(e) { /* cross-origin */ }
    };
  }

  function renderSVG(content) {
    var container = document.createElement('div');
    container.innerHTML = content;
    contentArea.appendChild(container);
  }

  function renderMarkdown(content) {
    var container = document.createElement('div');
    container.className = 'markdown-body';
    container.innerHTML = marked.parse(content);
    // Highlight code blocks
    container.querySelectorAll('pre code').forEach(function(block) {
      hljs.highlightElement(block);
    });
    contentArea.appendChild(container);
  }

  function renderCode(content) {
    var pre = document.createElement('pre');
    var code = document.createElement('code');
    code.textContent = content;
    pre.appendChild(code);
    contentArea.appendChild(pre);
    hljs.highlightElement(code);
  }

  function renderTable(content) {
    try {
      var data = typeof content === 'string' ? JSON.parse(content) : content;
      if (!Array.isArray(data) || data.length === 0) {
        contentArea.textContent = 'Empty or invalid table data';
        return;
      }

      var table = document.createElement('table');
      var thead = document.createElement('thead');
      var headerRow = document.createElement('tr');
      var keys = Object.keys(data[0]);

      keys.forEach(function(key) {
        var th = document.createElement('th');
        th.textContent = key;
        headerRow.appendChild(th);
      });
      thead.appendChild(headerRow);
      table.appendChild(thead);

      var tbody = document.createElement('tbody');
      data.forEach(function(row) {
        var tr = document.createElement('tr');
        keys.forEach(function(key) {
          var td = document.createElement('td');
          td.textContent = row[key] != null ? String(row[key]) : '';
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      contentArea.appendChild(table);
    } catch (e) {
      contentArea.textContent = 'Invalid table JSON: ' + e.message;
    }
  }

  function renderText(content) {
    var pre = document.createElement('pre');
    pre.style.whiteSpace = 'pre-wrap';
    pre.textContent = content;
    contentArea.appendChild(pre);
  }

  // -- Init -----------------------------------------------------------------
  connect();

})();
</script>
</body>
</html>
```

### Step 3: Update MANIFEST.in for static files

The `pyproject.toml` already specifies `packages = ["letsgo_channel_canvas"]` and hatchling includes package data by default. No additional configuration needed — `static/index.html` is inside the package directory.

### Step 4: Verify static file is served

Run: `PYTHONPATH=channels/canvas:gateway python -c "from pathlib import Path; p = Path('channels/canvas/letsgo_channel_canvas/static/index.html'); print('EXISTS' if p.exists() else 'MISSING')"`
Expected: `EXISTS`

### Step 5: Commit

```
git add channels/canvas/letsgo_channel_canvas/static/
git commit -m "feat(canvas): multi-panel web UI with WebSocket, Vega-Lite, markdown, and code rendering"
```

---

## Task 5: Satellite Bundle Structure

**Files:**
- Create: `canvas/bundle.md`
- Create: `canvas/behaviors/canvas-capabilities.yaml`
- Create: `canvas/context/canvas-awareness.md`
- Create: `canvas/skills/canvas-design/SKILL.md`
- Create: `docs/CANVAS_WIRE_FORMAT.md`

No tests for bundle structure — validated by Amplifier's bundle loader at runtime.

### Step 1: Create bundle.md

Create `canvas/bundle.md`:

```markdown
---
bundle:
  name: letsgo-canvas
  version: 0.1.0
  description: Visual workspace for LetsGo — push charts, HTML, SVG, markdown, code, and tables to a web UI
includes:
  - bundle: letsgo-canvas:behaviors/canvas-capabilities
---

# LetsGo Canvas

Visual workspace for the LetsGo gateway — agents push rich content to a multi-panel web UI via the DisplaySystem protocol.

@letsgo-canvas:context/canvas-awareness.md
```

### Step 2: Create behavior YAML

Create `canvas/behaviors/canvas-capabilities.yaml`:

```yaml
bundle:
  name: behavior-canvas-capabilities
  version: 1.0.0
  description: Canvas visual workspace capabilities for LetsGo

tools:
  - module: tool-canvas
    source: ../modules/tool-canvas
    config: {}

context:
  include:
    - letsgo-canvas:context/canvas-awareness.md
```

### Step 3: Create canvas awareness context

Create `canvas/context/canvas-awareness.md`:

```markdown
# Canvas Capabilities

You have access to a visual workspace (canvas) for displaying rich content to the user.

## canvas_push Tool

Use the `canvas_push` tool to display visual content on the canvas web UI:

- **chart**: Vega-Lite JSON specs rendered as interactive charts
  - Content: Valid Vega-Lite JSON specification string
- **html**: Arbitrary HTML rendered in a sandboxed iframe
  - Content: HTML string
- **svg**: Inline SVG graphics
  - Content: SVG markup string
- **markdown**: Rendered markdown with syntax-highlighted code blocks
  - Content: Markdown text
- **code**: Syntax-highlighted code blocks
  - Content: Source code string
- **table**: Tabular data rendered as an HTML table
  - Content: JSON array of objects (e.g., `[{"name": "Alice", "score": 95}]`)

## Parameters

- `content_type` (required): One of chart, html, svg, markdown, code, table
- `content` (required): The content string
- `id` (optional): Stable identifier — use the same ID to update an existing item in-place
- `title` (optional): Display title shown in the sidebar

## Tips

- Use `id` when you want to update content (e.g., a chart that refreshes with new data)
- Omit `id` when pushing one-off content
- Charts work best with self-contained Vega-Lite specs (include `$schema`, `data`, `mark`, `encoding`)
- Tables expect a JSON array of flat objects — all keys become column headers
- The canvas web UI is at `http://localhost:8080/canvas` — tell the user to open it in their browser

## Fallback

If no canvas channel is connected, content is sent as text to the first available chat channel. The JSON envelope will appear as-is — this is expected behavior for users who haven't enabled the canvas.
```

### Step 4: Create canvas design skill

Create `canvas/skills/canvas-design/SKILL.md`:

```markdown
---
skill:
  name: canvas-design
  version: 1.0.0
  description: Guide for using the canvas visual workspace effectively
  tags:
    - canvas
    - visualization
    - design
---

# Canvas Design Guide

## Content Type Selection

Choose the right content type for your visualization:

| Content Type | Best For | Content Format |
|-------------|----------|----------------|
| `chart` | Data visualization, graphs, plots | Vega-Lite JSON spec |
| `html` | Rich formatted content, interactive widgets | HTML string |
| `svg` | Diagrams, icons, custom graphics | SVG markup |
| `markdown` | Documentation, formatted text, mixed content | Markdown text |
| `code` | Source code, configuration files, logs | Plain text |
| `table` | Tabular data, comparison tables, results | JSON array of objects |

## Vega-Lite Charts

For charts, provide a complete Vega-Lite spec:

```json
{
  "$schema": "https://vega-lite.github.io/schema/v5.json",
  "data": {"values": [{"x": 1, "y": 2}, {"x": 2, "y": 4}]},
  "mark": "line",
  "encoding": {
    "x": {"field": "x", "type": "quantitative"},
    "y": {"field": "y", "type": "quantitative"}
  }
}
```

## Update-in-Place

Use the `id` parameter to update existing content:

1. First push: `canvas_push(content_type="chart", content=spec, id="sales-chart", title="Sales")`
2. Update: `canvas_push(content_type="chart", content=new_spec, id="sales-chart", title="Sales (Updated)")`

The item in the sidebar updates in place with a brief flash animation.

## Table Data Format

Tables expect a JSON array of objects. All keys become column headers:

```json
[
  {"Name": "Alice", "Score": 95, "Grade": "A"},
  {"Name": "Bob", "Score": 87, "Grade": "B+"},
  {"Name": "Carol", "Score": 92, "Grade": "A-"}
]
```

## Gateway Configuration

Add a canvas channel to `~/.letsgo/gateway/config.yaml`:

```yaml
channels:
  - name: canvas
    type: canvas
    config:
      host: localhost
      port: 8080
```

Install the channel package: `pip install letsgo-channel-canvas`
```

### Step 5: Create wire format documentation

Create `docs/CANVAS_WIRE_FORMAT.md`:

```markdown
# Canvas Wire Format

The JSON envelope is the shared contract between `tool-canvas` (producer) and `CanvasChannel` (consumer). Both components sit on opposite sides of the `DisplaySystem` protocol boundary but must agree on this structure.

## Envelope Schema

```json
{
  "content_type": "chart",
  "content": "<vega-lite-spec-or-html-or-svg-or-markdown>",
  "id": "chart-1",
  "title": "Monthly Revenue"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content_type` | string | Yes | One of: `chart`, `html`, `svg`, `markdown`, `code`, `table` |
| `content` | string | Yes | The actual content (Vega-Lite JSON, HTML, SVG, markdown text, code, or JSON array for tables) |
| `id` | string | No | Stable identifier for update-in-place — same ID replaces previous content |
| `title` | string | No | Display title shown in the canvas sidebar |

## Transport

The envelope travels as a JSON string in `OutboundMessage.text`:

```
tool-canvas → json.dumps(envelope) → DisplaySystem.display(text, metadata)
             → OutboundMessage(text=json_string)
             → CanvasChannel.send(message) → json.loads(message.text)
```

The `DisplaySystem` is a transparent pipe — it routes but does not interpret the content. Content semantics live at the edges.

## Content Type Details

### `chart`
Content is a complete Vega-Lite specification as a JSON string. The canvas UI parses it and renders via `vega-embed`.

### `html`
Content is an HTML string rendered in a sandboxed iframe (`sandbox="allow-scripts"`).

### `svg`
Content is an SVG markup string injected as inline SVG.

### `markdown`
Content is a markdown string rendered via the `marked` library with `highlight.js` for code blocks.

### `code`
Content is a source code string rendered in a `<pre><code>` block with syntax highlighting.

### `table`
Content is a JSON string containing an array of flat objects. All keys become column headers, values become cells.

## Update-in-Place Semantics

When `id` is provided:
- If an item with the same `id` exists, it is replaced with the new content
- The item moves to the top of the sidebar (newest position)
- Connected WebSocket clients see a brief flash animation

When `id` is omitted:
- A random 8-character ID is generated
- A new item is created at the top of the sidebar

## WebSocket Message Format

The `CanvasChannel` pushes updates to connected browsers as JSON over WebSocket:

```json
{
  "type": "update",
  "id": "chart-1",
  "content_type": "chart",
  "content": "<vega-lite-spec>",
  "title": "Monthly Revenue"
}
```

## State Recovery

On WebSocket reconnection, the client fetches `GET /canvas/state` which returns:

```json
{
  "items": [
    {"id": "chart-1", "content_type": "chart", "content": "...", "title": "..."},
    {"id": "html-2", "content_type": "html", "content": "...", "title": null}
  ]
}
```

Items are ordered newest first.
```

### Step 6: Commit

```
git add canvas/ docs/CANVAS_WIRE_FORMAT.md
git commit -m "feat(canvas): satellite bundle structure — bundle.md, behaviors, context, skill, wire format docs"
```

---

## Task 6: Update Setup Wizard Recipe

**Files:**
- Modify: `recipes/setup-wizard.yaml` (extend satellite-setup stage)

### Step 1: Read current satellite-setup step

The satellite-setup stage already mentions Canvas (lines 136-139):

```yaml
          **Canvas** (amplifier-bundle-letsgo-canvas)
          - Rich visual output (charts, HTML, SVG)
          - Web UI at localhost:8080/canvas
          - Auto-render tool outputs
```

### Step 2: Add canvas configuration step to satellite-setup stage

Edit `recipes/setup-wizard.yaml` — add a new step after `configure-voice` (insert between the `configure-voice` step's `timeout: 300` and the `approval:` block of the `satellite-setup` stage):

```yaml
      - id: configure-canvas
        agent: self
        prompt: >
          If canvas was selected in {{satellite_config}}:

          1. **Canvas channel setup:**
             - Ask: What port should the canvas web UI use? (default: 8080)
             - Ask: Bind to localhost only or all interfaces? (default: localhost)
             - Note: The canvas URL will be http://{host}:{port}/canvas

          2. **Install canvas channel package:**
             - Run: pip install letsgo-channel-canvas

          3. **Update gateway config:**
             - Add canvas channel to ~/.letsgo/gateway/config.yaml:
               channels:
                 - name: canvas
                   type: canvas
                   config:
                     host: "<chosen-host>"
                     port: <chosen-port>

          4. **Verify:**
             - Confirm the channel package is installed
             - Report the canvas URL

          If canvas was NOT selected, skip this step entirely and report "Canvas: skipped".
        output: canvas_config
        timeout: 180
```

Also update the approval prompt of the `satellite-setup` stage to include canvas configuration:

Replace the approval section:
```yaml
    approval:
      required: true
      prompt: |
        Satellite setup:

        {{satellite_config}}

        Voice configuration: {{voice_config}}

        Proceed to daemon startup?
```

With:
```yaml
    approval:
      required: true
      prompt: |
        Satellite setup:

        {{satellite_config}}

        Voice configuration: {{voice_config}}

        Canvas configuration: {{canvas_config}}

        Proceed to daemon startup?
```

### Step 3: Validate YAML

Run: `python -c "import yaml; yaml.safe_load(open('recipes/setup-wizard.yaml')); print('Valid YAML')"`
Expected: `Valid YAML`

### Step 4: Commit

```
git add recipes/setup-wizard.yaml
git commit -m "feat(canvas): add canvas configuration step to setup-wizard recipe"
```

---

## Task 7: Integration Tests — Full Canvas Pipeline

**Files:**
- Create: `tests/test_gateway/test_canvas_integration.py`

### Step 1: Write integration tests

Create `tests/test_gateway/test_canvas_integration.py`:

```python
"""Integration tests — full canvas pipeline from tool-canvas to CanvasChannel."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from letsgo_gateway.daemon import GatewayDaemon
from letsgo_gateway.display import GatewayDisplaySystem
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_daemon(tmp_path: Path, **config_overrides: Any) -> GatewayDaemon:
    """Create a GatewayDaemon with given config overrides."""
    config = {
        "channels": [],
        "files_dir": str(tmp_path / "files"),
        **config_overrides,
    }
    return GatewayDaemon(config=config)


class FakeCanvasChannel:
    """Fake canvas channel that records sent messages."""

    def __init__(self, name: str = "canvas") -> None:
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
# tool-canvas → DisplaySystem → CanvasChannel
# ---------------------------------------------------------------------------


class TestToolToDisplay:
    """tool-canvas execute → DisplaySystem routes to canvas channel."""

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

        envelope = json.dumps(
            {"content_type": "html", "content": "<p>hello</p>"}
        )

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
        await display.display(
            envelope, metadata={"content_type": "svg", "id": "svg-1"}
        )

        assert "svg-1" in display.canvas_state
        assert display.canvas_state["svg-1"]["content_type"] == "svg"

    @pytest.mark.asyncio
    async def test_display_with_no_channels(self) -> None:
        """DisplaySystem with no channels doesn't crash."""
        display = GatewayDisplaySystem(channels={})
        envelope = json.dumps(
            {"content_type": "markdown", "content": "# Hello"}
        )
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
        from amplifier_module_tool_canvas import CanvasPushTool, mount

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

        await tool.execute(
            {"content_type": "html", "content": "<p>test</p>"}
        )

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
                channels=[{"name": "canvas", "type": "canvas", "config": {}}],
            )
            assert "canvas" in daemon._channels

    def test_daemon_without_canvas_works(self, tmp_path: Path) -> None:
        """Daemon works fine without any canvas channel."""
        daemon = _make_daemon(tmp_path)
        assert "canvas" not in daemon._channels
```

### Step 2: Run integration tests

Run: `python -m pytest tests/test_gateway/test_canvas_integration.py -v`
Expected: all 7 tests PASS

### Step 3: Run the complete test suite

Run: `python -m pytest tests/ -v`
Expected: all tests PASS (existing ~391 + new ~13 tool-canvas tests + ~7 integration tests)

### Step 4: Commit

```
git add tests/test_gateway/test_canvas_integration.py
git commit -m "test(canvas): integration tests for full canvas pipeline through DisplaySystem"
```

---

## Task 8: Final Verification and Cleanup

**Files:**
- Verify: all existing files (no modifications needed)

### Step 1: Run full gateway test suite

Run: `python -m pytest tests/ -v`
Expected: no new failures (3 pre-existing telegram/discord/slack stub failures unchanged)

### Step 2: Run canvas channel adapter tests

Run: `PYTHONPATH=channels/canvas:gateway python -m pytest channels/canvas/tests/ -v`
Expected: all 15 tests PASS

### Step 3: Run python_check on all new files

Run: `python_check` on:
- `modules/tool-canvas/`
- `channels/canvas/letsgo_channel_canvas/`
- `tests/test_tool_canvas.py`
- `tests/test_gateway/test_canvas_integration.py`

Expected: all clean

### Step 4: Verify git log

```
git log --oneline --no-decorate
```

Expected commits (newest first):
```
test(canvas): integration tests for full canvas pipeline through DisplaySystem
feat(canvas): add canvas configuration step to setup-wizard recipe
feat(canvas): satellite bundle structure — bundle.md, behaviors, context, skill, wire format docs
feat(canvas): multi-panel web UI with WebSocket, Vega-Lite, markdown, and code rendering
test(canvas): WebSocket transport tests for CanvasChannel
feat(canvas): CanvasChannel adapter with JSON envelope parsing and state management
feat(canvas): tool-canvas module with canvas_push action and display capability
```

---

## Summary

| Task | What | Files Created | Files Modified | Tests |
|------|------|---------------|----------------|-------|
| 1 | tool-canvas module | `pyproject.toml`, `__init__.py`, `test_tool_canvas.py` | `conftest.py` | 13 |
| 2 | CanvasChannel core | `pyproject.toml`, `__init__.py`, `adapter.py`, `test_canvas_adapter.py` | — | 10 |
| 3 | WebSocket transport | — | `test_canvas_adapter.py` | 5 |
| 4 | Canvas web UI | `static/index.html` | — | 0 (manual) |
| 5 | Satellite bundle | `bundle.md`, behavior, context, skill, `CANVAS_WIRE_FORMAT.md` | — | 0 |
| 6 | Recipe update | — | `setup-wizard.yaml` | 0 (validate) |
| 7 | Integration tests | `test_canvas_integration.py` | — | 7 |
| 8 | Final verification | — | — | 0 (verify) |
| **Total** | | **~16 new files** | **~2 modified** | **~35 tests** |

### Commit sequence
1. `feat(canvas): tool-canvas module with canvas_push action and display capability`
2. `feat(canvas): CanvasChannel adapter with JSON envelope parsing and state management`
3. `test(canvas): WebSocket transport tests for CanvasChannel`
4. `feat(canvas): multi-panel web UI with WebSocket, Vega-Lite, markdown, and code rendering`
5. `feat(canvas): satellite bundle structure — bundle.md, behaviors, context, skill, wire format docs`
6. `feat(canvas): add canvas configuration step to setup-wizard recipe`
7. `test(canvas): integration tests for full canvas pipeline through DisplaySystem`