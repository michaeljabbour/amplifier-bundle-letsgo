# LetsGo

> Security, memory, secrets, sandbox, observability, gateway, and multi-agent capabilities for Amplifier.

## Overview

LetsGo is a comprehensive Amplifier bundle that provides enterprise-grade capabilities for AI agent sessions. It wraps security policies, encrypted secret management, sandboxed execution, telemetry, a neuroscience-inspired memory system, and a multi-channel messaging gateway into a single composable package.

Every module follows Amplifier's thin-bundle philosophy: behaviors compose modules, modules register capabilities, and hooks subscribe to events. Nothing is monolithic — you can include the full capability set or pick individual behaviors.

## Quick Start

```yaml
# In your bundle.md
includes:
  - bundle: letsgo:behaviors/letsgo-capabilities
```

This single include activates all LetsGo capabilities. For selective inclusion, reference individual behaviors:

```yaml
includes:
  - bundle: letsgo:behaviors/security-policy
  - bundle: letsgo:behaviors/memory-pipeline
  - bundle: letsgo:behaviors/secrets-management
```

## Capabilities

### Security & Tool Policy

The `hooks-tool-policy` module intercepts every tool call at `tool:pre` priority 5, enforcing a 4-tier risk classification system.

- **4-tier risk classification**: blocked, high, medium, low, plus unclassified fallback
- **Command allowlist**: Prefix matching with word boundaries for bash commands
- **Path allowlist**: Prefix matching with path-traversal protection for filesystem writes
- **Careful mode**: Approval gates for high-risk tools with configurable timeout (default 30s)
- **Automation mode**: Restrictive policy for unattended runs — blocks secrets, denies high-risk and unclassified tools
- **Sandbox rewrite**: Optional auto-routing of bash calls through the sandbox
- **JSONL audit trail**: Full audit log at `~/.letsgo/logs/tool-policy-audit.jsonl`

See [docs/TOOL_POLICY_GUIDE.md](docs/TOOL_POLICY_GUIDE.md) for the complete reference.

### Encrypted Secrets

The `tool-secrets-manager` provides encrypted credential storage with handle-based access.

- **Fernet encryption**: AES-128-CBC + HMAC-SHA256 for data at rest
- **Handle-based access**: `get_secret` returns an opaque handle, never plaintext — handles are passed to sandbox execution where they are resolved
- **5-minute handle TTL**: Handles expire automatically to limit exposure window
- **Operations**: get, set, list, delete, rotate
- **Archive on rotate**: Previous values are archived with timestamps for audit
- **Audit trail**: Every access (get, set, rotate, delete) is logged with timestamps and session context
- **Automation lockout**: Secrets tool is entirely blocked in automation mode

### Sandboxed Execution

The `tool-sandbox` provides isolated command execution with resource limits.

- **Docker-first**: Uses Docker containers when available for full isolation
- **Native fallback**: Falls back to restricted subprocess with resource limits when Docker is unavailable
- **Resource limits**: 512MB memory, 1.0 CPU, 120-second timeout (all configurable)
- **Network isolation**: Only `none` network mode is permitted — no outbound connections
- **Read-only mount**: Project directory mounted read-only by default
- **Sandbox rewrite integration**: When `sandbox_mode=enforce` in tool policy, bash calls are automatically routed through the sandbox

### Observability & Telemetry

The `hooks-telemetry` module provides comprehensive session observability.

- **7-event subscription**: Covers session (start/end), prompt (submit/complete), tool (pre/post), and provider events
- **Tool metrics**: Call counts, durations (min/max/mean/p95), error counts per tool
- **Token tracking**: Input tokens, output tokens, cumulative totals per provider call
- **Session summary**: Generated at session end with aggregate statistics
- **JSONL telemetry log**: Structured event log at `~/.letsgo/logs/telemetry.jsonl`

### Memory System (Neuroscience-Inspired)

An 8-module pipeline that gives agents durable, intelligent memory across sessions. Inspired by human memory formation: encoding, consolidation, compression, and retrieval.

