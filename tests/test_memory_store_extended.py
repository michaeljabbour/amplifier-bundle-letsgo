"""Extended tests for tool-memory-store — covers operations with NO prior coverage.

Tests update, facts, file/concept search, timeline, summarization,
eviction, journal, rich metadata, access tracking, and public scoring API.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import pytest

from amplifier_module_tool_memory_store import MemoryStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store(tmp_path: Path, *, max_memories: int = 0) -> MemoryStore:
    return MemoryStore(tmp_path / "test_memories.db", max_memories=max_memories)


def _age_memory(tmp_path: Path, mem_id: str, days: int) -> None:
    """Manually backdate a memory's created_at and updated_at."""
    db_path = tmp_path / "test_memories.db"
    old_dt = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE memories SET created_at = ?, updated_at = ? WHERE id = ?",
        (old_dt, old_dt, mem_id),
    )
    conn.commit()
    conn.close()


# ===========================================================================
# Update tests
# ===========================================================================


class TestUpdate:
    """Tests for MemoryStore.update()."""

    def test_update_memory(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        mem_id = store.store("Original content", title="Old title", importance=0.3)

        result = store.update(
            mem_id,
            content="Updated content",
            title="New title",
            importance=0.9,
        )
        assert result is not None
        assert result["content"] == "Updated content"
        assert result["title"] == "New title"
        assert result["importance"] == 0.9

        # Verify via get
        records = store.get([mem_id])
        assert len(records) == 1
        assert records[0]["content"] == "Updated content"
        assert records[0]["title"] == "New title"
        assert records[0]["importance"] == 0.9

    def test_update_memory_recalculates_hash(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        mem_id = store.store("Content version one")

        rec_before = store.get([mem_id])[0]
        hash_before = rec_before["content_hash"]

        store.update(mem_id, content="Content version two completely different")

        rec_after = store.get([mem_id])[0]
        hash_after = rec_after["content_hash"]

        assert hash_before != hash_after

    def test_update_partial_fields(self, tmp_path: Path) -> None:
        """Updating only some fields should leave others unchanged."""
        store = _make_store(tmp_path)
        mem_id = store.store(
            "Content stays the same",
            category="original",
            importance=0.5,
        )

        store.update(mem_id, category="updated")

        rec = store.get([mem_id])[0]
        assert rec["content"] == "Content stays the same"
        assert rec["category"] == "updated"
        assert rec["importance"] == 0.5

    def test_update_nonexistent_returns_none(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        result = store.update("nonexistent_id", content="anything")
        assert result is None

    def test_update_clamps_importance(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        mem_id = store.store("Clamp test")

        store.update(mem_id, importance=5.0)
        rec = store.get([mem_id])[0]
        assert rec["importance"] == 1.0

        store.update(mem_id, importance=-2.0)
        rec = store.get([mem_id])[0]
        assert rec["importance"] == 0.0


# ===========================================================================
# Fact store tests
# ===========================================================================


class TestFacts:
    """Tests for fact triple storage and querying."""

    def test_store_fact_and_query(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        fact_id = store.store_fact(
            "Python", "is_type", "programming_language", confidence=0.95
        )
        assert isinstance(fact_id, str)
        assert len(fact_id) == 12

        # Query by subject
        results = store.query_facts(subject="Python")
        assert len(results) >= 1
        assert results[0]["subject"] == "Python"
        assert results[0]["predicate"] == "is_type"
        assert results[0]["object"] == "programming_language"
        assert results[0]["confidence"] == 0.95

        # Query by predicate
        results = store.query_facts(predicate="is_type")
        assert len(results) >= 1

        # Query by object
        results = store.query_facts(object_value="programming_language")
        assert len(results) >= 1

    def test_fact_deduplication(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        id1 = store.store_fact("Python", "version", "3.12", confidence=0.8)
        id2 = store.store_fact("Python", "version", "3.12", confidence=0.95)

        # Should be the same fact, with updated confidence
        assert id1 == id2

        results = store.query_facts(subject="Python", predicate="version")
        assert len(results) == 1
        assert results[0]["confidence"] == 0.95

    def test_delete_fact(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        fact_id = store.store_fact("Rust", "has", "borrow_checker")

        results = store.query_facts(subject="Rust")
        assert len(results) == 1

        deleted = store.delete_fact(fact_id)
        assert deleted is True

        results = store.query_facts(subject="Rust")
        assert len(results) == 0

        # Deleting again returns False
        assert store.delete_fact(fact_id) is False

    def test_query_facts_min_confidence(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.store_fact("A", "rel", "B", confidence=0.3)
        store.store_fact("C", "rel", "D", confidence=0.9)

        results = store.query_facts(min_confidence=0.5)
        assert len(results) == 1
        assert results[0]["subject"] == "C"

    def test_store_fact_with_source_entry(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        mem_id = store.store("Some observation about testing patterns")
        fact_id = store.store_fact(
            "testing", "uses", "patterns", source_entry_id=mem_id
        )

        results = store.query_facts(subject="testing")
        assert len(results) == 1
        assert results[0]["source_entry_id"] == mem_id


# ===========================================================================
# File and concept search tests
# ===========================================================================


class TestFileAndConceptSearch:
    """Tests for search_by_file and search_by_concept."""

    def test_search_by_file(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.store(
            "Discovered auth bug in login module",
            files_read=["src/auth/login.py", "src/auth/utils.py"],
        )
        store.store(
            "Refactored database connection pool",
            files_modified=["src/db/pool.py"],
        )
        store.store("Unrelated memory with no files")

        results = store.search_by_file("src/auth/login.py")
        assert len(results) >= 1
        assert any("auth" in r["content"].lower() for r in results)

        results_db = store.search_by_file("src/db/pool.py")
        assert len(results_db) >= 1
        assert any("database" in r["content"].lower() for r in results_db)

        results_none = store.search_by_file("nonexistent/file.py")
        assert len(results_none) == 0

    def test_search_by_concept(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.store(
            "Found a gotcha with async generators",
            concepts=["gotcha", "how-it-works"],
        )
        store.store(
            "Decision: use PostgreSQL over MySQL for this project",
            concepts=["trade-off"],
        )
        store.store("Simple change with no concepts")

        results = store.search_by_concept("gotcha")
        assert len(results) >= 1
        assert any("gotcha" in r["content"].lower() for r in results)

        results_trade = store.search_by_concept("trade-off")
        assert len(results_trade) >= 1

        results_none = store.search_by_concept("nonexistent-concept")
        assert len(results_none) == 0


# ===========================================================================
# Timeline tests
# ===========================================================================


class TestTimeline:
    """Tests for get_timeline."""

    def test_get_timeline(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        id1 = store.store("First event", type="discovery")
        time.sleep(0.05)
        id2 = store.store("Second event", type="change")
        time.sleep(0.05)
        id3 = store.store("Third event", type="bugfix")

        timeline = store.get_timeline(limit=50)
        assert len(timeline) == 3
        # Should be ordered by created_at DESC (newest first)
        assert timeline[0]["id"] == id3
        assert timeline[1]["id"] == id2
        assert timeline[2]["id"] == id1

    def test_get_timeline_filters(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.store("Bug fix in auth", type="bugfix", project="web-app")
        store.store("Feature in API", type="feature", project="api-server")
        store.store("Discovery about DB", type="discovery", session_id="sess-123")
        store.store("Change in config", type="change", session_id="sess-456")

        # Filter by type
        results = store.get_timeline(type="bugfix")
        assert all(r["type"] == "bugfix" for r in results)
        assert len(results) == 1

        # Filter by project
        results = store.get_timeline(project="api-server")
        assert all(r["project"] == "api-server" for r in results)
        assert len(results) == 1

        # Filter by session_id
        results = store.get_timeline(session_id="sess-123")
        assert all(r["session_id"] == "sess-123" for r in results)
        assert len(results) == 1

    def test_get_timeline_excludes_expired(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        mem_id = store.store("Will expire", ttl_days=1)
        store.store("Will not expire")

        # Manually expire the first one
        db_path = tmp_path / "test_memories.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "UPDATE memories SET expires_at = '2000-01-01T00:00:00+00:00' "
            "WHERE id = ?",
            (mem_id,),
        )
        conn.commit()
        conn.close()

        timeline = store.get_timeline()
        assert len(timeline) == 1
        assert timeline[0]["id"] != mem_id


# ===========================================================================
# Summarize old tests
# ===========================================================================


class TestSummarizeOld:
    """Tests for summarize_old."""

    def test_summarize_old(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)

        # Create several old memories in the same category
        ids = []
        for i in range(8):
            mid = store.store(
                f"Old observation number {i} about Python testing patterns",
                category="python",
            )
            ids.append(mid)
            _age_memory(tmp_path, mid, days=45)

        # Create a recent memory that should NOT be summarized
        recent_id = store.store("Recent Python memory", category="python")

        initial_count = store.count()
        assert initial_count == 9

        stats = store.summarize_old(max_age_days=30, max_memories=5)

        assert stats["categories_summarized"] >= 1
        assert stats["memories_archived"] >= 1
        assert stats["summaries_created"] >= 1

        # Recent memory should still exist
        assert store.get([recent_id]) != []

        # Total count should have decreased (originals removed, summary added)
        assert store.count() < initial_count


# ===========================================================================
# Eviction tests
# ===========================================================================


class TestEviction:
    """Tests for _enforce_limit eviction."""

    def test_enforce_limit_eviction(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path, max_memories=5)

        ids = []
        for i in range(7):
            mid = store.store(f"Memory number {i} with unique content here")
            ids.append(mid)

        # Should have evicted down to max_memories
        assert store.count() <= 5

        # The most recently added should still exist
        assert store.get([ids[-1]]) != []


# ===========================================================================
# Journal tests
# ===========================================================================


class TestJournal:
    """Tests for journal recording of operations."""

    def test_journal_records_operations(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        mem_id = store.store("Journal test content here with enough length")

        store.update(mem_id, content="Updated journal test content")
        store.delete(mem_id)

        # Read journal directly
        db_path = tmp_path / "test_memories.db"
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT memory_id, operation FROM memory_journal "
            "WHERE memory_id = ? ORDER BY seq",
            (mem_id,),
        ).fetchall()
        conn.close()

        operations = [r[1] for r in rows]
        assert "insert" in operations
        assert "update" in operations
        assert "delete" in operations


# ===========================================================================
# Rich metadata tests
# ===========================================================================


class TestRichMetadata:
    """Tests for full metadata round-trip."""

    def test_rich_metadata_storage(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        mem_id = store.store(
            "Discovered that async generators need special cleanup handling",
            title="Async generator cleanup",
            subtitle="Found during debugging session",
            type="discovery",
            concepts=["gotcha", "how-it-works"],
            files_read=["src/async/generators.py"],
            files_modified=["src/async/cleanup.py"],
            session_id="sess-abc-123",
            project="my-project",
            discovery_tokens=1500,
            category="async",
            importance=0.85,
            sensitivity="private",
            tags=["python", "async", "generators"],
        )

        rec = store.get([mem_id])[0]
        assert rec["title"] == "Async generator cleanup"
        assert rec["subtitle"] == "Found during debugging session"
        assert rec["type"] == "discovery"
        assert "gotcha" in rec["concepts"]
        assert "how-it-works" in rec["concepts"]
        assert "src/async/generators.py" in rec["files_read"]
        assert "src/async/cleanup.py" in rec["files_modified"]
        assert rec["session_id"] == "sess-abc-123"
        assert rec["project"] == "my-project"
        assert rec["discovery_tokens"] == 1500
        assert rec["category"] == "async"
        assert rec["importance"] == 0.85
        assert rec["sensitivity"] == "private"
        assert "python" in rec["tags"]


# ===========================================================================
# Access tracking tests
# ===========================================================================


class TestAccessTracking:
    """Tests for access count increment behavior."""

    def test_access_count_increment(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        mem_id = store.store("Track my access count please")

        rec = store.get([mem_id])[0]
        assert rec["accessed_count"] == 0

        # Get with increment
        rec = store.get([mem_id], _increment_access=True)[0]
        assert rec["accessed_count"] == 1

        rec = store.get([mem_id], _increment_access=True)[0]
        assert rec["accessed_count"] == 2

        # Without increment should not change
        rec = store.get([mem_id])[0]
        assert rec["accessed_count"] == 2

    def test_search_v2_auto_access_tracking(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        mem_id = store.store("Python testing best practices and patterns")

        # Verify initial count
        rec = store.get([mem_id])[0]
        assert rec["accessed_count"] == 0

        # Search should auto-increment
        results = store.search_v2(
            "Python testing",
            scoring={"min_score": 0.0},
        )
        assert len(results) >= 1

        # Check the count was bumped
        rec = store.get([mem_id])[0]
        assert rec["accessed_count"] >= 1


# ===========================================================================
# Public scoring API tests
# ===========================================================================


class TestPublicScoringAPI:
    """Tests for the static scoring helper methods."""

    def test_extract_keywords(self) -> None:
        keywords = MemoryStore.extract_keywords(
            "How do I use the Python asyncio library for concurrent tasks?"
        )
        assert isinstance(keywords, list)
        assert "python" in keywords
        assert "asyncio" in keywords
        # Stopwords should be filtered
        assert "how" not in keywords
        assert "the" not in keywords

    def test_extract_keywords_max_limit(self) -> None:
        text = "alpha bravo charlie delta echo foxtrot golf hotel india juliet"
        keywords = MemoryStore.extract_keywords(text, max_keywords=3)
        assert len(keywords) == 3

    def test_compute_score(self) -> None:
        item = {
            "importance": 0.8,
            "trust": 0.9,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        score = MemoryStore.compute_score(item, match_score=0.7)
        assert 0.0 <= score <= 1.0
        assert score > 0.5  # High match + importance + trust + recent

    def test_compute_score_with_custom_weights(self) -> None:
        item = {
            "importance": 1.0,
            "trust": 0.5,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        # Weight importance heavily
        score_importance = MemoryStore.compute_score(
            item,
            match_score=0.5,
            weights={"match": 0.0, "recency": 0.0, "importance": 1.0, "trust": 0.0},
        )
        assert score_importance > 0.9

    def test_allow_by_sensitivity(self) -> None:
        assert MemoryStore.allow_by_sensitivity("public") is True
        assert MemoryStore.allow_by_sensitivity("private") is False
        assert MemoryStore.allow_by_sensitivity("private", allow_private=True) is True
        assert MemoryStore.allow_by_sensitivity("secret") is False
        assert MemoryStore.allow_by_sensitivity("secret", allow_secret=True) is True
        assert (
            MemoryStore.allow_by_sensitivity(
                "secret", allow_private=True, allow_secret=False
            )
            is False
        )
        # Unknown sensitivity fails closed
        assert MemoryStore.allow_by_sensitivity("unknown") is False
