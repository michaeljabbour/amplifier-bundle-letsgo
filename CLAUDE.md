# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

LetsGo is an Amplifier bundle providing security, memory, secrets, sandbox, observability, gateway, and multi-agent capabilities. The memory system is a bio-inspired pipeline modeled on neuroscience research.

## Structure

```
amplifier-bundle-letsgo/
├── bundle.md                    # Bundle manifest
├── README.md                    # Full documentation
├── SCAFFOLDING.md               # Build status, deferred items, known issues
├── behaviors/                   # 15 behavior YAML files (module composition)
│   └── letsgo-capabilities.yaml # Master includes (mount order matters)
├── context/                     # 12 awareness docs (injected into agent context)
├── agents/                      # 3 agent definitions
├── recipes/                     # 4 workflow recipes
├── skills/                      # 5 loadable skills
├── modules/                     # 12 Python modules (8 memory + 4 infrastructure)
├── tests/                       # 285 tests
├── docs/                        # 2 guide documents
└── gateway/                     # Gateway application
```

## Key Files

| File | Purpose |
|------|---------|
| `SCAFFOLDING.md` | **Start here** for memory system status, known issues, deferred work |
| `README.md` | Full documentation of all capabilities |
| `behaviors/letsgo-capabilities.yaml` | Mount order — dependency chain for all modules |
| `context/memory-system-awareness.md` | Unified memory system reference (injected into sessions) |
| `context/letsgo-instructions.md` | Master context with all capabilities listed |

## Memory System Architecture

8 modules forming a bio-inspired pipeline:

```
tool:post → boundaries(@100) → capture(@150) → store
prompt:submit → inject(@50) ← temporal ← store
session:end → capture(@100) → consolidation(@200) → compression(@300)
```

Capabilities registered: `memory.store`, `memory.memorability`, `memory.boundaries`, `memory.temporal`, `memory.consolidation`, `memory.compression`

All inter-module communication via capability registry. Every dependency is optional — graceful degradation.

## Testing

```bash
# Run all tests (excluding gateway — needs aiohttp)
python -m pytest tests/ --ignore=tests/test_gateway -v

# Run only memory tests
python -m pytest tests/test_*memory*.py tests/test_hooks_memory*.py -v
```

285 tests total (195 memory, 90 infrastructure). 0 failures.

## Working with the Code

- **Module pattern**: Each module has `__init__.py` with `async def mount(coordinator, config)` entry point
- **Hook pattern**: Hooks register on lifecycle events with priority ordering
- **Capability pattern**: `coordinator.register_capability(name, obj)` / `coordinator.get_capability(name)`
- **Behavior pattern**: YAML files in `behaviors/` compose modules + context + config
- **Context pattern**: Markdown files in `context/` are injected into agent sessions via behaviors

## Research Foundation

The memory system is grounded in neuroscience research. See [amplifier-memory-research](https://github.com/michaeljabbour/amplifier-memory-research) for:
- 9 Engramme papers (Kreiman lab) + 19 Jake papers (classical neuro + LLM memory)
- CONCEPT_MAP.md: 64 biological concepts mapped to implementation
- IMPLEMENTABILITY.md: 80% natively implementable in Amplifier
- IDD_SCAFFOLDING.md: 6-generation roadmap to true bio-inspired memory

## Known Issues

See SCAFFOLDING.md for the full list. Top issues:
1. Boundary detection is inert (detected but never consumed)
2. Consolidation scans entire DB (O(n) every session:end)
3. Compression uses content_preview not full content for clustering
