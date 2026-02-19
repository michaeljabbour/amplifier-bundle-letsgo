# LetsGo

> Security, memory, secrets, sandbox, observability, gateway, and multi-agent capabilities for Amplifier.

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
  - bundle: letsgo:behaviors/memory-store
  - bundle: letsgo:behaviors/memory-capture
  - bundle: letsgo:behaviors/secrets
```

## Capabilities

LetsGo provides seven capability areas, each composed from thin behaviors and modules:

- **Security & Tool Policy** — 4-tier risk classification, command/path allowlists, careful mode, automation mode
- **Encrypted Secrets** — Fernet-encrypted credential storage with handle-based access and 5-minute TTL
- **Sandboxed Execution** — Docker-first isolated command execution with resource limits
- **Observability & Telemetry** — 7-event session telemetry with tool metrics, token tracking, JSONL logs
- **Memory System** — 8-module bio-inspired pipeline: encoding, consolidation, compression, retrieval
- **Gateway** — Multi-channel messaging (Discord, Telegram, Slack, Webhook) with file exchange, sender pairing, and CLI
- **Heartbeat** — Proactive scheduled agent sessions via CronScheduler and HeartbeatEngine

## Memory System (Neuroscience-Inspired)

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

### Tool Operations

| Operation | Purpose |
|-----------|---------|
| `store_memory` | Persist with title, category, importance, sensitivity, tags, concepts, file links, TTL |
| `search_memories` | Full-text scored search (BM25 + recency + importance + trust weighting) |
| `list_memories` | Browse metadata with content previews |
| `get_memory` | Retrieve by ID (increments access count — feeds consolidation) |
| `update_memory` | Refine content, metadata, or tags in place |
| `delete_memory` | Remove (logged in append-only journal) |
| `search_by_file` | Find memories linked to a file path |
| `search_by_concept` | Find by knowledge category (how-it-works, gotcha, pattern, etc.) |
| `get_timeline` | Chronological view, filterable by type/project/session |
| `store_fact` / `query_facts` | Structured subject/predicate/object triples |
| `purge_expired` | Remove memories past their TTL |
| `summarize_old` | Condense old memories by category |

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
  |  Store   |<-----------| Boundaries   | (records context shifts as facts)
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

See [docs/MEMORY_GUIDE.md](docs/MEMORY_GUIDE.md) for the complete reference.

## Security & Tool Policy

The `hooks-tool-policy` module intercepts every tool call at `tool:pre` priority 5, enforcing a 4-tier risk classification system.

- **4-tier risk classification**: blocked, high, medium, low, plus unclassified fallback
- **Command allowlist**: Prefix matching with word boundaries for bash commands
- **Path allowlist**: Prefix matching with path-traversal protection for filesystem writes
- **Careful mode**: Approval gates for high-risk tools with configurable timeout (default 30s)
- **Automation mode**: Restrictive policy for unattended runs — blocks secrets, denies high-risk and unclassified tools
- **Sandbox rewrite**: Optional auto-routing of bash calls through the sandbox
- **JSONL audit trail**: Full audit log at `~/.letsgo/logs/tool-policy-audit.jsonl`

See [docs/TOOL_POLICY_GUIDE.md](docs/TOOL_POLICY_GUIDE.md) for the complete reference.

## Encrypted Secrets

The `tool-secrets` module provides encrypted credential storage with handle-based access.

- **Fernet encryption**: AES-128-CBC + HMAC-SHA256 for data at rest
- **Handle-based access**: `get_secret` returns an opaque handle, never plaintext — handles are passed to sandbox execution where they are resolved
- **5-minute handle TTL**: Handles expire automatically to limit exposure window
- **Operations**: get, set, list, delete, rotate
- **Archive on rotate**: Previous values are archived with timestamps for audit
- **Audit trail**: Every access (get, set, rotate, delete) is logged with timestamps and session context
- **Automation lockout**: Secrets tool is entirely blocked in automation mode

## Sandboxed Execution

The `tool-sandbox` module provides isolated command execution with resource limits.

- **Docker-first**: Uses Docker containers when available for full isolation
- **Native fallback**: Falls back to restricted subprocess with resource limits when Docker is unavailable
- **Resource limits**: 512MB memory, 1.0 CPU, 120-second timeout (all configurable)
- **Network isolation**: Only `none` network mode is permitted — no outbound connections
- **Read-only mount**: Project directory mounted read-only by default
- **Sandbox rewrite integration**: When `sandbox_mode=enforce` in tool policy, bash calls are automatically routed through the sandbox

## Observability & Telemetry

The `hooks-telemetry` module provides comprehensive session observability.

- **7-event subscription**: Covers session (start/end), prompt (submit/complete), tool (pre/post), and provider events
- **Tool metrics**: Call counts, durations (min/max/mean/p95), error counts per tool
- **Token tracking**: Input tokens, output tokens, cumulative totals per provider call
- **Session summary**: Generated at session end with aggregate statistics
- **JSONL telemetry log**: Structured event log at `~/.letsgo/logs/telemetry.jsonl`

## Gateway

The gateway provides multi-channel messaging, file exchange, and scheduled automation across 16 Python source files.

### Channel Adapters

All channel adapters are full production implementations with unified message routing, sender pairing, and file exchange.

| Channel | Library | Key Features |
|---------|---------|-------------|
| **Discord** | discord.py | DM-only messaging, attachment download, message splitting (2000 chars), typing indicators, proactive DM delivery, channel commands (`/agent`, `/reset`) |
| **Telegram** | python-telegram-bot v20+ | All 8 media types (photo, document, audio, voice, video, video_note, sticker, animation), MIME-based extension detection, message splitting (4096 chars), typing indicators, bot command registration, chat allowlist |
| **Slack** | slack-sdk | Socket Mode (preferred) + HTTP Events API fallback, HMAC-SHA256 signature verification, file download via authenticated API, message splitting (4000 chars), `files_upload_v2` for attachments |
| **Webhook** | aiohttp | HTTP server, HMAC signature validation, JSON request/response |
| **WhatsApp** | — | Stub (future) |

### File Exchange

The gateway implements a unified file exchange protocol across all channels:

- **Inbound** — `[file: /path/to/downloaded]` tags: channel adapters download media attachments to a temp directory and append file reference tags to the message text
- **Outbound** — `[send_file: /path/to/file]` tags: agents include these tags in responses; the gateway strips the tags and attaches the referenced files natively per channel
- **Long responses** — messages exceeding 4000 characters are saved as `.md` files with a truncated preview sent inline plus the full file attached

### Core Infrastructure

- **Sender pairing**: 6-character authentication codes for sender identity verification
- **Session routing**: Per-sender Amplifier sessions created via the `amplifier` CLI bridge (SessionRouter), with fallback to echo mode
- **Cron scheduler**: Cron expressions for timed automation — executes recipes via the `amplifier tool invoke recipes` CLI bridge; schedules persist across restarts
- **Rate limiting**: 10 requests per minute sliding window per sender
- **Message queue**: SQLite-backed durable queue with retry logic

### CLI

```
letsgo-gateway start                                              # Start the daemon
letsgo-gateway send --channel CH --sender-id ID --message TEXT    # Proactive send
letsgo-gateway pairing list [--approved|--pending]                # List senders
letsgo-gateway pairing approve CODE                               # Approve pairing
letsgo-gateway cron list                                          # List jobs
letsgo-gateway cron create --name N --cron EXPR --recipe PATH     # Create job
letsgo-gateway cron delete --name N                               # Delete job
```

### Installation

```bash
pip install letsgo-gateway                    # Core (webhook only)
pip install letsgo-gateway[discord]           # + Discord
pip install letsgo-gateway[telegram]          # + Telegram
pip install letsgo-gateway[slack]             # + Slack
pip install letsgo-gateway[all-channels]      # All channels
```

## Heartbeat

The heartbeat is a **direct programmatic session** — not a recipe, not a hook. This follows Amplifier's "mechanism not policy" principle: the kernel provides session mechanisms, the gateway daemon decides when to invoke them.

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

## Artifact Inventory

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
| `tool-sandbox`               | tool | Isolated command execution with resource limits|
| `tool-secrets`               | tool | Encrypted secret storage with handle access    |

### Behaviors (15)

| Behavior                | Description                                          |
|-------------------------|------------------------------------------------------|
| `letsgo-capabilities`   | Full capability set — includes all other behaviors   |
| `security-policy`       | Tool policy, risk classification, allowlists         |
| `secrets`               | Encrypted secrets with handle-based access           |
| `sandbox`               | Docker-first sandboxed command execution             |
| `observability`         | Session observability and metrics collection         |
| `gateway`               | Multi-channel messaging daemon                       |
| `heartbeat`             | Proactive agent check-ins via HeartbeatEngine        |
| `memory-store`          | Memory data layer (SQLite + FTS5)                    |
| `memory-memorability`   | Selective encoding with memorability scoring         |
| `memory-boundaries`     | Event segmentation and context shift detection       |
| `memory-capture`        | Auto-capture and classification from tool outputs    |
| `memory-temporal`       | Multi-scale temporal scaffolding                     |
| `memory-consolidation`  | Session-end boost/decay consolidation                |
| `memory-compression`    | Session-end cluster-and-merge compaction             |
| `memory-inject`         | Prompt-time memory retrieval and injection           |

### Context Files (12)

| Context File                    | Purpose                                           |
|---------------------------------|---------------------------------------------------|
| `letsgo-instructions.md`       | Core bundle instructions                          |
| `tool-policy-awareness.md`     | Tool policy awareness for agent sessions          |
| `secrets-awareness.md`         | Secrets tool awareness for agent sessions         |
| `sandbox-awareness.md`         | Sandbox tool awareness for agent sessions         |
| `observability-awareness.md`   | Telemetry and observability awareness             |
| `gateway-awareness.md`         | Gateway configuration and operations awareness    |
| `heartbeat/`                   | Heartbeat system context (directory)              |
| `memory-awareness.md`          | Memory injection awareness for agent sessions     |
| `memory-store-awareness.md`    | Memory store operations awareness                 |
| `memory-system-awareness.md`   | Memory system overview and lifecycle              |
| `soul-framework-awareness.md`  | Soul framework awareness                          |
| `team-collaboration-awareness.md` | Team collaboration awareness                   |

### Agents (3)

| Agent                | Purpose                                                         |
|----------------------|-----------------------------------------------------------------|
| `gateway-operator`   | Gateway management — channel configuration, sender pairing, schedule management |
| `memory-curator`     | Memory system management — maintenance, search, analysis, and health monitoring |
| `security-reviewer`  | Security posture review — policy audit, allowlist verification, log analysis |

### Recipes (4)

| Recipe                | Purpose                                           |
|-----------------------|---------------------------------------------------|
| `channel-onboard`     | Channel setup and sender pairing workflow         |
| `daily-digest`        | Daily summary generation and distribution         |
| `memory-maintenance`  | Scheduled memory consolidation and compression    |
| `setup-wizard`        | First-run project setup with memory, secrets, and policy |

### Skills (5)

| Skill                  | Description                                      |
|------------------------|--------------------------------------------------|
| `agent-browser`        | Browser automation for agent tasks               |
| `imagegen`             | Image generation capability                      |
| `schedule`             | Scheduling and cron expression patterns           |
| `send-user-message`    | User message delivery capability                 |
| `skill-creator`        | Skill authoring and creation tooling             |

### Docs (2)

| Document               | Purpose                                          |
|------------------------|--------------------------------------------------|
| `MEMORY_GUIDE.md`      | Comprehensive memory system reference            |
| `TOOL_POLICY_GUIDE.md` | Tool policy and risk classification reference    |

## Hook Event Map

| Event            | Hooks (priority order)                                                        |
|------------------|-------------------------------------------------------------------------------|
| `tool:pre`       | hooks-telemetry (1), hooks-tool-policy (5)                                    |
| `tool:post`      | hooks-telemetry (90), hooks-memory-boundaries (100), hooks-memory-capture (150) |
| `prompt:submit`  | hooks-memory-inject (50)                                                      |
| `session:start`  | hooks-memory-capture (50)                                                     |
| `session:end`    | hooks-memory-capture (100), hooks-memory-consolidation (200), hooks-memory-compression (300) |

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

## Architecture

### Bundle Composition

```
bundle.md
  +-- includes: letsgo:behaviors/letsgo-capabilities
        |
        +-- behaviors/security-policy.yaml
        |     +-- modules: hooks-tool-policy
        |     +-- context: tool-policy-awareness.md
        |
        +-- behaviors/secrets.yaml
        |     +-- modules: tool-secrets
        |     +-- context: secrets-awareness.md
        |
        +-- behaviors/sandbox.yaml
        |     +-- modules: tool-sandbox
        |     +-- context: sandbox-awareness.md
        |
        +-- behaviors/observability.yaml
        |     +-- modules: hooks-telemetry
        |     +-- context: observability-awareness.md
        |
        +-- behaviors/memory-store.yaml
        |     +-- modules: tool-memory-store
        |     +-- context: memory-store-awareness.md
        |
        +-- behaviors/memory-memorability.yaml
        |     +-- modules: hooks-memory-memorability
        |
        +-- behaviors/memory-boundaries.yaml
        |     +-- modules: hooks-memory-boundaries
        |
        +-- behaviors/memory-capture.yaml
        |     +-- modules: hooks-memory-capture
        |     +-- context: memory-awareness.md, memory-system-awareness.md
        |
        +-- behaviors/memory-temporal.yaml
        |     +-- modules: hooks-memory-temporal
        |
        +-- behaviors/memory-consolidation.yaml
        |     +-- modules: hooks-memory-consolidation
        |
        +-- behaviors/memory-compression.yaml
        |     +-- modules: hooks-memory-compression
        |
        +-- behaviors/memory-inject.yaml
        |     +-- modules: hooks-memory-inject
        |
        +-- behaviors/gateway.yaml
        |     +-- context: gateway-awareness.md
        |
        +-- behaviors/heartbeat.yaml
              +-- context: heartbeat/
```

## Research Foundation

The memory system is grounded in neuroscience research documented in the [amplifier-memory-research](https://github.com/microsoft/amplifier-memory-research) repository.

Key findings:
- **CONCEPT_MAP** — maps 64 biological memory concepts to Amplifier implementation primitives via IDD decomposition
- **IMPLEMENTABILITY** — assesses each concept's feasibility, categorizing them as directly implementable, partially implementable, or requiring novel approaches

The bio-inspired pipeline (memorability scoring, boundary detection, temporal scaffolding, consolidation, compression) draws directly from these research findings.

## License

MIT