| # | Module             | Role                                                              |
|---|--------------------|-------------------------------------------------------------------|
| 1 | **Store**          | SQLite + FTS5 data layer. Scored search (match 0.55, recency 0.20, importance 0.15, trust 0.10). SHA-256 dedup, TTL/expiry, access counting, fact store (S/P/O triples), mutation journal. |
| 2 | **Memorability**   | Selective encoding. Scores content 0.0-1.0 on substance, salience, distinctiveness, type weight. Gate threshold: 0.30. |
| 3 | **Boundaries**     | Event segmentation. Detects context shifts via keyword Jaccard similarity in sliding window. Records boundaries as facts. |
| 4 | **Capture**        | Auto-capture from tool outputs. Classifies observations (bugfix/feature/refactor/change/discovery/decision). Auto-generates titles, subtitles, importance, concept tags. Session summaries and checkpoints. |
| 5 | **Temporal**       | Multi-scale scaffolding. 4 scales: immediate (5min), task (30min), session (2hr), project. Default allocation: 1+2+1+1 = 5 memories. |
| 6 | **Consolidation**  | Session-end replay (priority 200). Logarithmic boost for accessed memories, linear decay for unaccessed. Decisions and discoveries decay at half rate. |
| 7 | **Compression**    | Session-end cluster-and-merge (priority 300). Greedy single-linkage clustering by Jaccard similarity. Merges clusters of 3+. Only processes memories older than 7 days. |
| 8 | **Injection**      | Prompt-time injection (priority 50). Queries store and temporal scaffolding. Formats as `<memory-context>` block. Memory governor blocks instruction-like content. Token budget: 2000, max 5 memories. |

See [docs/MEMORY_GUIDE.md](docs/MEMORY_GUIDE.md) for the complete reference.

### Gateway

The `gateway-daemon` provides multi-channel messaging and scheduled automation.

- **Multi-channel support**: Webhook, Telegram, Discord, Slack — unified message routing
- **Sender pairing**: 6-character authentication codes for sender identity verification
- **Session routing**: Per-sender Amplifier session routing with automatic stale session cleanup
- **Cron scheduler**: Cron expressions for timed automation — schedules persist across restarts
- **Heartbeat engine**: Proactive session creation — CronScheduler fires HeartbeatEngine per agent, building prompts from context files and executing full Amplifier sessions
- **Rate limiting**: 10 requests per minute sliding window per sender
- **Message queue**: SQLite-backed durable queue with retry logic

## Constructs

### Modules (12)

| Module                       | Type | Purpose                                        |
|------------------------------|------|------------------------------------------------|
| `hooks-tool-policy`          | hook | Tool call risk classification and gating       |
| `hooks-telemetry`            | hook | Session observability and metrics              |
| `hooks-memory-memorability`  | hook | Content memorability scoring                   |
| `hooks-memory-boundaries`    | hook | Event segmentation and context shift detection |
| `hooks-memory-capture`       | hook | Auto-capture and classification of observations|
| `hooks-memory-temporal`      | hook | Multi-scale temporal memory scaffolding        |
| `hooks-memory-consolidation` | hook | Access-based boost and age-based decay         |
| `hooks-memory-compression`   | hook | Cluster-and-merge memory compaction            |
| `hooks-memory-inject`        | hook | Prompt-time memory retrieval and injection     |
| `tool-memory-store`          | tool | Memory CRUD, search, facts, and maintenance    |
| `tool-secrets-manager`       | tool | Encrypted secret storage with handle access    |
| `tool-sandbox`               | tool | Isolated command execution with resource limits|

### Behaviors (15)

| Behavior                     | Description                                          |
|------------------------------|------------------------------------------------------|
| `letsgo-capabilities`        | Full capability set — includes all other behaviors   |
| `security-policy`            | Tool policy, risk classification, allowlists         |
| `secrets-management`         | Encrypted secrets with handle-based access           |
| `sandbox-execution`          | Docker-first sandboxed command execution             |
| `telemetry`                  | Session observability and metrics collection         |
| `memory-pipeline`            | Full 8-module memory system                          |
| `memory-store`               | Memory data layer only (SQLite + FTS5)               |
| `memory-capture`             | Capture + memorability + boundaries                  |
| `memory-temporal`            | Temporal scaffolding only                            |
| `memory-consolidation`       | Consolidation + compression                          |
| `memory-injection`           | Prompt-time memory injection only                    |
| `gateway`                    | Multi-channel messaging daemon                       |
| `gateway-scheduler`          | Cron-based scheduled automation                      |
| `heartbeat`                  | Proactive agent check-ins via HeartbeatEngine        |
| `careful-mode`               | Approval gates for high-risk operations              |

### Context Files (13)

| Context File                 | Purpose                                             |
|------------------------------|-----------------------------------------------------|
| `MEMORY_GUIDE.md`            | Comprehensive memory system reference               |
| `TOOL_POLICY_GUIDE.md`       | Tool policy and risk classification reference       |
| `memory-operations.md`       | Memory tool operation reference                     |
| `memory-concepts.md`         | Concept taxonomy and usage guide                    |
| `security-model.md`          | Security architecture overview                      |
| `secrets-operations.md`      | Secrets tool operation reference                    |
| `sandbox-operations.md`      | Sandbox tool operation reference                    |
| `gateway-operations.md`      | Gateway configuration and operations                |
| `telemetry-events.md`        | Telemetry event schema reference                    |
| `capability-registry.md`     | Full capability registry with providers/consumers   |
| `heartbeat-awareness.md`    | Heartbeat system awareness for agent sessions       |
| `heartbeat-system.md`       | Heartbeat engine architecture and configuration     |
| `agents/default.md`         | Default heartbeat agent prompt template             |

