# Memory System Guide

## Overview

The LetsGo memory system is a neuroscience-inspired pipeline of 8 modules working together to give AI agents durable, intelligent memory across sessions. Rather than treating memory as a simple key-value store, the system models the stages of human memory formation: encoding, consolidation, compression, and retrieval — each handled by a dedicated module with its own event subscriptions and configuration.

Memories flow through the pipeline automatically. Tool outputs are captured and scored for memorability. Context shifts are detected and recorded. Temporal scaffolding organizes memories across multiple time scales. During idle periods, consolidation strengthens important memories while compression merges redundant ones. At prompt time, the most relevant memories are injected into context — governed, sensitivity-gated, and budget-constrained.

## Architecture

```
  Tool Output / Agent Activity
           |
           v
  +---------------------------+
  |  hooks-memory-capture     |  <-- Classifies observations, auto-generates metadata
  |  (tool:post)              |
  +------------+--------------+
               |
               v
  +---------------------------+
  | hooks-memory-memorability |  <-- Scores content (0.0-1.0), gate threshold 0.30
  |  (consulted by capture)   |
  +------------+--------------+
               |
               v
  +---------------------------+
  | hooks-memory-boundaries   |  <-- Detects context shifts via Jaccard similarity
  |  (tool:post)              |
  +------------+--------------+
               |
               v
  +---------------------------+
  |  hooks-memory-temporal    |  <-- Multi-scale scaffolding (immediate/task/session/project)
  |  (tool:post)              |
  +------------+--------------+
               |
               v
  +---------------------------+
  |   tool-memory-store       |  <-- SQLite + FTS5 data layer, scored search, dedup, facts
  |   (tool implementation)   |
  +------------+--------------+
               |
       +-------+--------+
       v                v
  +--------------+  +----------------+
  | consolidation|  |  compression   |  <-- Session-end maintenance
  | (session:end |  | (session:end   |
  |  pri 200)    |  |  pri 300)      |
  +--------------+  +----------------+
               |
               v
  +---------------------------+
  |  hooks-memory-inject      |  <-- Prompt-time retrieval and injection
  |  (prompt:submit pri 50)   |
  +---------------------------+
```

## Module Details

### 1. tool-memory-store — Data Layer

The foundation of the memory system. Provides the `memory` tool with all CRUD operations.

**Storage engine:** SQLite with FTS5 full-text search extension.

**Metadata model:**
- **Observation type**: bugfix, feature, refactor, change, discovery, decision
- **Concepts**: how-it-works, why-it-exists, what-changed, problem-solution, gotcha, pattern, trade-off
- **File tracking**: files_read, files_modified arrays for file-based retrieval
- **Session/project linking**: session_id, project identifier
- **Sensitivity**: public, private, secret, unknown
- **Importance**: 0.0-1.0 float
- **TTL**: Optional time-to-live in days

**Scored search** uses weighted factors:

| Factor        | Weight | Description                              |
|---------------|--------|------------------------------------------|
| Match quality | 0.55   | FTS5 rank + title/content matching       |
| Recency       | 0.20   | Exponential decay from creation time     |
| Importance    | 0.15   | Author-assigned or auto-generated score  |
| Trust         | 0.10   | Derived from access count and age        |

**Deduplication:** SHA-256 hash of content. Duplicate stores update metadata rather than creating new entries.

**TTL/Expiry:** Memories with `ttl_days` set are excluded from search after expiration. `purge_expired` permanently removes them.

**Access counting:** Every search hit or direct get increments `access_count`, feeding into consolidation scoring.

**Max-memories cap:** Configurable upper bound. When exceeded, lowest-scored memories are pruned.

**Fact store:** Subject/predicate/object triples with confidence scores (0.0-1.0). Linked to source memories. Queryable by any component.

**Mutation journal:** All writes (create, update, delete) are journaled for auditability.

### 2. hooks-memory-memorability — Selective Encoding

Not everything deserves to be remembered. This module scores content memorability on a 0.0-1.0 scale.

**Scoring dimensions:**
- **Substance** — Does the content contain actionable information, decisions, or discoveries?
- **Salience** — Is it relevant to the current task or project context?
- **Distinctiveness** — Is it novel compared to existing memories?
- **Type weight** — Some observation types (decisions, discoveries) have inherent higher weight

**Gate threshold:** 0.30. Content scoring below this is not stored. This prevents noise accumulation from routine tool outputs like directory listings or simple grep results.

**Hook:** Consulted by `hooks-memory-capture` before storing. Not a direct event subscriber — it is a scoring service.

### 3. hooks-memory-boundaries — Event Segmentation

Inspired by Event Segmentation Theory — humans chunk continuous experience into discrete events at contextual boundaries.

**Detection method:** Keyword Jaccard similarity in a sliding window over recent tool interactions. When the similarity between adjacent windows drops below a threshold, a boundary is detected.

**Boundary recording:** Detected boundaries are stored as facts in the fact store:
- Subject: `session:{session_id}`
- Predicate: `boundary_at`
- Object: timestamp and context summary

