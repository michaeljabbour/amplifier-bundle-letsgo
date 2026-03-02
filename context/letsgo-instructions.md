# LetsGo Capabilities

Enhanced capabilities provided by the LetsGo bundle.

## Getting Started

**New user?** Type `/letsgo-init` to run the interactive setup wizard — provider configuration, channel selection, satellite bundle installation, and gateway startup in one guided flow.

## Core Capabilities

| Capability | Purpose |
|------------|---------|
| Tool Policy | 4-tier risk classification, command/path allowlists, careful mode, automation mode |
| Secrets | Fernet-encrypted credential storage with handle-based access and 5-minute TTL |
| Sandbox | Docker-first isolated execution with resource limits and network isolation |
| Telemetry | 7-event session telemetry — tool latency, token usage, error rates, JSONL logs |
| Memory | Bio-inspired 8-module pipeline — capture, score, consolidate, compress, inject |
| Gateway | Multi-channel messaging daemon with 13 channel adapters, sender pairing, cron scheduling |
| Heartbeat | Proactive scheduled sessions — CronScheduler fires HeartbeatEngine per agent |
| Modes | Careful mode (approval gates), Automation mode (restricted profile), LetsGo Init (onboarding) |
| Skills | 21 domain expertise packages across document, creative, developer, communication, and operations |

## Optional Capabilities

- **Voice** — Transcription (Whisper) + TTS across all channels: `pip install amplifier-module-tool-media-pipeline`
- **Canvas** — Visual workspace: charts, HTML, SVG, code at localhost:8080/canvas: `pip install letsgo-channel-canvas`
- **WebChat** — Web chat + 6-tab admin dashboard: `pip install letsgo-channel-webchat`
- **Browser** — 3 browser automation agents (operator, researcher, visual-documenter): `npm install -g agent-browser`
- **MCP** — Bridge to external MCP tool servers via stdio or Streamable HTTP: `pip install amplifier-module-tool-mcp-client`

## Specialist Agents

| Agent | Domain |
|-------|--------|
| `letsgo:gateway-operator` | Channel config, sender pairing, cron scheduling, gateway diagnostics |
| `letsgo:memory-curator` | Complex memory retrieval, health analysis, consolidation oversight |
| `letsgo:security-reviewer` | Tool policy review, risk classification, allowlist management |
| `letsgo:creative-specialist` | Canvas design, algorithmic art, brand guidelines, frontend design, themes, GIFs |
| `letsgo:document-specialist` | Word documents, PDFs, presentations, spreadsheets |
