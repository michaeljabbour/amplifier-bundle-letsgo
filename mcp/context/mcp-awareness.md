# MCP Awareness

You have access to the `mcp_call` tool which bridges you to external MCP (Model Context Protocol) servers.

## How to Use

### Discover available servers

```
mcp_call(action="list_servers")
```

Returns all configured MCP servers with their transport type and connection status.

### Discover a server's tools

```
mcp_call(action="list_tools", server="filesystem")
```

Returns the tools available on the named server with their descriptions and input schemas.

### Call a tool

```
mcp_call(server="filesystem", tool="read_file", arguments={"path": "/tmp/example.txt"})
```

Calls the named tool on the server with the provided arguments.

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

## Transport Types

- **stdio** — Local MCP server run as a subprocess. Most common. Requires `command` list.
- **streamable-http** — Remote MCP server accessed via HTTP. Requires `url`. Supports `headers` for auth.

## Important Notes

- Connections are lazy — created on first use, then cached
- If a server is unreachable, the error message will tell you what went wrong
- Use `list_servers` first to see what's available before calling tools
- Each MCP server has its own set of tools — use `list_tools` to discover them
