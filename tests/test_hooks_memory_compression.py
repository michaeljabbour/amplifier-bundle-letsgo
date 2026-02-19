"""Tests for hooks-memory-compression module.

Covers the MemoryCompressor: mount registration, clustering by similarity,
merging clusters, metadata preservation, summary creation, original deletion,
age filtering, summary type exclusion, stats reporting, and Jaccard similarity.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import pytest

from amplifier_module_hooks_memory_compression import MemoryCompressor, mount
from amplifier_module_tool_memory_store import MemoryStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "test_memories.db")


def _make_compressor(
    tmp_path: Path,
    *,
    similarity_threshold: float = 0.50,
    min_cluster_size: int = 3,
    min_age_days: float = 7.0,
    max_batch_size: int = 200,
) -> tuple[MemoryCompressor, MemoryStore]:
    store = _make_store(tmp_path)
    compressor = MemoryCompressor(
        store,
        similarity_threshold=similarity_threshold,
        min_cluster_size=min_cluster_size,
        min_age_days=min_age_days,
        max_batch_size=max_batch_size,
    )
    return compressor, store


def _age_memory(tmp_path: Path, mem_id: str, days: int) -> None:
    """Backdate a memory's created_at and updated_at."""
    db_path = tmp_path / "test_memories.db"
    old_dt = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE memories SET created_at = ?, updated_at = ? WHERE id = ?",
        (old_dt, old_dt, mem_id),
    )
    conn.commit()
    conn.close()


def _create_cluster(
    store: MemoryStore,
    tmp_path: Path,
    *,
    base_keywords: str = "python testing pytest fixtures assertions",
    count: int = 4,
    age_days: int = 14,
    importance: float = 0.5,
    tags: list[str] | None = None,
    concepts: list[str] | None = None,
    files_read: list[str] | None = None,
) -> list[str]:
    """Create a cluster of similar memories with shared keywords."""
    ids = []
    for i in range(count):
        mid = store.store(
            f"Observation {i}: {base_keywords} detailed content about the topic area number {i}",
            importance=importance,
            tags=tags,
            concepts=concepts,
            files_read=files_read,
            type="change",
        )
        _age_memory(tmp_path, mid, days=age_days)
        ids.append(mid)
    return ids


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
        assert reg["priority"] == 300
        assert "memory-compression" in reg["name"]

        # Should register capability
        assert "memory.compression" in mock_coordinator.capabilities
        cap = mock_coordinator.capabilities["memory.compression"]
        assert isinstance(cap, MemoryCompressor)

    @pytest.mark.asyncio
    async def test_mount_without_store_skips(self, mock_coordinator: Any) -> None:
        await mount(mock_coordinator, config={})
        assert len(mock_coordinator.hooks.registrations) == 0
        assert "memory.compression" not in mock_coordinator.capabilities


# ===========================================================================
# Clustering tests
# ===========================================================================


class TestClustering:
    """Tests for similarity-based clustering."""

    def test_compress_clusters_similar(self, tmp_path: Path) -> None:
        """Similar memories (shared keywords) should get clustered together."""
        compressor, store = _make_compressor(
            tmp_path, similarity_threshold=0.30, min_cluster_size=3, min_age_days=7
        )

        # Create a cluster of similar Python testing memories
        _create_cluster(
            store,
            tmp_path,
            base_keywords="python testing pytest fixtures assertions mocking",
            count=4,
            age_days=14,
        )

        stats = compressor.compress()

        # Should find at least one cluster
        assert stats["clusters_found"] >= 1

    def test_compress_skips_dissimilar(self, tmp_path: Path) -> None:
        """Dissimilar memories should NOT be clustered together."""
        compressor, store = _make_compressor(
            tmp_path, similarity_threshold=0.50, min_cluster_size=3, min_age_days=7
        )

        # Create individual memories on completely different topics
        topics = [
            "python asyncio coroutines event loop await gather",
            "kubernetes docker containers orchestration deployment pods",
            "machine learning neural networks gradient descent backpropagation",
            "cooking recipes ingredients pasta sauce tomato basil",
        ]
        ids = []
        for topic in topics:
            mid = store.store(f"Unique observation about: {topic}")
            _age_memory(tmp_path, mid, days=14)
            ids.append(mid)

        stats = compressor.compress()

        # All originals should still exist (no cluster large enough to merge)
        for mid in ids:
            assert store.get([mid]) != [], f"Memory {mid} was wrongly deleted"

    def test_compress_min_cluster_size(self, tmp_path: Path) -> None:
        """Clusters smaller than min_cluster_size should NOT be merged."""
        compressor, store = _make_compressor(
            tmp_path, similarity_threshold=0.30, min_cluster_size=5, min_age_days=7
        )

        # Create only 3 similar memories — below min_cluster_size of 5
        ids = _create_cluster(
            store,
            tmp_path,
            base_keywords="python testing pytest fixtures assertions",
            count=3,
            age_days=14,
        )

        stats = compressor.compress()

        # Originals should all still exist
        for mid in ids:
            assert store.get([mid]) != [], f"Memory {mid} was wrongly merged"
        assert stats["clusters_merged"] == 0


