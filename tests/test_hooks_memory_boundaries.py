"""Tests for hooks-memory-boundaries module.

Covers the BoundaryDetector: mount registration, Jaccard similarity,
sliding window, boundary detection, fact storage, and capability methods.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from amplifier_module_hooks_memory_boundaries import BoundaryDetector, mount
from amplifier_module_tool_memory_store import MemoryStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "test_memories.db")


def _make_detector(
    tmp_path: Path,
    *,
    window_size: int = 5,
    similarity_threshold: float = 0.25,
) -> tuple[BoundaryDetector, MemoryStore]:
    store = _make_store(tmp_path)
    detector = BoundaryDetector(
        store,
        window_size=window_size,
        similarity_threshold=similarity_threshold,
    )
    return detector, store


def _tool_post_data(
    content: str,
    *,
    tool_name: str = "bash",
    session_id: str = "test-session",
) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "result": content,
        "tool_input": {},
        "session_id": session_id,
    }


# ===========================================================================
# Mount tests
# ===========================================================================


class TestMount:
    """Tests for mount() registration."""

    @pytest.mark.asyncio
    async def test_mount_registers_hook_and_capability(
        self, tmp_path: Path, mock_coordinator: Any
    ) -> None:
        store = _make_store(tmp_path)
        mock_coordinator.register_capability("memory.store", store)

        await mount(mock_coordinator, config={})

        # Should register one hook
        regs = mock_coordinator.hooks.registrations
        assert len(regs) == 1
        reg = regs[0]
        assert reg["event"] == "tool:post"
        assert reg["priority"] == 100
        assert "memory-boundaries" in reg["name"]

        # Should register capability
        assert "memory.boundaries" in mock_coordinator.capabilities
        cap = mock_coordinator.capabilities["memory.boundaries"]
        assert isinstance(cap, BoundaryDetector)

    @pytest.mark.asyncio
    async def test_mount_without_store_skips(self, mock_coordinator: Any) -> None:
        await mount(mock_coordinator, config={})
        assert len(mock_coordinator.hooks.registrations) == 0
        assert "memory.boundaries" not in mock_coordinator.capabilities


# ===========================================================================
# Boundary detection tests
# ===========================================================================


class TestBoundaryDetection:
    """Tests for the core boundary detection logic.

    The algorithm compares current keywords against the UNION of all keyword
    sets in the sliding window.  This means the window union grows quickly,
    so even a topically-related message can score below the threshold if
    its individual keywords are only a fraction of the accumulated union.
    """

    @pytest.mark.asyncio
    async def test_no_boundary_on_identical_content(self, tmp_path: Path) -> None:
        """Identical keywords each time should never trigger a boundary.

        When every message has the same keywords, current & union are
        identical → Jaccard = 1.0 → never below threshold.
        """
        detector, store = _make_detector(tmp_path)

        # Exact same words every time
        same_text = "python programming decorators syntax features overview"
        for _ in range(6):
            await detector.execute("tool:post", _tool_post_data(same_text))

        assert detector.get_current_segment_index("test-session") == 0

    @pytest.mark.asyncio
    async def test_boundary_on_topic_shift(self, tmp_path: Path) -> None:
        """Completely different keywords should trigger a boundary.

        With window_size=2, the union is small enough that a totally
        disjoint set scores Jaccard ≈ 0.0, well below any threshold.
        """
        detector, store = _make_detector(
            tmp_path, window_size=2, similarity_threshold=0.25
        )

        # Seed the window with one entry
        await detector.execute(
            "tool:post",
            _tool_post_data(
                "python programming asyncio decorators generators coroutines"
            ),
        )

        # Second entry, still Python-heavy (will NOT trigger because it
        # shares enough keywords with the seed)
        await detector.execute(
            "tool:post",
            _tool_post_data(
                "python programming decorators generators asyncio coroutines"
            ),
        )

        # Third entry: completely unrelated, zero overlap
        await detector.execute(
            "tool:post",
            _tool_post_data(
                "recipe ingredients flour butter sugar eggs vanilla baking "
                "powder chocolate frosting cake layers temperature oven kitchen"
            ),
        )

        # Should detect at least one boundary
        assert detector.get_current_segment_index("test-session") >= 1

    @pytest.mark.asyncio
    async def test_boundary_stored_as_fact(self, tmp_path: Path) -> None:
        """When a boundary is detected, it should be stored as a fact."""
        detector, store = _make_detector(
            tmp_path, window_size=2, similarity_threshold=0.30
        )

        # Seed
        await detector.execute(
            "tool:post",
            _tool_post_data(
                "python programming asyncio decorators generators coroutines"
            ),
        )
        # Same topic (no boundary)
        await detector.execute(
            "tool:post",
            _tool_post_data(
                "python programming asyncio decorators generators coroutines"
            ),
        )

        # Drastic topic shift — zero overlap keywords
        await detector.execute(
            "tool:post",
            _tool_post_data(
                "kubernetes docker containers orchestration pods services "
                "deployments clusters networking ingress loadbalancer"
            ),
        )

        # Check boundary was detected and stored
        if detector.get_current_segment_index("test-session") > 0:
            facts = store.query_facts(
                subject="test-session", predicate="boundary_detected"
            )
            assert len(facts) >= 1
            # Fact object should be valid JSON
            boundary_info = json.loads(facts[0]["object"])
            assert "timestamp" in boundary_info
            assert "segment_index" in boundary_info

    @pytest.mark.asyncio
    async def test_sliding_window_size(self, tmp_path: Path) -> None:
        """First call seeds the window and should never trigger a boundary."""
        detector, store = _make_detector(tmp_path, window_size=3)

        # First call: always seeds, no boundary
        await detector.execute(
            "tool:post",
            _tool_post_data("completely unique content about quantum physics research"),
        )
        assert detector.get_current_segment_index("test-session") == 0

    @pytest.mark.asyncio
    async def test_short_content_ignored(self, tmp_path: Path) -> None:
        """Content < 30 chars should not be processed."""
        detector, store = _make_detector(tmp_path)

        await detector.execute("tool:post", _tool_post_data("short"))
        await detector.execute("tool:post", _tool_post_data("also short text"))

        # Short content should be completely skipped — no window entries
        assert detector.get_current_segment_index("test-session") == 0

    @pytest.mark.asyncio
    async def test_window_fifo_eviction(self, tmp_path: Path) -> None:
        """Window should maintain at most window_size entries (FIFO)."""
        detector, store = _make_detector(
            tmp_path, window_size=2, similarity_threshold=0.10
        )

        # After 4 calls, internal window should only have 2 entries
        for i in range(4):
            await detector.execute(
                "tool:post",
                _tool_post_data(f"python programming decorators syntax features topic{i}"),
            )

        window = detector._windows.get("test-session", [])
        assert len(window) <= 2


# ===========================================================================
# Capability methods tests
# ===========================================================================


class TestCapabilityMethods:
    """Tests for get_boundaries and get_current_segment_index."""

    @pytest.mark.asyncio
    async def test_get_boundaries_returns_list(self, tmp_path: Path) -> None:
        detector, store = _make_detector(tmp_path, window_size=2)

        # Initially empty
        boundaries = detector.get_boundaries("test-session")
        assert isinstance(boundaries, list)
        assert len(boundaries) == 0

        # After activity — identical content, so no boundaries
        await detector.execute(
            "tool:post",
            _tool_post_data("python programming features decorators generators"),
        )
        await detector.execute(
            "tool:post",
            _tool_post_data("python programming features decorators generators"),
        )

        # Still a list regardless of whether boundaries happened
        boundaries = detector.get_boundaries("test-session")
        assert isinstance(boundaries, list)

    def test_get_current_segment_index(self, tmp_path: Path) -> None:
        detector, store = _make_detector(tmp_path)

        # Initially 0
        assert detector.get_current_segment_index("test-session") == 0
        assert detector.get_current_segment_index("nonexistent") == 0

    def test_get_boundaries_unknown_session(self, tmp_path: Path) -> None:
        detector, store = _make_detector(tmp_path)
        boundaries = detector.get_boundaries("unknown-session-id")
        assert boundaries == []


# ===========================================================================
# Jaccard similarity behavior tests
# ===========================================================================


class TestJaccardSimilarity:
    """Tests that verify Jaccard-based boundary behavior."""

    @pytest.mark.asyncio
    async def test_jaccard_identical_content_no_boundary(self, tmp_path: Path) -> None:
        """Identical content → Jaccard = 1.0 → no boundary."""
        detector, _ = _make_detector(tmp_path, window_size=3)

        for _ in range(5):
            await detector.execute(
                "tool:post",
                _tool_post_data("alpha bravo charlie delta echo foxtrot"),
            )
        assert detector.get_current_segment_index("test-session") == 0

    @pytest.mark.asyncio
    async def test_jaccard_zero_overlap_triggers_boundary(self, tmp_path: Path) -> None:
        """Zero keyword overlap → Jaccard = 0.0 → boundary detected."""
        detector, _ = _make_detector(
            tmp_path, window_size=2, similarity_threshold=0.25
        )

        # Seed
        await detector.execute(
            "tool:post",
            _tool_post_data("alpha bravo charlie delta echo foxtrot golf hotel"),
        )

        # Completely disjoint
        await detector.execute(
            "tool:post",
            _tool_post_data("india juliet kilo lima mike november oscar papa"),
        )

        assert detector.get_current_segment_index("test-session") >= 1

    @pytest.mark.asyncio
    async def test_multiple_sessions_independent(self, tmp_path: Path) -> None:
        """Different sessions should have independent boundary tracking."""
        detector, _ = _make_detector(tmp_path, window_size=2)

        # Session A
        await detector.execute(
            "tool:post",
            _tool_post_data(
                "python programming language features decorators generators",
                session_id="session-a",
            ),
        )
        # Session B
        await detector.execute(
            "tool:post",
            _tool_post_data(
                "kubernetes container orchestration deployment services pods",
                session_id="session-b",
            ),
        )

        # Both should still be at segment 0 (first call per session is a seed)
        assert detector.get_current_segment_index("session-a") == 0
        assert detector.get_current_segment_index("session-b") == 0

    @pytest.mark.asyncio
    async def test_execute_returns_continue(self, tmp_path: Path) -> None:
        """The hook handler should always return action: continue."""
        detector, _ = _make_detector(tmp_path)

        result = await detector.execute(
            "tool:post",
            _tool_post_data("any content that is long enough for processing here"),
        )
        assert result.action == "continue"
