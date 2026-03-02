# MCP Guide

Comprehensive reference for configuring, connecting, and troubleshooting MCP (Model Context Protocol) servers via the LetsGo gateway.

---

## Configuration

MCP servers are configured in the gateway or tool config:

```yaml
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

---

## Transport Types

- **stdio** — Local MCP server run as a subprocess. Most common. Requires `command` list.
- **streamable-http** — Remote MCP server accessed via HTTP. Requires `url`. Supports `headers` for auth.

---

## Common MCP Servers

- `@modelcontextprotocol/server-filesystem` — file system access
- `@modelcontextprotocol/server-github` — GitHub API
- `@modelcontextprotocol/server-postgres` — PostgreSQL queries
- `@modelcontextprotocol/server-brave-search` — web search

---

## Troubleshooting

### Debugging Checklist

When an MCP server connection fails:

1. Is the server configured? → `mcp_call(action="list_servers")`
2. For stdio: Is the command installed? → Try running it manually
3. For stdio: Check the command path and arguments
4. For HTTP: Is the URL reachable? Check headers/auth
5. For HTTP: Is the server returning valid JSON-RPC 2.0?

### Important Notes

- Connections are lazy — created on first use, then cached
- If a server is unreachable, the error message will tell you what went wrong
- Use `list_servers` first to see what's available before calling tools
- Each MCP server has its own set of tools — use `list_tools` to discover them