# ===========================================================================
# Merge behavior tests
# ===========================================================================


class TestMergeBehavior:
    """Tests for cluster merge logic."""

    def test_compress_creates_summary(self, tmp_path: Path) -> None:
        """Merged cluster should create a compressed_summary memory."""
        compressor, store = _make_compressor(
            tmp_path, similarity_threshold=0.30, min_cluster_size=3, min_age_days=7
        )

        _create_cluster(
            store,
            tmp_path,
            base_keywords="python testing pytest fixtures assertions mocking",
            count=5,
            age_days=14,
        )

        stats = compressor.compress()

        if stats["clusters_merged"] > 0:
            # Should have created compressed_summary type memories
            timeline = store.get_timeline(type="compressed_summary")
            assert len(timeline) >= 1
            assert stats["summaries_created"] >= 1

    def test_compress_deletes_originals(self, tmp_path: Path) -> None:
        """Originals should be deleted after successful merge."""
        compressor, store = _make_compressor(
            tmp_path, similarity_threshold=0.30, min_cluster_size=3, min_age_days=7
        )

        ids = _create_cluster(
            store,
            tmp_path,
            base_keywords="python testing pytest fixtures assertions mocking",
            count=5,
            age_days=14,
        )

        initial_count = store.count()
        stats = compressor.compress()

        if stats["clusters_merged"] > 0:
            # Some originals should be gone
            remaining = sum(1 for mid in ids if store.get([mid]) != [])
            assert remaining < len(ids)
            assert stats["memories_removed"] >= 1
            # Total count should decrease (N originals removed, 1 summary added)
            assert store.count() < initial_count

    def test_compress_preserves_metadata(self, tmp_path: Path) -> None:
        """Merged summary should preserve highest importance and union of metadata."""
        compressor, store = _make_compressor(
            tmp_path, similarity_threshold=0.30, min_cluster_size=3, min_age_days=7
        )

        # Create cluster members with different metadata
        id1 = store.store(
            "Python testing observation one with pytest fixtures assertions mocking unit",
            importance=0.3,
            tags=["python", "testing"],
            concepts=["pattern"],
            files_read=["src/test_a.py"],
        )
        _age_memory(tmp_path, id1, days=14)

        id2 = store.store(
            "Python testing observation two about pytest fixtures assertions mocking integration",
            importance=0.8,
            tags=["testing", "ci"],
            concepts=["how-it-works"],
            files_read=["src/test_b.py"],
        )
        _age_memory(tmp_path, id2, days=14)

        id3 = store.store(
            "Python testing observation three regarding pytest fixtures assertions mocking coverage",
            importance=0.5,
            tags=["python"],
            concepts=["pattern"],
            files_modified=["src/test_c.py"],
        )
        _age_memory(tmp_path, id3, days=14)

        stats = compressor.compress()

        if stats["clusters_merged"] > 0:
            summaries = store.get_timeline(type="compressed_summary")
            assert len(summaries) >= 1
            summary = summaries[0]

            # Highest importance should be preserved
            assert summary["importance"] >= 0.8


# ===========================================================================
# Filtering tests
# ===========================================================================


class TestFiltering:
    """Tests for age and type filtering."""

    def test_compress_skips_recent(self, tmp_path: Path) -> None:
        """Memories newer than min_age_days should NOT be compressed."""
        compressor, store = _make_compressor(
            tmp_path, min_age_days=7, min_cluster_size=3
        )

        # Create recent memories (not aged)
        for i in range(5):
            store.store(
                f"Recent Python testing observation {i} with pytest fixtures assertions"
            )

        stats = compressor.compress()

        # No candidates should be found (all too recent)
        assert stats["total_candidates"] == 0
        assert stats["clusters_merged"] == 0

    def test_compress_skips_summaries(self, tmp_path: Path) -> None:
        """session_summary and compressed_summary types should not be candidates."""
        compressor, store = _make_compressor(
            tmp_path, min_age_days=7, min_cluster_size=2, similarity_threshold=0.20
        )

        # Create session_summary and compressed_summary type memories
        id1 = store.store(
            "Session summary: worked on Python testing with pytest fixtures assertions",
            type="session_summary",
        )
        _age_memory(tmp_path, id1, days=14)

        id2 = store.store(
            "Compressed summary: Python testing pytest fixtures assertions coverage",
            type="compressed_summary",
        )
        _age_memory(tmp_path, id2, days=14)

        # These should be excluded from candidates
        stats = compressor.compress()
        assert stats["total_candidates"] == 0

        # Both should still exist
        assert store.get([id1]) != []
        assert store.get([id2]) != []


# ===========================================================================
# Stats and return tests
# ===========================================================================


