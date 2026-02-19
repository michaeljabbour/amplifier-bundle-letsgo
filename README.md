# LetsGo

**Security, memory, secrets, sandbox, and observability capabilities for Amplifier.**

LetsGo is an Amplifier bundle that provides production-grade infrastructure modules. Its memory system implements a bio-inspired pipeline modeled on neuroscience research into how biological memory works — from selective encoding to self-amplifying consolidation.

## Quick Start

```yaml
# In your bundle.md
includes:
  - bundle: letsgo:behaviors/letsgo-capabilities
```

This composes all LetsGo capabilities into your session. Each capability is independently removable — comment out any behavior you don't need.

## Capabilities

### Memory System (Bio-Inspired Pipeline)

LetsGo's memory system is an 8-module pipeline inspired by neuroscience research on how biological memory works. Each module is independently removable — the system degrades gracefully.

```
tool:post events
  │
  ├── Boundary Detection (@100)     ─── Detects contextual shifts
  │                                      via keyword similarity
  ├── Memorability Scoring          ─── Filters low-value observations
  │   (consulted by capture)             before storage
  └── Auto-Capture (@150)           ─── Extracts and stores observations
                                         from tool executions
prompt:submit
  │
  └── Memory Injection (@50)        ─── Injects relevant memories
      ├── Temporal Scaffolding           (balanced across timescales)
      └── Scored Retrieval               (BM25 + recency + importance)

session:end
  │
  ├── Consolidation (@200)          ─── Boosts accessed memories,
  │                                      decays unused ones
  └── Compression (@300)            ─── Clusters and merges similar
                                         old memories
```

| Module | Type | Biological Inspiration | What It Does |
|--------|------|----------------------|-------------|
| **tool-memory-store** | Tool | — | SQLite + FTS5 storage with scored search, dedup, TTL, fact triples, mutation journal |
| **hooks-memory-memorability** | Capability | Selective encoding (55.7% real-world recall) | Scores content by substance, salience, distinctiveness; gates storage |
| **hooks-memory-boundaries** | Hook | Boundary cells in human MTL | Detects contextual shifts via Jaccard similarity on keyword sliding windows |
| **hooks-memory-capture** | Hook | — | Auto-captures observations from tool results, tracks files, creates session summaries |
| **hooks-memory-temporal** | Capability | Temporally Periodic Cells | Multi-scale retrieval: immediate (5min), task (30min), session (2hr), project (days+) |
| **hooks-memory-consolidation** | Hook | Self-amplifying replay | Boosts importance for accessed memories; decays unused; removes old forgotten memories |
| **hooks-memory-compression** | Hook | CRUMB compositional replay | Clusters similar old memories by keyword overlap, merges into compressed summaries |
| **hooks-memory-inject** | Hook | — | Injects top relevant memories into each prompt as ephemeral context |

#### Capabilities Registered

| Capability | Provider | Consumers |
|-----------|----------|-----------|
| `memory.store` | tool-memory-store | All memory modules |
| `memory.memorability` | hooks-memory-memorability | hooks-memory-capture (optional) |
| `memory.boundaries` | hooks-memory-boundaries | hooks-memory-capture (optional) |
| `memory.temporal` | hooks-memory-temporal | hooks-memory-inject (optional) |
| `memory.consolidation` | hooks-memory-consolidation | Manual trigger |
| `memory.compression` | hooks-memory-compression | Manual trigger |

#### Memory Tool Operations

| Operation | Description |
|-----------|-------------|
| `store_memory` | Store with title, category, importance, sensitivity, TTL, concepts, file links |
| `search_memories` | Full-text scored search (BM25 + recency + importance + trust) |
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

### Security & Tool Policy

Classifies tool calls by risk level and enforces approval gates:

| Risk Level | Tools | Behavior |
|-----------|-------|----------|
| Blocked | Explicitly blocked | Denied outright |
| High | bash, write_file | Auto-allowed; approval-gated when `careful_mode=true` |
| Medium | edit_file, filesystem | Logged with audit trail |
| Low | search, glob, grep | Executes freely |

