# LetsGo Capabilities

You have enhanced capabilities provided by the LetsGo bundle. Use them appropriately.

## Getting Started

**New user?** Type `/letsgo-init` to run the interactive setup wizard. It will walk you through provider configuration, channel selection, satellite bundle installation, and gateway startup — all in one guided flow.

## The LetsGo Ecosystem

LetsGo is a family of composable bundles. The **core** bundle provides security, memory, observability, and the gateway. **Satellite bundles** add optional capabilities — voice, canvas, webchat, browser automation, and MCP integration. You only install what you need.

### Core Capabilities (always available)

| Capability | Type | Purpose |
|------------|------|---------|
| Tool Policy | Hook | 4-tier risk classification, command/path allowlists, careful mode, automation mode |
| Secrets | Tool | Fernet-encrypted credential storage with handle-based access and 5-minute TTL |
| Sandbox | Tool | Docker-first isolated execution with resource limits and network isolation |
| Telemetry | Hook | 7-event session telemetry — tool latency, token usage, error rates, JSONL logs |
| Memory | Hook+Tool | Bio-inspired 8-module pipeline — capture, score, consolidate, compress, inject |
| Gateway | Application | Multi-channel messaging daemon with 13 channel adapters, sender pairing, cron scheduling |
| Heartbeat | Application | Proactive scheduled sessions — CronScheduler fires HeartbeatEngine per agent |
| Modes | Runtime | Careful mode (approval gates), Automation mode (restricted profile), LetsGo Init (onboarding) |
| Skills | Knowledge | 21 domain expertise packages across document, creative, developer, communication, and operations categories |

### Optional Capabilities (activate by installing dependencies)

All capabilities are included in the bundle. They activate when their pip dependencies are installed — the setup wizard handles this, or install manually:

| Capability | What It Adds | Activate |
|-----------|-------------|----------|
| **Voice** | Transcription (Whisper) + TTS (ElevenLabs, edge-tts, OpenAI) across all channels | `pip install amplifier-module-tool-media-pipeline` |
| **Canvas** | Visual workspace — charts, HTML, SVG, code — at localhost:8080/canvas with WebSocket push | `pip install letsgo-channel-canvas` |
| **WebChat** | Web chat + 6-tab admin dashboard (sessions, channels, senders, cron, usage, agents) | `pip install letsgo-channel-webchat` |
| **Browser** | 3 browser agents (operator, researcher, visual-documenter) + gateway skills | `npm install -g agent-browser` |
| **MCP** | Bridge to external MCP tool servers via stdio or Streamable HTTP | `pip install amplifier-module-tool-mcp-client` |

No separate bundles needed. One `amplifier-bundle-letsgo` includes everything. The `/letsgo-init` wizard handles dependency installation.

### Gateway Channels (13 adapters)

The gateway supports 13 messaging platforms via a pluggable adapter system:

| Channel | Type | Install |
|---------|------|---------|
| Webhook | Built-in | Always available |
| WhatsApp | Built-in | Always available |
| Telegram | Built-in (optional dep) | `pip install letsgo-gateway[telegram]` |
| Discord | Built-in (optional dep) | `pip install letsgo-gateway[discord]` |
| Slack | Built-in (optional dep) | `pip install letsgo-gateway[slack]` |
| Signal | Plugin | `pip install letsgo-channel-signal` |
| Matrix | Plugin | `pip install letsgo-channel-matrix` |
| Teams | Plugin | `pip install letsgo-channel-teams` |
| LINE | Plugin | `pip install letsgo-channel-line[sdk]` |
| Google Chat | Plugin | `pip install letsgo-channel-googlechat[sdk]` |
| iMessage | Plugin | `pip install letsgo-channel-imessage` (macOS only) |
| Nostr | Plugin | `pip install letsgo-channel-nostr[sdk]` |
| IRC | Plugin | `pip install letsgo-channel-irc[sdk]` |
| Mattermost | Plugin | `pip install letsgo-channel-mattermost[sdk]` |
| Twitch | Plugin | `pip install letsgo-channel-twitch[sdk]` |
| Feishu | Plugin | `pip install letsgo-channel-feishu[sdk]` |

The `/letsgo-init` command handles channel selection, installation, credential storage, and connection testing.

## Behavioral Guidelines

- **High-risk tools** (bash, write_file) are auto-allowed by default. Enable `careful_mode` for approval prompts.
- **Secrets** must always go through `tool-secrets` — never store credentials in plain text.
- **Untrusted code** should be executed inside the sandbox when available.
- **Telemetry** runs silently in the background.

## Memory System

LetsGo includes a bio-inspired memory system. The `memory` tool provides durable
storage with scored retrieval, structured facts, and TTL-based expiry. Several
background hooks handle automatic capture, memorability filtering, consolidation,
compression, and injection — these run without explicit invocation.

For complex multi-criteria retrieval, maintenance, or memory health analysis,
delegate to `letsgo:memory-curator`.

## Gateway

The gateway is a multi-channel messaging daemon that bridges 13 external messaging
platforms to Amplifier sessions. It handles sender pairing, message routing, voice
transcription (if letsgo-voice is installed), and cron-based scheduled automation.

Type `/letsgo-init` to configure the gateway, or run the `setup-wizard` recipe directly.

### Heartbeat Engine

The heartbeat is a proactive session engine built into the gateway daemon:

- **Cron-scheduled**: CronScheduler fires `HeartbeatEngine.run_all()` on a configurable schedule
- **Per-agent prompts**: Each agent's heartbeat prompt is defined in `context/heartbeat/agents/{id}.md`
- **Full Amplifier sessions**: Each heartbeat creates a real session — all memory hooks fire, all tools available
- **Channel routing**: Heartbeat responses are routed to configured channels

## Specialist Agents

| Agent | Domain |
|-------|--------|
| `letsgo:gateway-operator` | Channel config, sender pairing, cron scheduling, gateway diagnostics |
| `letsgo:memory-curator` | Complex memory retrieval, health analysis, consolidation oversight |
| `letsgo:security-reviewer` | Tool policy review, risk classification, allowlist management |
| `letsgo:creative-specialist` | Orchestrates 6 creative skills (canvas-design, algorithmic-art, brand-guidelines, frontend-design, theme-factory, slack-gif-creator) |
| `letsgo:document-specialist` | Orchestrates 4 document skills (docx, pdf, pptx, xlsx) |

## Skills (21)

| Category | Skills |
|----------|--------|
| Document | docx, pdf, pptx, xlsx |
| Creative | algorithmic-art, brand-guidelines, canvas-design, frontend-design, slack-gif-creator, theme-factory |
| Developer | mcp-builder, web-artifacts-builder, webapp-testing |
| Communication | doc-coauthoring, internal-comms |
| Operations | agent-browser, imagegen, schedule, send-user-message, skill-creator, skill-migrator |

Use `load_skill(skill_name="...")` to load any skill on demand.

## Modes

- **Careful mode** — Approval gates on high-risk tool calls
- **Automation mode** — Restricted profile for unattended operation
- **LetsGo Init** — Interactive setup wizard for first-run configuration (`/letsgo-init`)
