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

_VALID_CONTENT_TYPES = frozenset({"chart", "html", "svg", "markdown", "code", "table"})


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
            self._coordinator.get_capability("display") if self._coordinator else None
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
