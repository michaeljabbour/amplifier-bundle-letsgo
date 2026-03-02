# Observability

LetsGo provides session-level telemetry via `hooks-telemetry`. Events are written as JSONL to `~/.letsgo/logs/telemetry.jsonl`.

## What Is Tracked

| Metric | Source Event | Details |
|--------|-------------|---------|
| Tool call counts | `tool:pre` | Per-tool name counters |
| Tool durations | `tool:post` | min/max/mean/p95 statistics per tool |
| Tool errors | `tool:error` | Per-tool error counters, truncated messages |
| Provider calls | `provider:response` | Call count, cumulative input/output tokens |
| Prompt hashes | `prompt:submit` | SHA-256 hash + length (never full content) |

## What You Should Know

- Telemetry never blocks or modifies tool execution — it only observes.
- Write failures are silently caught; telemetry never breaks the session.
- Error messages are truncated to 500 characters.
- No secret values flow through telemetry events.
