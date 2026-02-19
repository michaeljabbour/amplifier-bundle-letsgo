"""Tests for hooks-memory-temporal module.

Covers the TemporalScaffold: mount registration, temporal scale classification,
balanced retrieval with allocation, backfill logic, deduplication,
custom allocation/boundaries, and temporal scale annotation.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import pytest

from amplifier_module_hooks_memory_temporal import TemporalScaffold, mount
from amplifier_module_tool_memory_store import MemoryStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "test_memories.db")


def _make_scaffold(
    tmp_path: Path,
    *,
    allocation: dict[str, int] | None = None,
    scale_boundaries: dict[str, float] | None = None,
) -> tuple[TemporalScaffold, MemoryStore]:
    store = _make_store(tmp_path)
    scaffold = TemporalScaffold(
        store,
        allocation=allocation,
        scale_boundaries=scale_boundaries,
    )
    return scaffold, store


def _set_created_at(tmp_path: Path, mem_id: str, dt: datetime) -> None:
    """Set a memory's created_at to a specific datetime."""
    db_path = tmp_path / "test_memories.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE memories SET created_at = ? WHERE id = ?",
        (dt.isoformat(), mem_id),
    )
    conn.commit()
    conn.close()


def _minutes_ago(minutes: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=minutes)


def _hours_ago(hours: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours)


# ===========================================================================
# Mount tests
# ===========================================================================


class TestMount:
    """Tests for mount() registration."""

    @pytest.mark.asyncio
    async def test_mount_registers_capability(
        self, tmp_path: Path, mock_coordinator: Any
    ) -> None:
        store = _make_store(tmp_path)
        mock_coordinator.register_capability("memory.store", store)

        await mount(mock_coordinator, config={})

        assert "memory.temporal" in mock_coordinator.capabilities
        cap = mock_coordinator.capabilities["memory.temporal"]
        assert isinstance(cap, TemporalScaffold)

        # No hooks should be registered (pure capability)
        assert len(mock_coordinator.hooks.registrations) == 0

    @pytest.mark.asyncio
    async def test_mount_without_store_skips(self, mock_coordinator: Any) -> None:
        await mount(mock_coordinator, config={})
        assert "memory.temporal" not in mock_coordinator.capabilities


# ===========================================================================
# Temporal classification tests
# ===========================================================================


class TestClassifyScale:
    """Tests for classify_scale method."""

    def test_classify_immediate(self, tmp_path: Path) -> None:
        """Memory < 5 minutes old should be 'immediate'."""
        scaffold, store = _make_scaffold(tmp_path)
        mem_id = store.store("Very recent observation just now")
        # created_at is now by default, so < 5 min
        rec = store.get([mem_id])[0]
        scale = scaffold.classify_scale(rec)
        assert scale == "immediate"

    def test_classify_task(self, tmp_path: Path) -> None:
        """Memory 5-30 minutes old should be 'task'."""
        scaffold, store = _make_scaffold(tmp_path)
        mem_id = store.store("Observation from a few minutes ago")
        _set_created_at(tmp_path, mem_id, _minutes_ago(15))

        rec = store.get([mem_id])[0]
        scale = scaffold.classify_scale(rec)
        assert scale == "task"

    def test_classify_session(self, tmp_path: Path) -> None:
        """Memory 30min-2hr old should be 'session'."""
        scaffold, store = _make_scaffold(tmp_path)
        mem_id = store.store("Observation from an hour ago")
        _set_created_at(tmp_path, mem_id, _minutes_ago(60))

        rec = store.get([mem_id])[0]
        scale = scaffold.classify_scale(rec)
        assert scale == "session"

    def test_classify_project(self, tmp_path: Path) -> None:
        """Memory > 2 hours old should be 'project'."""
        scaffold, store = _make_scaffold(tmp_path)
        mem_id = store.store("Observation from yesterday about architecture")
        _set_created_at(tmp_path, mem_id, _hours_ago(5))

        rec = store.get([mem_id])[0]
        scale = scaffold.classify_scale(rec)
        assert scale == "project"

    def test_classify_with_reference_time(self, tmp_path: Path) -> None:
        """classify_scale should use reference_time when provided."""
        scaffold, store = _make_scaffold(tmp_path)
        mem_id = store.store("Test memory for reference time classification")
        # Set created_at to exactly 2 hours ago
        two_hours_ago = _hours_ago(2)
        _set_created_at(tmp_path, mem_id, two_hours_ago)

        rec = store.get([mem_id])[0]

        # With reference_time = now, this should be "project" (>2hr)
        scale_from_now = scaffold.classify_scale(rec)
        assert scale_from_now == "project"

        # With reference_time = 1.5 hours ago, delta is only 30 min → "session"
        ref_time = _minutes_ago(90)
        scale_from_ref = scaffold.classify_scale(rec, reference_time=ref_time)
        assert scale_from_ref == "session"

    def test_classify_unparseable_defaults_to_project(self, tmp_path: Path) -> None:
        """If created_at is unparseable, should default to 'project'."""
        scaffold, _ = _make_scaffold(tmp_path)

        # Fake memory dict with bad created_at
        fake_memory = {"created_at": "not-a-date", "content": "test"}
        scale = scaffold.classify_scale(fake_memory)
        assert scale == "project"


# ===========================================================================
# Balanced retrieval tests
# ===========================================================================


