# Bundle Composition at Scale: The LetsGo Architecture Guide

**Audience:** Intermediate-to-expert developers familiar with Amplifier basics  
**Scope:** How to structure large bundle families using the LetsGo project as a reference implementation  
**Last updated:** 2026-02-24  

---

## Overview

LetsGo is a comprehensive AI assistant platform built as an Amplifier bundle family. It provides security policy enforcement, encrypted secrets, sandboxed execution, observability, a bio-inspired memory system, a multi-channel messaging gateway, proactive heartbeat sessions, and browser/canvas/voice/webchat/MCP satellite capabilities.

That is a lot of surface area. This guide explains how LetsGo organizes all of it into a decomposed, composable architecture — and, more importantly, extracts the patterns you can reuse in your own projects.

The narrative follows a before/after arc. We start with the monobundle trap — the natural but painful approach most projects begin with — then walk through LetsGo's actual architecture, compare the two side-by-side with annotated code, and close with the reusable rules that fall out of the comparison.

---

## 1. Before: The Monobundle Trap

When you start building on Amplifier, the first instinct is to put everything in one bundle. One `bundle.md`, one `behaviors/` directory, one big ball of capability. It works at first. Then the project grows.

### What a monobundle looks like

Imagine LetsGo's entire feature set crammed into a single bundle manifest:

```yaml
# THE MONOBUNDLE — don't do this
bundle:
  name: letsgo-everything
  version: 1.0.0
  description: Security, secrets, sandbox, observability, memory, gateway,
               voice, canvas, browser, webchat, MCP, heartbeat, skills...

includes:
  - bundle: letsgo-everything:behaviors/security-policy
  - bundle: letsgo-everything:behaviors/secrets
  - bundle: letsgo-everything:behaviors/sandbox
  - bundle: letsgo-everything:behaviors/observability
  - bundle: letsgo-everything:behaviors/memory-store
  - bundle: letsgo-everything:behaviors/memory-memorability
  - bundle: letsgo-everything:behaviors/memory-boundaries
  - bundle: letsgo-everything:behaviors/memory-capture
  - bundle: letsgo-everything:behaviors/memory-temporal
  - bundle: letsgo-everything:behaviors/memory-consolidation
  - bundle: letsgo-everything:behaviors/memory-compression
  - bundle: letsgo-everything:behaviors/memory-inject
  - bundle: letsgo-everything:behaviors/heartbeat
  - bundle: letsgo-everything:behaviors/gateway
  - bundle: letsgo-everything:behaviors/skills
  - bundle: letsgo-everything:behaviors/voice-capabilities
  - bundle: letsgo-everything:behaviors/canvas-capabilities
  - bundle: letsgo-everything:behaviors/browser-capabilities
  - bundle: letsgo-everything:behaviors/webchat-capabilities
  - bundle: letsgo-everything:behaviors/mcp-capabilities
  - amplifier-bundle-browser-tester   # external dependency baked in
```

Twenty-one includes. Every feature forced into a single namespace. This creates five concrete problems:

**The manifest becomes unmanageable.** Twenty-plus behavior includes with implicit ordering dependencies. Which ones depend on which? The manifest doesn't tell you — you have to hold the dependency graph in your head.

**Everything is coupled.** A user who wants voice transcription must also load the browser automation stack, the canvas display system, and the MCP bridge. There is no way to opt in to just one capability domain.

**No clear dependency ordering.** The memory system has strict internal ordering — the store must register before capture can consume it, memorability scoring must exist before capture filters through it, and injection must come last because it reads from the store. In a monobundle, this ordering is implicit and fragile. Move one line and the system breaks silently.

**Contributors step on each other.** The person building voice features edits the same `bundle.md` and `behaviors/` directory as the person building canvas. Merge conflicts are constant. Ownership boundaries don't exist.

**Testing is all-or-nothing.** You cannot test the memory system in isolation. Loading the bundle loads everything — gateway, browser, voice, the works. Test setup becomes a project in itself.

The monobundle works for small projects. For anything with more than five or six behaviors, you need a different structure.

---

## 2. After: The LetsGo Family Architecture

LetsGo decomposes into **six bundles**: one core and five satellites.