**Purpose:** Boundaries inform temporal scaffolding and help the injection module select memories from the right "episode" of work.

### 4. hooks-memory-capture — Auto-Capture

The primary ingestion module. Subscribes to `tool:post` events and processes tool outputs for memory storage.

**Classification:** Automatically classifies observations into types:
- `bugfix` — Error resolution, fix application
- `feature` — New functionality, capability addition
- `refactor` — Code restructuring, cleanup
- `change` — Configuration, dependency, or environment changes
- `discovery` — New understanding, pattern recognition
- `decision` — Architectural or design decisions

**Auto-generation:**
- **Titles**: Concise summary of the observation
- **Subtitles**: Supporting detail or context
- **Importance**: 0.0-1.0 based on observation type and content analysis
- **Concept tags**: Automatically assigned from the concept taxonomy

**Memorability consultation:** Before storing, consults the memorability scorer. Content below the 0.30 threshold is discarded.

**Session summaries:** Periodically generates session-level summaries that capture the arc of work.

**Checkpoints:** Creates checkpoint memories at significant milestones (task completion, file saves, test passes).

### 5. hooks-memory-temporal — Multi-Scale Temporal Scaffolding

Organizes memories across 4 time scales, inspired by how human memory operates at different temporal granularities.

| Scale     | Window    | Purpose                                     |
|-----------|-----------|---------------------------------------------|
| Immediate | 5 min     | What just happened — working memory analog   |
| Task      | 30 min    | Current task context                         |
| Session   | 2 hr      | Session-level narrative                      |
| Project   | unbounded | Long-term project knowledge                  |

**Default allocation:** 1 + 2 + 1 + 1 = 5 memories across scales. This budget is used by the injection module to select memories from each temporal level.

**Scale management:** Each scale maintains its own retrieval index. Memories are tagged with their temporal scale on creation and can be promoted (immediate -> task -> session -> project) as they prove durable.

### 6. hooks-memory-consolidation — Self-Amplifying Replay

Runs at `session:end` with priority 200 (before compression). Inspired by memory consolidation during sleep.

**Access-based boost:** Memories that were accessed during the session get a score boost. The boost follows a logarithmic curve based on access count — diminishing returns prevent runaway amplification.

**Age-based decay:** Unaccessed memories decay linearly with age. This natural forgetting curve ensures the memory store stays relevant.

**Protected types:** Decisions and discoveries decay at half rate. These observation types represent durable knowledge that should persist longer than routine observations.

**Effect:** Over multiple sessions, frequently-accessed memories strengthen while unused ones fade — a form of spaced repetition that emerges naturally from usage patterns.

### 7. hooks-memory-compression — Cluster-and-Merge

Runs at `session:end` with priority 300 (after consolidation). Reduces memory count while preserving knowledge.

**Algorithm:** Greedy single-linkage clustering using Jaccard similarity on memory content tokens.

**Merge threshold:** Clusters of 3 or more similar memories are merged into a single summary memory that preserves the essential information from all members.

**Age gate:** Only processes memories older than 7 days. Recent memories are left intact to preserve detail that may still be needed.

**Result:** The memory store naturally compacts over time. Five related bug-fix memories from two weeks ago become one concise summary, while yesterday's detailed debugging session stays intact.

### 8. hooks-memory-inject — Prompt-Time Injection

Subscribes to `prompt:submit` at priority 50. Retrieves and injects relevant memories into the prompt context.

**Retrieval:** Queries both the memory store (scored search) and temporal scaffolding for memories relevant to the current prompt.

**Formatting:** Injects memories as a `<memory-context>` block in the system prompt area:

```xml
<memory-context>
  <memory type="discovery" importance="0.8" age="2d">
    Title: SQLite FTS5 requires explicit rebuild after schema changes
    Content: When adding new columns to FTS5 virtual tables...
  </memory>
  ...
</memory-context>
```

**Memory governor:** Security layer that:
- Blocks instruction-like content (prompt injection defense)
- Strips role prefixes ("As an AI...", "You are...", etc.)
- Validates sensitivity levels before injection

**Budget constraints:**
- **Token budget**: 2000 tokens maximum for the memory-context block
- **Memory count**: 5 memories maximum per injection

## Memory Operations

### Core CRUD

| Operation         | Description                                          |
|-------------------|------------------------------------------------------|
| `store_memory`    | Create a new memory with full metadata               |
| `search_memories` | Scored search across all memories                    |
| `list_memories`   | Paginated listing with optional filters              |
| `get_memory`      | Retrieve a single memory by ID (increments access)   |
| `update_memory`   | Modify memory content or metadata                    |
| `delete_memory`   | Permanently remove a memory                          |

### Specialized Retrieval

| Operation           | Description                                        |
|---------------------|----------------------------------------------------|
| `search_by_file`    | Find memories related to a specific file path      |
| `search_by_concept` | Find memories tagged with a specific concept       |
| `get_timeline`      | Chronological view of memories for a session/project|

### Knowledge Graph

| Operation      | Description                                           |
|----------------|-------------------------------------------------------|
| `store_fact`   | Store a subject/predicate/object triple               |
| `query_facts`  | Query facts by subject, predicate, and/or object      |

