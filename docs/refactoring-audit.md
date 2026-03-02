# Thin-Behaviors Refactoring Audit

Tracking document for the `feat/thin-behaviors` refactoring. Each awareness
context file and agent description is audited for line count, behavior
inclusion, planned action, and current status.

---

## Target Metrics

| Metric | Before | After (target) |
|--------|--------|-----------------|
| Total context lines | 1273 | < 400 |
| Total agent lines | 495 | < 200 |
| Combined lines | 1768 | < 600 |

---

## Awareness Files

| File | Lines | Behavior | Expert Agent | Action | Status |
|------|-------|----------|--------------|--------|--------|
| browser-awareness.md | 36 | browser-capabilities | gateway-operator | trim to @mentions | pending |
| canvas-awareness.md | 39 | canvas-capabilities | creative-specialist | trim to @mentions | pending |
| gateway-awareness.md | 108 | gateway | gateway-operator | extract to skill, slim context | pending |
| heartbeat-awareness.md | 49 | heartbeat | admin-assistant | trim to @mentions | pending |
| heartbeat-system.md | 28 | (standalone) | admin-assistant | trim to @mentions | pending |
| letsgo-instructions.md | 126 | (standalone) | (root) | extract to skill, slim context | pending |
| mcp-awareness.md | 58 | mcp-capabilities | mcp-specialist | trim to @mentions | pending |
| memory-awareness.md | 42 | memory-inject | memory-curator | merge with memory-system, trim | pending |
| memory-store-awareness.md | 109 | memory-store | memory-curator | extract to skill, slim context | pending |
| memory-system-awareness.md | 70 | memory-inject, memory-store | memory-curator | merge with memory-awareness, trim | pending |
| observability-awareness.md | 43 | observability | admin-assistant | trim to @mentions | pending |
| sandbox-awareness.md | 28 | sandbox | security-reviewer | trim to @mentions | pending |
| secrets-awareness.md | 39 | secrets | security-reviewer | trim to @mentions | pending |
| skills-awareness.md | 90 | skills | admin-assistant | extract to skill, slim context | pending |
| soul-framework-awareness.md | 95 | (standalone) | (root) | extract to skill, slim context | pending |
| team-collaboration-awareness.md | 187 | (standalone) | (root) | extract to skill, slim context | pending |
| tool-policy-awareness.md | 48 | security-policy | security-reviewer | trim to @mentions | pending |
| voice-awareness.md | 28 | voice-capabilities | voice-specialist | trim to @mentions | pending |
| webchat-awareness.md | 50 | webchat-capabilities | gateway-operator | trim to @mentions | pending |

**Total: 19 files, 1273 lines**

---

## Agents

| Agent | Lines | Domain | Needs @mentions update | Status |
|-------|-------|--------|------------------------|--------|
| admin-assistant | 32 | scheduling, system health, heartbeat | yes | pending |
| creative-specialist | 68 | canvas, design, creative content | yes | pending |
| document-specialist | 61 | document generation, formatting | yes | pending |
| gateway-operator | 88 | gateway, channels, routing, browser, webchat | yes | pending |
| mcp-specialist | 30 | MCP server integration | yes | pending |
| memory-curator | 89 | memory pipeline, store, curation | yes | pending |
| security-reviewer | 96 | security policy, secrets, sandbox | yes | pending |
| voice-specialist | 31 | voice transcription, TTS | yes | pending |

**Total: 8 agents, 495 lines**

---

## Completed

_Files will be moved here as each is refactored._

| File | Before (lines) | After (lines) | Reduction | Commit |
|------|----------------|---------------|-----------|--------|
| | | | | |

---

## Progress

- [ ] Phase 1: Awareness files trimmed to @mentions
- [ ] Phase 2: Agent descriptions updated with @mentions
- [ ] Phase 3: Skills extracted from large context files
- [ ] Phase 4: Final validation and cleanup
