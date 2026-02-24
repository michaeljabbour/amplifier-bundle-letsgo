# OpenClaw Migration Phase 4: `letsgo-browser` Satellite Bundle — Design

## Goal

Add browser automation capabilities to the LetsGo ecosystem by composing the existing `amplifier-bundle-browser-tester` bundle with gateway-specific context and skills. This is the leanest phase — pure composition, no new modules or gateway middleware.

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | Composition-only | browser-tester already provides 3 agents + agent-browser CLI tooling |
| Playwright module | Deferred to Phase 4.1 | No concrete use case yet; agent-browser CLI handles navigation, screenshots, forms |
| Existing skills | Commit under satellite bundle | `agent-browser` and `webapp-testing` skills belong with the browser satellite |
| New gateway middleware | None | No browser-specific gateway processing needed |
| New tool modules | None | browser-tester's agent-browser CLI covers all current needs |

## What `browser-tester` Already Provides

The external `amplifier-bundle-browser-tester` bundle includes:

| Component | What It Does |
|-----------|-------------|
| `browser-operator` agent | General-purpose automation: navigation, forms, data extraction, screenshots |
| `browser-researcher` agent | Multi-page research, documentation lookup, data synthesis |
| `visual-documenter` agent | Screenshots at multiple viewports, QA evidence, flow documentation |
| `agent-browser` CLI tool | Token-efficient browser automation via accessibility-tree refs |
| Context + troubleshooting | Comprehensive browser guide + 666-line troubleshooting doc |
| Recipes | Competitive research, form automation, visual audit |

All three agents use the `agent-browser` CLI (npm package wrapping Playwright/Chromium).

## What the Satellite Adds

The `letsgo-browser` satellite layers gateway-specific value on top:

1. **Gateway-specific context** — How browser agents integrate with the LetsGo gateway: using browser for channel onboarding (WhatsApp QR screenshots, OAuth flows), pushing visual results to canvas, testing gateway endpoints
2. **Browser skills** — Two existing skills committed under the satellite:
   - `agent-browser`: Full agent-browser CLI reference (navigation, snapshots, sessions, auth persistence)
   - `webapp-testing`: Playwright-based programmatic testing with server lifecycle management

## Satellite Bundle Structure

```
browser/
├── bundle.md                          # Thin: includes browser-tester + own behavior
├── behaviors/
│   └── browser-capabilities.yaml      # Composes browser-tester behavior + context
├── context/
│   └── browser-awareness.md           # Gateway-specific browser instructions
└── skills/
    ├── agent-browser/                 # CLI reference skill (existing, committed)
    └── webapp-testing/                # Playwright testing skill (existing, committed)
```

## Composition Model

```yaml
# browser/bundle.md
includes:
  - amplifier-bundle-browser-tester    # External: 3 agents + CLI tool
  - bundle: letsgo-browser:behaviors/browser-capabilities
```

The user's root bundle includes both `letsgo` (core) and `letsgo-browser`. All agents from browser-tester are available in the merged session alongside gateway capabilities.

## What Phase 4 Ships

| Component | Type | What It Does |
|-----------|------|-------------|
| Satellite bundle | `browser/bundle.md` + behavior | Composes browser-tester with gateway context |
| Browser awareness | `browser/context/browser-awareness.md` | Gateway-specific browser instructions |
| agent-browser skill | `browser/skills/agent-browser/` | CLI reference (existing, committed) |
| webapp-testing skill | `browser/skills/webapp-testing/` | Playwright testing (existing, committed) |
| Recipe update | `recipes/setup-wizard.yaml` | Browser configuration step in satellite stage |

## What's NOT in Phase 4

| Deferred | Rationale | When |
|----------|-----------|------|
| `tool-browser-playwright` module | No concrete use case beyond what agent-browser CLI provides | Phase 4.1 when needed |
| QR scanner automation | agent-browser can screenshot QR codes already; Playwright overkill | Phase 4.1 |
| `web_auth.py` OAuth capture | Speculative; no channel currently requires it | Phase 4.1 |
| Gateway browser middleware | No browser-specific gateway processing needed | Not planned |

## Estimated Scope

| Metric | Value |
|--------|-------|
| New files | ~8 (bundle, behavior, context, skill files) |
| Modified files | 1 (setup-wizard.yaml) |
| New code | ~0 (all content/config files) |
| Tests | ~0 (no new code to test; bundle validated at runtime) |
| Tasks | 4-5 |

Fastest phase in the migration — pure composition and content.

---

*This is a composition-only satellite. The Amplifier experts validated the peer-bundle composition model in Phase 0. browser-tester's agents and tools are inherited via `includes:`.*