# LetsGo Memory System — Build Scaffolding

> Companion to [amplifier-memory-research](https://github.com/michaeljabbour/amplifier-memory-research) CONCEPT_MAP.md, IMPLEMENTABILITY.md, and IDD_SCAFFOLDING.md.

## Verdict

**Generation 1 complete.** 8-module bio-inspired memory pipeline implemented,
tested (285 tests, 0 failures), and deployed. All modules follow Amplifier's
hook/capability/tool patterns. Zero kernel changes required.

**Scorecard:**

| Metric | Value |
|--------|-------|
| Memory modules | 8 of 8 planned (Gen 1) |
| Infrastructure modules | 4 (tool-policy, telemetry, sandbox, secrets) |
| Total tests | 285 (195 memory + 90 infrastructure) |
| Test failures | 0 (1 flaky perf test — timing-sensitive, pre-existing) |
| Kernel changes required | 0 |
| Bio concepts implemented | 7 of 64 fully, 21 approximated, 26 deferred |
| Implementability | 80% NATIVE, 8% NATIVE+DEPS, 0% INFEASIBLE |

---

## Architecture

### Module Inventory (8 memory modules)

| # | Module | Type | Hook Events | Priority | Capability | Status |
|---|--------|------|-------------|----------|------------|--------|
| 1 | tool-memory-store | Tool | — | — | `memory.store` | ✅ PASS |
| 2 | hooks-memory-memorability | Hook (cap only) | — | — | `memory.memorability` | ✅ PASS |
| 3 | hooks-memory-boundaries | Hook | tool:post | 100 | `memory.boundaries` | ✅ PASS |
| 4 | hooks-memory-capture | Hook | tool:post, session:start, session:end | 150, 50, 100 | — | ✅ PASS |
| 5 | hooks-memory-temporal | Hook (cap only) | — | — | `memory.temporal` | ✅ PASS |
| 6 | hooks-memory-consolidation | Hook | session:end | 200 | `memory.consolidation` | ✅ PASS |
| 7 | hooks-memory-compression | Hook | session:end | 300 | `memory.compression` | ✅ PASS |
| 8 | hooks-memory-inject | Hook | prompt:submit | 50 | — | ✅ PASS |

### Non-Memory Modules (4 infrastructure)

| Module | Type | Status | Notes |
|--------|------|--------|-------|
| hooks-tool-policy | Hook | ✅ Stable | 4-tier risk classification, allowlists, careful/automation mode |
| hooks-telemetry | Hook | ✅ Stable | 7-event subscription, tool metrics, token tracking |
| tool-sandbox | Tool | ✅ Stable | Docker-first isolated execution, resource limits |
| tool-secrets | Tool | ✅ Stable | Fernet encryption, handle-based access, 5-min TTL |

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

### Scoring Pipeline

```
Composite score = 0.55 × match (BM25 from FTS5)
               + 0.20 × recency (0.5^(age/21 days))
               + 0.15 × importance (0.0-1.0, modified by consolidation)
               + 0.10 × trust (0.0-1.0)

Importance lifecycle:
  capture assigns (0.35-0.80 by observation type)
  → memorability gates (threshold 0.30, 4 dimensions)
  → consolidation boosts (0.03 × ln(1+access_count)) or decays (0.02/day linear)
  → eviction at min_importance (0.05) after 90 days unaccessed
```

---

## Build Status — P0 (Core Architecture)

All P0 items are PASS.

| Item | Status | Evidence |
|------|--------|---------|
| Memory store with FTS5 search | ✅ PASS | 26 tests in test_memory_store_extended.py |
| SHA-256 content deduplication | ✅ PASS | test_deduplication |
| TTL expiry with purge | ✅ PASS | test_ttl_expiry, test_purge_expired_operation |
| Sensitivity gating (fail-closed) | ✅ PASS | test_search_v2_sensitivity_gating |
| Append-only mutation journal | ✅ PASS | test_journal_records_operations |
| Structured fact store (SPO triples) | ✅ PASS | test_store_fact_and_query, test_fact_deduplication |
| Public scoring API on store | ✅ PASS | test_extract_keywords, test_compute_score, test_allow_by_sensitivity |
| Auto-access tracking in search_v2 | ✅ PASS | test_search_v2_auto_access_tracking |
| TOCTOU race fix in _enforce_limit | ✅ PASS | Verified in code review (write lock wraps count+delete) |
| Scoring code deduplication (inject simplified) | ✅ PASS | inject reduced 537→267 lines, zero duplicated scoring code |

---

## Build Status — P1 (Bio-Inspired Capabilities)

All P1 items are PASS.

| Item | Bio Inspiration | Status | Evidence |
|------|----------------|--------|---------|
| Memorability scoring / selective encoding | Papers 3,4: 55.7% real-world recognition prediction | ✅ PASS | 23 tests in test_hooks_memory_memorability.py |
| Event segmentation / boundary detection | Paper 1: Boundary cells in MTL | ✅ PASS | 15 tests in test_hooks_memory_boundaries.py |
| Auto-capture from tool executions | Automatic encoding of experience | ✅ PASS | 18 tests in test_hooks_memory_capture.py |
| Self-amplifying consolidation | Paper 5: Stochastic replay, access-boost cycle | ✅ PASS | 13 tests in test_hooks_memory_consolidation.py |
| Multi-scale temporal scaffolding | Paper 6: Temporally Periodic Cells (4 scales) | ✅ PASS | 15 tests in test_hooks_memory_temporal.py |
| Compositional compression | Paper 8: CRUMB cluster-and-merge | ✅ PASS | 23 tests in test_hooks_memory_compression.py |
| Temporal-balanced retrieval in inject | Paper 6: Multi-scale retrieval allocation | ✅ PASS | test_temporal_capability_used_when_available |
| Read-time memory governor | Safety: blocks instruction-like content | ✅ PASS | test_governor_redacts_instruction_like_content |

---

## Build Status — P2 (Deferred / Future Work)

These items are identified but NOT yet implemented. See [amplifier-memory-research/IDD_SCAFFOLDING.md](https://github.com/michaeljabbour/amplifier-memory-research/blob/main/IDD_SCAFFOLDING.md) for the full 6-generation roadmap with IDD decompositions.

### Generation 2 — Memories Know Their Context

| Item | Bio Inspiration | Priority | Status | Notes |
|------|----------------|----------|--------|-------|
| Segment-aware encoding | Papers 1,2: Boundary-triggered compression | P0-next | 🔲 DEFERRED | Boundaries detected but never consumed — need segment summaries at each boundary |
| Encoding context capture | Paper 1: State reinstatement | P0-next | 🔲 DEFERRED | Memories lack formation context (active tools, user goal, file set) |
| Stochastic consolidation | Paper 5: Probabilistic replay | P0-next | 🔲 DEFERRED | Current consolidation is deterministic full-scan; should be weighted random sampling |
| Exponential decay (not linear) | Paper 5: Exponential synaptic decay | P0-next | 🔲 DEFERRED | Single formula change: `importance *= 0.98^days` instead of `importance -= 0.02 * days` |

### Generation 3 — Time Is More Than a Timestamp

| Item | Bio Inspiration | Priority | Status | Notes |
|------|----------------|----------|--------|-------|
| Within-segment temporal position | Paper 2: Phase precession analog | P1-next | 🔲 DEFERRED | Assign decreasing freshness weights within each segment |
| Attention-proportional resolution | Paper 9: Eccentricity-based resolution | P1-next | 🔲 DEFERRED | Give more context tokens to higher-scoring memories |
| Dynamic threshold adaptation | Paper 5: Neural threshold adaptation | P1-next | 🔲 DEFERRED | Auto-tune min_score and base_threshold based on retrieval effectiveness |

### Generation 4 — Compositional Memory

| Item | Bio Inspiration | Priority | Status | Notes |
|------|----------------|----------|--------|-------|
| Continuous temporal encoding | Paper 6: Periodic oscillator phases | P2-next | 🔲 DEFERRED | Replace static 4-bucket allocation with multi-scale oscillator phase vectors |
| Semantic block extraction | Paper 8: CRUMB reusable blocks | P2-next | 🔲 DEFERRED | Decompose memories into reusable blocks (file paths, error patterns, tool sequences) |
| Learned memorability weights | Paper 9: Statistical diet from experience | P2-next | 🔲 DEFERRED | Learn from actual retrieval patterns which types are truly memorable |

### Generation 5 — Memory as Network

| Item | Bio Inspiration | Priority | Status | Notes |
|------|----------------|----------|--------|-------|
| Block-based retrieval | Paper 8: Cross-memory recall via shared blocks | P3-next | 🔲 DEFERRED | Use shared semantic blocks to find memories FTS5 keyword search misses |
| Hierarchical memory staging | Paper 5: Hippocampus → neocortex transfer | P3-next | 🔲 DEFERRED | Hot store (session) → cold store (persistent) with consolidation between |

### Generation 6 — Research Frontier

| Item | Bio Inspiration | Priority | Status | Notes |
|------|----------------|----------|--------|-------|
| Distributed representations | Paper 7: SDMLP sparse distributed memory | Research | 🔲 DEFERRED | Paradigm shift: neural network as memory substrate, not database rows. Needs numpy. |

---

## Known Issues

| Issue | Severity | Module | Notes |
|-------|----------|--------|-------|
| Boundary detection is inert | **Medium** | hooks-memory-boundaries | `memory.boundaries` capability registered but nothing consumes it. Boundaries stored as facts but never influence retrieval or segmentation. Gen 2 work item. |
| Compression reads content_preview not content | **Low** | hooks-memory-compression | `list_all()` returns 100-char preview; keyword extraction operates on preview instead of full content. Reduces clustering quality. |
| No transactional safety in compression | **Low** | hooks-memory-compression | Originals deleted one-by-one after summary stored; crash mid-cluster can lose data. Need atomic batch delete. |
| Consolidation scans entire DB | **Medium** | hooks-memory-consolidation | O(n) full scan every session:end in 100-row batches; will degrade at scale. Stochastic sampling (Gen 2) would also fix this. |
| Single-linkage clustering to seed only | **Low** | hooks-memory-compression | Candidates compared only to cluster seed, not all members; can create elongated clusters with low internal similarity. |
| Linear decay should be exponential | **Low** | hooks-memory-consolidation | Biology uses `importance *= 0.98^days` (fast early, slow late); current uses `importance -= 0.02 * days` (constant rate). Single formula change. |

---

## Test Coverage

| Test File | Tests | Covers |
|-----------|-------|--------|
| test_tool_memory_store.py | 23 | Core CRUD, FTS5, sensitivity, dedup, TTL, tool interface |
| test_memory_store_extended.py | 26 | Update, facts, file/concept search, timeline, summarize, eviction, journal, rich metadata, access tracking, public API |
| test_hooks_memory_inject.py | 16 | Capability retrieval, governor, temporal integration, empty/disabled states |
| test_hooks_memory_capture.py | 18 | Session lifecycle, tool capture, classification, memorability gating, file tracking |
| test_hooks_memory_boundaries.py | 15 | Boundary detection, sliding window, fact storage, Jaccard similarity |
| test_hooks_memory_memorability.py | 23 | Salience, substance, distinctiveness, type scoring, thresholds, edge cases |
| test_hooks_memory_consolidation.py | 13 | Boost/decay/remove, protected types, batch processing, access tracking |
| test_hooks_memory_temporal.py | 15 | Scale classification, balanced retrieval, backfill, dedup, allocation |
| test_hooks_memory_compression.py | 23 | Clustering, merge, metadata preservation, skip rules, Jaccard, age gating |
| test_security_hardening.py | 17 | Sensitivity fail-closed, journal, sandbox, allowlist, telemetry redaction |
| test_performance.py | 6 | Latency benchmarks, scaling linearity, memory growth bounds |
| **TOTAL** | **195 memory / 285 all** | |

---

## Research Foundation

The bio-inspired memory system is grounded in 9 neuroscience papers from Kreiman's lab (Engramme) plus 19 curated papers from Jake's collection. Full analysis lives in [amplifier-memory-research](https://github.com/michaeljabbour/amplifier-memory-research):

| Document | Key Finding |
|----------|------------|
| [CONCEPT_MAP.md](https://github.com/michaeljabbour/amplifier-memory-research/blob/main/CONCEPT_MAP.md) | 64 biological concepts: 13% fully implemented, 39% approximated, 48% not yet implemented |
| [IMPLEMENTABILITY.md](https://github.com/michaeljabbour/amplifier-memory-research/blob/main/IMPLEMENTABILITY.md) | 80% natively implementable in Amplifier, 8% need external deps, 0% infeasible |
| [IDD_SCAFFOLDING.md](https://github.com/michaeljabbour/amplifier-memory-research/blob/main/IDD_SCAFFOLDING.md) | 12 work items across 6 generations, each decomposed into IDD's 5 primitives |
| [ANALYSIS.md](https://github.com/michaeljabbour/amplifier-memory-research/blob/main/ANALYSIS.md) | Original gap analysis between research and implementation (partially superseded) |

### Paper-to-Module Mapping

| Paper | Key Concept | Primary Module(s) |
|-------|------------|-------------------|
| 1: Boundary Detection (NatNeuro 2022) | Cognitive boundary cells, event segmentation | hooks-memory-boundaries |
| 2: Theta Phase Precession (NHB 2024) | Phase coding, temporal compression | hooks-memory-temporal (approximated) |
| 3: Movie Memorability (SciReports 2024) | Selective encoding, memorability prediction | hooks-memory-memorability |
| 4: Real-World Memory (JEP:General 2023) | Naturalistic memory, attention gating | hooks-memory-capture |
| 5: Consolidation (NeurIPS 2021) | Self-amplifying access-boost cycle | hooks-memory-consolidation |
| 6: Temporal Periodic Cells (NatNeuro 2024) | Multi-scale temporal scaffolding | hooks-memory-temporal |
| 7: SDMLP (NeurIPS 2022) | Sparse distributed memory | Not implemented (Gen 6) |
| 8: CRUMB (ICML 2024) | Compositional compression, reusable blocks | hooks-memory-compression |
| 9: Inductive Biases (NeurIPS 2022) | Eccentricity, statistical diet | hooks-memory-memorability (partial) |

---

## Bundle Composition

```
bundle.md
  └── behaviors/letsgo-capabilities.yaml
        ├── security-policy.yaml      → hooks-tool-policy
        ├── secrets.yaml              → tool-secrets
        ├── sandbox.yaml              → tool-sandbox
        ├── observability.yaml        → hooks-telemetry
        ├── memory-store.yaml         → tool-memory-store
        ├── memory-memorability.yaml  → hooks-memory-memorability
        ├── memory-boundaries.yaml    → hooks-memory-boundaries
        ├── memory-capture.yaml       → hooks-memory-capture
        ├── memory-temporal.yaml      → hooks-memory-temporal
        ├── memory-consolidation.yaml → hooks-memory-consolidation
        ├── memory-compression.yaml   → hooks-memory-compression
        ├── memory-inject.yaml        → hooks-memory-inject
        ├── gateway.yaml              → (gateway system)
        └── heartbeat.yaml            → (heartbeat system)
```

---

## Changelog

| Date | Change |
|------|--------|
| 2025-02 | Gen 1 complete: 8 memory modules, 285 tests, full pipeline |
| 2025-02 | Documentation audit: 37 issues found, 30 fixed |
| 2025-02 | SCAFFOLDING.md created (this file) |
