# OpenClaw Migration Phase 5: `letsgo-webchat` Satellite Bundle — Design

## Goal

Add a web chat interface and admin dashboard to the LetsGo gateway — a single WebChatChannel gateway plugin that serves both a chat UI for messaging and a 6-view admin dashboard for gateway management, on one aiohttp server with URL-prefix separation.

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | Single gateway plugin, one port, URL prefix separation | Avoids port proliferation; clean separation via auth middleware |
| Chat auth | PairingStore (same as all channels) | Reuses existing sender auth mechanism |
| Admin auth | Bearer token from gateway config YAML | Minimum viable security for write ops; fail-closed if not configured |
| Admin dashboard | Single-page app with 6 tabs | Matches canvas pattern; WebSocket stays alive across tab switches |
| Telemetry | Gateway-level metrics (in-process) | Per-session telemetry via JSONL reader deferred to Phase 5.1 |
| Dashboard views | All 6 included | Sessions, channels, senders, cron/heartbeat, usage, agents |
| UI approach | Vanilla HTML/JS/CSS, no build step | Same pattern as canvas; CDN deps if needed |

## Architecture

### URL Structure (single aiohttp server)

```
GET  /chat              → Chat web UI (static HTML)
WS   /chat/ws           → Chat WebSocket (bidirectional, sender auth via PairingStore)
GET  /admin/            → Admin dashboard SPA (bearer token required)
GET  /admin/api/*       → Admin REST API (bearer token required)
```

### Auth Model (validated by Amplifier expert)

Two layers of defense:
1. **Network boundary** — localhost binding by default
2. **Bearer token** — required for all `/admin/` routes via aiohttp middleware

```yaml
# Gateway config
channels:
  webchat:
    type: webchat
    host: "127.0.0.1"
    port: 8090
    admin:
      enabled: true
      token: "your-secret-token-here"
```

- Chat routes: unauthenticated — PairingStore handles sender identity
- Admin routes: bearer token enforced via middleware
- If `admin.token` not configured: admin routes don't mount (fail-closed)

## Components

### WebChatChannel Adapter (`adapter.py`)

Gateway plugin following the CanvasChannel pattern:
- Subclasses `ChannelAdapter` (same as Canvas/Signal/Matrix/Teams)
- Entry point: `webchat = "letsgo_channel_webchat:WebChatChannel"` under `letsgo.channels`
- aiohttp server with chat + admin routes
- Chat WebSocket: bidirectional — client sends messages → `daemon._on_message()`, server pushes responses
- Holds reference to daemon instance for admin API data access

### Admin API (`admin.py`)

REST endpoints under `/admin/api/` returning JSON:

| Endpoint | Method | Source | Data |
|----------|--------|--------|------|
| `/admin/api/sessions` | GET | `daemon.router.active_sessions` | Active sessions, message counts, durations |
| `/admin/api/sessions/{key}` | DELETE | `daemon.router.close_session()` | Close a session |
| `/admin/api/channels` | GET | `daemon.channels` | Channel names, types, running status |
| `/admin/api/senders` | GET | `daemon.auth.get_all_senders()` | All senders with status, counts |
| `/admin/api/senders/{id}/block` | POST | `daemon.auth.block_sender()` | Block a sender |
| `/admin/api/senders/{id}/unblock` | POST | `daemon.auth.unblock_sender()` | Unblock a sender |
| `/admin/api/cron` | GET | `daemon.cron.list_jobs()` | Cron jobs + heartbeat status |
| `/admin/api/usage` | GET | In-process metrics | Uptime, message totals, sender counts |
| `/admin/api/agents` | GET | `daemon._config.get("agents")` | Configured agents from config |

Bearer token middleware (~15 lines):
```python
@web.middleware
async def admin_auth_middleware(request, handler):
    if not request.path.startswith("/admin/"):
        return await handler(request)
    expected = request.app["admin_token"]
    auth_header = request.headers.get("Authorization", "")
    if auth_header == f"Bearer {expected}":
        return await handler(request)
    raise web.HTTPUnauthorized(
        text="Invalid or missing admin token",
        headers={"WWW-Authenticate": "Bearer"},
    )
```

### Admin Dashboard UI (`static/admin/index.html`)