```
                         ┌─────────────────────┐
                         │   User's root        │
                         │   bundle.md          │
                         │                      │
                         │  includes:           │
                         │   - letsgo           │
                         │   - letsgo-voice     │
                         │   - letsgo-canvas    │
                         │   - letsgo-browser   │
                         │   - letsgo-webchat   │
                         │   - letsgo-mcp       │
                         └──────────┬───────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
              ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
              │  letsgo    │  │  letsgo-  │  │  letsgo-  │
              │  (core)    │  │  voice    │  │  canvas   │
              │            │  │           │  │           │
              │ 14 behav.  │  │ satellite │  │ satellite │
              │ security   │  │ peer      │  │ peer      │
              │ memory     │  │           │  │           │
              │ gateway    │  └───────────┘  └───────────┘
              │ heartbeat  │
              │ skills     │  ┌───────────┐  ┌───────────┐
              │ observ.    │  │  letsgo-  │  │  letsgo-  │
              └────────────┘  │  browser  │  │  webchat  │
                              │           │  │           │
                              │ satellite │  │ satellite │
                              │ (pure     │  │ peer      │
                              │ compose)  │  └───────────┘
                              └───────────┘
                                             ┌───────────┐
                                             │  letsgo-  │
                                             │  mcp      │
                                             │           │
                                             │ satellite │
                                             │ peer      │
                                             └───────────┘
```

### The core bundle: thin root, thick behaviors

The root `bundle.md` is 13 lines:

```yaml
# bundle.md — the entire root manifest
---
bundle:
  name: letsgo
  version: 1.0.0
  description: Security, memory, secrets, sandbox, observability,
               gateway, and multi-agent capabilities

includes:
  - bundle: letsgo:behaviors/letsgo-capabilities
---

# LetsGo Enhanced Capabilities

@letsgo:context/letsgo-instructions.md
```
> **Source:** `bundle.md`

That is the thin bundle pattern. The manifest declares identity (name, version, description), delegates all composition to a single master behavior, and injects one context file for agent awareness. Nothing else. No tools, no hooks, no modules — those live in the behaviors.

### The master behavior: ordered composition

All the real composition happens in `letsgo-capabilities.yaml`:

```yaml
# behaviors/letsgo-capabilities.yaml — the composition spine
bundle:
  name: behavior-letsgo-capabilities
  version: 1.0.0
  description: All LetsGo capability enhancements

includes:
  - bundle: letsgo:behaviors/security-policy
  - bundle: letsgo:behaviors/secrets
  - bundle: letsgo:behaviors/sandbox
  - bundle: letsgo:behaviors/observability
  # Memory system (order matters — capabilities must register before consumers)
  - bundle: letsgo:behaviors/memory-store          # 1. Data layer — registers memory.store
  - bundle: letsgo:behaviors/memory-memorability   # 2. Scoring capability — before capture
  - bundle: letsgo:behaviors/memory-boundaries     # 3. Boundary detection — before capture
  - bundle: letsgo:behaviors/memory-capture        # 4. Auto-capture from tool:post
  - bundle: letsgo:behaviors/memory-temporal       # 5. Temporal classification capability
  - bundle: letsgo:behaviors/memory-consolidation  # 6. Decay/boost cycle at session:end
  - bundle: letsgo:behaviors/memory-compression    # 7. Cluster merging at session:end
  - bundle: letsgo:behaviors/memory-inject         # 8. Prompt injection — reads from store last
  # Heartbeat
  - bundle: letsgo:behaviors/heartbeat
  # Gateway
  - bundle: letsgo:behaviors/gateway
```
> **Source:** `behaviors/letsgo-capabilities.yaml`

This file is the architectural spine. Read it top to bottom and you understand the entire capability stack:

| Order | Behavior | Layer | What It Provides |
|-------|----------|-------|------------------|
| 1 | `security-policy` | Foundation | Tool risk classification, approval gates, automation mode |
| 2 | `secrets` | Foundation | Encrypted credential storage, `secrets.redeem` capability |
| 3 | `sandbox` | Foundation | Docker-isolated execution for untrusted code |
| 4 | `observability` | Foundation | Telemetry hooks, `telemetry.metrics` capability |
| 5-12 | `memory-*` (8 files) | Memory Stack | Bio-inspired pipeline: store → score → detect → capture → classify → consolidate → compress → inject |
| 13 | `heartbeat` | Application | Proactive cron-scheduled sessions |
| 14 | `gateway` | Application | Multi-channel messaging daemon awareness |