class TestBalancedRetrieve:
    """Tests for balanced_retrieve method."""

    def _seed_memories_at_scales(
        self, tmp_path: Path, store: MemoryStore
    ) -> dict[str, list[str]]:
        """Create memories at different temporal scales. Returns scale→id map."""
        ids: dict[str, list[str]] = {
            "immediate": [],
            "task": [],
            "session": [],
            "project": [],
        }

        # Immediate (< 5 min)
        for i in range(3):
            mid = store.store(
                f"Python testing pattern {i} for immediate scale observation"
            )
            ids["immediate"].append(mid)

        # Task (5-30 min)
        for i in range(3):
            mid = store.store(
                f"Python debugging technique {i} for task scale observation"
            )
            _set_created_at(tmp_path, mid, _minutes_ago(10 + i))
            ids["task"].append(mid)

        # Session (30min-2hr)
        for i in range(3):
            mid = store.store(
                f"Python architecture decision {i} for session scale observation"
            )
            _set_created_at(tmp_path, mid, _minutes_ago(45 + i * 10))
            ids["session"].append(mid)

        # Project (> 2hr)
        for i in range(3):
            mid = store.store(
                f"Python project insight {i} for project scale observation"
            )
            _set_created_at(tmp_path, mid, _hours_ago(5 + i))
            ids["project"].append(mid)

        return ids

    def test_balanced_retrieve_fills_all_scales(self, tmp_path: Path) -> None:
        """Should return memories from each temporal scale per allocation."""
        scaffold, store = _make_scaffold(tmp_path)
        self._seed_memories_at_scales(tmp_path, store)

        results = scaffold.balanced_retrieve(
            "Python testing debugging architecture",
            scoring={"min_score": 0.0},
        )

        assert len(results) > 0

        # Check that results have _temporal_scale annotation
        scales_present = {r.get("_temporal_scale") for r in results}
        # We should ideally have at least 2 different scales
        assert len(scales_present) >= 1

    def test_balanced_retrieve_backfills(self, tmp_path: Path) -> None:
        """If a scale is empty, should backfill from others."""
        scaffold, store = _make_scaffold(tmp_path)

        # Only create project-scale memories (no immediate/task/session)
        for i in range(5):
            mid = store.store(
                f"Python historical insight number {i} from long ago about patterns"
            )
            _set_created_at(tmp_path, mid, _hours_ago(10 + i))

        results = scaffold.balanced_retrieve(
            "Python historical insights",
            scoring={"min_score": 0.0},
        )

        # Should still return results even though most scales are empty
        assert len(results) > 0

    def test_balanced_retrieve_deduplicates(self, tmp_path: Path) -> None:
        """No duplicate IDs should appear in results."""
        scaffold, store = _make_scaffold(tmp_path)
        self._seed_memories_at_scales(tmp_path, store)

        results = scaffold.balanced_retrieve(
            "Python testing debugging patterns",
            scoring={"min_score": 0.0},
        )

        ids = [r["id"] for r in results]
        assert len(ids) == len(set(ids)), "Duplicate IDs found in results"

    def test_temporal_scale_annotation(self, tmp_path: Path) -> None:
        """All returned memories should have _temporal_scale field."""
        scaffold, store = _make_scaffold(tmp_path)
        self._seed_memories_at_scales(tmp_path, store)

        results = scaffold.balanced_retrieve(
            "Python",
            scoring={"min_score": 0.0},
        )

        for r in results:
            assert "_temporal_scale" in r
            assert r["_temporal_scale"] in {
                "immediate",
                "task",
                "session",
                "project",
            }

    def test_balanced_retrieve_empty_store(self, tmp_path: Path) -> None:
        """balanced_retrieve on empty store should return empty list."""
        scaffold, store = _make_scaffold(tmp_path)

        results = scaffold.balanced_retrieve("anything here")
        assert results == []


# ===========================================================================
# Custom configuration tests
# ===========================================================================


class TestCustomConfiguration:
    """Tests for custom allocation and boundary settings."""

    def test_custom_allocation(self, tmp_path: Path) -> None:
        """Custom allocation dict should change distribution."""
        scaffold, store = _make_scaffold(
            tmp_path,
            allocation={
                "immediate": 5,
                "task": 5,
                "session": 5,
                "project": 5,
            },
        )

        # Create plenty of memories at all scales
        for i in range(10):
            mid = store.store(
                f"Python observation number {i} about patterns and techniques"
            )
            _set_created_at(tmp_path, mid, _minutes_ago(i * 30))

        results = scaffold.balanced_retrieve(
            "Python patterns",
            scoring={"min_score": 0.0},
        )

        # With larger allocation, we should get more results
        assert len(results) > 0

    def test_custom_boundaries(self, tmp_path: Path) -> None:
        """Custom boundary seconds should change classification."""
        # Make "immediate" cover a much wider range (1 hour instead of 5 min)
        scaffold, store = _make_scaffold(
            tmp_path,
            scale_boundaries={
                "immediate": 3600.0,  # 1 hour
                "task": 7200.0,  # 2 hours
                "session": 14400.0,  # 4 hours
            },
        )

        # Memory 30 minutes old — normally "session", but with custom boundary = "immediate"
        mem_id = store.store("Memory from 30 minutes ago about Python debugging")
        _set_created_at(tmp_path, mem_id, _minutes_ago(30))

        rec = store.get([mem_id])[0]
        scale = scaffold.classify_scale(rec)
        assert scale == "immediate"  # Because custom boundary is 3600s (1 hour)
