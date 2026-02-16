"""Tests for tool-memory-store module.

Covers MemoryStore (storage engine), MemoryTool (LLM-callable),
and the mount() integration.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from amplifier_module_tool_memory_store import MemoryStore, MemoryTool, mount


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "test_memories.db")


# ===========================================================================
# MemoryStore tests
# ===========================================================================


class TestMemoryStore:
    """Unit tests for the MemoryStore storage engine."""

    def test_store_and_get(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        mem_id = store.store("Python is a great language", category="tech")
        assert isinstance(mem_id, str)
        assert len(mem_id) == 12

        records = store.get([mem_id])
        assert len(records) == 1
        rec = records[0]
        assert rec["id"] == mem_id
        assert rec["content"] == "Python is a great language"
        assert rec["category"] == "tech"
        assert rec["importance"] == 0.5
        assert rec["trust"] == 0.5
        assert rec["sensitivity"] == "public"
        assert rec["created_at"] is not None
        assert rec["updated_at"] is not None

    def test_search_v2_fts(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.store("Python programming language tips", category="tech")
        store.store("JavaScript frontend framework guide", category="tech")
        store.store("Python data science tutorial", category="data")

        results = store.search_v2(
            "Python programming",
            limit=5,
            scoring={"min_score": 0.0},
        )
        assert len(results) >= 1
        # All results should have _score and _match
        for r in results:
            assert "_score" in r
            assert "_match" in r
        # Python results should come first
        contents = [r["content"] for r in results]
        assert any("Python" in c for c in contents)

    def test_search_v2_sensitivity_gating(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.store("Public Python tutorial", sensitivity="public")
        store.store("Private Python secrets", sensitivity="private")
        store.store("Secret Python internals", sensitivity="secret")

        # Default gating: only public allowed
        results = store.search_v2(
            "Python",
            scoring={"min_score": 0.0},
            gating={"allow_private": False, "allow_secret": False},
        )
        sensitivities = {r["sensitivity"] for r in results}
        assert "private" not in sensitivities
        assert "secret" not in sensitivities

        # Allow private
        results_private = store.search_v2(
            "Python",
            scoring={"min_score": 0.0},
            gating={"allow_private": True, "allow_secret": False},
        )
        sensitivities_p = {r["sensitivity"] for r in results_private}
        assert "private" in sensitivities_p
        assert "secret" not in sensitivities_p

    def test_search_v2_min_score_filtering(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.store("unrelated content about cooking pasta recipes")
        store.store("another unrelated note about gardening flowers")

        results = store.search_v2(
            "quantum physics research",
            scoring={"min_score": 0.99},
        )
        # Very high min_score should filter out unrelated content
        assert len(results) == 0

    def test_search_ids(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.store("Rust systems programming language")
        store.store("Rust borrow checker explained")

        ids = store.search_ids(
            "Rust programming",
            scoring={"min_score": 0.0},
        )
        assert isinstance(ids, list)
        assert all(isinstance(i, str) for i in ids)
        assert len(ids) >= 1

    def test_delete(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        mem_id = store.store("To be deleted")

        assert store.get([mem_id]) != []
        deleted = store.delete(mem_id)
        assert deleted is True
        assert store.get([mem_id]) == []

        # Deleting again returns False
        assert store.delete(mem_id) is False

    def test_list_all(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.store("First memory content here")
        store.store("Second memory content here")
        store.store("Third memory content here")

        items = store.list_all()
        assert len(items) == 3
        # Should have content_preview, not full content key
        for item in items:
            assert "content_preview" in item
            assert "id" in item
            assert "category" in item

    def test_count(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        assert store.count() == 0

        store.store("one")
        store.store("two")
        store.store("three")
        assert store.count() == 3

        store.store("four")
        assert store.count() == 4

    def test_fts_sync(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        mem_id = store.store("Elasticsearch indexing performance tuning")

        results = store.search_v2(
            "Elasticsearch indexing",
            scoring={"min_score": 0.0},
        )
        assert len(results) >= 1

        store.delete(mem_id)

        results_after = store.search_v2(
            "Elasticsearch indexing",
            scoring={"min_score": 0.0},
        )
        assert len(results_after) == 0

    def test_get_empty_ids(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        assert store.get([]) == []

    def test_get_nonexistent_id(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        assert store.get(["nonexistent"]) == []

    def test_store_with_tags(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        mem_id = store.store(
            "Tagged memory",
            tags=["python", "testing"],
        )
        records = store.get([mem_id])
        assert records[0]["tags"] == "python,testing"

    def test_deduplication(self, tmp_path: Path) -> None:
        """Storing identical content twice returns the same id."""
        store = _make_store(tmp_path)
        id1 = store.store("Exact same content for dedup test")
        id2 = store.store("Exact same content for dedup test")

        assert id1 == id2
        assert store.count() == 1

    def test_ttl_expiry(self, tmp_path: Path) -> None:
        """Store with ttl_days, then verify purge_expired removes it."""
        store = _make_store(tmp_path)
        mem_id = store.store("Ephemeral memory", ttl_days=1)

        # Memory should exist before expiry
        assert store.get([mem_id]) != []

        # Manually set expires_at to the past to simulate expiry
        db_path = tmp_path / "test_memories.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "UPDATE memories SET expires_at = '2000-01-01T00:00:00+00:00' "
            "WHERE id = ?",
            (mem_id,),
        )
        conn.commit()
        conn.close()

        purged = store.purge_expired()
        assert purged == 1
        assert store.get([mem_id]) == []


# ===========================================================================
# MemoryTool tests
# ===========================================================================


class TestMemoryTool:
    """Unit tests for the MemoryTool (LLM-callable interface)."""

    @pytest.mark.asyncio
    async def test_store_memory_operation(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        tool = MemoryTool(store)

        result = await tool.execute({
            "operation": "store_memory",
            "content": "Remember this important fact",
            "category": "notes",
            "importance": 0.8,
        })
        assert result.success is True
        assert result.output["status"] == "stored"
        assert "id" in result.output
        assert len(result.output["id"]) == 12

    @pytest.mark.asyncio
    async def test_search_memories_operation(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        tool = MemoryTool(store)

        await tool.execute({
            "operation": "store_memory",
            "content": "Docker container orchestration with Kubernetes",
        })
        await tool.execute({
            "operation": "store_memory",
            "content": "Docker image building best practices",
        })

        result = await tool.execute({
            "operation": "search_memories",
            "query": "Docker container",
        })
        assert result.success is True
        assert "results" in result.output
        assert "count" in result.output
        assert result.output["count"] >= 1

    @pytest.mark.asyncio
    async def test_list_memories_operation(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        tool = MemoryTool(store)

        await tool.execute({
            "operation": "store_memory",
            "content": "First memory for listing",
        })
        await tool.execute({
            "operation": "store_memory",
            "content": "Second memory for listing",
        })

        result = await tool.execute({
            "operation": "list_memories",
            "limit": 10,
        })
        assert result.success is True
        assert "memories" in result.output
        assert "total" in result.output
        assert result.output["total"] == 2
        assert len(result.output["memories"]) == 2

    @pytest.mark.asyncio
    async def test_get_memory_operation(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        tool = MemoryTool(store)

        store_result = await tool.execute({
            "operation": "store_memory",
            "content": "Specific memory to retrieve",
        })
        mem_id = store_result.output["id"]

        result = await tool.execute({
            "operation": "get_memory",
            "id": mem_id,
        })
        assert result.success is True
        assert result.output["id"] == mem_id
        assert result.output["content"] == "Specific memory to retrieve"

    @pytest.mark.asyncio
    async def test_delete_memory_operation(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        tool = MemoryTool(store)

        store_result = await tool.execute({
            "operation": "store_memory",
            "content": "Memory to delete",
        })
        mem_id = store_result.output["id"]

        result = await tool.execute({
            "operation": "delete_memory",
            "id": mem_id,
        })
        assert result.success is True
        assert result.output["deleted"] is True

        # Verify it's gone
        get_result = await tool.execute({
            "operation": "get_memory",
            "id": mem_id,
        })
        assert get_result.success is False

    @pytest.mark.asyncio
    async def test_unknown_operation_returns_error(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        tool = MemoryTool(store)

        result = await tool.execute({"operation": "do_something_weird"})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_store_memory_missing_content(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        tool = MemoryTool(store)

        result = await tool.execute({"operation": "store_memory"})
        assert result.success is False

    def test_tool_properties(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        tool = MemoryTool(store)

        assert tool.name == "memory"
        assert isinstance(tool.description, str)
        schema = tool.input_schema
        assert schema["type"] == "object"
        assert "operation" in schema["properties"]

    @pytest.mark.asyncio
    async def test_purge_expired_operation(self, tmp_path: Path) -> None:
        """Test purge_expired through the tool execute interface."""
        store = _make_store(tmp_path)
        tool = MemoryTool(store)

        r = await tool.execute({
            "operation": "store_memory",
            "content": "Will expire soon via purge",
            "ttl_days": 1,
        })
        assert r.success is True
        mem_id = r.output["id"]

        # Manually expire the memory
        db_path = tmp_path / "test_memories.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "UPDATE memories SET expires_at = '2000-01-01T00:00:00+00:00' "
            "WHERE id = ?",
            (mem_id,),
        )
        conn.commit()
        conn.close()

        result = await tool.execute({"operation": "purge_expired"})
        assert result.success is True
        assert result.output["purged"] == 1


# ===========================================================================
# Integration: mount()
# ===========================================================================


class TestMount:
    """Integration test for the mount() entry point."""

    @pytest.mark.asyncio
    async def test_mount_registers_tool_and_capability(
        self, tmp_path: Path, mock_coordinator: Any
    ) -> None:
        await mount(
            mock_coordinator,
            config={"db_path": str(tmp_path / "memories.db")},
        )

        # Should have mounted a tool
        assert len(mock_coordinator.mounts) == 1
        tool_mount = mock_coordinator.mounts[0]
        assert tool_mount["category"] == "tools"
        assert tool_mount["name"] == "tool-memory-store"
        assert isinstance(tool_mount["obj"], MemoryTool)

        # Should have registered the capability
        assert "memory.store" in mock_coordinator.capabilities
        cap = mock_coordinator.capabilities["memory.store"]
        assert isinstance(cap, MemoryStore)
        assert hasattr(cap, "search_v2")
        assert hasattr(cap, "search_ids")
        assert hasattr(cap, "get")
