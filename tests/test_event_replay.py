"""Event replay test harness — verifies tool policy decisions are deterministic.

Records a series of tool:pre events and their HookResult actions, then replays
the same events through a fresh hook instance and asserts identical outcomes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from amplifier_module_hooks_tool_policy import ToolPolicyHook


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hook(tmp_path: Path, **overrides: object) -> ToolPolicyHook:
    """Create a ToolPolicyHook with comprehensive test config covering all tiers."""
    config: dict[str, object] = {
        "blocked_tools": ["tool-dangerous", "tool-nuke"],
        "high_risk_tools": ["tool-bash", "tool-write-file"],
        "medium_risk_tools": ["tool-filesystem", "tool-edit-file"],
        "low_risk_tools": ["tool-grep", "tool-glob", "tool-search", "tool-todo"],
        "allowed_commands": ["echo ", "ls ", "cat "],
        "allowed_write_paths": ["/tmp/safe/"],
        "sandbox_mode": "off",
        "default_action": "deny",
        "careful_mode": True,
        "automation_mode": False,
        "audit_log_path": str(tmp_path / "replay-audit.jsonl"),
    }
    config.update(overrides)
    return ToolPolicyHook(config)


def _tool_event(
    tool_name: str, tool_input: dict[str, object] | None = None
) -> dict[str, object]:
    """Build a minimal tool:pre event data dict."""
    return {
        "tool_name": tool_name,
        "tool_input": tool_input or {},
        "session_id": "replay-test-session",
    }


# 10 diverse events covering every risk tier and edge case:
#   [0] blocked                    [5] high → downgraded via command allowlist
#   [1] high (no allowlist match)  [6] medium → downgraded via path allowlist
#   [2] medium                     [7] low
#   [3] low                        [8] blocked (second tool)
#   [4] unlisted → deny            [9] medium (second tool)
DIVERSE_EVENTS: list[dict[str, object]] = [
    _tool_event("tool-dangerous"),
    _tool_event("tool-bash", {"command": "rm -rf /"}),
    _tool_event("tool-filesystem", {"file_path": "/etc/hosts"}),
    _tool_event("tool-grep", {"pattern": "TODO"}),
    _tool_event("tool-unknown-thing"),
    _tool_event("tool-bash", {"command": "echo hello world"}),
    _tool_event(
        "tool-filesystem",
        {"file_path": "/tmp/safe/out.txt", "content": "data"},
    ),
    _tool_event("tool-glob", {"pattern": "**/*.py"}),
    _tool_event("tool-nuke"),
    _tool_event("tool-edit-file", {"file_path": "/src/main.py"}),
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replay_produces_identical_decisions(tmp_path: Path) -> None:
    """Record 10 diverse events, replay through a fresh hook, assert identical."""
    # --- Record phase ---
    hook_a = _make_hook(tmp_path / "a")
    recorded: list[tuple[dict[str, object], str]] = []

    for event_data in DIVERSE_EVENTS:
        result = await hook_a.handle("tool:pre", event_data)
        recorded.append((event_data, result.action))

    assert len(recorded) == 10

    # Sanity-check a few known outcomes (default-deny, sandbox_mode=off):
    assert recorded[0][1] == "deny"      # blocked
    assert recorded[1][1] == "ask_user"  # high, no allowlist
    assert recorded[3][1] == "continue"  # low
    assert recorded[4][1] == "deny"      # unlisted, default_action=deny
    assert recorded[5][1] == "continue"  # high → downgraded to low

    # --- Replay phase: fresh instance, identical config ---
    hook_b = _make_hook(tmp_path / "b")

    for event_data, expected_action in recorded:
        result = await hook_b.handle("tool:pre", event_data)
        tool = event_data.get("tool_name", "?")
        assert result.action == expected_action, (
            f"Replay mismatch for {tool}: "
            f"expected {expected_action!r}, got {result.action!r}"
        )


@pytest.mark.asyncio
async def test_replay_with_automation_mode(tmp_path: Path) -> None:
    """Same replay approach but with automation_mode=True.

    Key behavioural shifts under automation:
      - high-risk (non-downgraded) → deny instead of ask_user
      - secrets tools → blocked
      - unlisted tools → deny regardless of default_action
    """
    # --- Record phase ---
    hook_a = _make_hook(tmp_path / "a", automation_mode=True)
    recorded: list[tuple[dict[str, object], str]] = []

    for event_data in DIVERSE_EVENTS:
        result = await hook_a.handle("tool:pre", event_data)
        recorded.append((event_data, result.action))

    # Sanity: non-downgraded high-risk is denied (not ask_user) in automation
    assert recorded[1][1] == "deny"
    # Downgraded bash (echo) should still pass — downgrade happens before check
    assert recorded[5][1] == "continue"

    # --- Replay phase ---
    hook_b = _make_hook(tmp_path / "b", automation_mode=True)

    for event_data, expected_action in recorded:
        result = await hook_b.handle("tool:pre", event_data)
        tool = event_data.get("tool_name", "?")
        assert result.action == expected_action, (
            f"Automation replay mismatch for {tool}: "
            f"expected {expected_action!r}, got {result.action!r}"
        )


@pytest.mark.asyncio
async def test_replay_with_allowlist_downgrades(tmp_path: Path) -> None:
    """Events that trigger allowlist downgrades produce identical results on replay."""
    downgrade_events = [
        _tool_event("tool-bash", {"command": "echo test output"}),
        _tool_event("tool-bash", {"command": "ls /tmp/safe"}),
        _tool_event("tool-bash", {"command": "cat README.md"}),
        _tool_event(
            "tool-filesystem",
            {"file_path": "/tmp/safe/output.txt", "content": "data"},
        ),
    ]

    # --- Record ---
    hook_a = _make_hook(tmp_path / "a")
    recorded: list[tuple[dict[str, object], str]] = []

    for event_data in downgrade_events:
        result = await hook_a.handle("tool:pre", event_data)
        recorded.append((event_data, result.action))
        # All downgrades with sandbox_mode=off should land on "continue"
        assert result.action == "continue", (
            f"Expected downgrade → continue for {event_data.get('tool_input')}"
        )

    # --- Replay ---
    hook_b = _make_hook(tmp_path / "b")

    for event_data, expected_action in recorded:
        result = await hook_b.handle("tool:pre", event_data)
        assert result.action == expected_action


@pytest.mark.asyncio
async def test_event_log_serialization(tmp_path: Path) -> None:
    """Record events to JSONL, read them back, replay, verify.

    Proves that json.dumps({"event_data": ..., "action": ...}) per line
    is a sufficient format for deterministic replay.
    """
    log_path = tmp_path / "event_log.jsonl"

    # --- Record phase: run events and persist to JSONL ---
    hook_a = _make_hook(tmp_path / "a")

    with log_path.open("w") as f:
        for event_data in DIVERSE_EVENTS:
            result = await hook_a.handle("tool:pre", event_data)
            entry = {"event_data": event_data, "action": result.action}
            f.write(json.dumps(entry, default=str) + "\n")

    # --- Deserialize phase: read JSONL back ---
    loaded: list[tuple[dict[str, object], str]] = []

    with log_path.open() as f:
        for line in f:
            entry = json.loads(line)
            loaded.append((entry["event_data"], entry["action"]))

    assert len(loaded) == len(DIVERSE_EVENTS), (
        f"Log line count {len(loaded)} != event count {len(DIVERSE_EVENTS)}"
    )

    # --- Replay phase: fresh hook replays from the deserialized log ---
    hook_b = _make_hook(tmp_path / "b")

    for event_data, expected_action in loaded:
        result = await hook_b.handle("tool:pre", event_data)
        tool = event_data.get("tool_name", "?")
        assert result.action == expected_action, (
            f"Serialized replay mismatch for {tool}: "
            f"expected {expected_action!r}, got {result.action!r}"
        )

    # Verify the JSONL is well-formed: every line is valid JSON
    with log_path.open() as f:
        for i, line in enumerate(f, 1):
            parsed = json.loads(line)
            assert "event_data" in parsed, f"Line {i} missing event_data"
            assert "action" in parsed, f"Line {i} missing action"
