# Memory Store

LetsGo provides durable, searchable memory via `tool-memory-store`.

## Operations

| Operation | Description |
|-----------|-------------|
| `store_memory` | Store content with category, importance, sensitivity, tags, optional TTL |
| `search_memories` | Full-text search with scored relevance (FTS5 + BM25) |
| `list_memories` | List memory metadata with content previews |
| `get_memory` | Retrieve full memory entries by ID |
| `delete_memory` | Remove a memory (logged in journal) |
| `store_fact` | Store a subject/predicate/object triple |
| `query_facts` | Query the fact store with optional filters |
| `purge_expired` | Remove memories past their TTL |

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

## Mutation Journal

All write operations (insert, delete, dedup refresh) are recorded in an
append-only `memory_journal` table. This provides an audit trail for memory
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
