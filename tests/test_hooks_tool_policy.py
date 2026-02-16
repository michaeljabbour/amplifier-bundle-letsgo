"""Tests for hooks-tool-policy module.

Exercises risk classification, allowlist downgrades, sandbox rewriting,
and the JSONL audit trail — all against the ToolPolicyHook class directly,
with no running Amplifier session required.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from amplifier_module_hooks_tool_policy import ToolPolicyHook, mount


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hook(tmp_path: Path, **overrides) -> ToolPolicyHook:
    """Create a ToolPolicyHook with sane test defaults."""
    config = {
        "blocked_tools": ["tool-dangerous"],
        "high_risk_tools": ["tool-bash"],
        "medium_risk_tools": ["tool-filesystem"],
        "low_risk_tools": ["tool-grep"],
        "allowed_commands": ["echo ", "ls "],
        "allowed_write_paths": ["/tmp/safe/"],
        "sandbox_mode": "off",
        "audit_log_path": str(tmp_path / "audit.jsonl"),
    }
    config.update(overrides)
    return ToolPolicyHook(config)


def _tool_event(tool_name: str, tool_input: dict | None = None) -> dict:
    """Build a minimal tool:pre event data dict."""
    return {
        "tool_name": tool_name,
        "tool_input": tool_input or {},
        "session_id": "test-session-001",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blocked_tool_denied(tmp_path: Path) -> None:
    """A tool in blocked_tools must return action='deny'."""
    hook = _make_hook(tmp_path)
    data = _tool_event("tool-dangerous")

    result = await hook.handle("tool:pre", data)

    assert result.action == "deny"
    assert "blocked" in (result.reason or "").lower()


@pytest.mark.asyncio
async def test_high_risk_tool_asks_user(tmp_path: Path) -> None:
    """A high-risk tool (not allowlisted) must return action='ask_user'."""
    hook = _make_hook(tmp_path, allowed_commands=[])  # no allowlist
    data = _tool_event("tool-bash", {"command": "rm -rf /"})

    result = await hook.handle("tool:pre", data)

    assert result.action == "ask_user"
    assert result.approval_prompt is not None
    assert "tool-bash" in result.approval_prompt


@pytest.mark.asyncio
async def test_low_risk_tool_continues(tmp_path: Path) -> None:
    """A low-risk tool must return action='continue'."""
    hook = _make_hook(tmp_path)
    data = _tool_event("tool-grep")

    result = await hook.handle("tool:pre", data)

    assert result.action == "continue"


@pytest.mark.asyncio
async def test_command_allowlist_downgrade(tmp_path: Path) -> None:
    """An allowed bash command prefix should downgrade high -> low -> continue.

    With sandbox_mode='off', the result is a plain continue (no ask_user).
    """
    hook = _make_hook(tmp_path, sandbox_mode="off")
    data = _tool_event("tool-bash", {"command": "echo hello world"})

    result = await hook.handle("tool:pre", data)

    assert result.action == "continue"


@pytest.mark.asyncio
async def test_sandbox_rewrite(tmp_path: Path) -> None:
    """With sandbox_mode='enforce', an allowlisted bash call gets rewritten
    to tool-sandbox via action='modify'.
    """
    hook = _make_hook(tmp_path, sandbox_mode="enforce")
    data = _tool_event("tool-bash", {"command": "echo hello"})

    result = await hook.handle("tool:pre", data)

    assert result.action == "modify"
    assert result.data is not None
    assert result.data["tool_name"] == "tool-sandbox"
    assert result.data["tool_input"]["command"] == "echo hello"
    assert result.data["tool_input"]["original_tool"] == "tool-bash"


@pytest.mark.asyncio
async def test_audit_log_written(tmp_path: Path) -> None:
    """Every handle() call must append a JSON line to the audit log."""
    audit_path = tmp_path / "audit.jsonl"
    hook = _make_hook(tmp_path)
    data = _tool_event("tool-grep")

    await hook.handle("tool:pre", data)

    assert audit_path.exists()
    lines = audit_path.read_text().strip().splitlines()
    assert len(lines) == 1

    entry = json.loads(lines[0])
    assert entry["tool_name"] == "tool-grep"
    assert entry["session_id"] == "test-session-001"
    assert entry["risk_level"] == "low"
    assert "timestamp" in entry


@pytest.mark.asyncio
async def test_mount_registers_hook(mock_coordinator, tmp_path: Path) -> None:
    """mount() should register a tool:pre hook on the coordinator."""
    config = {"audit_log_path": str(tmp_path / "audit.jsonl")}
    cleanup = await mount(mock_coordinator, config)

    assert len(mock_coordinator.hooks.registrations) == 1
    reg = mock_coordinator.hooks.registrations[0]
    assert reg["event"] == "tool:pre"
    assert reg["name"] == "hooks-tool-policy"
    assert reg["priority"] == 5

    # cleanup callable should unregister
    cleanup()
    assert len(mock_coordinator.hooks.registrations) == 0


@pytest.mark.asyncio
async def test_unlisted_tool_defaults_to_low(tmp_path: Path) -> None:
    """Tools not in any risk list should default to low risk."""
    hook = _make_hook(tmp_path)
    data = _tool_event("tool-unknown-new-thing")

    result = await hook.handle("tool:pre", data)

    assert result.action == "continue"


@pytest.mark.asyncio
async def test_path_allowlist_downgrades_medium(tmp_path: Path) -> None:
    """A filesystem write to an allowed path should downgrade medium -> low."""
    hook = _make_hook(tmp_path, sandbox_mode="off")
    data = _tool_event(
        "tool-filesystem",
        {"file_path": "/tmp/safe/output.txt", "content": "data"},
    )

    result = await hook.handle("tool:pre", data)

    # Downgraded from medium to low => continue (no info message about medium)
    assert result.action == "continue"
    # A true low-risk result has no user_message
    assert result.user_message is None
