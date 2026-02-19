"""Tests for hooks-memory-consolidation module.

Covers the MemoryConsolidator: mount registration, boost/decay logic,
protected types, removal of old unaccessed memories, batch processing,
purge integration, and stats reporting.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import pytest

from amplifier_module_hooks_memory_consolidation import MemoryConsolidator, mount
from amplifier_module_tool_memory_store import MemoryStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "test_memories.db")


def _make_consolidator(
    tmp_path: Path,
    *,
    decay_rate: float = 0.02,
    access_boost_factor: float = 0.03,
    min_importance: float = 0.05,
    max_unaccessed_age_days: float = 90.0,
    protected_types: list[str] | None = None,
) -> tuple[MemoryConsolidator, MemoryStore]:
    store = _make_store(tmp_path)
    consolidator = MemoryConsolidator(
        store,
        decay_rate=decay_rate,
        access_boost_factor=access_boost_factor,
        min_importance=min_importance,
        max_unaccessed_age_days=max_unaccessed_age_days,
        protected_types=protected_types,
    )
    return consolidator, store


def _age_memory(
    tmp_path: Path, mem_id: str, days: int, *, set_accessed: int = 0
) -> None:
    """Backdate a memory and optionally set its accessed_count."""
    db_path = tmp_path / "test_memories.db"
    old_dt = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE memories SET created_at = ?, updated_at = ?, accessed_count = ? "
        "WHERE id = ?",
        (old_dt, old_dt, set_accessed, mem_id),
    )
    conn.commit()
    conn.close()


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

        # Should register one hook on session:end
        regs = mock_coordinator.hooks.registrations
        assert len(regs) == 1
        reg = regs[0]
        assert reg["event"] == "session:end"
        assert reg["priority"] == 200
        assert "memory-consolidation" in reg["name"]

        # Should register capability
        assert "memory.consolidation" in mock_coordinator.capabilities
        cap = mock_coordinator.capabilities["memory.consolidation"]
        assert isinstance(cap, MemoryConsolidator)

    @pytest.mark.asyncio
    async def test_mount_without_store_skips(self, mock_coordinator: Any) -> None:
        await mount(mock_coordinator, config={})
        assert len(mock_coordinator.hooks.registrations) == 0
        assert "memory.consolidation" not in mock_coordinator.capabilities


# ===========================================================================
# Boost tests
# ===========================================================================


class TestBoost:
    """Tests for importance boosting of accessed memories."""

    def test_boost_accessed_memories(self, tmp_path: Path) -> None:
        """Memory with accessed_count > 0 should get importance boost."""
        consolidator, store = _make_consolidator(
            tmp_path, access_boost_factor=0.03
        )
        mem_id = store.store(
            "Frequently accessed observation about Python patterns",
            importance=0.5,
        )
        # Set accessed_count to 5 and age it slightly
        _age_memory(tmp_path, mem_id, days=2, set_accessed=5)

        rec_before = store.get([mem_id])[0]
        assert rec_before["importance"] == 0.5

        stats = consolidator.consolidate()

        rec_after = store.get([mem_id])[0]
        assert rec_after["importance"] > 0.5
        assert stats["boosted"] >= 1


# ===========================================================================
# Decay tests
# ===========================================================================


class TestDecay:
    """Tests for importance decay of unaccessed memories."""

    def test_decay_unaccessed_memories(self, tmp_path: Path) -> None:
        """Memory with accessed_count=0 and some age should decay."""
        consolidator, store = _make_consolidator(
            tmp_path, decay_rate=0.02
        )
        mem_id = store.store(
            "Never accessed observation that should decay over time",
            importance=0.5,
            type="change",
        )
        # Age it so decay kicks in
        _age_memory(tmp_path, mem_id, days=10, set_accessed=0)

        stats = consolidator.consolidate()

        rec_after = store.get([mem_id])[0]
        assert rec_after["importance"] < 0.5
        assert stats["decayed"] >= 1

    def test_fresh_memory_minimal_decay(self, tmp_path: Path) -> None:
        """Recently updated memory should have minimal or no decay."""
        consolidator, store = _make_consolidator(
            tmp_path, decay_rate=0.02
        )
        mem_id = store.store(
            "Just created memory should not decay much at all",
            importance=0.5,
            type="change",
        )
        # Don't age it — it's fresh

        consolidator.consolidate()

        rec_after = store.get([mem_id])[0]
        # Importance should be essentially the same (within floating-point tolerance)
        assert rec_after["importance"] >= 0.49


# ===========================================================================
# Removal tests
# ===========================================================================


class TestRemoval:
    """Tests for removal of old, unaccessed, low-importance memories."""

    def test_remove_old_unaccessed_below_threshold(self, tmp_path: Path) -> None:
        """Very old, low importance, never accessed memory should be deleted."""
        consolidator, store = _make_consolidator(
            tmp_path,
            decay_rate=0.5,  # Aggressive decay to push below threshold
            min_importance=0.05,
            max_unaccessed_age_days=90.0,
        )
        mem_id = store.store(
            "Old memory that nobody ever accessed or cared about",
            importance=0.06,
            type="change",
        )
        # Age it well past max_unaccessed_age_days
        _age_memory(tmp_path, mem_id, days=120, set_accessed=0)

        stats = consolidator.consolidate()

        # Memory should be gone
        assert store.get([mem_id]) == []
        assert stats["removed"] >= 1


# ===========================================================================
# Protected types tests
# ===========================================================================


class TestProtectedTypes:
    """Tests for protected types decaying at half rate."""

    def test_protected_types_decay_slower(self, tmp_path: Path) -> None:
        """'decision' type should decay at half the rate of 'change'.

        With decay_rate=0.01 over 10 days:
          - change (unprotected): decay = 0.01 * 10 = 0.10 -> 0.8 - 0.10 = 0.70
          - decision (protected): decay = 0.01 * 0.5 * 10 = 0.05 -> 0.8 - 0.05 = 0.75
        """
        # Create two separate stores/consolidators
        store_protected = MemoryStore(tmp_path / "protected.db")
        store_normal = MemoryStore(tmp_path / "normal.db")

        consolidator_protected = MemoryConsolidator(
            store_protected,
            decay_rate=0.01,
            protected_types=["decision", "discovery"],
        )
        consolidator_normal = MemoryConsolidator(
            store_normal,
            decay_rate=0.01,
            protected_types=["decision", "discovery"],
        )

        id_decision = store_protected.store(
            "Important architectural decision about database choice",
            importance=0.8,
            type="decision",
        )
        id_change = store_normal.store(
            "Routine change to configuration file settings",
            importance=0.8,
            type="change",
        )

        # Age both the same moderate amount (10 days)
        db_protected = tmp_path / "protected.db"
        db_normal = tmp_path / "normal.db"
        old_dt = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()

        for db_path, mid in [(db_protected, id_decision), (db_normal, id_change)]:
            conn = sqlite3.connect(str(db_path))
            conn.execute(
                "UPDATE memories SET created_at = ?, updated_at = ?, accessed_count = 0 "
                "WHERE id = ?",
                (old_dt, old_dt, mid),
            )
            conn.commit()
            conn.close()

        consolidator_protected.consolidate()
        consolidator_normal.consolidate()

        rec_decision = store_protected.get([id_decision])[0]
        rec_change = store_normal.get([id_change])[0]

        # Decision (protected, half decay rate) should retain more importance
        assert rec_decision["importance"] > rec_change["importance"]
        # Both should still be above zero
        assert rec_decision["importance"] > 0.0
        assert rec_change["importance"] > 0.0


# ===========================================================================
# Batch processing tests
# ===========================================================================


class TestBatchProcessing:
    """Tests for handling multiple memories."""

    def test_consolidate_batch_processing(self, tmp_path: Path) -> None:
        """Should handle multiple memories across batches."""
        consolidator, store = _make_consolidator(tmp_path)

        # Create many memories
        ids = []
        for i in range(15):
            mid = store.store(
                f"Memory number {i} with unique content for batch test",
                importance=0.5,
            )
            ids.append(mid)
            _age_memory(tmp_path, mid, days=10, set_accessed=0)

        stats = consolidator.consolidate()

        assert stats["total_processed"] >= 15

    def test_consolidation_purges_expired(self, tmp_path: Path) -> None:
        """consolidate() should also call purge_expired."""
        consolidator, store = _make_consolidator(tmp_path)

        mem_id = store.store("Will expire soon", ttl_days=1)

        # Manually expire it
        db_path = tmp_path / "test_memories.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "UPDATE memories SET expires_at = '2000-01-01T00:00:00+00:00' "
            "WHERE id = ?",
            (mem_id,),
        )
        conn.commit()
        conn.close()

        consolidator.consolidate()

        # Expired memory should be gone
        assert store.get([mem_id]) == []


# ===========================================================================
# Stats and hook return tests
# ===========================================================================


class TestStatsAndReturn:
    """Tests for consolidation stats and hook return values."""

    def test_consolidate_returns_stats(self, tmp_path: Path) -> None:
        """consolidate() should return a dict with proper count keys."""
        consolidator, store = _make_consolidator(tmp_path)

        store.store("Test memory for stats verification")

        stats = consolidator.consolidate()

        assert isinstance(stats, dict)
        assert "boosted" in stats
        assert "decayed" in stats
        assert "removed" in stats
        assert "total_processed" in stats
        assert all(isinstance(v, int) for v in stats.values())

    @pytest.mark.asyncio
    async def test_execute_hook_returns_continue(self, tmp_path: Path) -> None:
        """Hook handler should return action: continue."""
        consolidator, store = _make_consolidator(tmp_path)

        result = await consolidator.execute("session:end", {})

        assert result.action == "continue"

    def test_consolidate_empty_store(self, tmp_path: Path) -> None:
        """consolidate() on an empty store should not error."""
        consolidator, store = _make_consolidator(tmp_path)

        stats = consolidator.consolidate()

        assert stats["total_processed"] == 0
        assert stats["boosted"] == 0
        assert stats["decayed"] == 0
        assert stats["removed"] == 0


# ===========================================================================
# Mixed scenario tests
# ===========================================================================


class TestMixedScenarios:
    """Tests combining boost, decay, and removal in a single pass."""

    def test_mixed_consolidation(self, tmp_path: Path) -> None:
        """Mix of accessed, unaccessed, and old memories in one pass."""
        consolidator, store = _make_consolidator(
            tmp_path,
            decay_rate=0.5,
            min_importance=0.05,
            max_unaccessed_age_days=90.0,
        )

        # Frequently accessed (should boost)
        id_accessed = store.store(
            "Frequently accessed memory about important patterns",
            importance=0.5,
        )
        _age_memory(tmp_path, id_accessed, days=10, set_accessed=10)

        # Unaccessed but recent (should decay a little)
        id_recent = store.store(
            "Recent unaccessed memory that should decay slightly",
            importance=0.5,
            type="change",
        )
        _age_memory(tmp_path, id_recent, days=5, set_accessed=0)

        # Old, unaccessed, low importance (should be removed)
        id_old = store.store(
            "Very old memory nobody ever looked at or used",
            importance=0.06,
            type="change",
        )
        _age_memory(tmp_path, id_old, days=120, set_accessed=0)

        stats = consolidator.consolidate()

        # Accessed memory should have higher importance
        rec_accessed = store.get([id_accessed])[0]
        assert rec_accessed["importance"] > 0.5

        # Recent memory should still exist
        assert store.get([id_recent]) != []

        # Old memory should be gone (or have very low importance)
        old_results = store.get([id_old])
        if old_results:
            assert old_results[0]["importance"] < 0.06
        # At least some processing happened
        assert stats["total_processed"] >= 2
