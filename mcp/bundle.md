---
name: letsgo-mcp
version: 1.0.0
description: MCP satellite bundle — bridge to external MCP servers
author: letsgo
tags:
  - mcp
  - tools
  - integration
---

# letsgo-mcp

Satellite bundle that bridges Amplifier agents to external MCP (Model Context Protocol) servers.

## What This Provides

- **tool-mcp-client** — call tools on any configured MCP server (local via stdio or remote via Streamable HTTP)
- **MCP awareness context** — teaches agents how to discover and use MCP servers
- **MCP specialist agent** — helps debug MCP connections and configure new servers

## Capabilities

- `mcp.client` — programmatic access to MCP server tools

## Prerequisites

- `amplifier-bundle-letsgo` (core) must be included in the root bundle
- MCP servers must be configured in the tool config or gateway YAML
