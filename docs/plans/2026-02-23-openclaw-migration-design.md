# OpenClaw → LetsGo Migration Design

## Goal

Achieve full capability parity between OpenClaw (standalone AI assistant platform) and LetsGo (Amplifier bundle family), migrating all remaining OpenClaw capabilities into the Amplifier ecosystem following Amplifier-native architecture patterns.

## Background

OpenClaw is a standalone AI assistant platform with capabilities spanning voice, canvas rendering, browser automation, MCP integration, web chat with admin dashboard, and a rich library of skills. LetsGo already exists as an Amplifier bundle providing security, secrets, sandboxing, observability, memory, a gateway daemon with channel adapters, onboarding, and agents. This design covers migrating all remaining OpenClaw capabilities into the Amplifier ecosystem as a composable family of bundles.

## Approach

**Vertical Slices** — Design the bundle family structure and contracts now, then build each bundle as a complete vertical slice, fully functional and shippable on its own. Eight phases, each independently valuable.

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Migration boundary | Full parity | Port everything possible into Amplifier-native constructs |
| Bundle structure | Family of bundles (not monobundle) | Composable, independent deps, follows superpowers pattern |
| Native companion apps | Deferred | Huge separate effort, not deliverable as bundles |
| Onboarding | Recipe-driven (future: `amplifier onboard` CLI) | Recipes are the source of truth; CLI is a thin entry point later |
| Skill migration | Gene transfer + rewrite from scratch | Build reusable migration tool; OpenClaw skills as DNA, Amplifier-native output |
| MCP | Consumer + builder, gene transfer from OpenClaw + Anthropic | Best of both sources, Amplifier experts determine integration |
| Browser | Hybrid — compose browser-tester + thin Playwright module | General browsing via existing bundle, gateway-specific needs via Playwright |
| Voice | Channel-level voice messages (no standalone mic) | Practical without native apps; transcribe in, TTS out through messaging |
| Canvas | tool-canvas + DisplaySystem + CanvasChannel gateway plugin | Three-layer architecture validated by Amplifier experts; uses existing DisplaySystem protocol |
| WebChat | Full admin dashboard + chat interface | Parity with OpenClaw's Control UI |
| Channel adapters | Gateway plugins with Python entry-point discovery | NOT Amplifier modules (don't fit 5 module types); validated by both Amplifier expert and Foundation expert |
| Composition model | Peer bundles, user's root bundle as integration point | Satellites don't include core; flat merge into single AmplifierSession |

## Bundle Family Map

### Core: `amplifier-bundle-letsgo` (exists today)

```
amplifier-bundle-letsgo (CORE)
├── Security & tool policy (4-tier risk classification, audit trail)
├── Encrypted secrets (Fernet AES-128-CBC, handle-based access)
├── Sandboxed execution (Docker, 512MB/1CPU/120s limits)
├── Observability & telemetry (7-event pipeline, JSONL logs)
├── Memory system (8-module bio-inspired pipeline)
├── Gateway daemon
│   ├── ChannelAdapter ABC + entry-point discovery (NEW)
│   ├── Built-in channels: Webhook, Discord, Telegram, Slack, WhatsApp
│   ├── Plugin channels: Signal, iMessage, Teams, Matrix, LINE,
│   │   Google Chat, Nostr, IRC, Mattermost, Twitch, Feishu
│   ├── PairingStore, SessionRouter, CronScheduler
│   ├── HeartbeatEngine
│   └── DisplaySystem protocol (NEW)
├── Onboarding recipes (enhanced — 4-stage wizard)
├── Skills (20 existing + ~32 migrated)
├── Skill migration tool (NEW)
└── Agents, modes, recipes (existing)
```

### Satellite: `amplifier-bundle-letsgo-voice` (NEW)

```
amplifier-bundle-letsgo-voice/
├── bundle.md
├── behaviors/voice-capabilities.yaml
├── modules/
│   ├── tool-media-pipeline/          # Transcription + TTS
│   └── hooks-voice-message/          # Auto-transcribe inbound voice
├── context/voice-awareness.md
├── agents/voice-specialist.md
└── skills/voice-config/
```

**How it works:** Gateway downloads inbound audio → hooks-voice-message detects audio → calls tool-media-pipeline.transcribe() → injects text into context → agent responds → (optional) TTS synthesis → gateway sends audio back via channel's native voice message.

TTS providers: ElevenLabs (cloud), edge-tts (free), OpenAI TTS (cloud), local whisper (free).

### Satellite: `amplifier-bundle-letsgo-canvas` (NEW)

```
amplifier-bundle-letsgo-canvas/
├── bundle.md
├── behaviors/canvas-capabilities.yaml
├── modules/
│   ├── tool-canvas/                  # Layer 1: Agent calls canvas_push()
│   └── hooks-canvas-autorender/      # Auto-visualize tool outputs
├── gateway-plugin/
│   └── letsgo_channel_canvas/        # Layer 3: CanvasChannel adapter
│       ├── adapter.py                # WebSocket push, serves /canvas
│       └── static/                   # HTML + JS canvas UI
├── context/canvas-awareness.md
└── skills/canvas-design/
```

**Three-layer architecture (validated by Amplifier experts):**

1. `tool-canvas` (Tool module) — Agent calls `canvas_push(content_type, content)`. Knows nothing about WebSockets or rendering. Routes through DisplaySystem protocol.
2. Gateway DisplaySystem (Protocol boundary) — Routes content to appropriate surfaces. Decides format per channel.
3. CanvasChannel adapter (Gateway plugin) — Serves `localhost:8080/canvas` with WebSocket push. Just another channel alongside Discord/Telegram.

Content types: chart (Vega-Lite), html, svg, markdown, code, table, form (future).

Auto-render hook: Observes any tool output on `tool:post`, detects renderable patterns (CSV, JSON, tables), pushes auto-visualization. Transparent to agent.

Heartbeat integration: Add `"canvas"` to `heartbeat_channels` in config. Works because heartbeat sessions are identical to user sessions.

### Satellite: `amplifier-bundle-letsgo-browser` (NEW)

```
amplifier-bundle-letsgo-browser/
├── bundle.md
│   └── includes: amplifier-bundle-browser-tester
├── behaviors/browser-capabilities.yaml
├── modules/
│   └── tool-browser-playwright/      # Thin, gateway-specific
│       └── qr_scanner.py, web_auth.py
├── context/browser-awareness.md
└── skills/browser-workflows/
```

Mostly composition — includes existing `browser-tester` bundle for general browsing. Adds thin Playwright module for WhatsApp QR scanning and channel web auth flows during onboarding.

### Satellite: `amplifier-bundle-letsgo-webchat` (NEW)

```
amplifier-bundle-letsgo-webchat/
├── bundle.md
├── behaviors/webchat-capabilities.yaml
├── gateway-plugin/
│   └── letsgo_channel_webchat/
│       ├── adapter.py                # WebChatChannel
│       ├── admin.py                  # Admin dashboard routes
│       └── static/
│           ├── chat/                 # Chat interface
│           └── admin/                # Dashboard views
│               ├── sessions, channels, cron, usage, agents, pairing
├── context/webchat-awareness.md
└── agents/admin-assistant.md
```

WebChat is a channel adapter. Admin dashboard shares the web server. Dashboard views: sessions, channel status, cron/heartbeat, usage analytics, agent management, sender pairing/config.

### Satellite: `amplifier-bundle-letsgo-mcp` (NEW)

```
amplifier-bundle-letsgo-mcp/
├── bundle.md
├── behaviors/mcp-capabilities.yaml
├── modules/
│   └── tool-mcp-client/
│       ├── discovery.py              # Find + connect to MCP servers
│       ├── bridge.py                 # MCP tools → Amplifier tool calls
│       └── config.py                 # MCP server registry
├── context/mcp-awareness.md
├── skills/mcp-builder/
└── agents/mcp-specialist.md
```

MCP bridging: Reads configured MCP servers → connects via stdio/SSE → reads tool schemas → registers as bridged Amplifier tool calls → agent calls bridged tool → translates to MCP protocol → returns result as ToolResult.

Gene transfer from OpenClaw's mcporter (transport, lifecycle, error handling) and Anthropic's mcp-builder skill (creation patterns, best practices).

## Bundle Family Namespace Registry

| Bundle | `bundle.name` | Namespace | PyPI Package |
|--------|---------------|-----------|--------------|
| Core | `letsgo` | `letsgo:` | `amplifier-bundle-letsgo` |
| Voice | `letsgo-voice` | `letsgo-voice:` | `amplifier-bundle-letsgo-voice` |
| Canvas | `letsgo-canvas` | `letsgo-canvas:` | `amplifier-bundle-letsgo-canvas` |
| Browser | `letsgo-browser` | `letsgo-browser:` | `amplifier-bundle-letsgo-browser` |
| WebChat | `letsgo-webchat` | `letsgo-webchat:` | `amplifier-bundle-letsgo-webchat` |
| MCP | `letsgo-mcp` | `letsgo-mcp:` | `amplifier-bundle-letsgo-mcp` |

## Composition Model

**Peer composition, not parent-child.** The user's root bundle includes whichever bundles they want:

```yaml
# User's bundle.md
includes:
  - amplifier-bundle-letsgo           # Core (required)
  - amplifier-bundle-letsgo-voice     # Optional
  - amplifier-bundle-letsgo-canvas    # Optional
  - amplifier-bundle-letsgo-webchat   # Optional
```

All bundles merge into a single `AmplifierSession`. Canvas can use memory, voice can fire telemetry — because bundle boundaries dissolve at mount time.

**Satellites do NOT include the core.** They assume it's present because the user's root bundle includes both. This avoids duplicate loading.

**Validated by Amplifier experts.** This matches how `amplifier-foundation` and `amplifier-bundle-recipes` compose — the user's root bundle is the integration point.

### Runtime Safety

**Capability checks:** Each satellite module validates required capabilities at mount time with clear error messages:

```python
async def mount(coordinator):
    memory_store = coordinator.get_capability("memory.store")
    if memory_store is None:
        raise ModuleLoadError(
            "letsgo-voice requires amplifier-bundle-letsgo (core). "
            "Add it to your root bundle's includes."
        )
```

**Lazy resolution:** Satellites query capabilities at execution time, not mount time. This makes them ordering-resilient — doesn't matter if user puts `letsgo-voice` before `letsgo` in their includes.

## Gateway Plugin Architecture

### Current State (hardcoded)

`daemon.py` has `_CHANNEL_CLASSES` dict and `_STUB_CHANNELS` set. Channels are statically registered.

### Target State (entry-point discovery)

```python
# gateway/letsgo_gateway/channels/registry.py
def discover_channels() -> dict[str, type[ChannelAdapter]]:
    """Discover channel adapters from built-ins + entry points."""
    channels = {}
    # 1. Built-in channels (lazy import, graceful degradation)
    for name, dotpath in _BUILTINS.items():
        try:
            channels[name] = lazy_import(dotpath)
        except ImportError:
            logger.debug("Channel '%s' SDK not installed — skipping", name)
    # 2. Entry-point channels (group="letsgo.channels")
    for ep in importlib.metadata.entry_points(group="letsgo.channels"):
        channels[ep.name] = ep.load()
    return channels
```

### Channel Plugin Package Structure

```
channels/{name}/
├── pyproject.toml                    # depends on: letsgo-gateway, {sdk}
└── letsgo_channel_{name}/
    ├── __init__.py                   # exports {Name}Channel
    └── adapter.py                    # {Name}Channel(ChannelAdapter)
```

Entry point registration:

```toml
[project.entry-points."letsgo.channels"]
signal = "letsgo_channel_signal:SignalChannel"
```

### Dependency Story

```bash
pip install letsgo-gateway                         # Webhook only
pip install letsgo-gateway[discord,telegram]        # Pick what you need
pip install letsgo-gateway[all-channels]            # Everything
```

Onboarding recipe handles all installation — users never see pip commands.

### Channel Adapter Inventory

| Channel | Type | SDK | Priority |
|---------|------|-----|----------|
| Webhook | Built-in (core) | aiohttp (already present) | Exists |
| Discord | Built-in (optional dep) | discord.py | Exists |
| Telegram | Built-in (optional dep) | python-telegram-bot | Exists |
| Slack | Built-in (optional dep) | slack-sdk | Exists |
| WhatsApp | Built-in (optional dep) | whatsapp-web.js bridge | Exists |
| Canvas | Gateway plugin (from letsgo-canvas) | aiohttp + WebSocket | Phase 3 |
| WebChat | Gateway plugin (from letsgo-webchat) | aiohttp + WebSocket | Phase 5 |
| Signal | Separate package | signal-protocol / signal-cli | Phase 1 |
| Matrix | Separate package | matrix-nio | Phase 1 |
| Teams | Separate package | botbuilder-core | Phase 1 |
| LINE | Separate package | line-bot-sdk | Phase 7 |
| Google Chat | Separate package | google-api-python-client | Phase 7 |
| iMessage | Separate package | platform-specific | Phase 7 |
| Nostr | Separate package | nostr-sdk | Phase 7 |
| IRC | Separate package | irc3 or similar | Phase 7 |
| Mattermost | Separate package | mattermostdriver | Phase 7 |
| Twitch | Separate package | twitchio | Phase 7 |
| Feishu | Separate package | feishu-sdk | Phase 7 |

## Onboarding Experience

### Recipe: `letsgo:recipes/onboarding.yaml` (enhanced 4-stage)

**Stage 1: Welcome & Provider Setup**
- Detect existing config (fresh install vs returning user)
- AI provider selection (Anthropic / OpenAI / Azure / Ollama / Other)
- Store API key via tool-secrets (Fernet encrypted)
- Test provider connection
- Approval gate

**Stage 2: Channel Selection & Installation**
- Present available channels
- Install channel dependencies (pip install, transparent to user)
- Per-channel configuration (bot tokens, QR codes, phone numbers)
- Store credentials in secrets
- Test each channel connection + send test message
- Sender pairing setup
- Approval gate

**Stage 3: Satellite Bundle Selection**
- Present optional capabilities (Voice, Canvas, WebChat, Browser, MCP)
- Install selected bundles (pip install, transparent to user)
- Update user's bundle.md (add includes, with approval gate)
- Bundle-specific config (TTS provider, canvas port, admin password)

**Stage 4: Daemon & Heartbeat**
- Install gateway daemon (launchd on macOS, systemd on Linux)
- Configure heartbeat schedule and channels (optional)
- Start daemon + verify everything works
- Send welcome message through all configured channels
- Approval gate

**Design principles:** Secrets-first (all creds encrypted), test-as-you-go (each channel tested immediately), approval gates between stages, idempotent (re-run detects existing config), future `amplifier onboard` CLI simply discovers and executes this recipe.

## Skill Migration Tool

### What it is

A skill + recipe that reads OpenClaw TypeScript skills and generates Amplifier-native SKILL.md skeletons.

### Translation process

1. **Parse source** — Read OpenClaw SKILL.md (instructions), index.ts (tool schemas, APIs), config.json (parameters)
2. **Gene transfer (LLM-powered)** — Map OC tool definitions → Amplifier tool invocations, map config → secrets + env vars, preserve core instructions/workflows, adapt platform references, discard OC internals
3. **Generate skeleton** — Write SKILL.md with frontmatter, companion scripts for API integrations, flag areas needing manual review
4. **Validate** — Check Amplifier skills spec compliance, verify no OC references remain, test load_skill() works

### Delivered as

- `skills/skill-migrator/SKILL.md` — Teaches agents the translation process
- `recipes/skill-migration.yaml` — Automates batch migration with review gates

### Priority skills to migrate

| Priority | Skills |
|----------|--------|
| High | GitHub, Notion, 1Password, Obsidian, Apple Reminders |
| Medium | Spotify, Weather, Apple Notes, Google Calendar |
| Lower | Coding agent, Discord-specific, Slack-specific |

## Capability Contracts (Phase 0)

Capabilities registered by letsgo-core that satellites may depend on:

| Capability | Registered By | Required/Optional for Satellites |
|------------|---------------|----------------------------------|
| `memory.store` | tool-memory-store | Optional (graceful degradation) |
| `display` | gateway DisplaySystem | Required by letsgo-canvas |
| `telemetry.metrics` | hooks-telemetry | Optional |
| `secrets.redeem` | tool-secrets | Optional |

Satellite rules:
- Query capabilities lazily (execution time, not mount time)
- Gracefully degrade if optional capabilities missing
- Fail with clear error if required capabilities missing

## Implementation Phases

| Phase | What Ships | Key Deliverables |
|-------|-----------|-----------------|
| **0** | Shared foundation | Capability contracts doc, gateway entry-point plugin system, DisplaySystem protocol, enhanced onboarding recipe, skill migration tool, namespace registry |
| **1** | Gateway hardening | Entry-point discovery live, extract existing channels to optional deps, add Signal + Matrix + Teams channels, enhanced onboarding with channel install |
| **2** | `letsgo-voice` | tool-media-pipeline, hooks-voice-message, TTS provider abstraction, voice across all channels |
| **3** | `letsgo-canvas` | tool-canvas, hooks-canvas-autorender, CanvasChannel adapter, web UI at /canvas |
| **4** | `letsgo-browser` | Compose browser-tester + thin Playwright module for gateway-specific needs |
| **5** | `letsgo-webchat` | WebChatChannel adapter, admin dashboard (sessions, channels, cron, usage, agents, pairing) |
| **6** | Skill migration | Run skill translator on ~32 OpenClaw skills, manual review + refinement |
| **7** | `letsgo-mcp` + remaining | MCP client/consumer, Gmail triggers, remaining channel plugins (LINE, Google Chat, iMessage, Nostr, IRC, Mattermost, Twitch, Feishu) |

Each phase is independently shippable. Each phase validates architectural decisions for the next.

## Architecture Patterns

The design follows these patterns observed in `amplifier-bundle-superpowers`:

| Pattern | Application |
|---------|-------------|
| Thin bundle | Root bundle.md has includes + docs only; behavior does heavy lifting |
| Single root behavior | Each satellite has one behavior YAML composing all its tools/hooks/agents/context |
| Zero local modules (where possible) | Satellite modules referenced via git+https://; channel plugins are pip packages |
| Agent = markdown + frontmatter | meta.name + meta.description (with examples) + tools: + markdown body |
| Context layering | Philosophy → Instructions → Depth → Integration, injected at appropriate scopes |
| Namespace-scoped references | `@letsgo:` for core, `@letsgo-voice:` for satellites |
| Runtime capability checks | Satellites validate core capabilities at mount time |
| Lazy resolution | Query capabilities at execution time for ordering resilience |

## What's NOT In Scope

| Capability | Why Deferred |
|------------|-------------|
| Native companion apps (macOS/iOS/Android) | Fundamentally different artifacts; separate design process |
| Always-on Voice Wake / Talk Mode | Requires native app or standalone audio service |
| Skill registry / marketplace (ClawHub equivalent) | Future ecosystem concern; Amplifier's skill system handles discovery for now |
| Custom orchestrator for Canvas | Standard orchestrator works; canvas is just tool calls. Custom orchestrator only if needed later |

---

*This design was validated through consultation with Amplifier Expert (amplifier:amplifier-expert), Core Expert (core:core-expert), and Foundation Expert (foundation:foundation-expert) during the brainstorming process.*
