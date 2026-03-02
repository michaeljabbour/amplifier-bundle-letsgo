---
name: memory-guide
version: 1.0.0
description: Complete reference for LetsGo's bio-inspired memory system — storage, retrieval, lifecycle hooks, and configuration
---

# Memory System Guide

LetsGo's memory system is a bio-inspired pipeline of 8 modules that gives AI agents
durable, intelligent memory across sessions. Rather than a simple key-value store,
it models the stages of human memory formation: encoding, consolidation, compression,
and retrieval — each handled by a dedicated module coordinated through the capability
registry.

## Architecture

### Module Inventory

| # | Module | Type | Hook Events | Priority | Capability |
|---|--------|------|-------------|----------|------------|
| 1 | tool-memory-store | Tool | — | — | `memory.store` |
| 2 | hooks-memory-memorability | Hook (cap only) | — | — | `memory.memorability` |
| 3 | hooks-memory-boundaries | Hook | tool:post | 100 | `memory.boundaries` |
| 4 | hooks-memory-capture | Hook | tool:post, session:start, session:end | 150, 50, 100 | — |
| 5 | hooks-memory-temporal | Hook (cap only) | — | — | `memory.temporal` |
| 6 | hooks-memory-consolidation | Hook | session:end | 200 | `memory.consolidation` |
| 7 | hooks-memory-compression | Hook | session:end | 300 | `memory.compression` |
| 8 | hooks-memory-inject | Hook | prompt:submit | 50 | — |

### Capability Dependency Graph

```
memory.store ← ALL modules (required foundation)
memory.memorability ← capture (optional gate — skips if absent)
memory.boundaries ← capture (optional annotation — skips if absent)
memory.temporal ← inject (optional balanced retrieval — falls back to store-only)
memory.consolidation ← manual trigger only (session:end hook)
memory.compression ← manual trigger only (session:end hook)
```

Every dependency is optional — modules degrade gracefully if a capability is absent.

### Hook Execution Chain

```
prompt:submit
  └── @50  inject → retrieves + injects memories into prompt

tool:post
  ├── @100 boundaries → detects context shifts via keyword Jaccard
  └── @150 capture → extracts + stores observations from tool output

session:start
  └── @50  capture → initializes SessionContext

session:end
  ├── @100 capture → creates session summary memory
  ├── @200 consolidation → boost accessed / decay unaccessed / remove stale
  └── @300 compression → cluster + merge old memories (7+ days)
```

## Tool Operations

| Operation | Description |
|-----------|-------------|
| `store_memory` | Store content with category, importance, sensitivity, tags, optional TTL, plus rich metadata |
| `search_memories` | Full-text search with scored relevance (FTS5 + BM25) across content, title, subtitle |
| `list_memories` | List memory metadata with content previews |
| `get_memory` | Retrieve full memory by ID (increments access count) |
| `update_memory` | Update content, metadata, or tags in place |
| `delete_memory` | Remove a memory (logged in journal) |
| `search_by_file` | Find memories linked to a file path |
| `search_by_concept` | Find by knowledge category |
| `get_timeline` | Chronological view, filterable by type/project/session |
| `store_fact` / `query_facts` | Structured subject/predicate/object triples |
| `purge_expired` | Remove memories past their TTL |
| `summarize_old` | Condense old memories by category |

## Scored Retrieval

Composite score = 0.55 × match (BM25) + 0.20 × recency + 0.15 × importance + 0.10 × trust

| Factor | Weight | Description |
|--------|--------|-------------|
| Match quality | 0.55 | FTS5 BM25 relevance |
| Recency | 0.20 | Exponential decay, 21-day half-life |
| Importance | 0.15 | Author-assigned, boosted by consolidation |
| Trust | 0.10 | Source trustworthiness |

Results below `min_score` (default 0.35) are filtered.

## Rich Metadata

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Short title (auto-generated if omitted) |
| `subtitle` | string | Secondary one-line description |
| `type` | enum | bugfix, feature, refactor, change, discovery, decision |
| `concepts` | array | how-it-works, why-it-exists, what-changed, problem-solution, gotcha, pattern, trade-off |
| `files_read` | array | File paths read |
| `files_modified` | array | File paths modified |
| `session_id` | string | Source session |
| `project` | string | Project identifier |
| `discovery_tokens` | integer | Token cost estimate |
| `accessed_count` | integer | Retrieval count (auto-incremented) |

