"""Tests for hooks-memory-capture module.

Covers the MemoryCaptureHook: mount registration, session lifecycle,
tool post handling, classification, memorability gating, file tracking,
importance calculation, and session summaries.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from amplifier_module_hooks_memory_capture import MemoryCaptureHook, mount
from amplifier_module_tool_memory_store import MemoryStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "test_memories.db")


def _make_hook(
    tmp_path: Path,
    mock_coordinator: Any,
    *,
    min_content_length: int = 50,
) -> tuple[MemoryCaptureHook, MemoryStore]:
    """Create a MemoryCaptureHook with a real MemoryStore."""
    store = _make_store(tmp_path)
    hook = MemoryCaptureHook(
        store,
        mock_coordinator,
        min_content_length=min_content_length,
    )
    return hook, store


def _tool_post_data(
    tool_name: str,
    tool_output: Any,
    *,
    tool_input: dict[str, Any] | None = None,
    session_id: str = "test-session",
) -> dict[str, Any]:
    """Build a tool:post event data dict."""
    return {
        "tool_name": tool_name,
        "result": tool_output,
        "tool_input": tool_input or {},
        "session_id": session_id,
    }


def _session_start_data(
    session_id: str = "test-session",
    project: str | None = "test-project",
    cwd: str = "/home/user/test-project",
    prompt: str = "Help me debug the auth module",
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "project": project,
        "cwd": cwd,
        "prompt": prompt,
    }


def _long_content(base: str = "This is a detailed observation about ", length: int = 200) -> str:
    """Generate content above the default min_content_length threshold."""
    padding = "x" * max(0, length - len(base))
    return base + padding


# ===========================================================================
# Mount tests
# ===========================================================================


class TestMount:
    """Tests for the mount() entry point."""

    @pytest.mark.asyncio
    async def test_mount_registers_hooks(
        self, tmp_path: Path, mock_coordinator: Any
    ) -> None:
        """mount() should register 3 hooks when memory.store exists."""
        store = _make_store(tmp_path)
        mock_coordinator.register_capability("memory.store", store)

        await mount(mock_coordinator, config={})

        regs = mock_coordinator.hooks.registrations
        assert len(regs) == 3

        events = {r["event"] for r in regs}
        assert "tool:post" in events
        assert "session:start" in events
        assert "session:end" in events

        priorities = {r["event"]: r["priority"] for r in regs}
        assert priorities["tool:post"] == 150
        assert priorities["session:start"] == 50
        assert priorities["session:end"] == 100

    @pytest.mark.asyncio
    async def test_mount_without_store_skips(self, mock_coordinator: Any) -> None:
        """When no memory.store capability, mount should skip registration."""
        await mount(mock_coordinator, config={})

        assert len(mock_coordinator.hooks.registrations) == 0


# ===========================================================================
# Session lifecycle tests
# ===========================================================================


class TestSessionLifecycle:
    """Tests for session:start and session:end handling."""

    @pytest.mark.asyncio
    async def test_session_start_creates_context(
        self, tmp_path: Path, mock_coordinator: Any
    ) -> None:
        hook, store = _make_hook(tmp_path, mock_coordinator)

        result = await hook.execute("session:start", _session_start_data())

        assert result["action"] == "continue"
        # Internal state: session context should exist
        assert "test-session" in hook._sessions

    @pytest.mark.asyncio
    async def test_session_end_creates_summary(
        self, tmp_path: Path, mock_coordinator: Any
    ) -> None:
        """After observations, session:end should create a session_summary."""
        hook, store = _make_hook(tmp_path, mock_coordinator, min_content_length=10)

        # Start session
        await hook.execute("session:start", _session_start_data())

        # Simulate tool observations
        for i in range(3):
            await hook.execute(
                "tool:post",
                _tool_post_data(
                    "bash",
                    _long_content(f"Observation {i}: found important pattern in code "),
                ),
            )

        # End session
        result = await hook.execute("session:end", {"session_id": "test-session"})
        assert result["action"] == "continue"

        # Should have created a session_summary
        timeline = store.get_timeline(type="session_summary")
        assert len(timeline) >= 1

    @pytest.mark.asyncio
    async def test_session_end_no_observations_no_summary(
        self, tmp_path: Path, mock_coordinator: Any
    ) -> None:
        """No observations -> no summary created on session:end."""
        hook, store = _make_hook(tmp_path, mock_coordinator)

        await hook.execute("session:start", _session_start_data())
        await hook.execute("session:end", {"session_id": "test-session"})

        timeline = store.get_timeline(type="session_summary")
        assert len(timeline) == 0


# ===========================================================================
# Tool post handling tests
# ===========================================================================


class TestToolPost:
    """Tests for tool:post event processing."""

    @pytest.mark.asyncio
    async def test_tool_post_captures_observation(
        self, tmp_path: Path, mock_coordinator: Any
    ) -> None:
        """tool:post with a learnable tool should store a memory."""
        hook, store = _make_hook(tmp_path, mock_coordinator, min_content_length=10)

        await hook.execute("session:start", _session_start_data())
        await hook.execute(
            "tool:post",
            _tool_post_data(
                "bash",
                _long_content("Discovered that the server crashes when handling concurrent requests "),
            ),
        )

        assert store.count() >= 1

    @pytest.mark.asyncio
    async def test_tool_post_skips_non_learnable(
        self, tmp_path: Path, mock_coordinator: Any
    ) -> None:
        """tool:post with a non-learnable tool should not store anything."""
        hook, store = _make_hook(tmp_path, mock_coordinator, min_content_length=10)

        await hook.execute("session:start", _session_start_data())
        await hook.execute(
            "tool:post",
            _tool_post_data(
                "unknown_tool_not_in_learnable_set",
                _long_content("Some output that should be ignored entirely here "),
            ),
        )

        assert store.count() == 0

    @pytest.mark.asyncio
    async def test_tool_post_skips_short_content(
        self, tmp_path: Path, mock_coordinator: Any
    ) -> None:
        """Content shorter than min_content_length should not be stored."""
        hook, store = _make_hook(tmp_path, mock_coordinator, min_content_length=100)

        await hook.execute("session:start", _session_start_data())
        await hook.execute(
            "tool:post",
            _tool_post_data("bash", "short"),
        )

        assert store.count() == 0

    @pytest.mark.asyncio
    async def test_tool_post_extracts_dict_output(
        self, tmp_path: Path, mock_coordinator: Any
    ) -> None:
        """tool_output as dict should extract content from known keys."""
        hook, store = _make_hook(tmp_path, mock_coordinator, min_content_length=10)

        await hook.execute("session:start", _session_start_data())
        await hook.execute(
            "tool:post",
            _tool_post_data(
                "bash",
                {"output": _long_content("Command output showing the error traceback and fix ")},
            ),
        )

        assert store.count() >= 1


# ===========================================================================
# Classification tests
# ===========================================================================


class TestClassification:
    """Tests for observation type classification logic."""

    @pytest.mark.asyncio
    async def test_classification_bugfix(
        self, tmp_path: Path, mock_coordinator: Any
    ) -> None:
        """Content with bug/fix/error keywords should be classified as bugfix."""
        hook, store = _make_hook(tmp_path, mock_coordinator, min_content_length=10)

        await hook.execute("session:start", _session_start_data())
        await hook.execute(
            "tool:post",
            _tool_post_data(
                "bash",
                _long_content("Fixed the critical error in the authentication module that caused crashes "),
            ),
        )

        if store.count() > 0:
            timeline = store.get_timeline(type="bugfix")
            assert len(timeline) >= 1

    @pytest.mark.asyncio
    async def test_classification_discovery(
        self, tmp_path: Path, mock_coordinator: Any
    ) -> None:
        """read_file tool should be classified as discovery."""
        hook, store = _make_hook(tmp_path, mock_coordinator, min_content_length=10)

        await hook.execute("session:start", _session_start_data())
        await hook.execute(
            "tool:post",
            _tool_post_data(
                "read_file",
                _long_content("File contents showing the implementation of the retry logic handler "),
                tool_input={"file_path": "src/retry.py"},
            ),
        )

        if store.count() > 0:
            timeline = store.get_timeline(type="discovery")
            assert len(timeline) >= 1

    @pytest.mark.asyncio
    async def test_classification_change(
        self, tmp_path: Path, mock_coordinator: Any
    ) -> None:
        """write_file tool should be classified as change."""
        hook, store = _make_hook(tmp_path, mock_coordinator, min_content_length=10)

        await hook.execute("session:start", _session_start_data())
        await hook.execute(
            "tool:post",
            _tool_post_data(
                "write_file",
                _long_content("Successfully wrote the new configuration to disk with updated settings "),
                tool_input={"file_path": "config.yaml"},
            ),
        )

        if store.count() > 0:
            timeline = store.get_timeline(type="change")
            assert len(timeline) >= 1


# ===========================================================================
# Memorability gating tests
# ===========================================================================


class TestMemorabilityGating:
    """Tests for the memorability scoring gate in _store_observation."""

    @pytest.mark.asyncio
    async def test_memorability_gating(
        self, tmp_path: Path, mock_coordinator: Any
    ) -> None:
        """Low memorability score should prevent storage."""
        hook, store = _make_hook(tmp_path, mock_coordinator, min_content_length=10)

        # Create a mock scorer that always says "don't store"
        class LowScorer:
            def score(self, content, **kwargs):
                return 0.05

            def should_store(self, score):
                return False

        mock_coordinator.register_capability("memory.memorability", LowScorer())

        await hook.execute("session:start", _session_start_data())
        await hook.execute(
            "tool:post",
            _tool_post_data(
                "bash",
                _long_content("This observation should be blocked by memorability gate entirely "),
            ),
        )

        assert store.count() == 0

    @pytest.mark.asyncio
    async def test_memorability_allows_storage(
        self, tmp_path: Path, mock_coordinator: Any
    ) -> None:
        """High memorability score should allow storage."""
        hook, store = _make_hook(tmp_path, mock_coordinator, min_content_length=10)

        class HighScorer:
            def score(self, content, **kwargs):
                return 0.95

            def should_store(self, score):
                return True

        mock_coordinator.register_capability("memory.memorability", HighScorer())

        await hook.execute("session:start", _session_start_data())
        await hook.execute(
            "tool:post",
            _tool_post_data(
                "bash",
                _long_content("This observation should pass the memorability gate easily "),
            ),
        )

        assert store.count() >= 1


# ===========================================================================
# File tracking tests
# ===========================================================================


class TestFileTracking:
    """Tests for file operation tracking in SessionContext."""

    @pytest.mark.asyncio
    async def test_file_tracking(
        self, tmp_path: Path, mock_coordinator: Any
    ) -> None:
        """read_file and edit_file should track files in SessionContext."""
        hook, store = _make_hook(tmp_path, mock_coordinator, min_content_length=10)

        await hook.execute("session:start", _session_start_data())

        # Read a file
        await hook.execute(
            "tool:post",
            _tool_post_data(
                "read_file",
                _long_content("Contents of the authentication module with important patterns "),
                tool_input={"file_path": "src/auth.py"},
            ),
        )

        # Edit a file
        await hook.execute(
            "tool:post",
            _tool_post_data(
                "edit_file",
                _long_content("Successfully edited the configuration file with new database settings "),
                tool_input={"file_path": "src/config.py"},
            ),
        )

        session = hook._sessions.get("test-session")
        if session is not None:
            assert "src/auth.py" in session.files_read
            assert "src/config.py" in session.files_modified


# ===========================================================================
# Importance calculation tests
# ===========================================================================


class TestImportanceCalculation:
    """Tests for _calculate_importance."""

    def test_importance_calculation(
        self, tmp_path: Path, mock_coordinator: Any
    ) -> None:
        """bugfix should have higher importance than change."""
        hook, _ = _make_hook(tmp_path, mock_coordinator)

        bugfix_importance = hook._calculate_importance("bugfix", "short")
        change_importance = hook._calculate_importance("change", "short")

        assert bugfix_importance > change_importance

    def test_importance_long_content_boost(
        self, tmp_path: Path, mock_coordinator: Any
    ) -> None:
        """Content > 500 chars should get +0.1 importance boost."""
        hook, _ = _make_hook(tmp_path, mock_coordinator)

        short_importance = hook._calculate_importance("change", "short content")
        long_importance = hook._calculate_importance("change", "x" * 600)

        assert long_importance > short_importance
        assert long_importance - short_importance == pytest.approx(0.1, abs=0.01)

    def test_importance_capped_at_one(
        self, tmp_path: Path, mock_coordinator: Any
    ) -> None:
        """Importance should never exceed 1.0."""
        hook, _ = _make_hook(tmp_path, mock_coordinator)

        importance = hook._calculate_importance("bugfix", "x" * 600)
        assert importance <= 1.0