### Maintenance

| Operation        | Description                                          |
|------------------|------------------------------------------------------|
| `purge_expired`  | Remove memories past their TTL                       |
| `summarize_old`  | Compress old memories into summaries (default 30 days)|

## Sensitivity Levels

| Level     | Behavior                                                        |
|-----------|-----------------------------------------------------------------|
| `public`  | Always returned in search results and injection                 |
| `private` | Gated — only returned when explicitly requested                 |
| `secret`  | Gated — only returned when explicitly requested                 |
| `unknown` | Denied — fail-closed. Memories with unknown sensitivity are never returned |

The fail-closed default for `unknown` ensures that memories created without explicit sensitivity classification are not accidentally exposed.

## Capability Registry

Modules register capabilities that other modules can check for:

| Capability              | Registered By                | Consumers                     |
|-------------------------|------------------------------|-------------------------------|
| `memory.store`          | tool-memory-store            | capture, temporal, inject     |
| `memory.memorability`   | hooks-memory-memorability    | capture                       |
| `memory.boundaries`     | hooks-memory-boundaries      | temporal, inject              |
| `memory.temporal`       | hooks-memory-temporal        | inject                        |
| `memory.consolidation`  | hooks-memory-consolidation   | (standalone)                  |
| `memory.compression`    | hooks-memory-compression     | (standalone)                  |

## Event Subscription Map

| Module                      | Event          | Priority | Purpose                        |
|-----------------------------|----------------|----------|--------------------------------|
| hooks-memory-capture        | tool:post      | 100      | Auto-capture tool outputs      |
| hooks-memory-boundaries     | tool:post      | 90       | Detect context shifts          |
| hooks-memory-temporal       | tool:post      | 110      | Update temporal scaffolding    |
| hooks-memory-consolidation  | session:end    | 200      | Boost/decay memory scores      |
| hooks-memory-compression    | session:end    | 300      | Cluster and merge old memories |
| hooks-memory-inject         | prompt:submit  | 50       | Inject relevant memories       |

**Priority ordering matters:**
- At `tool:post`: boundaries (90) -> capture (100) -> temporal (110). Boundaries are detected before capture decides what to store, and temporal scaffolding updates after storage.
- At `session:end`: consolidation (200) -> compression (300). Scores are updated before clustering decisions are made.
- At `prompt:submit`: injection (50) runs early to ensure memories are available in the prompt.

## Configuration

### pyproject.toml

```toml
[tool.letsgo.memory]
max_memories = 1000          # Upper bound on stored memories
default_ttl_days = 90        # Default TTL when not specified
memorability_threshold = 0.30 # Gate threshold for memorability
compression_min_age_days = 7  # Minimum age for compression eligibility
consolidation_decay_rate = 0.05  # Linear decay rate per day
token_budget = 2000          # Max tokens for memory injection
max_inject_count = 5         # Max memories per injection
```

### Module-Level Configuration

Each module accepts configuration through its behavior definition:

```yaml
# Example: hooks-memory-memorability behavior
modules:
  - type: hook
    name: hooks-memory-memorability
    config:
      threshold: 0.30
      type_weights:
        decision: 0.8
        discovery: 0.7
        bugfix: 0.5
        feature: 0.5
        refactor: 0.3
        change: 0.3
```

### Environment Variables

| Variable                    | Description                          | Default             |
|-----------------------------|--------------------------------------|---------------------|
| `LETSGO_HOME`              | Base directory for LetsGo data       | `~/.letsgo`         |
| `LETSGO_MEMORY_DB`         | Path to SQLite database              | `{base}/memory.db`  |
| `LETSGO_MEMORY_LOG`        | Path to mutation journal             | `{base}/logs/memory-journal.jsonl` |

## Best Practices

1. **Store with rich metadata for better retrieval.** Always include observation type, concepts, and file paths when storing memories. The scored search heavily rewards metadata completeness.

2. **Use concepts for knowledge categorization.** The seven concept types (how-it-works, why-it-exists, what-changed, problem-solution, gotcha, pattern, trade-off) create a navigable knowledge taxonomy.

3. **Let consolidation and compression run naturally.** Do not manually delete old memories — the consolidation/compression pipeline handles this. Memories that stay relevant will be preserved; redundant ones will be merged.

4. **Use `search_by_file` when investigating file-related memories.** This is more targeted than general search and leverages the file tracking metadata.

5. **Monitor `access_count` for memory value signals.** High access counts indicate memories that are genuinely useful. Low counts on old memories suggest they can be safely pruned.

6. **Prefer `store_fact` for structured knowledge.** When you learn a clear relationship (X uses Y, A depends on B), store it as a fact triple rather than a narrative memory. Facts are more precisely queryable.

7. **Set appropriate sensitivity levels.** Memories containing credentials, internal URLs, or personal information should be marked `private` or `secret`. The fail-closed default on `unknown` protects against accidental exposure.

8. **Use `summarize_old` proactively in long-running projects.** While compression runs automatically at session end, manual summarization can help manage memory growth in projects with heavy activity.
