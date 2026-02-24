"""JSON-RPC 2.0 protocol layer for MCP communication."""

from __future__ import annotations

import itertools
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

JSONRPC_VERSION = "2.0"

# MCP method names
INITIALIZE = "initialize"
TOOLS_LIST = "tools/list"
TOOLS_CALL = "tools/call"

# Auto-incrementing request ID generator
_id_counter = itertools.count(1)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MCPError(Exception):
    """Error from an MCP server or invalid protocol message."""

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Request / Response helpers
# ---------------------------------------------------------------------------


def build_request(
    method: str,
    params: dict[str, Any] | None = None,
    *,
    req_id: int | None = None,
) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 request envelope.

    Args:
        method: The MCP method to call (e.g., ``tools/call``).
        params: Method parameters.
        req_id: Explicit request ID.  Auto-generated if omitted.

    Returns:
        A dict ready for ``json.dumps()``.
    """
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": req_id if req_id is not None else next(_id_counter),
        "method": method,
        "params": params or {},
    }


def parse_response(data: dict[str, Any]) -> Any:
    """Parse a JSON-RPC 2.0 response and return the result payload.

    Raises:
        MCPError: If the response contains an ``error`` field or is
            not a valid JSON-RPC 2.0 message.
    """
    if data.get("jsonrpc") != JSONRPC_VERSION:
        raise MCPError("Invalid JSON-RPC response: missing or wrong 'jsonrpc' field")

    if "error" in data:
        err = data["error"]
        code = err.get("code")
        message = err.get("message", "Unknown MCP error")
        raise MCPError(message, code=code)

    return data.get("result")
