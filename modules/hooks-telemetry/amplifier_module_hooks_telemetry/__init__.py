"""Telemetry and metrics collection hook for session observability.

Tracks tool invocations, provider token usage, durations, and error rates.
Writes metrics to JSONL and exposes a `telemetry.metrics` capability for
other modules to query live stats.
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from amplifier_core.models import HookResult

__amplifier_module_type__ = "hook"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Metrics collector
# ---------------------------------------------------------------------------


class TelemetryCollector:
    """Accumulates session-level telemetry and writes JSONL snapshots."""

    def __init__(self, metrics_path: Path) -> None:
        self._metrics_path = metrics_path
        self._session_start: float = time.monotonic()
        self._session_start_utc: str = _utcnow_iso()

        # Tool metrics  (keyed by tool name)
        self._tool_call_counts: dict[str, int] = defaultdict(int)
        self._tool_durations_ms: dict[str, list[float]] = defaultdict(list)
        self._tool_error_counts: dict[str, int] = defaultdict(int)

        # In-flight tool timings  (tool_call_id -> monotonic start)
        self._tool_timers: dict[str, float] = {}

        # Provider / token metrics
        self._provider_call_count: int = 0
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0

    # -- public API (exposed as capability) ---------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Return a point-in-time copy of all collected metrics."""
        uptime_s = time.monotonic() - self._session_start
        return {
            "session_start_utc": self._session_start_utc,
            "uptime_seconds": round(uptime_s, 2),
            "tools": {
                "call_counts": dict(self._tool_call_counts),
                "durations_ms": {
                    name: _stats(durations)
                    for name, durations in self._tool_durations_ms.items()
                },
                "error_counts": dict(self._tool_error_counts),
            },
            "provider": {
                "call_count": self._provider_call_count,
                "total_input_tokens": self._total_input_tokens,
                "total_output_tokens": self._total_output_tokens,
                "total_tokens": self._total_input_tokens + self._total_output_tokens,
            },
        }

    # -- event handlers -----------------------------------------------------

    async def on_session_start(self, event: str, data: dict[str, Any]) -> HookResult:
        self._session_start = time.monotonic()
        self._session_start_utc = _utcnow_iso()
        self._write_event("session_start", {"session_id": data.get("session_id")})
        return HookResult(action="continue")

    async def on_session_end(self, event: str, data: dict[str, Any]) -> HookResult:
        summary = self.snapshot()
        self._write_event("session_end", summary)

        total_calls = sum(self._tool_call_counts.values())
        total_errors = sum(self._tool_error_counts.values())
        total_tokens = summary["provider"]["total_tokens"]
        uptime = summary["uptime_seconds"]

        msg = (
            f"Session telemetry: {uptime:.0f}s uptime | "
            f"{total_calls} tool calls ({total_errors} errors) | "
            f"{self._provider_call_count} provider calls | "
            f"{total_tokens:,} tokens"
        )
        return HookResult(
            action="continue",
            user_message=msg,
            user_message_level="info",
            user_message_source="telemetry",
        )

    async def on_tool_pre(self, event: str, data: dict[str, Any]) -> HookResult:
        tool_name = data.get("tool_name", "unknown")
        call_id = data.get("tool_call_id", "")
        self._tool_call_counts[tool_name] += 1
        if call_id:
            self._tool_timers[call_id] = time.monotonic()
        self._write_event("tool_pre", {"tool_name": tool_name, "call_id": call_id})
        return HookResult(action="continue")

    async def on_tool_post(self, event: str, data: dict[str, Any]) -> HookResult:
        tool_name = data.get("tool_name", "unknown")
        call_id = data.get("tool_call_id", "")
        duration_ms: float | None = None
        if call_id and call_id in self._tool_timers:
            elapsed = time.monotonic() - self._tool_timers.pop(call_id)
            duration_ms = round(elapsed * 1000, 2)
            self._tool_durations_ms[tool_name].append(duration_ms)
        self._write_event(
            "tool_post",
            {"tool_name": tool_name, "call_id": call_id, "duration_ms": duration_ms},
        )
        return HookResult(action="continue")

    async def on_tool_error(self, event: str, data: dict[str, Any]) -> HookResult:
        tool_name = data.get("tool_name", "unknown")
        call_id = data.get("tool_call_id", "")
        error_msg = str(data.get("error", ""))[:500]
        self._tool_error_counts[tool_name] += 1
        # Clean up any in-flight timer
        self._tool_timers.pop(call_id, None)
        self._write_event(
            "tool_error",
            {"tool_name": tool_name, "call_id": call_id, "error": error_msg},
        )
        return HookResult(action="continue")

    async def on_provider_response(
        self, event: str, data: dict[str, Any]
    ) -> HookResult:
        self._provider_call_count += 1
        usage = data.get("usage") or {}
        input_tok = usage.get("input_tokens", 0)
        output_tok = usage.get("output_tokens", 0)
        self._total_input_tokens += input_tok
        self._total_output_tokens += output_tok
        self._write_event(
            "provider_response",
            {
                "input_tokens": input_tok,
                "output_tokens": output_tok,
                "cumulative_input": self._total_input_tokens,
                "cumulative_output": self._total_output_tokens,
            },
        )
        return HookResult(action="continue")

    # -- internal -----------------------------------------------------------

    def _write_event(self, event_type: str, metrics: dict[str, Any]) -> None:
        """Append one JSONL record.

        Never raises — telemetry must not break the session.
        """
        try:
            self._metrics_path.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "timestamp": _utcnow_iso(),
                "event_type": event_type,
                "metrics_snapshot": metrics,
            }
            with self._metrics_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, separators=(",", ":")) + "\n")
        except Exception:
            logger.debug(
                "telemetry: failed to write event %s", event_type, exc_info=True
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _stats(values: list[float]) -> dict[str, float]:
    """Compute min / max / mean / p95 for a list of durations."""
    if not values:
        return {}
    n = len(values)
    sorted_v = sorted(values)
    p95_idx = min(int(n * 0.95), n - 1)
    return {
        "count": n,
        "min": round(sorted_v[0], 2),
        "max": round(sorted_v[-1], 2),
        "mean": round(sum(sorted_v) / n, 2),
        "p95": round(sorted_v[p95_idx], 2),
    }


# ---------------------------------------------------------------------------
# Module entry point
# ---------------------------------------------------------------------------

_EVENT_MAP: list[tuple[str, str]] = [
    ("session:start", "on_session_start"),
    ("session:end", "on_session_end"),
    ("tool:pre", "on_tool_pre"),
    ("tool:post", "on_tool_post"),
    ("tool:error", "on_tool_error"),
    ("provider:response", "on_provider_response"),
]


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> None:
    """Mount telemetry hook.

    Register event handlers and expose metrics capability.
    """
    cfg = config or {}
    raw_path = cfg.get("metrics_path", "~/.letsgo/logs/telemetry.jsonl")
    metrics_path = Path(raw_path).expanduser()

    collector = TelemetryCollector(metrics_path)

    for event_name, method_name in _EVENT_MAP:
        handler = getattr(collector, method_name)
        coordinator.hooks.register(
            event=event_name,
            handler=handler,
            priority=90,
            name=f"telemetry.{method_name}",
        )

    # Expose capability so other modules can query live metrics
    coordinator.register_capability("telemetry.metrics", collector.snapshot)

    logger.info("hooks-telemetry mounted — writing to %s", metrics_path)