Single-page app (~900 lines vanilla HTML/JS/CSS):
- 6 tabs: Sessions, Channels, Senders, Cron/Heartbeat, Usage, Agents
- Auto-refresh via polling (every 5s)
- Each tab fetches from corresponding `/admin/api/*` endpoint
- Actions: block/unblock senders, close sessions
- Connection status indicator
- Responsive layout

### Chat UI (`static/chat/index.html`)

Simple chat interface (~200 lines):
- Message input + response display
- WebSocket connection for bidirectional messaging
- Sender identification via configurable username or auto-generated ID
- Pairing flow handled in-chat (first message triggers pairing code)
- Auto-reconnect on disconnect

## Prerequisite: PairingStore Additions

Two methods needed in `gateway/letsgo_gateway/auth.py`:

```python
def get_all_senders(self, channel: ChannelType | None = None) -> list[SenderRecord]:
    """Return all senders regardless of status, optionally filtered by channel."""

def unblock_sender(self, sender_id: str, channel: ChannelType) -> None:
    """Set a blocked sender's status back to APPROVED."""
```

Both are ~5 lines each. Tests added for both.

## Satellite Bundle Structure

```
webchat/
├── bundle.md
├── behaviors/webchat-capabilities.yaml
├── context/webchat-awareness.md
└── agents/admin-assistant.md

channels/
└── webchat/                              # Gateway plugin (pip package)
    ├── pyproject.toml
    ├── letsgo_channel_webchat/
    │   ├── __init__.py
    │   ├── adapter.py                    # WebChatChannel
    │   ├── admin.py                      # Admin API routes + auth middleware
    │   └── static/
    │       ├── chat/index.html           # Chat interface (~200 lines)
    │       └── admin/index.html          # Admin dashboard SPA (~900 lines)
    └── tests/
        ├── __init__.py
        └── test_webchat_adapter.py
```

## Telemetry Strategy

**Phase 5 MVP — gateway-level metrics (in-process):**
- Uptime, total messages routed, active session count
- Sender counts by status (approved/blocked/pending)
- Channel running status
- Cron job execution history

**Phase 5.1 — JSONL reader (follow-up):**
- Read `session_end` records from `~/.letsgo/logs/telemetry.jsonl`
- Per-session token usage, tool call distributions, error rates
- ~30 line utility function, not a new module

## What Phase 5 Ships

| Component | Type | What It Does |
|-----------|------|-------------|
| PairingStore additions | Core prerequisite | `get_all_senders()`, `unblock_sender()` |
| `WebChatChannel` | Gateway plugin | Chat + admin on one aiohttp server |
| Admin auth middleware | Bearer token | Protects `/admin/` routes |
| Admin REST API | 9 endpoints | Data for all 6 dashboard views + actions |
| Admin Dashboard | SPA (single HTML) | 6-tab dashboard with auto-refresh |
| Chat UI | SPA (single HTML) | WebSocket chat with pairing flow |
| Satellite bundle | Bundle structure | `webchat/bundle.md` + behavior + context + agent |
| Recipe update | Setup wizard | Webchat configuration step |

## What's NOT in Phase 5

| Deferred | Rationale | When |
|----------|-----------|------|
| Per-session telemetry | Requires JSONL reader; gateway metrics cover MVP | Phase 5.1 |
| User/role/session auth system | Single-operator daemon; bearer token is sufficient | Not planned |
| CORS headers | Localhost-only; no cross-origin scenario | Not planned |
| Token refresh/expiry | Static config, same lifetime as daemon process | Not planned |

## Estimated Tests (~30)

| Area | Count | What |
|------|-------|------|
| PairingStore additions | ~3 | get_all_senders, unblock_sender |
| WebChatChannel lifecycle | ~4 | Start/stop, port binding, config |
| Chat WebSocket | ~5 | Send/receive messages, pairing flow, disconnect |
| Admin auth middleware | ~4 | Valid token, invalid token, missing token, non-admin passthrough |
| Admin API endpoints | ~10 | All 9 endpoints + error cases |
| Integration | ~4 | Daemon wiring, end-to-end chat flow |

---

*Auth model validated by Amplifier Expert — bearer token for admin, PairingStore for chat, fail-closed if not configured. Telemetry strategy: gateway-level metrics for MVP, JSONL reader as follow-up.*