The ordering is deliberate. Foundation behaviors register capabilities that the memory stack consumes. The memory stack has its own strict internal ordering (annotated inline with numbered comments). Application-level behaviors come last because they depend on all of the above.

### Satellites are peers, not children

The five satellite bundles — `letsgo-voice`, `letsgo-canvas`, `letsgo-browser`, `letsgo-webchat`, `letsgo-mcp` — share a critical design property: **they do not include the core bundle.** They assume it is present because the user's root bundle includes both.

This is the peer composition model. The user's root `bundle.md` is the integration point:

```yaml
# The user's root bundle — the integration point
includes:
  - letsgo                # core
  - letsgo-voice          # satellite — assumes core is present
  - letsgo-canvas         # satellite — assumes core is present
  - letsgo-browser        # satellite — assumes core is present
```

Satellites never import core. They never depend on each other. They are independent peers that happen to share a common foundation. This means a user can include any combination:

- `letsgo` + `letsgo-voice` — voice only, no browser/canvas overhead
- `letsgo` + `letsgo-mcp` — MCP bridge only
- `letsgo` + all five — the full platform

Each satellite follows the same thin pattern as core. Here is `letsgo-voice`:

```yaml
# voice/bundle.md
---
bundle:
  name: letsgo-voice
  version: 0.1.0
  description: Voice message transcription and TTS for LetsGo channels
includes:
  - bundle: letsgo-voice:behaviors/voice-capabilities
---

# LetsGo Voice

Voice capabilities for the LetsGo gateway — auto-transcribe inbound
audio messages and optionally synthesize text-to-speech responses.

@letsgo-voice:context/voice-awareness.md
```
> **Source:** `voice/bundle.md`

Same structure every time: identity, one behavior include, one context reference. Predictable, scannable, minimal.

---

## 3. Side-by-Side Analysis

Now let's go deep on the five architectural patterns that make this work.

### A. The Thin Bundle Pattern

The thin bundle pattern is a separation of concerns: the `bundle.md` handles **identity and entry point**, while behaviors handle **composition logic**.

Compare the core `bundle.md` (13 lines) to what a monobundle would require. The monobundle version needs 20+ includes, mixed tool/hook/context declarations, and implicit ordering spread across the manifest. The thin version has exactly one include and one context reference. Everything else is delegated.

Why this matters:

- **Readability.** A new contributor opens `bundle.md` and immediately understands the bundle's scope from its description and context file. They don't wade through 50 lines of YAML.
- **Stability.** The manifest almost never changes. New capabilities are added to behaviors, not to the root. This reduces merge conflicts to near zero.
- **Composability.** Other bundles can include `letsgo` without worrying about what's inside. The thin surface area makes it a reliable dependency.

The pattern is recursive. Each satellite bundle is also thin — identity plus one behavior include. And each behavior file is focused on exactly one concern. The result is a tree where complexity is distributed across many small files instead of concentrated in one large one.

### B. Behavior Composition and Dependency Ordering

The master behavior `letsgo-capabilities.yaml` is the most architecturally significant file in the project. It defines the composition order for 14 sub-behaviors organized into three layers.

**Foundation layer** (behaviors 1-4):

```yaml
includes:
  - bundle: letsgo:behaviors/security-policy    # Hook: tool risk classification
  - bundle: letsgo:behaviors/secrets            # Tool: encrypted credential store
  - bundle: letsgo:behaviors/sandbox            # Tool: Docker-isolated execution
  - bundle: letsgo:behaviors/observability      # Hook: telemetry + metrics capability
```

These register core capabilities (`secrets.redeem`, `telemetry.metrics`) that downstream behaviors may query. They have no internal dependencies on each other.

**Memory stack** (behaviors 5-12):

