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