## FTS5 Full-Text Search

Indexes three columns: `content`, `title`, `subtitle`. Auto-upgrades from older
single-column schemas. Concepts and file paths use dedicated LIKE-based operations.

## Deduplication

SHA-256 content hash. Duplicate stores return existing ID and refresh timestamp.

## Sensitivity Gating

- `public` — always returned
- `private` — only when `allow_private=True`
- `secret` — only when `allow_secret=True`
- Unknown — denied (fail-closed)

## TTL and Expiry

Memories with `ttl_days` are excluded from search after expiration.
`purge_expired` permanently removes them.

## Eviction Priority

When `max_memories` cap is exceeded:
1. Lowest `accessed_count`
2. Oldest `updated_at`
3. Lowest `importance`

## Mutation Journal

All write operations recorded in append-only `memory_journal` table —
audit trail that cannot be modified through the tool interface.

## Temporal Scales

| Scale | Window | Purpose |
|-------|--------|---------|
| Immediate | < 5 min | Working memory — current tool activity |
| Task | 5–30 min | Current task context |
| Session | 30 min – 2 hr | Session-level knowledge |
| Project | > 2 hr | Long-term project wisdom |

Default allocation: 1 + 2 + 1 + 1 = 5 memories across scales.

## Module Details

### hooks-memory-memorability — Selective Encoding

Scores content 0.0–1.0 on four dimensions: substance, salience, distinctiveness,
type weight. Gate threshold: 0.30. Not a direct event subscriber — consulted as
a scoring service by capture.

### hooks-memory-boundaries — Event Segmentation

Detects context shifts via keyword Jaccard similarity in a sliding window.
Boundaries stored as facts: subject=`session:{id}`, predicate=`boundary_at`.

### hooks-memory-capture — Auto-Capture

Classifies observations (bugfix/feature/refactor/change/discovery/decision).
Auto-generates titles, subtitles, importance, concept tags. Consults memorability
scorer before storing. Creates session summaries and checkpoint memories.

### hooks-memory-temporal — Multi-Scale Scaffolding

Manages per-scale retrieval indexes. Memories can be promoted across scales
(immediate → task → session → project) as they prove durable.

### hooks-memory-consolidation — Self-Amplifying Replay

Access-based boost: logarithmic curve (0.03 × ln(1+access_count)).
Age-based decay: 0.02/day linear. Decisions/discoveries decay at half rate.
Eviction at min_importance 0.05 after 90 days unaccessed.

### hooks-memory-compression — Cluster-and-Merge

Greedy single-linkage clustering via Jaccard similarity. Merges clusters of 3+
into summaries. Age gate: only memories older than 7 days.

### hooks-memory-inject — Prompt-Time Injection

Injects top memories as `<memory-context>` block. Token budget: 2000. Count: 5 max.
Memory governor blocks instruction-injection attacks, strips role prefixes,
validates sensitivity.

## Configuration

```toml
[tool.letsgo.memory]
max_memories = 1000
default_ttl_days = 90
memorability_threshold = 0.30
compression_min_age_days = 7
consolidation_decay_rate = 0.05
token_budget = 2000
max_inject_count = 5
```

| Variable | Description | Default |
|----------|-------------|---------|
| `LETSGO_HOME` | Base directory | `~/.letsgo` |
| `LETSGO_MEMORY_DB` | SQLite database path | `{base}/memory.db` |
| `LETSGO_MEMORY_LOG` | Mutation journal path | `{base}/logs/memory-journal.jsonl` |

## Troubleshooting

- **Memories not being captured**: Check memorability threshold (default 0.30).
  Routine tool outputs score below the gate. Lower threshold or verify content
  has substance/salience.
- **Search results seem stale**: Recency factor has 21-day half-life. Old memories
  need high match quality to surface. Run `summarize_old` to consolidate.
- **Duplicate memories**: Dedup uses content hash. Semantically similar but textually
  different content creates separate entries. Run maintenance via memory-curator.
- **Missing file-linked memories**: Ensure `files_read`/`files_modified` metadata
  is populated at store time. `search_by_file` queries these arrays.
