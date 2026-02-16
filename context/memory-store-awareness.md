# Memory Store

LetsGo provides durable, searchable memory via `tool-memory-store`.

## Operations

| Operation | Description |
|-----------|-------------|
| `store_memory` | Store content with category, importance, sensitivity, tags, optional TTL, plus rich metadata (title, subtitle, type, concepts, files, session, project) |
| `search_memories` | Full-text search with scored relevance (FTS5 + BM25) across content, title, and subtitle |
| `list_memories` | List memory metadata with content previews and rich fields |
| `get_memory` | Retrieve full memory by ID (increments access count) |
| `update_memory` | Update a memory in place (content, title, subtitle, type, concepts, files, category, importance, tags, sensitivity, trust) |
| `delete_memory` | Remove a memory (logged in journal) |
| `search_by_file` | Find memories related to a specific file path (searches files_read and files_modified) |
| `search_by_concept` | Find memories tagged with a specific concept |
| `get_timeline` | Get memories ordered by creation date, optionally filtered by type/project/session |
| `store_fact` | Store a subject/predicate/object triple |
| `query_facts` | Query the fact store with optional filters |
| `purge_expired` | Remove memories past their TTL |
| `summarize_old` | Condense old memories by category into summaries |

## Rich Metadata Fields

Memories support structured observation metadata beyond basic content:

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Short title (auto-generated from content if omitted) |
| `subtitle` | string | Secondary one-line description |
| `type` | enum | Observation type: `bugfix`, `feature`, `refactor`, `change`, `discovery`, `decision` |
| `concepts` | array | Knowledge categories: `how-it-works`, `why-it-exists`, `what-changed`, `problem-solution`, `gotcha`, `pattern`, `trade-off` |
| `files_read` | array | File paths read during the observation |
| `files_modified` | array | File paths modified |
| `session_id` | string | Link to the session that created this memory |
| `project` | string | Project identifier |
| `discovery_tokens` | integer | Estimated token cost of the discovery |
| `accessed_count` | integer | How many times this memory has been retrieved (auto-incremented) |

All metadata fields are optional. Existing `store_memory` calls without these
fields continue to work unchanged.

## Deduplication

Memories are deduplicated by SHA-256 content hash. Storing identical content
twice returns the existing ID and refreshes its timestamp — no duplicate rows.

## Sensitivity Gating

Memories have a sensitivity level (`public`, `private`, `secret`). Search
results are filtered by sensitivity:

- `public` — always returned.
- `private` — returned only when `allow_private=True`.
- `secret` — returned only when `allow_secret=True`.
- Unknown levels — **denied** (fail-closed).

## Scored Relevance

Search results are ranked by a weighted score:
- Match quality (0.55) — FTS5 BM25 or keyword hit ratio
- Recency (0.20) — exponential decay, 21-day half-life
- Importance (0.15) — author-assigned weight
- Trust (0.10) — source trustworthiness

Results below `min_score` (default 0.35) are filtered out.

## Enhanced FTS5

Full-text search indexes three columns: `content`, `title`, and `subtitle`.
The FTS index is automatically upgraded from older single-column versions
on first use. Concepts and file paths are searchable via dedicated operations
(`search_by_concept`, `search_by_file`) using LIKE queries.

## Access Counting

Every `get_memory` call increments the memory's `accessed_count`. This
tracks retrieval frequency and informs eviction decisions when a max
memories cap is configured.

## Max Memories Cap

Configure `max_memories` (default: 0 = no limit) to cap the store size.
When exceeded after a store, the least valuable memories are evicted.
Eviction priority: lowest `accessed_count`, then oldest `updated_at`,
then lowest `importance`.

## Mutation Journal

All write operations (insert, update, delete, dedup refresh) are recorded in
an append-only `memory_journal` table. This provides an audit trail for memory
mutations that cannot be modified or deleted through the tool interface.

## TTL and Expiry

Memories can be stored with `ttl_days`. Expired memories are excluded from
search results and can be permanently removed via `purge_expired`.

## What You Should Know

- The memory store is registered as the `memory.store` capability.
- `hooks-memory-inject` uses this capability to inject relevant memories
  at prompt time — you do not need to search manually.
- Use `store_memory` for persistent knowledge; use `store_fact` for
  structured subject/predicate/object triples.
- Use `search_by_file` to find all memories about a specific file.
- Use `search_by_concept` to find memories by knowledge category.
- Use `get_timeline` to see what happened chronologically.
- Use `update_memory` to refine or correct existing memories.
