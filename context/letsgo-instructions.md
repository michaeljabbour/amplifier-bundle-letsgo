# LetsGo Capabilities

You have enhanced capabilities provided by the LetsGo bundle. Use them appropriately.

## Available Capabilities

| Capability | Type | Purpose |
|------------|------|---------|
| Tool Policy | Hook | Classifies tool calls by risk level, gates high-risk operations |
| Secrets | Tool | Encrypted storage for API keys, tokens, and credentials |
| Sandbox | Tool | Isolated Docker execution for untrusted or experimental code |
| Telemetry | Hook | Metrics collection — tool latency, token usage, error rates |
| Memory | Hook+Tool | Neuroscience-inspired memory pipeline — capture, score, consolidate, compress, inject |
| Memory Store | `memory` tool | Persistent memory with scored search, dedup, TTL, facts, sensitivity gating |
| Memory Capture | auto (hook) | Extracts observations from tool results; gated by memorability scoring |
| Memory Boundaries | auto (hook) | Detects contextual shifts in tool activity for segment-aware memory |
| Memory Memorability | auto (capability) | Scores content memorability; filters low-value observations before storage |
| Memory Temporal | auto (capability) | Multi-scale retrieval: immediate, task, session, project timescales |
| Memory Consolidation | auto (hook) | Boosts accessed memories, decays unused ones at session end |
| Memory Compression | auto (hook) | Clusters and merges similar old memories at session end |
| Memory Injection | auto (hook) | Injects relevant memories into each prompt as ephemeral context |
| Gateway | Application | Multi-channel messaging daemon with sender pairing and cron scheduling |
| Modes | Runtime | Careful mode (approval gates) and Automation mode (restricted profile) |
| Skills | Knowledge | Domain expertise packages — browser automation, image generation, scheduling, messaging, skill authoring |

## Behavioral Guidelines

- **High-risk tools** (bash, write_file) are auto-allowed by default.
- Enable `careful_mode` in tool-policy config to require explicit approval prompts.
- **Secrets** must always go through `tool-secrets` — never store credentials in plain text, environment variables, or conversation history.
- **Untrusted code** should be executed inside the sandbox when available.
- **Telemetry** runs silently in the background. Other modules can query live metrics via the `telemetry.metrics` capability.

## Context Awareness

Each capability injects its own thin awareness context. Refer to them for specific usage rules:

- Tool policy risk levels and approval behavior
- Secret management operations and security rules
- Sandbox resource limits and network isolation
- Telemetry output location and metric types
- Memory system operations and safety rules (see `memory-system-awareness.md`)

## Memory System

LetsGo includes a bio-inspired memory system. The `memory` tool provides durable
storage with scored retrieval, structured facts, and TTL-based expiry. Several
background hooks handle automatic capture, memorability filtering, consolidation,
compression, and injection — these run without explicit invocation.

For complex multi-criteria retrieval, maintenance, or memory health analysis,
delegate to `letsgo:memory-curator`.

## Gateway

The gateway is a multi-channel messaging daemon that bridges external messaging
platforms (webhook, telegram, discord, slack) to Amplifier sessions. It handles
sender pairing, message routing, and cron-based scheduled tasks. Use the
`setup-wizard` recipe for first-run configuration.

## Modes

LetsGo supports runtime modes that adjust agent behavior:

- **Careful mode** — enables approval gates on high-risk tool calls, requiring explicit user confirmation before execution.
- **Automation mode** — applies a restricted profile suitable for unattended operation, limiting tools to a safe subset.

## Skills

Domain expertise packages that provide specialized knowledge and workflows.
Available skills cover browser automation, image generation, scheduling,
messaging integration, and skill authoring. Use `load_skill` to discover
and load skills as needed.
