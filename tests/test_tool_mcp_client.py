"""Tests for tool-mcp-client — MCP bridge for Amplifier agents."""

from __future__ import annotations

import pytest

from amplifier_module_tool_mcp_client.protocol import (
    INITIALIZE,
    JSONRPC_VERSION,
    TOOLS_CALL,
    TOOLS_LIST,
    MCPError,
    build_request,
    parse_response,
)


# ---------------------------------------------------------------------------
# Protocol — build_request
# ---------------------------------------------------------------------------


class TestBuildRequest:
    """JSON-RPC 2.0 request construction."""

    def test_request_format(self) -> None:
        req = build_request("tools/list", {"cursor": None}, req_id=1)
        assert req["jsonrpc"] == "2.0"
        assert req["id"] == 1
        assert req["method"] == "tools/list"
        assert req["params"] == {"cursor": None}

    def test_request_auto_id(self) -> None:
        req = build_request("initialize", {})
        assert "id" in req
        assert isinstance(req["id"], int)


# ---------------------------------------------------------------------------
# Protocol — parse_response
# ---------------------------------------------------------------------------


class TestParseResponse:
    """JSON-RPC 2.0 response parsing."""

    def test_successful_response(self) -> None:
        data = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"tools": [{"name": "read_file"}]},
        }
        result = parse_response(data)
        assert result == {"tools": [{"name": "read_file"}]}

    def test_error_response_raises(self) -> None:
        data = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32601, "message": "Method not found"},
        }
        with pytest.raises(MCPError, match="Method not found"):
            parse_response(data)

    def test_invalid_jsonrpc_raises(self) -> None:
        data = {"id": 1, "result": {}}
        with pytest.raises(MCPError, match="Invalid JSON-RPC"):
            parse_response(data)


# ---------------------------------------------------------------------------
# Protocol — constants
# ---------------------------------------------------------------------------


class TestProtocolConstants:
    """MCP method name constants."""

    def test_jsonrpc_version(self) -> None:
        assert JSONRPC_VERSION == "2.0"

    def test_method_constants(self) -> None:
        assert INITIALIZE == "initialize"
        assert TOOLS_LIST == "tools/list"
        assert TOOLS_CALL == "tools/call"


from amplifier_module_tool_mcp_client.config import (
    ServerConfig,
    load_server_configs,
)


# ---------------------------------------------------------------------------
# Config — ServerConfig + load_server_configs
# ---------------------------------------------------------------------------