```yaml
includes:
  # Memory system (order matters — capabilities must register before consumers)
  - bundle: letsgo:behaviors/memory-store          # 1. Data layer — registers memory.store
  - bundle: letsgo:behaviors/memory-memorability   # 2. Scoring — before capture
  - bundle: letsgo:behaviors/memory-boundaries     # 3. Boundary detection — before capture
  - bundle: letsgo:behaviors/memory-capture        # 4. Auto-capture from tool:post
  - bundle: letsgo:behaviors/memory-temporal       # 5. Temporal classification
  - bundle: letsgo:behaviors/memory-consolidation  # 6. Decay/boost at session:end
  - bundle: letsgo:behaviors/memory-compression    # 7. Cluster merging at session:end
  - bundle: letsgo:behaviors/memory-inject         # 8. Prompt injection — reads from store last
```

This is the most order-sensitive section. The memory store must register the `memory.store` capability before any other memory behavior can consume it. Memorability scoring and boundary detection must exist before capture runs, because capture uses them to filter and tag observations. Injection comes last because it reads from the fully populated store.

Each behavior is a standalone YAML file with a single hook or tool. For example, `memory-capture.yaml`:

```yaml
# behaviors/memory-capture.yaml
bundle:
  name: behavior-memory-capture
  version: 1.0.0
  description: Auto-capture hook — extracts observations from tool executions

hooks:
  - module: hooks-memory-capture
    source: ../modules/hooks-memory-capture
    config:
      min_content_length: 50
      auto_summarize_interval: 10
```
> **Source:** `behaviors/memory-capture.yaml`

One behavior, one module, one config block. No ambiguity about what it does or what it depends on.

**Application layer** (behaviors 13-14):

```yaml
includes:
  - bundle: letsgo:behaviors/heartbeat    # Proactive cron-scheduled sessions
  - bundle: letsgo:behaviors/gateway      # Multi-channel messaging daemon
```

These are context-only behaviors — they inject awareness documents that teach the agent about gateway and heartbeat capabilities. The actual gateway and heartbeat code runs in a separate daemon process, not as Amplifier modules. The behaviors here exist to give the agent knowledge about those systems, not to load them.

### C. Capability Contracts

Satellites need to use capabilities registered by core (like the memory store or the display system). But satellites don't include core, and they can't assume any particular loading order. How do they find each other?

The answer is **capability contracts** — a documented protocol for runtime capability discovery. LetsGo defines four contracts:

| Capability | Registered By | Required By | Degradation |
|-----------|---------------|-------------|-------------|
| `memory.store` | `tool-memory-store` module | None (optional for all) | Satellites skip memory features |
| `display` | Gateway `DisplaySystem` | `letsgo-canvas` (required) | Canvas fails with clear error |
| `telemetry.metrics` | `hooks-telemetry` module | None (optional for all) | Satellites skip telemetry |
| `secrets.redeem` | `tool-secrets` module | None (optional for all) | Satellites fail with clear error |

> **Source:** `docs/CAPABILITY_CONTRACTS.md`

The contracts document specifies four rules for satellites:

**Rule 1 — Lazy query.** Query capabilities at execution time, not mount time.

```python
# GOOD: query at execution time
async def execute(self, coordinator, ...):
    display = coordinator.get_capability("display")
    if display is None:
        raise ModuleLoadError(
            "letsgo-canvas requires amplifier-bundle-letsgo (core). "
            "Add it to your root bundle's includes."
        )

# BAD: query at mount time
def __init__(self, coordinator, ...):
    self.display = coordinator.get_capability("display")  # may not exist yet!
```

This is the key insight. At mount time, you don't know whether core has been loaded yet. The user might list `letsgo-canvas` before `letsgo` in their includes. By deferring the check to execution time, you guarantee all bundles have had a chance to register their capabilities.

**Rule 2 — Graceful degradation.** If an optional capability is missing, skip the feature and log a debug message. Never crash.

**Rule 3 — Clear error on required.** If a required capability is missing, raise `ModuleLoadError` with an actionable message that tells the user exactly what to add.

**Rule 4 — Never assume ordering.** Satellites don't include the core bundle. The user's root bundle includes both. Capabilities may be registered in any order.

This contract system gives you the benefits of dependency injection without the complexity of a DI framework. Satellites declare what they need, core registers what it provides, and the coordinator mediates at runtime.

