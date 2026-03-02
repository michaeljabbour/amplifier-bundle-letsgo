# MCP Awareness

You have access to the `mcp_call` tool, which bridges you to external MCP (Model Context Protocol) servers.

## Operations

- **list_servers** — `mcp_call(action="list_servers")` — returns all configured servers with transport type and status
- **list_tools** — `mcp_call(action="list_tools", server="<name>")` — returns tools available on a server with descriptions and schemas
- **call** — `mcp_call(server="<name>", tool="<tool>", arguments={...})` — calls a tool on the named server

## When This Activates

- User wants to use an external tool or data source via MCP
- User asks to list available MCP servers or tools
- An MCP server call fails and needs diagnosis

## Delegate to Expert

For MCP server setup or troubleshooting, delegate to `letsgo:mcp-specialist`.

The expert handles:
- Adding and configuring new MCP servers (stdio and streamable-http)
- Diagnosing connection failures and auth issues
- Discovering and explaining available tools on a server