class TestServerConfig:
    """Server configuration dataclass."""

    def test_load_stdio_config(self) -> None:
        raw = {
            "mcp": {
                "servers": {
                    "filesystem": {
                        "transport": "stdio",
                        "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                    },
                },
            },
        }
        configs = load_server_configs(raw)
        assert "filesystem" in configs
        cfg = configs["filesystem"]
        assert cfg.name == "filesystem"
        assert cfg.transport == "stdio"
        assert cfg.command == ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        assert cfg.url is None

    def test_load_http_config(self) -> None:
        raw = {
            "mcp": {
                "servers": {
                    "remote-api": {
                        "transport": "streamable-http",
                        "url": "https://api.example.com/mcp",
                        "headers": {"Authorization": "Bearer tok123"},
                    },
                },
            },
        }
        configs = load_server_configs(raw)
        cfg = configs["remote-api"]
        assert cfg.transport == "streamable-http"
        assert cfg.url == "https://api.example.com/mcp"
        assert cfg.headers == {"Authorization": "Bearer tok123"}

    def test_stdio_missing_command_raises(self) -> None:
        raw = {
            "mcp": {
                "servers": {
                    "bad": {"transport": "stdio"},
                },
            },
        }
        with pytest.raises(ValueError, match="command"):
            load_server_configs(raw)

    def test_http_missing_url_raises(self) -> None:
        raw = {
            "mcp": {
                "servers": {
                    "bad": {"transport": "streamable-http"},
                },
            },
        }
        with pytest.raises(ValueError, match="url"):
            load_server_configs(raw)


import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from amplifier_module_tool_mcp_client.transport import (
    StdioTransport,
    Transport,
)


# ---------------------------------------------------------------------------
# Transport — ABC
# ---------------------------------------------------------------------------


class TestTransportABC:
    """Transport abstract base class."""

    def test_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            Transport()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# Transport — StdioTransport
# ---------------------------------------------------------------------------


class TestStdioTransport:
    """StdioTransport spawns an MCP server as a subprocess."""

    @pytest.mark.asyncio
    async def test_connect_spawns_process(self) -> None:
        transport = StdioTransport(command=["echo", "hello"])
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = AsyncMock()
        mock_proc.returncode = None

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            await transport.connect()
            mock_exec.assert_called_once()
            assert transport.is_connected

        # Cleanup
        mock_proc.terminate = MagicMock()
        mock_proc.wait = AsyncMock()
        await transport.close()

    @pytest.mark.asyncio
    async def test_send_request_writes_and_reads(self) -> None:
        transport = StdioTransport(command=["fake"])
        mock_proc = MagicMock()

        response_data = {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
        response_bytes = json.dumps(response_data).encode() + b"\n"

        mock_proc.stdin = MagicMock()
        mock_proc.stdin.write = MagicMock()
        mock_proc.stdin.drain = AsyncMock()
        mock_proc.stdout = AsyncMock()
        mock_proc.stdout.readline = AsyncMock(return_value=response_bytes)
        mock_proc.returncode = None

        transport._process = mock_proc

        result = await transport.send_request("tools/list", {})
        assert result == {"tools": []}
        mock_proc.stdin.write.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_terminates_process(self) -> None:
        transport = StdioTransport(command=["fake"])
        mock_proc = MagicMock()
        mock_proc.terminate = MagicMock()
        mock_proc.wait = AsyncMock()
        mock_proc.returncode = None
        transport._process = mock_proc

        await transport.close()
        mock_proc.terminate.assert_called_once()
        assert not transport.is_connected

    @pytest.mark.asyncio
    async def test_command_not_found_raises(self) -> None:
        transport = StdioTransport(
            command=["__nonexistent_binary_8675309__"],
        )
        with pytest.raises(FileNotFoundError):
            await transport.connect()


from amplifier_module_tool_mcp_client.transport import StreamableHTTPTransport


# ---------------------------------------------------------------------------
# Transport — StreamableHTTPTransport
# ---------------------------------------------------------------------------


class TestStreamableHTTPTransport:
    """StreamableHTTPTransport posts JSON-RPC to an HTTP endpoint."""

    @pytest.mark.asyncio
    async def test_send_request_posts_to_url(self) -> None:
        transport = StreamableHTTPTransport(
            url="https://api.example.com/mcp",
        )
        await transport.connect()

        response_data = {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=response_data)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await transport.send_request("tools/list", {})
            assert result == {"tools": []}

    @pytest.mark.asyncio
    async def test_headers_included(self) -> None:
        transport = StreamableHTTPTransport(
            url="https://api.example.com/mcp",
            headers={"Authorization": "Bearer tok123"},
        )
        await transport.connect()
        assert transport._headers == {"Authorization": "Bearer tok123"}

    @pytest.mark.asyncio
    async def test_http_error_raises(self) -> None:
        transport = StreamableHTTPTransport(url="https://api.example.com/mcp")
        await transport.connect()

        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(MCPError, match="HTTP 500"):
                await transport.send_request("tools/list", {})

    @pytest.mark.asyncio
    async def test_is_connected_after_connect(self) -> None:
        transport = StreamableHTTPTransport(url="https://api.example.com/mcp")
        assert not transport.is_connected
        await transport.connect()
        assert transport.is_connected
        await transport.close()
        assert not transport.is_connected


from typing import Any

from amplifier_module_tool_mcp_client import MCPClientTool, mount


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool(config: dict[str, Any] | None = None) -> MCPClientTool:
    return MCPClientTool(config=config or {})


def _make_tool_with_server() -> MCPClientTool:
    """Tool with a configured stdio server."""
    config = {
        "mcp": {
            "servers": {
                "test-server": {
                    "transport": "stdio",
                    "command": ["echo", "hello"],
                },
            },
        },
    }
    return MCPClientTool(config=config)


# ---------------------------------------------------------------------------
# MCPClientTool — protocol compliance
# ---------------------------------------------------------------------------


class TestMCPClientToolProtocol:
    """MCPClientTool implements the Amplifier tool protocol."""

    def test_name(self) -> None:
        tool = _make_tool()
        assert tool.name == "mcp_call"

    def test_description_not_empty(self) -> None:
        tool = _make_tool()
        assert len(tool.description) > 20

    def test_input_schema_has_server(self) -> None:
        tool = _make_tool()
        schema = tool.input_schema
        assert "server" in schema["properties"]

    def test_input_schema_has_tool(self) -> None:
        tool = _make_tool()
        schema = tool.input_schema
        assert "tool" in schema["properties"]

    def test_input_schema_has_action(self) -> None:
        tool = _make_tool()
        schema = tool.input_schema
        assert "action" in schema["properties"]
        assert set(schema["properties"]["action"]["enum"]) == {
            "list_servers",
            "list_tools",
        }


# ---------------------------------------------------------------------------
# MCPClientTool — execute
# ---------------------------------------------------------------------------


class TestMCPClientToolExecute:
    """MCPClientTool.execute dispatches correctly."""

    @pytest.mark.asyncio
    async def test_list_servers(self) -> None:
        tool = _make_tool_with_server()
        result = await tool.execute({"action": "list_servers"})
        assert result.success is True
        assert "test-server" in result.output["servers"]

    @pytest.mark.asyncio
    async def test_list_tools_mock_transport(self) -> None:
        tool = _make_tool_with_server()

        mock_transport = AsyncMock()
        mock_transport.is_connected = True
        mock_transport.send_request = AsyncMock(
            return_value={"tools": [{"name": "read_file", "description": "Read a file"}]},
        )
        tool._connections["test-server"] = mock_transport

        result = await tool.execute({"action": "list_tools", "server": "test-server"})
        assert result.success is True
        assert result.output["tools"][0]["name"] == "read_file"

    @pytest.mark.asyncio
    async def test_call_tool_mock_transport(self) -> None:
        tool = _make_tool_with_server()

        mock_transport = AsyncMock()
        mock_transport.is_connected = True
        mock_transport.send_request = AsyncMock(
            side_effect=[
                # initialize response
                {"capabilities": {}, "serverInfo": {"name": "test"}},
                # tools/call response
                {"content": [{"type": "text", "text": "file contents"}]},
            ],
        )
        tool._connections["test-server"] = mock_transport

        result = await tool.execute({
            "server": "test-server",
            "tool": "read_file",
            "arguments": {"path": "/tmp/foo"},
        })
        assert result.success is True
        assert "file contents" in str(result.output)

    @pytest.mark.asyncio
    async def test_missing_server_returns_error(self) -> None:
        tool = _make_tool_with_server()
        result = await tool.execute({
            "server": "nonexistent",
            "tool": "read_file",
            "arguments": {},
        })
        assert result.success is False
        assert "not configured" in result.error["message"]

    @pytest.mark.asyncio
    async def test_missing_tool_param_returns_error(self) -> None:
        tool = _make_tool_with_server()
        result = await tool.execute({"server": "test-server"})
        assert result.success is False
        assert "tool" in result.error["message"].lower()


# ---------------------------------------------------------------------------
# Mount
# ---------------------------------------------------------------------------


class TestMCPClientToolMount:
    """mount() registers the tool and capability."""

    @pytest.mark.asyncio
    async def test_mount_registers_tool_and_capability(
        self,
        mock_coordinator: Any,
    ) -> None:
        await mount(mock_coordinator, config={})
        names = [m["name"] for m in mock_coordinator.mounts]
        assert "tool-mcp-client" in names
        assert "mcp.client" in mock_coordinator.capabilities

    @pytest.mark.asyncio
    async def test_mount_stores_coordinator(
        self,
        mock_coordinator: Any,
    ) -> None:
        await mount(mock_coordinator, config={})
        tool = mock_coordinator.mounts[0]["obj"]
        assert tool._coordinator is mock_coordinator