### D. Pure Composition Bundles

`letsgo-browser` is the most instructive satellite because it has **zero Python code**. No tools, no hooks, no modules. It is pure composition:

```yaml
# browser/bundle.md
---
bundle:
  name: letsgo-browser
  version: 0.1.0
  description: Browser automation for LetsGo — general browsing, research,
               visual documentation, and gateway-specific workflows
includes:
  - amplifier-bundle-browser-tester                        # external bundle
  - bundle: letsgo-browser:behaviors/browser-capabilities  # local behavior
---

# LetsGo Browser

Browser automation capabilities for the LetsGo gateway — composes the
browser-tester bundle for general web automation with gateway-specific
context and skills.

@letsgo-browser:context/browser-awareness.md
```
> **Source:** `browser/bundle.md`

The browser behavior is equally minimal:

```yaml
# browser/behaviors/browser-capabilities.yaml
bundle:
  name: behavior-browser-capabilities
  version: 1.0.0
  description: Browser automation capabilities for LetsGo gateway

context:
  include:
    - letsgo-browser:context/browser-awareness.md
```
> **Source:** `browser/behaviors/browser-capabilities.yaml`

That is it. Eight lines of YAML. The behavior includes a single context file — an awareness document that teaches the agent how to use browser capabilities within the LetsGo gateway context.

What `letsgo-browser` actually does:

1. **Includes** `amplifier-bundle-browser-tester` — an external bundle that provides three agents (browser-operator, browser-researcher, visual-documenter) and a CLI tool.
2. **Adds** gateway-specific context — how to use browser automation within the LetsGo messaging context.

That's it. No wrapping code, no adapter layer, no glue logic. The capability contracts document confirms this explicitly:

> `letsgo-browser` does not register any capabilities [...] Demonstrates that a satellite can add value purely through context, skills, and bundle composition without registering any new capabilities on the coordinator.

This is the purest expression of the thin bundle philosophy. If an existing bundle provides the functionality you need, your satellite's job is just to compose it with the right context for your domain. Not every bundle needs to contain code.

### E. Plugin Architecture for the Gateway

The gateway is LetsGo's multi-channel messaging daemon — it bridges external platforms (WhatsApp, Telegram, Discord, Slack, webhooks) to Amplifier sessions. Channel adapters are how new platforms get added.

Critically, channel adapters are **gateway plugins, not Amplifier modules**. They run in the daemon process, not in the Amplifier session. This distinction matters: Amplifier modules participate in the session lifecycle (hooks, tools, capabilities), while gateway plugins participate in the HTTP/WebSocket lifecycle (message routing, authentication, channel management).

The plugin discovery system in `registry.py` uses a two-tier approach:

```python
# gateway/letsgo_gateway/channels/registry.py

# Built-in channels: name -> fully-qualified class path
# Webhook and WhatsApp have no optional deps (always available).
# Telegram, Discord, Slack require optional SDK packages.
_BUILTINS: dict[str, str] = {
    "webhook": "letsgo_gateway.channels.webhook.WebhookChannel",
    "whatsapp": "letsgo_gateway.channels.whatsapp.WhatsAppChannel",
    "telegram": "letsgo_gateway.channels.telegram.TelegramChannel",
    "discord": "letsgo_gateway.channels.discord.DiscordChannel",
    "slack": "letsgo_gateway.channels.slack.SlackChannel",
}


def _lazy_import(dotpath: str) -> type[ChannelAdapter]:
    """Import a class by its fully-qualified dotted path."""
    module_path, class_name = dotpath.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def discover_channels() -> dict[str, type[ChannelAdapter]]:
    """Discover channel adapters from built-ins + entry points."""
    channels: dict[str, type[ChannelAdapter]] = {}

    # 1. Built-in channels (lazy import, graceful degradation)
    for name, dotpath in _BUILTINS.items():
        try:
            channels[name] = _lazy_import(dotpath)
        except ImportError:
            logger.debug("Channel '%s' SDK not installed — skipping", name)

    # 2. Entry-point channels (group="letsgo.channels")
    for ep in entry_points(group="letsgo.channels"):
        try:
            channels[ep.name] = ep.load()
        except Exception:
            logger.warning(
                "Failed to load channel plugin '%s' from entry point",
                ep.name,
                exc_info=True,
            )

    return channels
```
> **Source:** `gateway/letsgo_gateway/channels/registry.py`