### Agents (3)

| Agent                | Purpose                                                         |
|----------------------|-----------------------------------------------------------------|
| `memory-curator`     | Memory system management — maintenance, search, analysis, and health monitoring |
| `security-reviewer`  | Security posture review — policy audit, allowlist verification, log analysis |
| `gateway-operator`   | Gateway management — channel configuration, sender pairing, schedule management |

### Recipes (4)

| Recipe                       | Purpose                                           |
|------------------------------|---------------------------------------------------|
| `daily-digest`               | Daily summary generation and distribution         |
| `memory-maintenance`         | Scheduled memory consolidation and compression    |
| `channel-onboard`            | Channel setup and sender pairing workflow         |
| `setup-wizard`               | First-run project setup with memory, secrets, and policy |

### Skills (5)

| Skill                        | Description                                       |
|------------------------------|---------------------------------------------------|
| `memory-patterns`            | Best practices for memory storage and retrieval   |
| `security-hardening`         | Security configuration and hardening guide        |
| `gateway-channels`           | Channel-specific setup guides (Telegram, Discord, Slack) |
| `recipe-scheduling`          | Cron expression patterns and scheduling strategies|
| `troubleshooting`            | Common issues and diagnostic procedures           |

### Modes (2)

| Mode           | Description                                                    |
|----------------|----------------------------------------------------------------|
| `careful`      | Require approval for high-risk tool calls. Activates approval gates on bash and write_file. |
| `automation`   | Restrict tool access for unattended execution. Blocks secrets, denies high-risk and unclassified tools. |

## Architecture

### Bundle Composition

```
bundle.md
  +-- includes: letsgo:behaviors/letsgo-capabilities
        |
        +-- behaviors/security-policy.yaml
        |     +-- modules: hooks-tool-policy
        |     +-- context: security-model.md, TOOL_POLICY_GUIDE.md
        |
        +-- behaviors/secrets-management.yaml
        |     +-- modules: tool-secrets-manager
        |     +-- context: secrets-operations.md
        |
        +-- behaviors/sandbox-execution.yaml
        |     +-- modules: tool-sandbox
        |     +-- context: sandbox-operations.md
        |
        +-- behaviors/telemetry.yaml
        |     +-- modules: hooks-telemetry
        |     +-- context: telemetry-events.md
        |
        +-- behaviors/memory-pipeline.yaml
        |     +-- modules: tool-memory-store,
        |     |           hooks-memory-memorability,
        |     |           hooks-memory-boundaries,
        |     |           hooks-memory-capture,
        |     |           hooks-memory-temporal,
        |     |           hooks-memory-consolidation,
        |     |           hooks-memory-compression,
        |     |           hooks-memory-inject
        |     +-- context: MEMORY_GUIDE.md, memory-operations.md
        |
        +-- behaviors/gateway.yaml
              +-- modules: gateway-daemon
              +-- context: gateway-operations.md
```

### Hook Event Map

| Event            | Hooks (priority)                                                             |
|------------------|------------------------------------------------------------------------------|
| `tool:pre`       | hooks-tool-policy (5)                                                        |
| `tool:post`      | hooks-memory-boundaries (90), hooks-memory-capture (100), hooks-memory-temporal (110), hooks-telemetry (100) |
| `prompt:submit`  | hooks-memory-inject (50)                                                     |
| `prompt:complete` | hooks-telemetry (100)                                                       |
| `session:start`  | hooks-telemetry (100)                                                        |
| `session:end`    | hooks-memory-consolidation (200), hooks-memory-compression (300), hooks-telemetry (100) |
| `provider:*`     | hooks-telemetry (100)                                                        |

### Capability Registry

| Capability              | Registered By                | Consumers                         |
|-------------------------|------------------------------|-----------------------------------|
| `memory.store`          | tool-memory-store            | capture, temporal, inject         |
| `memory.memorability`   | hooks-memory-memorability    | capture                           |
| `memory.boundaries`     | hooks-memory-boundaries      | temporal, inject                  |
| `memory.temporal`       | hooks-memory-temporal        | inject                            |
| `memory.consolidation`  | hooks-memory-consolidation   | (standalone — session:end)        |
| `memory.compression`    | hooks-memory-compression     | (standalone — session:end)        |
| `secrets.manage`        | tool-secrets-manager         | tool-policy (automation lockout)  |
| `sandbox.execute`       | tool-sandbox                 | tool-policy (sandbox rewrite)     |
| `telemetry.collect`     | hooks-telemetry              | (standalone — all events)         |
| `gateway.route`         | gateway-daemon               | scheduler, agents                 |

