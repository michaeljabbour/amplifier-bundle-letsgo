"""Tests for hooks-telemetry module.

Exercises the TelemetryCollector event handlers and snapshot() — verifying
counters, durations, error tracking, and that all handlers return
action='continue'. No running Amplifier session required.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from amplifier_module_hooks_telemetry import TelemetryCollector, mount


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_collector(tmp_path: Path) -> TelemetryCollector:
    """Create a TelemetryCollector writing to a temp JSONL file."""
    return TelemetryCollector(tmp_path / "telemetry.jsonl")


def _tool_pre_data(
    tool_name: str = "tool-bash", call_id: str = "call-001"
) -> dict:
    return {"tool_name": tool_name, "tool_call_id": call_id}


def _tool_post_data(
    tool_name: str = "tool-bash", call_id: str = "call-001"
) -> dict:
    return {"tool_name": tool_name, "tool_call_id": call_id}


def _tool_error_data(
    tool_name: str = "tool-bash",
    call_id: str = "call-001",
    error: str = "something broke",
) -> dict:
    return {"tool_name": tool_name, "tool_call_id": call_id, "error": error}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_pre_increments_count(tmp_path: Path) -> None:
    """on_tool_pre should increment the tool call count."""
    collector = _make_collector(tmp_path)

    await collector.on_tool_pre("tool:pre", _tool_pre_data("tool-bash", "c1"))
    await collector.on_tool_pre("tool:pre", _tool_pre_data("tool-bash", "c2"))
    await collector.on_tool_pre("tool:pre", _tool_pre_data("tool-grep", "c3"))

    snap = collector.snapshot()
    assert snap["tools"]["call_counts"]["tool-bash"] == 2
    assert snap["tools"]["call_counts"]["tool-grep"] == 1


@pytest.mark.asyncio
async def test_tool_post_records_duration(tmp_path: Path) -> None:
    """on_tool_post should record duration when a matching timer exists."""
    collector = _make_collector(tmp_path)

    # Start the timer via on_tool_pre
    await collector.on_tool_pre("tool:pre", _tool_pre_data("tool-bash", "c1"))

    # Small delay so duration is measurable
    time.sleep(0.01)

    # Complete via on_tool_post
    await collector.on_tool_post("tool:post", _tool_post_data("tool-bash", "c1"))

    snap = collector.snapshot()
    durations = snap["tools"]["durations_ms"]
    assert "tool-bash" in durations
    stats = durations["tool-bash"]
    assert stats["count"] == 1
    assert stats["min"] > 0  # should have non-zero duration


@pytest.mark.asyncio
async def test_tool_error_increments_errors(tmp_path: Path) -> None:
    """on_tool_error should increment the error count for that tool."""
    collector = _make_collector(tmp_path)

    await collector.on_tool_error("tool:error", _tool_error_data("tool-bash", "c1"))
    await collector.on_tool_error("tool:error", _tool_error_data("tool-bash", "c2"))

    snap = collector.snapshot()
    assert snap["tools"]["error_counts"]["tool-bash"] == 2


@pytest.mark.asyncio
async def test_snapshot_returns_metrics(tmp_path: Path) -> None:
    """snapshot() should return a dict with all expected top-level keys."""
    collector = _make_collector(tmp_path)

    # Generate some activity
    await collector.on_tool_pre("tool:pre", _tool_pre_data())
    await collector.on_tool_post("tool:post", _tool_post_data())
    await collector.on_provider_response(
        "provider:response",
        {"usage": {"input_tokens": 100, "output_tokens": 50}},
    )

    snap = collector.snapshot()

    # Top-level structure
    assert "session_start_utc" in snap
    assert "uptime_seconds" in snap
    assert isinstance(snap["uptime_seconds"], float)
    assert "tools" in snap
    assert "provider" in snap

    # Provider metrics
    assert snap["provider"]["call_count"] == 1
    assert snap["provider"]["total_input_tokens"] == 100
    assert snap["provider"]["total_output_tokens"] == 50
    assert snap["provider"]["total_tokens"] == 150


@pytest.mark.asyncio
async def test_all_handlers_return_continue(tmp_path: Path) -> None:
    """Every event handler must return HookResult(action='continue')."""
    collector = _make_collector(tmp_path)

    results = []
    results.append(
        await collector.on_session_start("session:start", {"session_id": "s1"})
    )
    results.append(
        await collector.on_tool_pre("tool:pre", _tool_pre_data())
    )
    results.append(
        await collector.on_tool_post("tool:post", _tool_post_data())
    )
    results.append(
        await collector.on_tool_error("tool:error", _tool_error_data())
    )
    results.append(
        await collector.on_provider_response(
            "provider:response", {"usage": {"input_tokens": 10, "output_tokens": 5}}
        )
    )
    results.append(
        await collector.on_session_end("session:end", {"session_id": "s1"})
    )

    for r in results:
        assert r.action == "continue", f"Expected 'continue', got '{r.action}'"


@pytest.mark.asyncio
async def test_session_end_includes_summary_message(tmp_path: Path) -> None:
    """on_session_end should include a user_message summary."""
    collector = _make_collector(tmp_path)

    await collector.on_tool_pre("tool:pre", _tool_pre_data("tool-bash", "c1"))
    result = await collector.on_session_end("session:end", {"session_id": "s1"})

    assert result.action == "continue"
    assert result.user_message is not None
    assert "telemetry" in result.user_message.lower()


@pytest.mark.asyncio
async def test_provider_response_accumulates_tokens(tmp_path: Path) -> None:
    """Multiple provider:response events should accumulate token counts."""
    collector = _make_collector(tmp_path)

    await collector.on_provider_response(
        "provider:response",
        {"usage": {"input_tokens": 100, "output_tokens": 50}},
    )
    await collector.on_provider_response(
        "provider:response",
        {"usage": {"input_tokens": 200, "output_tokens": 75}},
    )

    snap = collector.snapshot()
    assert snap["provider"]["call_count"] == 2
    assert snap["provider"]["total_input_tokens"] == 300
    assert snap["provider"]["total_output_tokens"] == 125
    assert snap["provider"]["total_tokens"] == 425


@pytest.mark.asyncio
async def test_mount_registers_hooks_and_capability(
    mock_coordinator, tmp_path: Path
) -> None:
    """mount() should register all event handlers and the metrics capability."""
    config = {"metrics_path": str(tmp_path / "telemetry.jsonl")}
    await mount(mock_coordinator, config)

    # Should register 7 hooks (session:start/end, prompt:submit, tool:pre/post/error, provider:response)
    assert len(mock_coordinator.hooks.registrations) == 7

    events = {r["event"] for r in mock_coordinator.hooks.registrations}
    assert "session:start" in events
    assert "session:end" in events
    assert "prompt:submit" in events
    assert "tool:pre" in events
    assert "tool:post" in events
    assert "tool:error" in events
    assert "provider:response" in events

    # tool:pre should be at priority 1 (before policy at 5)
    tool_pre_reg = [r for r in mock_coordinator.hooks.registrations if r["event"] == "tool:pre"]
    assert tool_pre_reg[0]["priority"] == 1

    # prompt:submit and other events should be at priority 90
    prompt_reg = [r for r in mock_coordinator.hooks.registrations if r["event"] == "prompt:submit"]
    assert prompt_reg[0]["priority"] == 90

    # Capability should be registered
    assert "telemetry.metrics" in mock_coordinator.capabilities
    # The capability should be callable and return a dict
    metrics_fn = mock_coordinator.capabilities["telemetry.metrics"]
    snap = metrics_fn()
    assert isinstance(snap, dict)
    assert "tools" in snap


@pytest.mark.asyncio
async def test_metrics_file_written(tmp_path: Path) -> None:
    """Event handlers should write JSONL records to the metrics file."""
    metrics_path = tmp_path / "telemetry.jsonl"
    collector = TelemetryCollector(metrics_path)

    await collector.on_tool_pre("tool:pre", _tool_pre_data())

    assert metrics_path.exists()
    lines = metrics_path.read_text().strip().splitlines()
    assert len(lines) >= 1