The design has two tiers of discovery:

**Tier 1: Built-in channels with lazy imports.** Five channels are built-in but not eagerly loaded. Each is a dotted path string, resolved only when `discover_channels()` runs. If a channel's SDK package isn't installed (e.g., `python-telegram-bot` for Telegram), the import fails gracefully with a debug log. The gateway starts without it. This means you can install only the SDKs you need — a WhatsApp-only deployment doesn't pull in the Discord SDK.

**Tier 2: Entry-point plugins.** Third-party packages can register channel adapters via Python's standard `entry_points` mechanism under the `letsgo.channels` group. A custom channel adapter package would declare:

```toml
# In a third-party package's pyproject.toml
[project.entry-points."letsgo.channels"]
my_custom_channel = "my_package.channels:MyCustomChannel"
```

Entry-point plugins override built-ins with the same name. This allows replacing a built-in implementation without forking the gateway.

The pattern is deliberately simple — no plugin registry service, no configuration-driven loading, no abstract factory. Just lazy imports for known channels and standard Python entry points for unknown ones. The `discover_channels()` function is called once at gateway startup, returns a flat dictionary, and that's it.

---

## 4. Patterns You Can Reuse

Seven architectural rules emerge from the LetsGo design. These are not LetsGo-specific — they apply to any Amplifier project that outgrows a single bundle.

### Pattern 1: Family over monobundle

**Decompose by capability domain.** If your project has distinct capability areas (security, memory, messaging, browser automation), each one becomes its own bundle. The threshold is roughly five or six behaviors — below that, a single bundle is fine.

The LetsGo family has six bundles, each with a clear domain boundary. No bundle crosses domains. Voice doesn't know about canvas. Browser doesn't know about MCP. The core doesn't know about any satellite.

### Pattern 2: Thin root, thick behaviors

**Keep `bundle.md` minimal. Move all composition logic into behaviors.**

The root manifest should contain identity (name, version, description), one master behavior include, and one context reference. That's it. If your `bundle.md` has more than 20 lines of YAML, you're putting too much in it.

The master behavior (`letsgo-capabilities.yaml`) is where the composition lives. It includes sub-behaviors in dependency order, with comments explaining the ordering rationale. This file is the architectural spine — readable top-to-bottom as a capability manifest.

### Pattern 3: Satellites as peers

**No parent-child coupling. The user's bundle is the integration point.**

Satellites never include core. Core never includes satellites. Both are included by the user's root bundle. This means:

- Satellites can be added or removed without modifying core.
- Satellites can't break core (they have no access to its internals).
- Users compose exactly the combination they need.
- Satellite development is fully independent — different teams, different repos, different release cycles.

### Pattern 4: Capability contracts over imports

**Satellites check capabilities at execution time, not mount time.**

Instead of importing from core or requiring a specific loading order, satellites query the coordinator for named capabilities at the moment they need them. This creates a contract boundary that is:

- **Documented** — the `CAPABILITY_CONTRACTS.md` file lists every capability, who registers it, who consumes it, and what happens when it's missing.
- **Runtime-checked** — no compile-time or mount-time coupling.
- **Order-independent** — doesn't matter which bundle loads first.

### Pattern 5: Lazy checks for ordering resilience

**Don't fail at mount time. Gracefully degrade at execution time.**

This is a corollary of Pattern 4. If a satellite checks for a capability in its constructor, it will fail whenever it happens to load before core. By deferring the check to `execute()`, you get ordering resilience for free. The satellite works regardless of include order in the user's root bundle.

For optional capabilities, the degradation is silent — skip the feature, log at debug level, continue. For required capabilities, the error message is actionable — it tells the user exactly which bundle to add.

### Pattern 6: Plugin discovery for extensibility

**Use Python entry points for open-ended extension.**

When you have an interface that third parties should be able to implement (like channel adapters), use the standard `entry_points` mechanism. The pattern is:

1. Define a built-in registry with lazy imports.
2. Overlay entry-point discoveries on top.
3. Entry points can override built-ins.
4. Fail gracefully on missing SDKs.