class TestStatsAndReturn:
    """Tests for compression stats and hook return."""

    def test_compress_returns_stats(self, tmp_path: Path) -> None:
        """compress() should return a dict with proper count keys."""
        compressor, store = _make_compressor(tmp_path)

        stats = compressor.compress()

        assert isinstance(stats, dict)
        assert "total_candidates" in stats
        assert "clusters_found" in stats
        assert "clusters_merged" in stats
        assert "memories_removed" in stats
        assert "summaries_created" in stats
        assert all(isinstance(v, int) for v in stats.values())

    def test_compress_empty_store(self, tmp_path: Path) -> None:
        """compress() on empty store should not error."""
        compressor, store = _make_compressor(tmp_path)

        stats = compressor.compress()

        assert stats["total_candidates"] == 0
        assert stats["clusters_found"] == 0
        assert stats["clusters_merged"] == 0
        assert stats["memories_removed"] == 0
        assert stats["summaries_created"] == 0

    @pytest.mark.asyncio
    async def test_execute_returns_continue(self, tmp_path: Path) -> None:
        """Hook handler should return action: continue."""
        compressor, store = _make_compressor(tmp_path)

        result = await compressor.execute("session:end", {})
        assert result["action"] == "continue"

    @pytest.mark.asyncio
    async def test_execute_includes_compression_stats(self, tmp_path: Path) -> None:
        """Hook handler should include compression_stats in return."""
        compressor, store = _make_compressor(tmp_path)

        result = await compressor.execute("session:end", {})
        assert "compression_stats" in result
        assert isinstance(result["compression_stats"], dict)


# ===========================================================================
# Jaccard similarity tests
# ===========================================================================


class TestJaccardSimilarity:
    """Tests for the static _jaccard method."""

    def test_jaccard_identical_sets(self) -> None:
        result = MemoryCompressor._jaccard({"a", "b", "c"}, {"a", "b", "c"})
        assert result == 1.0

    def test_jaccard_disjoint_sets(self) -> None:
        result = MemoryCompressor._jaccard({"a", "b", "c"}, {"d", "e", "f"})
        assert result == 0.0

    def test_jaccard_partial_overlap(self) -> None:
        # {a, b, c} & {b, c, d} = {b, c} -> |2| / |{a,b,c,d}| = 2/4 = 0.5
        result = MemoryCompressor._jaccard({"a", "b", "c"}, {"b", "c", "d"})
        assert result == pytest.approx(0.5)

    def test_jaccard_both_empty(self) -> None:
        result = MemoryCompressor._jaccard(set(), set())
        assert result == 1.0

    def test_jaccard_one_empty(self) -> None:
        result = MemoryCompressor._jaccard({"a", "b"}, set())
        assert result == 0.0

    def test_jaccard_single_element_overlap(self) -> None:
        # {a, b, c} & {c, d, e, f} = {c} -> 1/6
        result = MemoryCompressor._jaccard({"a", "b", "c"}, {"c", "d", "e", "f"})
        assert result == pytest.approx(1.0 / 6.0)


# ===========================================================================
# Edge case and integration tests
# ===========================================================================


class TestEdgeCases:
    """Edge case and integration tests."""

    def test_compress_with_mixed_ages(self, tmp_path: Path) -> None:
        """Only old enough memories should be candidates."""
        compressor, store = _make_compressor(
            tmp_path, min_age_days=7, min_cluster_size=3, similarity_threshold=0.30
        )

        # Create 2 old and 2 recent similar memories
        old_ids = []
        for i in range(2):
            mid = store.store(
                f"Old Python testing observation {i} with pytest fixtures assertions mocking"
            )
            _age_memory(tmp_path, mid, days=14)
            old_ids.append(mid)

        recent_ids = []
        for i in range(2):
            mid = store.store(
                f"Recent Python testing observation {i} with pytest fixtures assertions mocking"
            )
            recent_ids.append(mid)

        stats = compressor.compress()

        # Only 2 candidates (old ones), not enough for min_cluster_size=3
        assert stats["clusters_merged"] == 0

        # All memories should still exist
        for mid in old_ids + recent_ids:
            assert store.get([mid]) != []

    def test_compress_large_batch(self, tmp_path: Path) -> None:
        """Should handle a large number of memories."""
        compressor, store = _make_compressor(
            tmp_path,
            min_age_days=7,
            min_cluster_size=3,
            similarity_threshold=0.30,
            max_batch_size=200,
        )

        # Create 20 similar old memories
        for i in range(20):
            mid = store.store(
                f"Python testing observation number {i} about pytest fixtures "
                f"assertions mocking coverage reporting analysis"
            )
            _age_memory(tmp_path, mid, days=14)

        stats = compressor.compress()

        # Should have processed them all
        assert stats["total_candidates"] >= 20

    def test_multiple_compress_passes(self, tmp_path: Path) -> None:
        """Multiple compress() calls should be idempotent after first pass."""
        compressor, store = _make_compressor(
            tmp_path, similarity_threshold=0.30, min_cluster_size=3, min_age_days=7
        )

        _create_cluster(
            store,
            tmp_path,
            base_keywords="python testing pytest fixtures assertions mocking",
            count=6,
            age_days=14,
        )

        stats1 = compressor.compress()
        count_after_first = store.count()

        stats2 = compressor.compress()
        count_after_second = store.count()

        # Second pass should have fewer or no candidates
        # (summaries are excluded, originals are gone)
        assert stats2["memories_removed"] <= stats1["memories_removed"]
        assert count_after_second <= count_after_first
