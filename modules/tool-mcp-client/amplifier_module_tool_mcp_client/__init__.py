"""MCP client bridge tool for Amplifier.

Provides an ``mcp_call`` tool that lets agents call tools on external
MCP servers via stdio subprocess or Streamable HTTP transports.
"""

from __future__ import annotations

import logging
from typing import Any

from amplifier_core.models import ToolResult  # type: ignore[import-not-found]

from .config import ServerConfig, load_server_configs
from .protocol import INITIALIZE, TOOLS_CALL, TOOLS_LIST, MCPError
from .transport import StdioTransport, StreamableHTTPTransport, Transport

__amplifier_module_type__ = "tool"
__all__ = ["MCPClientTool", "mount"]

logger = logging.getLogger(__name__)


class MCPClientTool:
    """Amplifier tool that bridges to external MCP servers.

    Three modes of operation:

    1. **Call a tool** — ``server`` + ``tool`` + ``arguments``
    2. **List servers** — ``action: "list_servers"``
    3. **List tools** — ``action: "list_tools"`` + ``server``
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._coordinator: Any = None
        self._server_configs: dict[str, ServerConfig] = {}
        self._connections: dict[str, Transport] = {}
        self._initialized: set[str] = set()

        try:
            self._server_configs = load_server_configs(config)
        except Exception:
            logger.exception("Failed to load MCP server configs")

    # -- Amplifier Tool protocol --------------------------------------------

    @property
    def name(self) -> str:
        return "mcp_call"

    @property
    def description(self) -> str:
        return (
            "Call tools on external MCP servers. "
            "Supports stdio (local subprocess) and Streamable HTTP (remote) transports. "
            "Use action='list_servers' to see configured servers, "
            "action='list_tools' to discover a server's tools, "
            "or provide server + tool + arguments to call a tool."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list_servers", "list_tools"],
                    "description": (
                        "Optional action. 'list_servers' returns configured servers. "
                        "'list_tools' returns tools on a server. "
                        "Omit to call a tool directly."
                    ),
                },
                "server": {
                    "type": "string",
                    "description": "Name of the MCP server to connect to.",
                },
                "tool": {
                    "type": "string",
                    "description": "Name of the MCP tool to call.",
                },
                "arguments": {
                    "type": "object",
                    "description": "Arguments to pass to the MCP tool.",
                },
            },
        }

    async def execute(self, input: dict[str, Any]) -> ToolResult:  # noqa: A002
        """Dispatch to the appropriate MCP action."""
        action = input.get("action")

        try:
            if action == "list_servers":
                return self._list_servers()
            if action == "list_tools":
                return await self._list_tools(input)
            return await self._call_tool(input)
        except MCPError as exc:
            return ToolResult(
                success=False,
                error={"message": f"MCP error: {exc}"},
            )
        except Exception as exc:
            logger.exception("mcp_call error")
            return ToolResult(
                success=False,
                error={"message": str(exc)},
            )

    # -- Internal actions ---------------------------------------------------

    def _list_servers(self) -> ToolResult:
        """Return configured MCP servers."""
        servers: dict[str, dict[str, Any]] = {}
        for name, cfg in self._server_configs.items():
            connected = name in self._connections and self._connections[name].is_connected
            servers[name] = {
                "transport": cfg.transport,
                "connected": connected,
            }
        return ToolResult(success=True, output={"servers": servers})

    async def _list_tools(self, input: dict[str, Any]) -> ToolResult:  # noqa: A002
        """List tools available on an MCP server."""
        server_name = input.get("server", "")
        if not server_name or server_name not in self._server_configs:
            return ToolResult(
                success=False,
                error={
                    "message": (
                        f"Server '{server_name}' not configured. "
                        f"Available: {', '.join(self._server_configs)}"
                    ),
                },
            )

        transport = await self._get_connection(server_name)
        result = await transport.send_request(TOOLS_LIST, {})
        return ToolResult(success=True, output={"tools": result.get("tools", [])})

    async def _call_tool(self, input: dict[str, Any]) -> ToolResult:  # noqa: A002
        """Call a tool on an MCP server."""
        server_name = input.get("server", "")
        tool_name = input.get("tool", "")
        arguments = input.get("arguments", {})

        if not server_name or server_name not in self._server_configs:
            return ToolResult(
                success=False,
                error={
                    "message": (
                        f"Server '{server_name}' not configured. "
                        f"Available: {', '.join(self._server_configs)}"
                    ),
                },
            )
        if not tool_name:
            return ToolResult(
                success=False,
                error={"message": "Parameter 'tool' is required to call an MCP tool."},
            )

        transport = await self._get_connection(server_name)

        # Initialize session if needed
        if server_name not in self._initialized:
            await transport.send_request(
                INITIALIZE,
                {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "letsgo-mcp-client", "version": "0.1.0"},
                },
            )
            self._initialized.add(server_name)

        result = await transport.send_request(
            TOOLS_CALL,
            {"name": tool_name, "arguments": arguments},
        )

        # Extract text content from MCP result
        content_items = result.get("content", [])
        texts = [c.get("text", "") for c in content_items if c.get("type") == "text"]
        output_text = "\n".join(texts)

        return ToolResult(
            success=True,
            output={"result": output_text, "raw": result},
        )

    # -- Connection management ----------------------------------------------

    async def _get_connection(self, server_name: str) -> Transport:
        """Get or create a cached transport connection."""
        if server_name in self._connections and self._connections[server_name].is_connected:
            return self._connections[server_name]

        cfg = self._server_configs[server_name]
        transport: Transport

        if cfg.transport == "stdio":
            assert cfg.command is not None
            transport = StdioTransport(command=cfg.command, env=cfg.env or None)
        elif cfg.transport == "streamable-http":
            assert cfg.url is not None
            transport = StreamableHTTPTransport(url=cfg.url, headers=cfg.headers or None)
        else:
            msg = f"Unknown transport: {cfg.transport}"
            raise MCPError(msg)

        await transport.connect()
        self._connections[server_name] = transport
        return transport

    async def close_all(self) -> None:
        """Close all open transport connections."""
        for name, transport in self._connections.items():
            try:
                await transport.close()
            except Exception:
                logger.exception("Error closing transport for %s", name)
        self._connections.clear()
        self._initialized.clear()


# ---------------------------------------------------------------------------
# Module mount point
# ---------------------------------------------------------------------------


async def mount(
    coordinator: Any,
    config: dict[str, Any] | None = None,
) -> None:
    """Mount the MCP client tool into the Amplifier coordinator.

    Configuration keys:
        mcp.servers: Dict of server name → {transport, command/url, ...}
    """
    config = config or {}
    tool = MCPClientTool(config=config)
    tool._coordinator = coordinator

    await coordinator.mount("tools", tool, name="tool-mcp-client")
    coordinator.register_capability("mcp.client", tool)

    logger.info("tool-mcp-client mounted with %d servers", len(tool._server_configs))