### Encrypted Secrets

Handle-based secret management with Fernet encryption (AES-128-CBC + HMAC-SHA256):
- `get_secret` returns opaque handles, never plaintext
- Handles expire after 5 minutes
- All access logged to audit trail

### Sandboxed Execution

Docker-based isolated execution for untrusted code:
- 512 MB memory, 1.0 CPU, 120s timeout
- Network disabled by default
- Working directory bind-mounted

### Observability

Session-level telemetry via hooks:
- Tool call counts and duration statistics
- Provider call tracking with token usage
- Prompt hashes (never full content)
- JSONL event log for replay correlation

## Agents

| Agent | Description |
|-------|-------------|
| `letsgo:memory-curator` | Specialist for complex memory operations: multi-criteria retrieval, maintenance, deduplication, health analysis |
| `letsgo:security-reviewer` | Tool execution policy specialist: risk classification, approval gates, capability boundaries |

## Recipes

| Recipe | Description |
|--------|-------------|
| `memory-maintenance` | 4-step pipeline: audit → deduplicate → summarize old → report |
| `daily-digest` | Gather sessions and memories, synthesize daily summary |
| `channel-onboard` | Configure, authenticate, and activate communication channels |

## Configuration

Each behavior accepts configuration via its YAML file. Key tuning parameters:

### Memory Scoring Weights
```yaml
# behaviors/memory-inject.yaml
weights:
  match: 0.55       # FTS5 BM25 relevance
  recency: 0.20     # Exponential decay (21-day half-life)
  importance: 0.15   # Author-assigned weight
  trust: 0.10       # Source trustworthiness
```

### Memorability Threshold
```yaml
# behaviors/memory-memorability.yaml
base_threshold: 0.30    # Below this, observations are NOT stored
```

### Consolidation Rates
```yaml
# behaviors/memory-consolidation.yaml
decay_rate: 0.02                # Importance loss per day (unaccessed)
access_boost_factor: 0.03       # Importance gain per access (logarithmic)
max_unaccessed_age_days: 90     # Remove after this if still unaccessed
protected_types:                # These decay at half rate
  - decision
  - discovery
```

### Temporal Scale Boundaries
```yaml
# behaviors/memory-temporal.yaml
scale_boundaries:
  immediate: 300     # < 5 minutes
  task: 1800         # < 30 minutes
  session: 7200      # < 2 hours
  # project: everything beyond session
allocation:
  immediate: 1       # memories per scale in balanced retrieval
  task: 2
  session: 1
  project: 1
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  bundle.md → letsgo-capabilities.yaml                       │
│    Composes all behaviors in dependency order                │
└───────────────────────────┬─────────────────────────────────┘
                            │
    ┌───────────────────────┼───────────────────────────┐
    │                       │                           │
    ▼                       ▼                           ▼
 MEMORY SYSTEM         SECURITY              INFRASTRUCTURE
 (8 modules)           (1 module)            (3 modules)
                                             
 store ──capability──▶ All hooks             secrets
   │                   boundaries            sandbox
   │                   memorability          observability
   │                   capture
   │                   temporal
   │                   consolidation
   │                   compression
   │                   inject
   │
   └── memory.store capability
       (central data layer)
```

## Research Background

The memory system is grounded in neuroscience research from Gabriel Kreiman's lab at Harvard (9 peer-reviewed papers). Key biological principles translated to AI:

1. **Selective encoding** — Most experience is never stored; memorability scoring filters low-value content
2. **Event segmentation** — Boundary cells detect contextual shifts; boundary detection marks topic changes
3. **Self-amplifying replay** — Retrieved memories strengthen; accessed memories get importance boosts
4. **Multi-scale temporal indexing** — Periodic cells fire at multiple timescales; balanced retrieval across scales
5. **Compositional compression** — Memories stored as compositions of reusable blocks; cluster-and-merge reduces redundancy

See `amplifier-memory-research/ANALYSIS.md` for the full research-to-implementation mapping.

## License

MIT
