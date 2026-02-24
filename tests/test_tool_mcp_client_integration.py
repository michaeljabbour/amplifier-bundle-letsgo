"""Integration tests — full MCP pipeline from config to tool call."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from amplifier_module_tool_mcp_client import MCPClientTool, mount
from amplifier_module_tool_mcp_client.config import load_server_configs
from amplifier_module_tool_mcp_client.protocol import MCPError
from amplifier_module_tool_mcp_client.transport import Transport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config() -> dict[str, Any]:
    return {
        "mcp": {
            "servers": {
                "test-fs": {
                    "transport": "stdio",
                    "command": ["echo", "test"],
                },
                "test-remote": {
                    "transport": "streamable-http",
                    "url": "https://api.example.com/mcp",
                },
            },
        },
    }


def _make_mock_transport(
    tools: list[dict[str, Any]] | None = None,
    call_result: dict[str, Any] | None = None,
) -> AsyncMock:
    """Create a mock transport that responds to initialize, tools/list, tools/call."""
    transport = AsyncMock(spec=Transport)
    transport.is_connected = True

    init_resp = {"capabilities": {}, "serverInfo": {"name": "mock"}}
    list_resp = {"tools": tools or [{"name": "read_file", "description": "Read a file"}]}
    call_resp = call_result or {"content": [{"type": "text", "text": "mock result"}]}

    transport.send_request = AsyncMock(
        side_effect=[init_resp, call_resp],
    )
    return transport


# ---------------------------------------------------------------------------
# Integration — full flow
# ---------------------------------------------------------------------------


class TestMCPIntegrationFlow:
    """End-to-end tests with mocked transports."""

    @pytest.mark.asyncio
    async def test_full_flow_configure_list_call(self) -> None:
        """Full flow: configure → list servers → list tools → call tool."""
        tool = MCPClientTool(config=_make_config())

        # List servers
        result = await tool.execute({"action": "list_servers"})
        assert result.success is True
        assert "test-fs" in result.output["servers"]
        assert "test-remote" in result.output["servers"]

        # Inject mock transport for list_tools
        mock_transport = AsyncMock(spec=Transport)
        mock_transport.is_connected = True
        mock_transport.send_request = AsyncMock(
            return_value={"tools": [{"name": "read_file"}]},
        )
        tool._connections["test-fs"] = mock_transport

        # List tools
        result = await tool.execute({"action": "list_tools", "server": "test-fs"})
        assert result.success is True
        assert result.output["tools"][0]["name"] == "read_file"

    @pytest.mark.asyncio
    async def test_call_tool_end_to_end(self) -> None:
        """Call a tool — initialize + tools/call."""
        tool = MCPClientTool(config=_make_config())
        mock = _make_mock_transport()
        tool._connections["test-fs"] = mock

        result = await tool.execute({
            "server": "test-fs",
            "tool": "read_file",
            "arguments": {"path": "/tmp/foo"},
        })
        assert result.success is True
        assert "mock result" in result.output["result"]

    @pytest.mark.asyncio
    async def test_server_not_configured(self) -> None:
        """Error when server is not in config."""
        tool = MCPClientTool(config=_make_config())
        result = await tool.execute({
            "server": "nonexistent",
            "tool": "foo",
            "arguments": {},
        })
        assert result.success is False
        assert "not configured" in result.error["message"]

    @pytest.mark.asyncio
    async def test_transport_connect_fails(self) -> None:
        """Error when transport cannot connect."""
        tool = MCPClientTool(config=_make_config())

        mock = AsyncMock(spec=Transport)
        mock.is_connected = False
        mock.connect = AsyncMock(side_effect=MCPError("Connection refused"))
        tool._connections.pop("test-fs", None)

        # Override _get_connection to use our failing transport
        original = tool._get_connection

        async def failing_connect(name: str) -> Transport:
            if name == "test-fs":
                raise MCPError("Connection refused")
            return await original(name)

        tool._get_connection = failing_connect  # type: ignore[assignment]

        result = await tool.execute({
            "server": "test-fs",
            "tool": "read_file",
            "arguments": {},
        })
        assert result.success is False
        assert "Connection refused" in result.error["message"]

    @pytest.mark.asyncio
    async def test_connection_caching(self) -> None:
        """Second call reuses cached transport."""
        tool = MCPClientTool(config=_make_config())
        mock = AsyncMock(spec=Transport)
        mock.is_connected = True
        mock.send_request = AsyncMock(
            side_effect=[
                # First call: initialize + call
                {"capabilities": {}, "serverInfo": {"name": "mock"}},
                {"content": [{"type": "text", "text": "result1"}]},
                # Second call: just call (already initialized)
                {"content": [{"type": "text", "text": "result2"}]},
            ],
        )
        tool._connections["test-fs"] = mock

        # First call — triggers initialize
        result1 = await tool.execute({
            "server": "test-fs",
            "tool": "read_file",
            "arguments": {"path": "/a"},
        })
        assert result1.success is True

        # Second call — reuses connection, skips initialize
        result2 = await tool.execute({
            "server": "test-fs",
            "tool": "read_file",
            "arguments": {"path": "/b"},
        })
        assert result2.success is True

        # Transport was not re-created — same mock object
        assert tool._connections["test-fs"] is mock

    @pytest.mark.asyncio
    async def test_mount_creates_working_tool(
        self,
        mock_coordinator: Any,
    ) -> None:
        """mount() produces a tool that can list servers."""
        config = _make_config()
        await mount(mock_coordinator, config=config)

        tool = mock_coordinator.mounts[0]["obj"]
        result = await tool.execute({"action": "list_servers"})
        assert result.success is True
        assert "test-fs" in result.output["servers"]
