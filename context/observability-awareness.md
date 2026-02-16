# Observability

LetsGo provides session-level telemetry via `hooks-telemetry`.

## What Is Tracked

| Metric | Source Event | Details |
|--------|-------------|---------|
| Tool call counts | `tool:pre` | Per-tool name counters |
| Tool durations | `tool:post` | min/max/mean/p95 statistics per tool |
| Tool errors | `tool:error` | Per-tool error counters, truncated messages |
| Provider calls | `provider:response` | Call count, cumulative input/output tokens |
| Prompt hashes | `prompt:submit` | SHA-256 hash + length (never full content) |

## Event Log

All events are written as JSONL to `~/.letsgo/logs/telemetry.jsonl`.

Each record contains:
- `timestamp` — ISO-8601 UTC
- `event_type` — one of `session_start`, `session_end`, `prompt_submit`, `tool_pre`, `tool_post`, `tool_error`, `provider_response`
- `metrics_snapshot` — event-specific payload

Tool events include redacted input/output summaries (keys and types only,
never full payloads) for replay correlation.

## Live Metrics

Other modules can query live metrics via the `telemetry.metrics` capability,
which returns a point-in-time snapshot of all counters and statistics.

## Hook Priority

The telemetry `tool:pre` handler runs at **priority 1** (before tool-policy
at priority 5) so that ALL tool call attempts are counted — including those
subsequently denied by policy. All other handlers run at priority 90.

## What You Should Know

- Telemetry never blocks or modifies tool execution — it only observes.
- Write failures are silently caught; telemetry never breaks the session.
- Error messages are truncated to 500 characters.
- No secret values flow through telemetry events.
