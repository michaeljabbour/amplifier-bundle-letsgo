# Memory Store

LetsGo provides durable, searchable memory via `tool-memory-store`.

## Operations

`store`, `search`, `list`, `get`, `update`, `delete`, `search_by_file`, `search_by_concept`, `get_timeline`, `store_fact`, `query_facts`, `purge_expired`, `summarize_old`

## Key Facts

- Memories are **deduplicated by hash** — storing identical content refreshes the existing entry
- Results are **sensitivity-gated** — private and secret memories require explicit opt-in
- Search results are **scored by relevance** — match quality, recency, importance, and trust
- Access counts track retrieval frequency and inform eviction decisions
- Memories can have TTL; expired entries are excluded from search

## What You Should Know

- The memory store is registered as the `memory.store` capability
- `hooks-memory-inject` uses this capability to inject relevant memories at prompt time
- Use `store_memory` for persistent knowledge; use `store_fact` for structured triples
- Use `search_by_file` and `search_by_concept` for targeted retrieval

## Delegate to Expert

For complex multi-criteria retrieval or maintenance, delegate to `letsgo:memory-curator`.