This is standard Python packaging — no custom plugin framework, no configuration files, no service locator. Third parties just declare an entry point in their `pyproject.toml` and the gateway finds it automatically.

Note the scope boundary: this plugin mechanism is for the gateway daemon, not for Amplifier sessions. Amplifier has its own module system for session-level extensibility (tools, hooks, capabilities). Gateway plugins live in a different process with a different lifecycle.

### Pattern 7: Pure composition as a valid pattern

**Sometimes wrapping an existing bundle with context is all you need.**

`letsgo-browser` proves that a bundle with zero Python code can still provide real value. It composes an external bundle (`amplifier-bundle-browser-tester`) with gateway-specific context. The context teaches the agent how to use browser capabilities within the LetsGo messaging paradigm.

This is the most radical application of the thin bundle philosophy. If someone else has built the tool, your job is not to rebuild it — it's to compose it with the right context for your users. Context is a first-class architectural material in Amplifier, not an afterthought.

---

## Quick Reference: The LetsGo File Map

```
amplifier-bundle-letsgo/
├── bundle.md                          # Thin root — identity + 1 include + 1 context
├── behaviors/
│   ├── letsgo-capabilities.yaml       # Master behavior — 14 sub-behaviors in order
│   ├── security-policy.yaml           # Hook: tool risk classification
│   ├── secrets.yaml                   # Tool: encrypted credential store
│   ├── sandbox.yaml                   # Tool: Docker-isolated execution
│   ├── observability.yaml             # Hook: telemetry + metrics
│   ├── memory-store.yaml              # Tool: durable memory (registers memory.store)
│   ├── memory-memorability.yaml       # Hook: selective encoding scoring
│   ├── memory-boundaries.yaml         # Hook: event segmentation
│   ├── memory-capture.yaml            # Hook: auto-extract from tool results
│   ├── memory-temporal.yaml           # Hook: multi-scale retrieval
│   ├── memory-consolidation.yaml      # Hook: decay/boost cycle
│   ├── memory-compression.yaml        # Hook: cluster and merge
│   ├── memory-inject.yaml             # Hook: prompt injection from store
│   ├── heartbeat.yaml                 # Context: proactive session awareness
│   ├── gateway.yaml                   # Context: messaging daemon awareness
│   └── skills.yaml                    # Context: domain expertise packages
├── context/                           # Awareness docs injected into agent context
├── modules/                           # Python modules (hooks + tools)
├── gateway/                           # Daemon process — channels, routing, cron
│   └── letsgo_gateway/channels/
│       └── registry.py                # Plugin discovery: built-ins + entry points
├── voice/                             # Satellite: transcription + TTS
│   ├── bundle.md                      #   Thin root
│   └── behaviors/
├── canvas/                            # Satellite: visual workspace
│   ├── bundle.md                      #   Thin root
│   └── behaviors/
├── browser/                           # Satellite: pure composition (zero Python)
│   ├── bundle.md                      #   Thin root — includes browser-tester
│   └── behaviors/
├── webchat/                           # Satellite: chat UI + admin dashboard
│   ├── bundle.md                      #   Thin root
│   └── behaviors/
├── mcp/                               # Satellite: MCP server bridge
│   ├── bundle.md                      #   Thin root
│   └── behaviors/
└── docs/
    └── CAPABILITY_CONTRACTS.md        # The 4 capability contracts
```

---

## Summary

The LetsGo architecture demonstrates that large Amplifier projects don't need to be large bundles. By decomposing along capability domain boundaries, keeping manifests thin, treating satellites as peers, and using capability contracts for loose coupling, you get a system where:

- Each piece can be understood, tested, and developed independently.
- Users compose exactly the capabilities they need.
- Contributors own clear domains without stepping on each other.
- New capabilities (like a future `letsgo-email` satellite) can be added without modifying any existing bundle.

The seven patterns — family decomposition, thin roots, peer satellites, capability contracts, lazy checks, plugin discovery, and pure composition — are not specific to LetsGo. They are structural patterns for any Amplifier project that has outgrown its first bundle.

Start with one bundle. When it gets uncomfortable, decompose into a family. The LetsGo architecture shows you how.