### Memory Pipeline Flow

```
  Agent Activity
       |
       v
  +----------+   score    +--------------+
  | Capture  |----------->| Memorability |---> score < 0.30? -> discard
  +----+-----+            +--------------+
       |                        |
       | score >= 0.30          |
       v                        v
  +----------+            +--------------+
  |  Store   |<-----------| Boundaries   | (records context shifts)
  +----+-----+            +--------------+
       |
       v
  +----------+
  | Temporal | (assigns to immediate/task/session/project scale)
  +----+-----+
       |
       | --- session continues ---
       |
       v (session:end)
  +---------------+    +--------------+
  | Consolidation |--->| Compression  |
  | (pri 200)     |    | (pri 300)    |
  | boost/decay   |    | cluster/merge|
  +---------------+    +--------------+
       |
       | --- next session ---
       |
       v (prompt:submit)
  +----------+
  | Injection| -> <memory-context> block in prompt
  | (pri 50) |    (governed, sensitivity-gated, 2000 token budget)
  +----------+
```

### Heartbeat Engine

The heartbeat is a **direct programmatic session** — not a recipe, not a hook.
This follows Amplifier's "mechanism not policy" principle: the kernel provides
session mechanisms, the gateway daemon decides when to invoke them.

```
CronScheduler (when)  →  HeartbeatEngine (what)  →  PreparedBundle (how)
     ↓                         ↓                          ↓
"0 * * * *"           build_prompt(agent_id)      create_session()
fires every hour      from context/ files         → session.execute(prompt)
                                                  → memory hooks fire
                                                  → route response to channels
```

Two session creation paths in the gateway:
- **Reactive**: SessionRouter.get_or_create(sender) — for user messages
- **Proactive**: HeartbeatEngine.run_heartbeat(agent_id) — for scheduled check-ins

Both produce identical Amplifier sessions. All hooks fire. All tools available.

## Configuration

### Behavior-Level Configuration

Each behavior accepts a `config` block that is passed to its modules:

```yaml
# Example: security-policy behavior
modules:
  - type: hook
    name: hooks-tool-policy
    config:
      default_action: continue
      careful_mode:
        enabled: false
      command_allowlist:
        - git
        - npm
        - pytest
```

### pyproject.toml

Project-level defaults can be set in `pyproject.toml`:

```toml
[tool.letsgo]
base_dir = "~/.letsgo"

[tool.letsgo.memory]
max_memories = 1000
memorability_threshold = 0.30
token_budget = 2000

[tool.letsgo.secrets]
handle_ttl = 300

[tool.letsgo.sandbox]
memory_limit = "512m"
cpu_limit = 1.0
timeout = 120

[tool.letsgo.telemetry]
enabled = true
log_path = "~/.letsgo/logs/telemetry.jsonl"
```

### Environment Variables

| Variable                | Description                              | Default           |
|-------------------------|------------------------------------------|--------------------|
| `LETSGO_HOME`          | Base directory for all LetsGo data       | `~/.letsgo`        |
| `LETSGO_CAREFUL_MODE`  | Enable careful mode globally             | `false`            |
| `LETSGO_SANDBOX_MODE`  | Sandbox enforcement level                | `off`              |
| `LETSGO_MEMORY_DB`     | Path to memory SQLite database           | `{base}/memory.db` |
| `LETSGO_TELEMETRY`     | Enable/disable telemetry                 | `true`             |

## Development

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=term-missing

# Run specific module tests
pytest tests/test_tool_policy.py
pytest tests/test_memory_store.py
pytest tests/test_secrets_manager.py
```

### Code Quality

```bash
# Lint and format
ruff check .
ruff format .

# Type checking
pyright
```

### Test File Locations

```
tests/
  test_tool_policy.py          # Tool policy risk classification and gating
  test_secrets_manager.py      # Secret encryption, handles, TTL
  test_sandbox.py              # Sandbox execution and resource limits
  test_telemetry.py            # Telemetry event collection and metrics
  test_memory_store.py         # Memory CRUD, search, facts
  test_memory_memorability.py  # Memorability scoring
  test_memory_boundaries.py    # Event segmentation
  test_memory_capture.py       # Auto-capture and classification
  test_memory_temporal.py      # Temporal scaffolding
  test_memory_consolidation.py # Consolidation boost/decay
  test_memory_compression.py   # Cluster-and-merge
  test_memory_inject.py        # Prompt-time injection
  test_gateway.py              # Gateway routing and channels
```

## License

MIT
