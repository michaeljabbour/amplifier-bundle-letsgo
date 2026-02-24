"""MCP transport layer — ABC, StdioTransport, StreamableHTTPTransport."""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from .protocol import MCPError, build_request, parse_response

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class Transport(ABC):
    """Abstract base class for MCP server transports."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the MCP server."""

    @abstractmethod
    async def send_request(self, method: str, params: dict[str, Any]) -> Any:
        """Send a JSON-RPC request and return the parsed result.

        Raises:
            MCPError: On protocol-level errors.
        """

    @abstractmethod
    async def close(self) -> None:
        """Close the connection."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Whether the transport is currently connected."""


# ---------------------------------------------------------------------------
# stdio — subprocess transport
# ---------------------------------------------------------------------------


class StdioTransport(Transport):
    """Transport that communicates with an MCP server via stdin/stdout.

    The server is spawned as a subprocess.  Messages are newline-delimited
    JSON-RPC 2.0.
    """

    def __init__(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
    ) -> None:
        self._command = command
        self._env = env
        self._process: asyncio.subprocess.Process | None = None

    # -- Transport interface ------------------------------------------------

    async def connect(self) -> None:
        """Spawn the MCP server subprocess."""
        import os

        env = {**os.environ, **(self._env or {})}
        self._process = await asyncio.create_subprocess_exec(
            *self._command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        logger.info("StdioTransport connected: %s (pid=%s)", self._command[0], self._process.pid)

    async def send_request(self, method: str, params: dict[str, Any]) -> Any:
        """Write a JSON-RPC request to stdin and read the response from stdout."""
        if not self._process or not self._process.stdin or not self._process.stdout:
            msg = "StdioTransport is not connected"
            raise MCPError(msg)

        request = build_request(method, params)
        line = json.dumps(request).encode() + b"\n"
        self._process.stdin.write(line)
        await self._process.stdin.drain()

        response_line = await asyncio.wait_for(
            self._process.stdout.readline(),
            timeout=30,
        )
        if not response_line:
            msg = "MCP server closed stdout unexpectedly"
            raise MCPError(msg)

        data = json.loads(response_line)
        return parse_response(data)

    async def close(self) -> None:
        """Terminate the subprocess."""
        if self._process:
            self._process.terminate()
            await self._process.wait()
            logger.info("StdioTransport closed")
        self._process = None

    @property
    def is_connected(self) -> bool:
        return self._process is not None and self._process.returncode is None
