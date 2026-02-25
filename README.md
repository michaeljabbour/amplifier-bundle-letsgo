# LetsGo

A personal AI assistant platform for [Amplifier](https://github.com/microsoft/amplifier) — security, memory, multi-channel messaging, voice, visual canvas, admin dashboard, browser automation, and MCP integration, all composable and configurable through a single onboarding flow.

## About LetsGo

LetsGo transforms Amplifier into a full personal AI assistant that connects to every major messaging platform (Discord, Telegram, Slack, WhatsApp, Signal, Matrix, Teams, and more), remembers context across sessions, manages credentials securely, and can be extended with voice transcription, a visual canvas, a web dashboard, browser automation, and external tool servers.

The core bundle provides security, memory, observability, and a multi-channel gateway. Five optional satellite bundles add capabilities on top. You install only what you need — the setup wizard handles everything.

## What This Bundle Provides

- **Multi-channel messaging gateway** — 13 channel adapters (Discord, Telegram, Slack, WhatsApp, Signal, Matrix, Teams, LINE, Google Chat, iMessage, Nostr, IRC, Mattermost, Twitch, Feishu) with sender pairing, file exchange, and cron scheduling
- **Bio-inspired memory system** — 8-module pipeline: capture, score, consolidate, compress, inject. Agents remember across sessions.
- **Encrypted secrets** — Fernet-encrypted credential storage with handle-based access (plaintext never exposed)
- **Security & tool policy** — 4-tier risk classification, command allowlists, careful mode, automation mode
- **Sandboxed execution** — Docker-first isolated command execution with resource limits
- **Observability & telemetry** — 7-event session telemetry with tool metrics and JSONL logs
- **Heartbeat engine** — Proactive scheduled agent sessions for check-ins and automation
- **21 domain skills** — Documents (docx/pdf/pptx/xlsx), creative design, MCP server building, browser automation, and more
- **5 specialist agents** — Gateway operator, memory curator, security reviewer, creative specialist, document specialist
- **3 runtime modes** — Careful mode, automation mode, `/letsgo init`

## Quick Start

The recommended way to use LetsGo is to install the behavior at your app level:

```bash
# Install (once)
amplifier bundle add --app git+https://github.com/microsoft/amplifier-bundle-letsgo@main#subdirectory=behaviors/letsgo-capabilities.yaml

# Start a session
amplifier
```

Then run the interactive setup wizard:

```
/letsgo init
```

The wizard walks you through everything:

1. **AI Provider** — Choose Anthropic, OpenAI, Azure, or Ollama. API key stored encrypted.
2. **Messaging Channels** — Select which platforms to connect. Dependencies installed automatically.
3. **Satellite Bundles** — Choose optional capabilities (voice, canvas, webchat, browser, MCP). Installed and wired into your bundle automatically.
4. **Gateway Daemon** — Start the always-on daemon with heartbeat scheduling.

Zero manual file editing. Zero pip commands. Zero YAML wrangling.

### Alternative: Direct Include

Add LetsGo to your existing bundle directly:

```yaml
# In your bundle.md
includes:
  - amplifier-bundle-letsgo
```

Or for selective inclusion, reference individual behaviors:

```yaml
includes:
  - bundle: letsgo:behaviors/security-policy
  - bundle: letsgo:behaviors/memory-store
  - bundle: letsgo:behaviors/memory-capture
  - bundle: letsgo:behaviors/secrets
```

## Satellite Bundles

LetsGo is a family of composable bundles. The core provides security, memory, observability, and the gateway. Satellites add optional capabilities:

| Satellite | What It Adds | Install |
|-----------|-------------|---------|
| **letsgo-voice** | Voice message transcription (Whisper API / local) + TTS (ElevenLabs / edge-tts / OpenAI) across all channels | `pip install amplifier-bundle-letsgo-voice` |
| **letsgo-canvas** | Agent-driven visual workspace — charts, HTML, SVG, code, tables at `localhost:8080/canvas` with real-time WebSocket push | `pip install amplifier-bundle-letsgo-canvas` |
| **letsgo-webchat** | Web chat interface + 6-tab admin dashboard (sessions, channels, senders, cron, usage, agents) with bearer token auth | `pip install amplifier-bundle-letsgo-webchat` |
| **letsgo-browser** | Browser automation via 3 browser-tester agents (operator, researcher, visual-documenter) + gateway-specific skills | `pip install amplifier-bundle-letsgo-browser` |
| **letsgo-mcp** | MCP client bridge — call tools on external MCP servers via stdio subprocess or Streamable HTTP | `pip install amplifier-bundle-letsgo-mcp` |

All satellites are peer bundles — the user's root `bundle.md` includes whichever ones they want:

```yaml
includes:
  - amplifier-bundle-letsgo           # Core (required)
  - amplifier-bundle-letsgo-voice     # Optional
  - amplifier-bundle-letsgo-canvas    # Optional
  - amplifier-bundle-letsgo-webchat   # Optional
```

The `/letsgo init` wizard handles satellite selection, installation, and bundle.md updates automatically.

## Gateway Channels

The gateway supports 13 messaging platforms through a pluggable adapter system with entry-point discovery:

| Channel | Type | Install |
|---------|------|---------|
| Webhook | Built-in | Always available |
| WhatsApp | Built-in | Always available (Node.js bridge) |
| Telegram | Built-in | `pip install letsgo-gateway[telegram]` |
| Discord | Built-in | `pip install letsgo-gateway[discord]` |
| Slack | Built-in | `pip install letsgo-gateway[slack]` |
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

New channels can be added by creating a package that registers a `letsgo.channels` entry point — no gateway code changes needed.

### Gateway CLI

```
letsgo-gateway start                                              # Start the daemon
letsgo-gateway send --channel CH --sender-id ID --message TEXT    # Proactive send
letsgo-gateway pairing list [--approved|--pending]                # List senders
letsgo-gateway pairing approve CODE                               # Approve pairing
letsgo-gateway cron list                                          # List scheduled jobs
letsgo-gateway cron create --name N --cron EXPR --recipe PATH     # Create job
```

## Modes

| Mode | Shortcut | Purpose |
|------|----------|---------|
| `letsgo-init` | `/letsgo init` | Interactive setup wizard — provider, channels, satellites, gateway |
| `careful` | `/careful` | Approval gates on high-risk tool calls |
| `automation` | `/automation` | Restricted profile for unattended operation |

## Agents

| Agent | Purpose |
|-------|---------|
| `letsgo:gateway-operator` | Channel configuration, sender pairing, cron scheduling, gateway diagnostics |
| `letsgo:memory-curator` | Complex memory retrieval, health analysis, consolidation oversight |
| `letsgo:security-reviewer` | Tool policy review, risk classification, allowlist management |
| `letsgo:creative-specialist` | Orchestrates 6 creative skills (canvas-design, algorithmic-art, brand-guidelines, frontend-design, theme-factory, slack-gif-creator) |
| `letsgo:document-specialist` | Orchestrates 4 document skills (docx, pdf, pptx, xlsx) |

## Skills

21 domain expertise packages loaded on demand via `load_skill`:

| Category | Skills |
|----------|--------|
| **Document** | `docx`, `pdf`, `pptx`, `xlsx` |
| **Creative** | `algorithmic-art`, `brand-guidelines`, `canvas-design`, `frontend-design`, `slack-gif-creator`, `theme-factory` |
| **Developer** | `mcp-builder`, `web-artifacts-builder`, `webapp-testing` |
| **Communication** | `doc-coauthoring`, `internal-comms` |
| **Operations** | `agent-browser`, `imagegen`, `schedule`, `send-user-message`, `skill-creator`, `skill-migrator` |

## Memory System

An 8-module bio-inspired pipeline that gives agents durable, intelligent memory across sessions:

```
Agent Activity → Capture → Memorability Score (gate: 0.30) → Store (SQLite + FTS5)
    → Temporal Classification (immediate/task/session/project)
    → [session:end] Consolidation (boost/decay) → Compression (cluster/merge)
    → [next prompt] Injection (<memory-context> block, 2000 token budget)
```

See [docs/MEMORY_GUIDE.md](docs/MEMORY_GUIDE.md) for the complete reference.

## Security

- **4-tier tool policy** — blocked, high (approval required), medium (logged), low (silent)
- **Fernet encryption** — AES-128-CBC + HMAC-SHA256 for secrets at rest
- **Handle-based secret access** — plaintext never returned; 5-minute TTL on handles
- **Docker sandbox** — isolated execution with 512MB/1CPU/120s limits, no network
- **Sender pairing** — 6-character codes, single-use, admin approval required
- **JSONL audit trails** — tool policy + secrets + telemetry at `~/.letsgo/logs/`

See [docs/TOOL_POLICY_GUIDE.md](docs/TOOL_POLICY_GUIDE.md) for the complete reference.

## Recipes

| Recipe | Purpose |
|--------|---------|
| `setup-wizard` | 4-stage interactive onboarding (provider → channels → satellites → daemon) |
| `channel-onboard` | Per-channel setup and credential configuration |
| `daily-digest` | Daily summary generation and distribution |
| `memory-maintenance` | Scheduled memory consolidation and compression |
| `skill-migration` | Batch-migrate OpenClaw skills to Amplifier-native format |

## Bundle Structure

```
amplifier-bundle-letsgo/
├── bundle.md                          # Root bundle (thin pattern)
├── behaviors/                         # 16 composable behaviors
│   ├── letsgo-capabilities.yaml      # Full capability set — includes all others
│   ├── security-policy.yaml          # Tool policy + risk classification
│   ├── secrets.yaml                  # Encrypted credential storage
│   ├── sandbox.yaml                  # Isolated execution
│   ├── observability.yaml            # Session telemetry
│   ├── memory-*.yaml                 # 8 memory pipeline behaviors
│   ├── gateway.yaml                  # Multi-channel messaging
│   ├── heartbeat.yaml                # Proactive scheduled sessions
│   └── skills.yaml                   # Skill discovery + specialist routing
├── modules/                           # 14 Python modules (9 hooks + 5 tools)
├── agents/                            # 5 specialist agents
├── modes/                             # 3 runtime modes
├── skills/                            # 21 domain skills
├── recipes/                           # 5 workflow recipes
├── context/                           # Agent awareness context files
├── gateway/                           # Gateway daemon (letsgo-gateway package)
├── channels/                          # 11 channel adapter plugin packages
│   ├── signal/, matrix/, teams/      # Phase 1 channels
│   ├── canvas/, webchat/             # Satellite channel plugins
│   └── line/, googlechat/, ...       # Phase 7 channels
├── voice/                             # Voice satellite bundle
├── canvas/                            # Canvas satellite bundle
├── browser/                           # Browser satellite bundle
├── webchat/                           # WebChat satellite bundle
└── mcp/                               # MCP satellite bundle
```

## Configuration

### pyproject.toml

```toml
[tool.letsgo]
base_dir = "~/.letsgo"

[tool.letsgo.memory]
max_memories = 1000
memorability_threshold = 0.30
token_budget = 2000

[tool.letsgo.secrets]
handle_ttl = 300

[tool.letsgo.sandbox]
memory_limit = "512m"
cpu_limit = 1.0
timeout = 120
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LETSGO_HOME` | Base directory for all LetsGo data | `~/.letsgo` |
| `LETSGO_CAREFUL_MODE` | Enable careful mode globally | `false` |
| `LETSGO_SANDBOX_MODE` | Sandbox enforcement level | `off` |
| `LETSGO_MEMORY_DB` | Path to memory SQLite database | `{base}/memory.db` |

## Research Foundation

The memory system is grounded in neuroscience research documented in the [amplifier-memory-research](https://github.com/microsoft/amplifier-memory-research) repository, mapping 64 biological memory concepts to implementation primitives.

## License

MIT
