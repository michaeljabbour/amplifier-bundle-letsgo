"""Event segmentation via contextual boundary detection.

Inspired by boundary cells in human medial temporal lobe that detect
contextual shifts and segment continuous experience into discrete episodes.

Detects when tool activity shifts topics by measuring keyword overlap
in a sliding window. Boundaries are stored as facts in the memory store.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from amplifier_core.models import HookResult

logger = logging.getLogger(__name__)

__amplifier_module_type__ = "hook"

# Inline stopwords — canonical set shared with compression and store modules
_STOPS = frozenset(
    {
        "a",
        "all",
        "also",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "but",
        "by",
        "can",
        "each",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "in",
        "into",
        "is",
        "it",
        "its",
        "just",
        "me",
        "more",
        "my",
        "not",
        "of",
        "on",
        "one",
        "or",
        "our",
        "out",
        "so",
        "some",
        "than",
        "that",
        "the",
        "this",
        "to",
        "was",
        "we",
        "what",
        "when",
        "who",
        "will",
        "with",
        "you",
        "your",
    }
)


def _extract_text(tool_output: Any) -> str:
    """Extract plain text from tool output."""
    if isinstance(tool_output, str):
        return tool_output
    if isinstance(tool_output, dict):
        for key in ("output", "content", "text", "result", "stdout"):
            if key in tool_output and tool_output[key]:
                val = tool_output[key]
                return val if isinstance(val, str) else str(val)
        return str(tool_output)
    return str(tool_output) if tool_output else ""


def _extract_keywords(text: str, max_keywords: int = 12) -> set[str]:
    """Extract meaningful keywords from text."""
    words = re.findall(r"[a-z_][a-z0-9_]{2,}", text.lower())
    filtered = [w for w in words if w not in _STOPS]
    counts: dict[str, int] = {}
    for w in filtered:
        counts[w] = counts.get(w, 0) + 1
    ranked = sorted(counts, key=lambda k: counts[k], reverse=True)
    return set(ranked[:max_keywords])


class BoundaryDetector:
    """Detects contextual boundaries in tool activity streams.

    Maintains a per-session sliding window of keyword sets. When Jaccard
    similarity between the current output's keywords and the window drops
    below threshold, a boundary is declared and recorded as a fact.
    """

    def __init__(
        self,
        store: Any,
        *,
        window_size: int = 5,
        similarity_threshold: float = 0.25,
    ) -> None:
        self._store = store
        self._window_size = window_size
        self._threshold = similarity_threshold
        self._windows: dict[str, list[set[str]]] = {}
        self._boundaries: dict[str, list[dict[str, Any]]] = {}

    @property
    def name(self) -> str:
        return "memory-boundaries"

    async def execute(self, event: str, data: dict[str, Any]) -> HookResult:
        """Hook handler for tool:post events."""
        session_id = data.get("session_id", "default")
        tool_output = data.get("result", {})
        tool_name = data.get("tool_name", "")

        content = _extract_text(tool_output)
        if not content or len(content) < 30:
            return HookResult(action="continue")

        keywords = _extract_keywords(content)
        is_boundary = self._check_boundary(session_id, keywords)

        if is_boundary:
            boundary_info = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tool_name": tool_name,
                "segment_index": len(self._boundaries.get(session_id, [])),
                "after_keywords": sorted(keywords)[:5],
            }
            self._boundaries.setdefault(session_id, []).append(boundary_info)

            try:
                self._store.store_fact(
                    subject=session_id,
                    predicate="boundary_detected",
                    object_value=json.dumps(boundary_info),
                )
            except Exception as e:
                logger.debug("Failed to store boundary fact: %s", e)

        return HookResult(action="continue")

    def _check_boundary(self, session_id: str, keywords: set[str]) -> bool:
        """Compare current keywords against sliding window."""
        window = self._windows.setdefault(session_id, [])

        if not window:
            window.append(keywords)
            return False

        window_union: set[str] = set()
        for kw_set in window:
            window_union |= kw_set

        if not window_union and not keywords:
            similarity = 1.0
        elif not window_union or not keywords:
            similarity = 0.0
        else:
            similarity = len(window_union & keywords) / len(window_union | keywords)

        window.append(keywords)
        if len(window) > self._window_size:
            window.pop(0)

        return similarity < self._threshold

    # --- Capability methods (memory.boundaries) ---

    def get_boundaries(self, session_id: str) -> list[dict[str, Any]]:
        """Return all detected boundaries for a session."""
        return list(self._boundaries.get(session_id, []))

    def get_current_segment_index(self, session_id: str) -> int:
        """Return the current segment number (0-indexed)."""
        return len(self._boundaries.get(session_id, []))


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> None:
    """Mount the boundary detection hook."""
    store = coordinator.get_capability("memory.store")
    if store is None:
        logger.info("memory.store not available; boundary detection disabled")
        return

    cfg = config or {}
    detector = BoundaryDetector(
        store=store,
        window_size=cfg.get("window_size", 5),
        similarity_threshold=cfg.get("similarity_threshold", 0.25),
    )

    coordinator.hooks.register(
        event="tool:post",
        handler=detector.execute,
        priority=100,
        name="memory-boundaries.tool_post",
    )
    coordinator.register_capability("memory.boundaries", detector)
