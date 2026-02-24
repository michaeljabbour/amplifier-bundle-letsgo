# OpenClaw Migration Phase 3: `letsgo-canvas` Satellite Bundle — Design

## Goal

Add a visual workspace to the LetsGo gateway — agents push rich content (charts, HTML, SVG, markdown, code, tables) to a web UI served by the gateway daemon. Builds directly on the DisplaySystem protocol shipped in Phase 0.

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | Three-layer (tool → DisplaySystem → CanvasChannel) | Validated by Amplifier experts; clean protocol boundaries |
| Wire format | JSON envelope in `OutboundMessage.text` | Zero changes to existing DisplaySystem; canvas adapter owns parsing |
| Content payload | `tool-canvas` wraps as JSON, CanvasChannel parses | Keeps protocol boundary thin |
| Auto-render hook | Deferred to Phase 3.1 | Ship explicit path first; hook is purely additive |
| Web UI complexity | Multi-panel (sidebar + main) | Supports updating items by ID, content browsing |
| Transport | WebSocket + REST state endpoint | Real-time push, reconnection recovery, future bidirectional support |
| CanvasChannel type | Gateway plugin (entry-point), NOT Amplifier module | Channel adapters don't fit the 5 module types |

## Three-Layer Architecture

Validated by Amplifier expert against kernel philosophy, foundation patterns, and application integration guide.

```
Layer 1: tool-canvas (Amplifier tool module)
    Agent calls canvas_push(content_type, content, id?, title?)
    → Lazy-queries "display" capability from coordinator
    → Calls display(json_envelope, metadata)

Layer 2: GatewayDisplaySystem (already built in Phase 0)
    → Routes to canvas channel if connected
    → Falls back to chat channel otherwise

Layer 3: CanvasChannel adapter (gateway plugin)
    → Receives OutboundMessage with JSON envelope in text
    → Pushes to connected WebSocket clients
    → Serves web UI at localhost:8080/canvas
    → GET /canvas/state for reconnection recovery
```

**Key principle:** DisplaySystem is a transparent pipe — it routes, it doesn't interpret. Content semantics live at the edges (tool-canvas produces, CanvasChannel consumes).

## Canvas Wire Format

The JSON envelope is the shared contract ("stud") between `tool-canvas` and `CanvasChannel`. Both components are on opposite sides of the DisplaySystem protocol boundary but must agree on this structure.

```json
{
  "content_type": "chart",
  "content": "<vega-lite-spec-or-html-or-svg-or-markdown>",
  "id": "chart-1",
  "title": "Monthly Revenue"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content_type` | string | Yes | One of: `chart`, `html`, `svg`, `markdown`, `code`, `table` |
| `content` | string | Yes | The actual content (Vega-Lite JSON, HTML, SVG, markdown text, etc.) |
| `id` | string | No | Stable identifier for updates — same ID replaces previous content |
| `title` | string | No | Display title shown in the sidebar |

When `id` is provided, sending new content with the same `id` replaces the previous item (update-in-place). When omitted, each push creates a new item.

## Component Details

### `tool-canvas` — Amplifier Tool Module

Standard tool module following the `tool-secrets` / `tool-media-pipeline` pattern.

**Location:** `modules/tool-canvas/`

**Tool name:** `canvas_push`

**Input schema:**
- `content_type` (required): enum of chart, html, svg, markdown, code, table
- `content` (required): the content string
- `id` (optional): stable identifier for update-in-place
- `title` (optional): display title

**Behavior:**
- `execute()` lazy-queries `coordinator.get_capability("display")` on every call (no caching — coordinator could reconfigure mid-session)
- If `display` capability is missing → `ToolResult(success=False)` with error: "letsgo-canvas requires amplifier-bundle-letsgo (core). Add it to your root bundle's includes."
- Wraps input as JSON envelope → calls `display(json_envelope, metadata={"content_type": ..., "id": ...})`
- Returns `ToolResult(success=True, output={"id": ..., "content_type": ...})`

**Mount:**
- Entry point: `tool-canvas = "amplifier_module_tool_canvas:mount"`
- Registers capability: `canvas.push`

### `CanvasChannel` — Gateway Plugin

Entry-point plugin following the Signal/Matrix/Teams adapter pattern.

**Location:** `channels/canvas/`

**Package:** `letsgo-channel-canvas`

**Entry point:** `canvas = "letsgo_channel_canvas:CanvasChannel"`

