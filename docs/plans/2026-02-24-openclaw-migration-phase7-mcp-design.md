# OpenClaw Migration Phase 7: `letsgo-mcp` + Remaining Channel Adapters — Design

## Goal

Complete the OpenClaw → LetsGo migration by shipping the MCP satellite bundle (full client implementation with stdio + Streamable HTTP transports) and 8 remaining channel adapter skeletons (LINE, Google Chat, iMessage, Nostr, IRC, Mattermost, Twitch, Feishu).

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| MCP client scope | Full implementation (not skeleton) | Ship a working MCP bridge, not a placeholder |
| Transports | stdio + Streamable HTTP | stdio covers 90%+ of MCP servers; Streamable HTTP is the modern remote transport |
| Tool registration | Single `mcp_call` tool with server/tool routing | Simple, testable, ships fast; dynamic per-tool registration is a follow-on |
| Connection lifecycle | Lazy connect, cached, close on session end | No upfront connections at mount time |
| Channel adapters | Skeletons with graceful SDK degradation | Same pattern as Phase 1 (Signal/Matrix/Teams) |
| Gmail triggers | Deferred | No design detail in the migration doc; out of scope for Phase 7 |

## Part A: `letsgo-mcp` Satellite Bundle

### `tool-mcp-client` — Amplifier Tool Module

A single `mcp_call` tool that bridges Amplifier agents to external MCP servers.

**Flow:**
```
Agent calls mcp_call(server="filesystem", tool="read_file", arguments={path: "/tmp/foo"})
  → tool-mcp-client looks up server config
  → Connects via stdio (subprocess) or Streamable HTTP (aiohttp)
  → Sends JSON-RPC tool/call request
  → Returns MCP result as ToolResult
```

**Input schema (3 modes):**

| Mode | Parameters | What It Does |
|------|-----------|-------------|
| Call a tool | `server` + `tool` + `arguments` | Calls an MCP tool on the specified server |
| List servers | `action: "list_servers"` | Returns configured MCP servers with status |
| List tools | `action: "list_tools"` + `server` | Returns available tools on a server |

### Module Structure

```
modules/tool-mcp-client/
├── pyproject.toml
└── amplifier_module_tool_mcp_client/
    ├── __init__.py          # MCPClientTool class + mount()
    ├── transport.py         # Transport ABC + StdioTransport + StreamableHTTPTransport
    ├── protocol.py          # JSON-RPC framing, MCP message types, request/response
    └── config.py            # Server config loading and validation
```

### Transport Layer

**Transport ABC:**
```python
class Transport(ABC):
    async def connect(self) -> None: ...
    async def send_request(self, method: str, params: dict) -> dict: ...
    async def close(self) -> None: ...
    @property
    def is_connected(self) -> bool: ...
```

**StdioTransport:**
- Spawns MCP server as subprocess via `asyncio.create_subprocess_exec`
- Reads/writes JSON-RPC messages over stdin/stdout (newline-delimited JSON)
- Handles process lifecycle (start, communicate, terminate)
- Graceful error handling if binary not found

**StreamableHTTPTransport:**
- POST JSON-RPC requests to configured HTTP endpoint via aiohttp
- Parse streaming HTTP response (chunked transfer encoding)
- Support configurable headers (for auth tokens)
- Handle connection errors gracefully

### Protocol Layer

JSON-RPC 2.0 framing for MCP:

```python
# Request
{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "read_file", "arguments": {"path": "/tmp"}}}

# Response
{"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "file contents"}]}}
```

MCP lifecycle:
1. `initialize` — send capabilities, receive server info + tool list
2. `tools/list` — discover available tools and their schemas
3. `tools/call` — execute a tool with arguments

### Server Configuration

```yaml
# In tool config or gateway YAML
mcp:
  servers:
    filesystem:
      transport: stdio
      command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    remote-api:
      transport: streamable-http
      url: "https://api.example.com/mcp"
      headers:
        Authorization: "Bearer <token>"
```

### Connection Lifecycle

- **Lazy:** connections created on first `mcp_call` to a server, not at mount time
- **Cached:** connections reused across calls to the same server
- **Closed:** all connections closed when the tool is unmounted (session end)
- **Error recovery:** if a connection drops, next call re-establishes it

### Satellite Bundle Structure

```
mcp/
├── bundle.md
├── behaviors/mcp-capabilities.yaml
├── context/mcp-awareness.md
└── agents/mcp-specialist.md
```

The `mcp-builder` skill already exists in `skills/mcp-builder/` from Phase 6.

## Part B: 8 Channel Adapter Skeletons

Following the Phase 1 pattern (Signal/Matrix/Teams). Each is a separate pip-installable package with entry-point registration and graceful SDK degradation.

| Channel | Package | SDK | Class |
|---------|---------|-----|-------|
| LINE | `letsgo-channel-line` | `line-bot-sdk` | `LINEChannel` |
| Google Chat | `letsgo-channel-googlechat` | `google-api-python-client` | `GoogleChatChannel` |
| iMessage | `letsgo-channel-imessage` | platform-specific (AppleScript) | `IMessageChannel` |
| Nostr | `letsgo-channel-nostr` | `nostr-sdk` | `NostrChannel` |
| IRC | `letsgo-channel-irc` | `irc3` | `IRCChannel` |
| Mattermost | `letsgo-channel-mattermost` | `mattermostdriver` | `MattermostChannel` |
| Twitch | `letsgo-channel-twitch` | `twitchio` | `TwitchChannel` |
| Feishu | `letsgo-channel-feishu` | `feishu-sdk` | `FeishuChannel` |

Each adapter skeleton:
- `pyproject.toml` with entry-point under `letsgo.channels`
- `__init__.py` re-exporting the channel class
- `adapter.py` subclassing `ChannelAdapter` with graceful SDK detection
- `tests/test_{name}_adapter.py` with ~6 tests (subclass, instantiation, start without SDK, stop, send when not running, format-specific)

All 8 use entry-point discovery — no changes to the gateway registry `_BUILTINS`.

## What Phase 7 Ships

| Component | Type | Tests |
|-----------|------|-------|
| `tool-mcp-client` | Amplifier tool module (stdio + Streamable HTTP) | ~18 |
| MCP satellite bundle | bundle.md + behavior + context + agent | 0 |
| 8 channel adapter skeletons | Gateway plugins (entry-point) | ~48 |
| Recipe updates | Setup wizard + channel-onboard | 0 |
| Integration tests | MCP end-to-end | ~6 |
| **Total** | | **~72** |

## What's NOT in Phase 7

| Deferred | Rationale |
|----------|-----------|
| Dynamic per-tool registration | Single `mcp_call` tool covers all needs; dynamic registration is an enhancement |
| SSE transport | Superseded by Streamable HTTP; add if a server requires it |
| Gmail triggers | No design specification; separate feature |
| MCP resource/prompt support | Tools-only for MVP; resources and prompts are MCP extensions |

## Estimated Scope

| Metric | Value |
|--------|-------|
| New files | ~50 (MCP module ~8, 8 adapters × ~5 each) |
| Tests | ~72 |
| Tasks | ~12 |
| Python code | ~600 lines (MCP module ~400, adapter skeletons ~25 each) |

---

*Phase 7 completes the OpenClaw → LetsGo migration. All 5 satellite bundles (voice, canvas, browser, webchat, MCP), the gateway plugin system (13 channel adapters), and the skill ecosystem (20 skills + migration tool) will be shipped.*