"""Tests for security hardening changes across all modules.

Covers: sandbox native-fallback gating, workdir validation, network
restriction, Docker mount mode, allowlist word-boundary matching,
path normalisation, unknown-sensitivity fail-closed, memory journal,
and telemetry event completeness.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from amplifier_module_hooks_tool_policy import ToolPolicyHook
from amplifier_module_tool_sandbox import SandboxTool
from amplifier_module_hooks_telemetry import TelemetryCollector
# _allow_by_sensitivity was removed from inject hook during dedup cleanup.
# Use the store's public API instead — both modules shared identical logic.
from amplifier_module_tool_memory_store import MemoryStore
inject_allow = MemoryStore.allow_by_sensitivity
from amplifier_module_tool_memory_store import MemoryStore
from amplifier_module_tool_memory_store import (
    _allow_by_sensitivity as store_allow,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hook(tmp_path: Path, **overrides) -> ToolPolicyHook:
    config = {
        "blocked_tools": ["tool-dangerous"],
        "high_risk_tools": ["tool-bash"],
        "medium_risk_tools": ["tool-filesystem"],
        "low_risk_tools": ["tool-grep"],
        "default_action": "deny",
        "careful_mode": True,
        "allowed_commands": ["git", "echo ", "ls "],
        "allowed_write_paths": ["/tmp/safe/"],
        "sandbox_mode": "off",
        "audit_log_path": str(tmp_path / "audit.jsonl"),
    }
    config.update(overrides)
    return ToolPolicyHook(config)


def _tool_event(tool_name: str, tool_input: dict | None = None) -> dict:
    return {
        "tool_name": tool_name,
        "tool_input": tool_input or {},
        "session_id": "hardening-test",
    }


def _make_sandbox(**overrides) -> SandboxTool:
    defaults = {
        "docker_available": False,
        "timeout_seconds": 30,
        "max_output_bytes": 1_048_576,
    }
    defaults.update(overrides)
    return SandboxTool(**defaults)


# ===================================================================
# 1. Sandbox — Native Fallback Gating (F3/F9)
# ===================================================================


class TestSandboxNativeFallback:
    """native_fallback config controls behavior when Docker is unavailable."""

    @pytest.mark.asyncio
    async def test_deny_refuses_execution(self) -> None:
        """native_fallback='deny' returns an error instead of executing."""
        sandbox = _make_sandbox(native_fallback="deny")
        result = await sandbox.execute({
            "operation": "execute",
            "command": "echo hello",
        })
        assert result.success is False
        assert "Docker is not available" in result.error["message"]
        assert "sandbox_type" in result.error

    @pytest.mark.asyncio
    async def test_warn_executes_with_warning(self) -> None:
        """native_fallback='warn' executes but adds an isolation warning."""
        sandbox = _make_sandbox(native_fallback="warn")
        result = await sandbox.execute({
            "operation": "execute",
            "command": "echo hello",
        })
        assert result.success is True
        assert "hello" in result.output["stdout"]
        assert "isolation_warning" in result.output
        assert "native mode" in result.output["isolation_warning"].lower()

    @pytest.mark.asyncio
    async def test_allow_executes_silently(self) -> None:
        """native_fallback='allow' executes without any warning."""
        sandbox = _make_sandbox(native_fallback="allow")
        result = await sandbox.execute({
            "operation": "execute",
            "command": "echo hello",
        })
        assert result.success is True
        assert "hello" in result.output["stdout"]
        assert "isolation_warning" not in result.output

    def test_invalid_native_fallback_raises(self) -> None:
        """An invalid native_fallback value raises ValueError."""
        with pytest.raises(ValueError, match="native_fallback"):
            _make_sandbox(native_fallback="yolo")

    @pytest.mark.asyncio
    async def test_status_includes_native_fallback(self) -> None:
        """Status output should report the native_fallback policy."""
        sandbox = _make_sandbox(native_fallback="deny")
        result = await sandbox.execute({"operation": "status"})
        assert result.output["native_fallback"] == "deny"


# ===================================================================
# 2. Sandbox — Workdir Validation (F16)
# ===================================================================


class TestSandboxWorkdirValidation:
    """workdir parameter is validated to prevent path traversal."""

    @pytest.mark.asyncio
    async def test_traversal_rejected(self) -> None:
        """workdir containing '..' is rejected."""
        sandbox = _make_sandbox(native_fallback="allow")
        result = await sandbox.execute({
            "operation": "execute",
            "command": "pwd",
            "workdir": "/tmp/../etc",
        })
        assert result.success is False
        assert "invalid workdir" in result.error["message"].lower()

    @pytest.mark.asyncio
    async def test_nonexistent_workdir_rejected(self) -> None:
        """workdir pointing to a non-existent directory is rejected."""
        sandbox = _make_sandbox(native_fallback="allow")
        result = await sandbox.execute({
            "operation": "execute",
            "command": "pwd",
            "workdir": "/nonexistent/dir/that/does/not/exist",
        })
        assert result.success is False
        assert "invalid workdir" in result.error["message"].lower()

    @pytest.mark.asyncio
    async def test_valid_workdir_accepted(self, tmp_path: Path) -> None:
        """A valid, existing directory is accepted."""
        sandbox = _make_sandbox(native_fallback="allow")
        result = await sandbox.execute({
            "operation": "execute",
            "command": "pwd",
            "workdir": str(tmp_path),
        })
        assert result.success is True


# ===================================================================
# 3. Sandbox — Network Restriction (F16)
# ===================================================================


class TestSandboxNetworkRestriction:
    """Only 'none' network mode is permitted."""

    @pytest.mark.asyncio
    async def test_host_network_rejected(self) -> None:
        """network='host' is rejected even when Docker is available."""
        sandbox = _make_sandbox(native_fallback="allow")
        result = await sandbox.execute({
            "operation": "execute",
            "command": "echo hello",
            "network": "host",
        })
        assert result.success is False
        assert "not allowed" in result.error["message"].lower()

    @pytest.mark.asyncio
    async def test_none_network_accepted(self) -> None:
        """network='none' is accepted."""
        sandbox = _make_sandbox(native_fallback="allow")
        result = await sandbox.execute({
            "operation": "execute",
            "command": "echo hello",
            "network": "none",
        })
        assert result.success is True


# ===================================================================
# 4. Sandbox — Mount Mode
# ===================================================================


class TestSandboxMountMode:
    """mount_mode controls Docker volume permissions."""

    def test_default_mount_mode_is_ro(self) -> None:
        """Default mount mode should be read-only."""
        sandbox = _make_sandbox()
        assert sandbox._mount_mode == "ro"

    def test_rw_mount_mode_accepted(self) -> None:
        """mount_mode='rw' is accepted when explicitly configured."""
        sandbox = _make_sandbox(mount_mode="rw")
        assert sandbox._mount_mode == "rw"

    def test_invalid_mount_mode_raises(self) -> None:
        """An invalid mount_mode raises ValueError."""
        with pytest.raises(ValueError, match="mount_mode"):
            _make_sandbox(mount_mode="rwx")


# ===================================================================
# 5. Allowlist Word-Boundary Matching
# ===================================================================


class TestAllowlistWordBoundary:
    """Allowlist prefix matching uses word boundaries, not bare startswith."""

    @pytest.mark.asyncio
    async def test_exact_prefix_with_space_matches(self, tmp_path: Path) -> None:
        """'echo hello' matches allowed prefix 'echo ' (with trailing space)."""
        hook = _make_hook(tmp_path, sandbox_mode="off")
        data = _tool_event("tool-bash", {"command": "echo hello"})
        result = await hook.handle("tool:pre", data)
        assert result.action == "continue"

    @pytest.mark.asyncio
    async def test_prefix_without_boundary_rejected(self, tmp_path: Path) -> None:
        """'gitevil --steal' must NOT match allowed prefix 'git'."""
        hook = _make_hook(tmp_path, sandbox_mode="off")
        data = _tool_event("tool-bash", {"command": "gitevil --steal"})
        result = await hook.handle("tool:pre", data)
        assert result.action == "ask_user", (
            "gitevil should NOT match 'git' prefix — word boundary violated"
        )

    @pytest.mark.asyncio
    async def test_prefix_with_space_boundary_matches(self, tmp_path: Path) -> None:
        """'git status' matches allowed prefix 'git' (space boundary)."""
        hook = _make_hook(tmp_path, sandbox_mode="off")
        data = _tool_event("tool-bash", {"command": "git status"})
        result = await hook.handle("tool:pre", data)
        assert result.action == "continue"

    @pytest.mark.asyncio
    async def test_prefix_with_slash_boundary_matches(self, tmp_path: Path) -> None:
        """'git/something' matches allowed prefix 'git' (slash boundary)."""
        hook = _make_hook(tmp_path, sandbox_mode="off")
        data = _tool_event("tool-bash", {"command": "git/something"})
        result = await hook.handle("tool:pre", data)
        assert result.action == "continue"

    @pytest.mark.asyncio
    async def test_prefix_with_hyphen_rejected(self, tmp_path: Path) -> None:
        """'git-evil' does NOT match allowed prefix 'git' (hyphen is not a boundary)."""
        hook = _make_hook(tmp_path, sandbox_mode="off")
        data = _tool_event("tool-bash", {"command": "git-evil --do-bad-things"})
        result = await hook.handle("tool:pre", data)
        assert result.action == "ask_user"


# ===================================================================
# 6. Path Allowlist Normalisation
# ===================================================================


class TestPathAllowlistNormalisation:
    """Path allowlist resolves paths to prevent traversal attacks."""

    @pytest.mark.asyncio
    async def test_traversal_path_not_downgraded(self, tmp_path: Path) -> None:
        """'/tmp/safe/../../etc/passwd' must NOT match allowlist '/tmp/safe/'."""
        hook = _make_hook(tmp_path, sandbox_mode="off")
        data = _tool_event(
            "tool-filesystem",
            {"file_path": "/tmp/safe/../../etc/passwd", "content": "evil"},
        )
        result = await hook.handle("tool:pre", data)
        # Medium-risk filesystem tool should NOT be downgraded to low
        # (it should stay at medium → continue with info message)
        assert result.user_message is not None, (
            "Path traversal must not downgrade to low — should stay medium with info"
        )

    @pytest.mark.asyncio
    async def test_clean_path_still_downgraded(self, tmp_path: Path) -> None:
        """'/tmp/safe/output.txt' should still match and downgrade."""
        hook = _make_hook(tmp_path, sandbox_mode="off")
        data = _tool_event(
            "tool-filesystem",
            {"file_path": "/tmp/safe/output.txt", "content": "safe data"},
        )
        result = await hook.handle("tool:pre", data)
        assert result.action == "continue"
        assert result.user_message is None  # low-risk = no info message


# ===================================================================
# 7. Unknown Sensitivity — Fail Closed
# ===================================================================


class TestSensitivityFailClosed:
    """Unknown sensitivity levels must be denied, not allowed."""

    def test_inject_module_denies_unknown(self) -> None:
        """hooks-memory-inject: unknown sensitivity returns False."""
        assert inject_allow("public", allow_private=False, allow_secret=False) is True
        assert inject_allow("private", allow_private=True, allow_secret=False) is True
        assert inject_allow("secret", allow_private=False, allow_secret=True) is True
        # Unknown level → denied (fail-closed)
        assert inject_allow("custom", allow_private=True, allow_secret=True) is False
        assert inject_allow("UNKNOWN", allow_private=True, allow_secret=True) is False

    def test_store_module_denies_unknown(self) -> None:
        """tool-memory-store: unknown sensitivity returns False."""
        assert store_allow("public", allow_private=False, allow_secret=False) is True
        assert store_allow("private", allow_private=True, allow_secret=False) is True
        assert store_allow("secret", allow_private=False, allow_secret=True) is True
        # Unknown level → denied (fail-closed)
        assert store_allow("custom", allow_private=True, allow_secret=True) is False
        assert store_allow("fancy", allow_private=True, allow_secret=True) is False


# ===================================================================
# 8. Memory Journal (F5/F6)
# ===================================================================


class TestMemoryJournal:
    """Memory mutations are recorded in the append-only journal table."""

    def test_insert_logged(self, tmp_path: Path) -> None:
        """store() should create a journal entry with operation='insert'."""
        store = MemoryStore(tmp_path / "mem.db")
        mem_id = store.store(content="journal test", category="test")

        entries = self._read_journal(tmp_path / "mem.db")
        insert_entries = [e for e in entries if e["operation"] == "insert"]
        assert len(insert_entries) >= 1
        assert insert_entries[0]["memory_id"] == mem_id

    def test_delete_logged(self, tmp_path: Path) -> None:
        """delete() should create a journal entry with operation='delete'."""
        store = MemoryStore(tmp_path / "mem.db")
        mem_id = store.store(content="to be deleted", category="test")
        store.delete(mem_id)

        entries = self._read_journal(tmp_path / "mem.db")
        delete_entries = [e for e in entries if e["operation"] == "delete"]
        assert len(delete_entries) >= 1
        assert delete_entries[0]["memory_id"] == mem_id

    def test_dedup_logged(self, tmp_path: Path) -> None:
        """Storing duplicate content should log a 'dedup_refresh' journal entry."""
        store = MemoryStore(tmp_path / "mem.db")
        content = "identical content for dedup test"
        store.store(content=content, category="test")
        store.store(content=content, category="test")  # duplicate

        entries = self._read_journal(tmp_path / "mem.db")
        dedup_entries = [e for e in entries if e["operation"] == "dedup_refresh"]
        assert len(dedup_entries) >= 1

    def test_journal_is_append_only(self, tmp_path: Path) -> None:
        """Journal entries cannot be deleted through the store interface."""
        store = MemoryStore(tmp_path / "mem.db")
        mem_id = store.store(content="audit trail", category="test")
        store.delete(mem_id)

        # After deleting the memory, journal entries remain
        entries = self._read_journal(tmp_path / "mem.db")
        assert len(entries) >= 2  # at least insert + delete

    @staticmethod
    def _read_journal(db_path: Path) -> list[dict]:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM memory_journal ORDER BY seq"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ===================================================================
# 9. Telemetry Event Completeness (F7/F8)
# ===================================================================


class TestTelemetryCompleteness:
    """Telemetry logs prompt hashes and tool I/O summaries."""

    @pytest.mark.asyncio
    async def test_prompt_submit_logs_hash(self, tmp_path: Path) -> None:
        """on_prompt_submit should log SHA-256 hash and length, not content."""
        metrics_path = tmp_path / "telemetry.jsonl"
        collector = TelemetryCollector(metrics_path)

        prompt = "Tell me about security hardening"
        await collector.on_prompt_submit(
            "prompt:submit", {"prompt": prompt}
        )

        lines = metrics_path.read_text().strip().splitlines()
        assert len(lines) >= 1
        record = json.loads(lines[0])
        assert record["event_type"] == "prompt_submit"
        metrics = record["metrics_snapshot"]
        expected_hash = hashlib.sha256(prompt.encode()).hexdigest()
        assert metrics["prompt_hash"] == expected_hash
        assert metrics["prompt_length"] == len(prompt)
        # Full prompt text must NOT appear in the log
        full_log = metrics_path.read_text()
        assert prompt not in full_log

    @pytest.mark.asyncio
    async def test_tool_pre_includes_input_summary(self, tmp_path: Path) -> None:
        """on_tool_pre should include a redacted summary of tool input."""
        metrics_path = tmp_path / "telemetry.jsonl"
        collector = TelemetryCollector(metrics_path)

        await collector.on_tool_pre(
            "tool:pre",
            {
                "tool_name": "tool-bash",
                "tool_call_id": "call_123",
                "tool_input": {"command": "echo secret"},
            },
        )

        lines = metrics_path.read_text().strip().splitlines()
        record = json.loads(lines[0])
        assert "input_summary" in record["metrics_snapshot"]

    @pytest.mark.asyncio
    async def test_tool_post_includes_output_summary(self, tmp_path: Path) -> None:
        """on_tool_post should include a redacted summary of tool output."""
        metrics_path = tmp_path / "telemetry.jsonl"
        collector = TelemetryCollector(metrics_path)

        # Start a timer first
        await collector.on_tool_pre(
            "tool:pre",
            {"tool_name": "tool-bash", "tool_call_id": "call_456"},
        )
        await collector.on_tool_post(
            "tool:post",
            {
                "tool_name": "tool-bash",
                "tool_call_id": "call_456",
                "tool_output": {"stdout": "hello world", "exit_code": 0},
            },
        )

        lines = metrics_path.read_text().strip().splitlines()
        post_record = json.loads(lines[-1])
        assert post_record["event_type"] == "tool_post"
        assert "output_summary" in post_record["metrics_snapshot"]