**Responsibilities:**
- Subclasses `ChannelAdapter`
- `start()` — Launches aiohttp web server on configurable host/port (default `localhost:8080`)
- `stop()` — Shuts down the web server and disconnects WebSocket clients
- `send(OutboundMessage)` — Parses JSON envelope from `message.text`, pushes to all connected WebSocket clients, updates in-memory canvas state
- Maintains in-memory canvas state (dict of `id → {content_type, content, title}`) for reconnection recovery

**HTTP routes:**

| Route | Purpose |
|-------|---------|
| `GET /canvas` | Serves the static HTML/JS UI |
| `GET /canvas/state` | Returns current canvas state as JSON |
| `WS /canvas/ws` | WebSocket — server pushes content updates |

**WebSocket message format** (server → client):
```json
{
  "type": "update",
  "id": "chart-1",
  "content_type": "chart",
  "content": "<vega-lite-spec>",
  "title": "Monthly Revenue"
}
```

### Canvas Web UI

Multi-panel layout, single `index.html` with inline CSS/JS (~400 lines). No build step, no framework.

**Layout:**
- Left sidebar (~250px): list of content items by ID/title, newest on top, click to select, content type badge
- Main panel: renders selected item based on `content_type`
- New items auto-appear at top of sidebar and auto-select
- Updated items (same `id`) update in place with brief flash

**Rendering by content type:**

| `content_type` | Renderer |
|----------------|----------|
| `chart` | `vega-embed` (Vega-Lite specs as interactive charts) |
| `html` | Injected into an iframe sandbox |
| `svg` | Inline SVG |
| `markdown` | `marked` library → rendered HTML |
| `code` | `<pre><code>` with `highlight.js` |
| `table` | HTML `<table>` (content is JSON array of objects) |

**JS dependencies** (CDN): `vega-embed`, `marked`, `highlight.js`

**Reconnection:** Auto-reconnect with exponential backoff. On reconnect, fetches `GET /canvas/state` to restore full state.

## Satellite Bundle Structure

Follows the voice satellite pattern:

```
canvas/
├── bundle.md                          # Thin: name=letsgo-canvas
├── behaviors/
│   └── canvas-capabilities.yaml       # Declares tool-canvas + context
├── context/
│   └── canvas-awareness.md            # Agent context
└── skills/
    └── canvas-design/
        └── SKILL.md                   # Usage guide

modules/
    └── tool-canvas/                   # Amplifier tool module

channels/
    └── canvas/                        # Gateway plugin (pip package)
```

## Capability Dependencies

| Capability | Source | Required? | Behavior |
|-----------|--------|-----------|----------|
| `display` | Gateway DisplaySystem | Required | Fail with clear error if missing |
| `memory.store` | tool-memory-store | Optional | Skip memory features |
| `telemetry.metrics` | hooks-telemetry | Optional | Skip telemetry |

Per capability contracts: lazy query at execution time, not mount time.

## What Phase 3 Ships

| Component | Type | What It Does |
|-----------|------|-------------|
| `tool-canvas` | Amplifier tool module | Agent calls `canvas_push()` → display capability → JSON envelope |
| `CanvasChannel` | Gateway plugin | WebSocket server at `:8080/canvas`, multi-panel web UI, state recovery |
| Canvas web UI | Static HTML/JS/CSS | Sidebar + main panel, renders 6 content types |
| Satellite bundle | Bundle structure | `canvas/bundle.md` + behavior + context + skill |
| Wire format doc | Contract | `CANVAS_WIRE_FORMAT.md` documenting envelope schema |

## What's NOT in Phase 3

| Deferred | Rationale |
|----------|-----------|
| `hooks-canvas-autorender` | Ship explicit path first; hook is purely additive (Phase 3.1) |
| Canvas state persistence | In-memory only; acceptable for MVP, add persistence if needed |
| Custom orchestrator | Standard orchestrator works; canvas is just tool calls |
| Form content type | Future interactive content; needs bidirectional WebSocket protocol |

## Estimated Tests (~35)

| Area | Count | What |
|------|-------|------|
| `tool-canvas` | ~10 | Schema, execute, capability lookup, error cases |
| `CanvasChannel` | ~12 | Adapter lifecycle, WebSocket push, JSON parsing, state management |
| Integration | ~8 | tool → DisplaySystem → CanvasChannel → WebSocket message |
| Bundle structure | ~2 | Satellite composition validation |

---

*Architecture validated by Amplifier Expert (amplifier:amplifier-expert) — all six design points passed against kernel philosophy, foundation patterns, and application integration guide.*