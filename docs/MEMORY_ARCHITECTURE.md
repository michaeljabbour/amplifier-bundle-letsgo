# Memory Pipeline Architecture

The memory pipeline is letsgo's most sophisticated subsystem. It spans seven
hook modules and one tool module, coordinated entirely through the capability
registry — no module imports another directly.

## Event Flow

Eight behaviors fire across three event phases. Priority determines order
within each phase (lower number = earlier).

```
prompt:submit (p50)     tool:post (p100→p150)     session:end (p100→p200→p300)
      │                        │                          │
      ▼                        ▼                          ▼
memory-inject           boundaries(100)            capture(100)
                        capture(150)               consolidation(200)
                                                   compression(300)
```

Two modules — `hooks-memory-temporal` and `hooks-memory-memorability` — run
only at mount time. They register capabilities consumed by the event hooks
above; they do not subscribe to any events themselves.

## Behavior Table

| Module                     | Event         | Priority | Registers capability   | Consumes capability              |
|----------------------------|---------------|----------|------------------------|----------------------------------|
| tool-memory-store          | (tool)        | —        | memory.store           | —                                |
| hooks-memory-temporal      | (mount only)  | —        | memory.temporal        | memory.store                     |
| hooks-memory-memorability  | (mount only)  | —        | memory.memorability    | memory.store                     |
| hooks-memory-inject        | prompt:submit | 50       | —                      | memory.store, memory.temporal    |
| hooks-memory-boundaries    | tool:post     | 100      | memory.boundaries      | memory.store                     |
| hooks-memory-capture       | tool:post     | 150      | —                      | memory.store, memory.memorability|
| hooks-memory-capture       | session:start | 50       | —                      | memory.store                     |
| hooks-memory-capture       | session:end   | 100      | —                      | memory.store, memory.memorability|
| hooks-memory-consolidation | session:end   | 200      | memory.consolidation   | memory.store                     |
| hooks-memory-compression   | session:end   | 300      | memory.compression     | memory.store                     |

## Data Flow

### prompt:submit — memory-inject (p50)
Reads stored memories via `memory.store`, applies temporal scaffolding from
`memory.temporal`, and injects relevant context into the prompt before the
model sees it.

### tool:post — boundaries (p100) then capture (p150)
`boundaries` examines each completed tool call and writes boundary markers to
the memory store, segmenting the session timeline. `capture` runs after
boundaries are set; it scores each tool exchange for memorability (via
`memory.memorability`) and persists high-value fragments to the store.

### session:start — capture (p50)
Initializes the session context window in the store, establishing the record
that `tool:post` events will append to.

### session:end — capture (p100) → consolidation (p200) → compression (300)
Three-stage pipeline runs in priority order:
1. `capture` flushes any buffered tool-post fragments and closes the session record.
2. `consolidation` merges fragments into durable long-term memories.
3. `compression` applies token budget management — summarizes or prunes the
   long-term store when it exceeds configured limits.

## Capability Registry

| Capability          | Registered by              | Consumed by                                      |
|---------------------|----------------------------|--------------------------------------------------|
| memory.store        | tool-memory-store          | all memory hook modules                          |
| memory.temporal     | hooks-memory-temporal      | hooks-memory-inject                              |
| memory.memorability | hooks-memory-memorability  | hooks-memory-capture                             |
| memory.boundaries   | hooks-memory-boundaries    | (available for future consumers)                 |
| memory.consolidation| hooks-memory-consolidation | (available for future consumers)                 |
| memory.compression  | hooks-memory-compression   | (available for future consumers)                 |

## Configuration Reference

Each behavior module has a YAML file under `behaviors/`:

| Module                     | Behavior file                                     |
|----------------------------|---------------------------------------------------|
| hooks-memory-inject        | `behaviors/hooks-memory-inject.yaml`              |
| hooks-memory-boundaries    | `behaviors/hooks-memory-boundaries.yaml`          |
| hooks-memory-capture       | `behaviors/hooks-memory-capture.yaml`             |
| hooks-memory-temporal      | `behaviors/hooks-memory-temporal.yaml`            |
| hooks-memory-memorability  | `behaviors/hooks-memory-memorability.yaml`        |
| hooks-memory-consolidation | `behaviors/hooks-memory-consolidation.yaml`       |
| hooks-memory-compression   | `behaviors/hooks-memory-compression.yaml`         |

The tool module is configured via `tools/tool-memory-store.yaml`.
