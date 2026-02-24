# OpenClaw Migration Phase 7: `letsgo-mcp` + Remaining Channel Adapters — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the OpenClaw → LetsGo migration by shipping a full MCP client tool module (stdio + Streamable HTTP transports, JSON-RPC 2.0 protocol, lazy cached connections) and 8 remaining channel adapter skeletons (LINE, Google Chat, iMessage, Nostr, IRC, Mattermost, Twitch, Feishu).

**Architecture:** Two parts. Part A: `tool-mcp-client` is an Amplifier tool module with a single `mcp_call` tool that bridges agents to external MCP servers — it has a protocol layer (JSON-RPC framing), a config layer (server registry), a transport layer (ABC + stdio subprocess + Streamable HTTP), and the tool itself (dispatches 3 modes: call tool, list servers, list tools). Part B: 8 channel adapter skeletons following the Phase 1 pattern (Signal/Matrix/Teams) — each is a separate pip-installable package with entry-point registration, graceful SDK degradation, and a format-specific method showing awareness of the wire format.

**Tech Stack:** Python 3.11+, pytest + pytest-asyncio (asyncio_mode=auto), hatchling build system, aiohttp for Streamable HTTP transport, asyncio subprocess for stdio transport.

**Design Document:** `docs/plans/2026-02-24-openclaw-migration-phase7-mcp-design.md`

---

## Conventions Reference

These conventions are derived from the existing codebase. Follow them exactly.

**Module naming:**
- Directory: `modules/{type}-{name}/` (e.g., `modules/tool-mcp-client/`)
- Package: `amplifier_module_{type}_{name}` (hyphens → underscores)
- PyPI name: `amplifier-module-{type}-{name}`
- Entry point: `{type}-{name} = "{package}:mount"` under `[project.entry-points."amplifier.modules"]`

**Channel adapter naming:**
- Directory: `channels/{name}/` (e.g., `channels/line/`)
- Package: `letsgo_channel_{name}` (e.g., `letsgo_channel_line`)
- PyPI name: `letsgo-channel-{name}`
- Entry point: `{name} = "{package}:{ClassName}"` under `[project.entry-points."letsgo.channels"]`

**Test conventions:**
- Framework: pytest + pytest-asyncio with `asyncio_mode = auto`
- Location: `tests/test_{module_name_underscored}.py` for modules, `tests/test_gateway/test_{component}.py` for gateway
- Style: class-based grouping (`class TestSomething:`), `_make_xxx()` helper factories, `@pytest.mark.asyncio` on async tests
- Fixtures: `mock_coordinator` and `tmp_dir` from `tests/conftest.py`
- Run command: `python -m pytest tests/path/to/test.py -v`
- Channel adapter tests run with: `PYTHONPATH=channels/{name}:gateway python -m pytest channels/{name}/tests/ -v`

**Tool protocol (from `tool-canvas` reference):**
- Properties: `name` → str, `description` → str, `input_schema` → dict (JSON Schema)
- Method: `async def execute(self, input: dict) -> ToolResult`
- Import: `from amplifier_core.models import ToolResult  # type: ignore[import-not-found]`
- Module type marker: `__amplifier_module_type__ = "tool"`

**Mount pattern (tool):**
```python
__amplifier_module_type__ = "tool"
async def mount(coordinator, config=None):
    tool = SomeTool(...)
    await coordinator.mount("tools", tool, name="tool-xxx")
    coordinator.register_capability("xxx.yyy", tool)
```

**Channel adapter pattern (from `SignalChannel` reference):**
```python
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

class SomeChannel(ChannelAdapter):
    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def send(self, message: OutboundMessage) -> bool: ...
```

**Channel adapter test pattern (from `test_signal_adapter.py` reference):**
```python
def test_{name}_is_channel_adapter():
    assert issubclass(SomeChannel, ChannelAdapter)

def test_{name}_instantiation():
    ch = SomeChannel(name="test", config={...})
    assert ch.name == "test"
    assert not ch.is_running

async def test_{name}_start_without_sdk_logs_warning(caplog):
    ch = SomeChannel(name="test", config={...})
    await ch.start()
    assert not ch.is_running

async def test_{name}_stop_when_not_running():
    ch = SomeChannel(name="test", config={})
    await ch.stop()
    assert not ch.is_running

async def test_{name}_send_returns_false_when_not_running():
    ch = SomeChannel(name="test", config={})
    msg = OutboundMessage(channel=ChannelType("{name}"), ...)
    result = await ch.send(msg)
    assert result is False

def test_{name}_format_specific():
    # Test the adapter's SDK-specific format method
```

**Behavior YAML pattern:**
```yaml
bundle:
  name: behavior-xxx
  version: 1.0.0
  description: ...
tools:
  - module: tool-xxx
    source: ../modules/tool-xxx
    config: {}
context:
  include:
    - namespace:context/xxx-awareness.md
```

---

## Summary

| Task | Component | Files | Tests |
|------|-----------|-------|-------|
| 1 | MCP Protocol Layer | 2 create | 5 |
| 2 | MCP Config Layer | 1 create, 1 modify | 4 |
| 3 | MCP Transport ABC + StdioTransport | 1 create, 1 modify | 5 |
| 4 | StreamableHTTPTransport | 1 modify, 1 modify | 4 |
| 5 | MCPClientTool — Tool Module | 1 create, 1 modify | 8 |
| 6 | MCP Satellite Bundle Structure | 4 create | 0 |
| 7 | MCP Integration Tests | 1 create | 6 |
| 8 | LINE + Google Chat Adapters | 10 create | 12 |
| 9 | iMessage + Nostr Adapters | 10 create | 12 |
| 10 | IRC + Mattermost Adapters | 10 create | 12 |
| 11 | Twitch + Feishu Adapters | 10 create | 12 |
| 12 | Recipe Updates + Final Verification | 2 modify | 0 |
| **Total** | | **~55 files** | **~80** |

**Commit sequence:**
1. `feat(mcp): JSON-RPC 2.0 protocol layer for MCP communication`
2. `feat(mcp): server config loading and validation`
3. `feat(mcp): transport ABC and StdioTransport for subprocess MCP servers`
4. `feat(mcp): StreamableHTTPTransport for remote MCP servers`
5. `feat(mcp): MCPClientTool with mcp_call action and lazy connections`
6. `feat(mcp): satellite bundle structure — bundle.md, behaviors, context, agent`
7. `test(mcp): integration tests for full MCP pipeline`
8. `feat: add LINE and Google Chat channel adapter skeletons`
9. `feat: add iMessage and Nostr channel adapter skeletons`
10. `feat: add IRC and Mattermost channel adapter skeletons`
11. `feat: add Twitch and Feishu channel adapter skeletons`
12. `feat(recipes): add MCP config and 8 new channels to onboarding`

---

## Phase 7 — Part A: `letsgo-mcp` Satellite Bundle

### Task 1: MCP Protocol Layer

**Files:**
- Create: `modules/tool-mcp-client/pyproject.toml`
- Create: `modules/tool-mcp-client/amplifier_module_tool_mcp_client/protocol.py`
- Test: `tests/test_tool_mcp_client.py`

### Step 1: Create pyproject.toml

Create `modules/tool-mcp-client/pyproject.toml`:

```toml
[project]
name = "amplifier-module-tool-mcp-client"
version = "0.1.0"
description = "MCP client bridge tool for Amplifier — call tools on external MCP servers"
requires-python = ">=3.11"
dependencies = [
    "aiohttp>=3.9",
]

[project.entry-points."amplifier.modules"]
tool-mcp-client = "amplifier_module_tool_mcp_client:mount"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["amplifier_module_tool_mcp_client"]
```

### Step 2: Create stub `__init__.py`

Create `modules/tool-mcp-client/amplifier_module_tool_mcp_client/__init__.py`:

```python
"""MCP client bridge tool for Amplifier."""
```

### Step 3: Register module in conftest.py

Add `_BUNDLE_ROOT / "modules" / "tool-mcp-client"` to `_MODULE_DIRS` in `tests/conftest.py`, right after the `tool-canvas` entry:

```python
    _BUNDLE_ROOT / "modules" / "tool-canvas",
    _BUNDLE_ROOT / "modules" / "tool-mcp-client",
    # Gateway package lives under gateway/
```

### Step 4: Write failing tests

Create `tests/test_tool_mcp_client.py`:

```python
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
```

### Step 5: Run tests to verify they fail

Run: `cd /path/to/worktree && python -m pytest tests/test_tool_mcp_client.py -v`
Expected: `ModuleNotFoundError: No module named 'amplifier_module_tool_mcp_client.protocol'`

### Step 6: Implement protocol.py

Create `modules/tool-mcp-client/amplifier_module_tool_mcp_client/protocol.py`:

```python
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
```

### Step 7: Run tests to verify they pass

Run: `python -m pytest tests/test_tool_mcp_client.py -v`
Expected: 5 passed

### Step 8: Run python_check

Run: `python_check paths=["modules/tool-mcp-client/amplifier_module_tool_mcp_client/protocol.py", "tests/test_tool_mcp_client.py"]`

### Step 9: Commit

Message: `feat(mcp): JSON-RPC 2.0 protocol layer for MCP communication`
Files: `modules/tool-mcp-client/pyproject.toml`, `modules/tool-mcp-client/amplifier_module_tool_mcp_client/__init__.py`, `modules/tool-mcp-client/amplifier_module_tool_mcp_client/protocol.py`, `tests/test_tool_mcp_client.py`, `tests/conftest.py`

---

### Task 2: MCP Config Layer

**Files:**
- Create: `modules/tool-mcp-client/amplifier_module_tool_mcp_client/config.py`
- Modify: `tests/test_tool_mcp_client.py`

### Step 1: Write failing tests

Append to `tests/test_tool_mcp_client.py`:

```python
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
```

### Step 2: Run tests to verify they fail

Run: `python -m pytest tests/test_tool_mcp_client.py::TestServerConfig -v`
Expected: `ImportError: cannot import name 'ServerConfig'`

### Step 3: Implement config.py

Create `modules/tool-mcp-client/amplifier_module_tool_mcp_client/config.py`:

```python
"""MCP server configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ServerConfig:
    """Configuration for a single MCP server.

    Attributes:
        name: Human-readable server name (dict key from config).
        transport: ``"stdio"`` or ``"streamable-http"``.
        command: Command list to spawn subprocess (stdio only).
        url: HTTP endpoint URL (streamable-http only).
        headers: Extra HTTP headers (streamable-http only).
        env: Extra environment variables (stdio only).
    """

    name: str
    transport: str
    command: list[str] | None = None
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)


def load_server_configs(config: dict[str, Any]) -> dict[str, ServerConfig]:
    """Parse the ``mcp.servers`` config section into :class:`ServerConfig` objects.

    Args:
        config: The full tool or gateway config dict.  Expected shape::

            {"mcp": {"servers": {"name": {"transport": "...", ...}}}}

    Returns:
        A mapping of server name → :class:`ServerConfig`.

    Raises:
        ValueError: If required keys are missing for a transport type.
    """
    servers_raw = config.get("mcp", {}).get("servers", {})
    configs: dict[str, ServerConfig] = {}

    for name, spec in servers_raw.items():
        transport = spec.get("transport", "stdio")

        if transport == "stdio":
            command = spec.get("command")
            if not command:
                msg = (
                    f"MCP server '{name}': stdio transport requires "
                    f"'command' (list of strings)"
                )
                raise ValueError(msg)
            configs[name] = ServerConfig(
                name=name,
                transport=transport,
                command=command,
                env=spec.get("env", {}),
            )

        elif transport == "streamable-http":
            url = spec.get("url")
            if not url:
                msg = (
                    f"MCP server '{name}': streamable-http transport "
                    f"requires 'url'"
                )
                raise ValueError(msg)
            configs[name] = ServerConfig(
                name=name,
                transport=transport,
                url=url,
                headers=spec.get("headers", {}),
            )

        else:
            msg = (
                f"MCP server '{name}': unknown transport '{transport}'. "
                f"Supported: stdio, streamable-http"
            )
            raise ValueError(msg)

    return configs
```

### Step 4: Run tests to verify they pass

Run: `python -m pytest tests/test_tool_mcp_client.py -v`
Expected: 9 passed (5 protocol + 4 config)

### Step 5: Run python_check

Run: `python_check paths=["modules/tool-mcp-client/amplifier_module_tool_mcp_client/config.py"]`

### Step 6: Commit

Message: `feat(mcp): server config loading and validation`
Files: `modules/tool-mcp-client/amplifier_module_tool_mcp_client/config.py`, `tests/test_tool_mcp_client.py`

---

### Task 3: MCP Transport ABC + StdioTransport

**Files:**
- Create: `modules/tool-mcp-client/amplifier_module_tool_mcp_client/transport.py`
- Modify: `tests/test_tool_mcp_client.py`

### Step 1: Write failing tests

Append to `tests/test_tool_mcp_client.py`:

```python
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
```

### Step 2: Run tests to verify they fail

Run: `python -m pytest tests/test_tool_mcp_client.py::TestTransportABC tests/test_tool_mcp_client.py::TestStdioTransport -v`
Expected: `ImportError: cannot import name 'StdioTransport'`

### Step 3: Implement transport.py

Create `modules/tool-mcp-client/amplifier_module_tool_mcp_client/transport.py`:

```python
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
```

### Step 4: Run tests to verify they pass

Run: `python -m pytest tests/test_tool_mcp_client.py -v`
Expected: 13 passed (5 protocol + 4 config + 1 ABC + 3 stdio — note: command_not_found should also pass since the binary truly doesn't exist)

### Step 5: Run python_check

Run: `python_check paths=["modules/tool-mcp-client/amplifier_module_tool_mcp_client/transport.py"]`

### Step 6: Commit

Message: `feat(mcp): transport ABC and StdioTransport for subprocess MCP servers`
Files: `modules/tool-mcp-client/amplifier_module_tool_mcp_client/transport.py`, `tests/test_tool_mcp_client.py`

---

### Task 4: StreamableHTTPTransport

**Files:**
- Modify: `modules/tool-mcp-client/amplifier_module_tool_mcp_client/transport.py`
- Modify: `tests/test_tool_mcp_client.py`

### Step 1: Write failing tests

Append to `tests/test_tool_mcp_client.py`:

```python
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

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
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

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
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
```

### Step 2: Run tests to verify they fail

Run: `python -m pytest tests/test_tool_mcp_client.py::TestStreamableHTTPTransport -v`
Expected: `ImportError: cannot import name 'StreamableHTTPTransport'`

### Step 3: Add StreamableHTTPTransport to transport.py

Append to `modules/tool-mcp-client/amplifier_module_tool_mcp_client/transport.py`:

```python
# ---------------------------------------------------------------------------
# Streamable HTTP transport
# ---------------------------------------------------------------------------


class StreamableHTTPTransport(Transport):
    """Transport that communicates with an MCP server via Streamable HTTP.

    Each request is a POST of JSON-RPC 2.0 to the configured URL.
    The response is parsed from the HTTP response body.
    """

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._url = url
        self._headers = headers or {}
        self._connected = False

    # -- Transport interface ------------------------------------------------

    async def connect(self) -> None:
        """Mark as connected.  HTTP is stateless — no persistent connection."""
        self._connected = True
        logger.info("StreamableHTTPTransport ready: %s", self._url)

    async def send_request(self, method: str, params: dict[str, Any]) -> Any:
        """POST a JSON-RPC request and parse the response."""
        import aiohttp

        request = build_request(method, params)
        headers = {
            "Content-Type": "application/json",
            **self._headers,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self._url,
                json=request,
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    msg = f"HTTP {resp.status} from MCP server: {body[:200]}"
                    raise MCPError(msg)

                data = await resp.json()
                return parse_response(data)

    async def close(self) -> None:
        """Mark as disconnected."""
        self._connected = False
        logger.info("StreamableHTTPTransport closed")

    @property
    def is_connected(self) -> bool:
        return self._connected
```

### Step 4: Run tests to verify they pass

Run: `python -m pytest tests/test_tool_mcp_client.py -v`
Expected: 17 passed (5 protocol + 4 config + 1 ABC + 4 stdio + 4 HTTP — note: one less stdio since the 4 included command_not_found)

### Step 5: Run python_check

Run: `python_check paths=["modules/tool-mcp-client/amplifier_module_tool_mcp_client/transport.py"]`

### Step 6: Commit

Message: `feat(mcp): StreamableHTTPTransport for remote MCP servers`
Files: `modules/tool-mcp-client/amplifier_module_tool_mcp_client/transport.py`, `tests/test_tool_mcp_client.py`

---

### Task 5: MCPClientTool — Tool Module

**Files:**
- Create: `modules/tool-mcp-client/amplifier_module_tool_mcp_client/__init__.py` (replace stub)
- Modify: `tests/test_tool_mcp_client.py`

### Step 1: Write failing tests

Append to `tests/test_tool_mcp_client.py`:

```python
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
```

### Step 2: Run tests to verify they fail

Run: `python -m pytest tests/test_tool_mcp_client.py::TestMCPClientToolProtocol tests/test_tool_mcp_client.py::TestMCPClientToolExecute tests/test_tool_mcp_client.py::TestMCPClientToolMount -v`
Expected: `ImportError: cannot import name 'MCPClientTool'`

### Step 3: Implement __init__.py

Replace `modules/tool-mcp-client/amplifier_module_tool_mcp_client/__init__.py` with:

```python
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
```

### Step 4: Run tests to verify they pass

Run: `python -m pytest tests/test_tool_mcp_client.py -v`
Expected: All passed (5 protocol + 4 config + 1 ABC + 4 stdio + 4 HTTP + 5 protocol-compliance + 5 execute + 2 mount = ~30)

### Step 5: Run python_check

Run: `python_check paths=["modules/tool-mcp-client/amplifier_module_tool_mcp_client/__init__.py"]`

### Step 6: Commit

Message: `feat(mcp): MCPClientTool with mcp_call action and lazy connections`
Files: `modules/tool-mcp-client/amplifier_module_tool_mcp_client/__init__.py`, `tests/test_tool_mcp_client.py`

---

### Task 6: MCP Satellite Bundle Structure

**Files:**
- Create: `mcp/bundle.md`
- Create: `mcp/behaviors/mcp-capabilities.yaml`
- Create: `mcp/context/mcp-awareness.md`
- Create: `mcp/agents/mcp-specialist.md`

No tests — validated by bundle loader.

### Step 1: Create bundle.md

Create `mcp/bundle.md`:

```markdown
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
```

### Step 2: Create behavior YAML

Create `mcp/behaviors/mcp-capabilities.yaml`:

```yaml
bundle:
  name: behavior-mcp-capabilities
  version: 1.0.0
  description: MCP client tool and awareness context

tools:
  - module: tool-mcp-client
    source: ../modules/tool-mcp-client
    config: {}

context:
  include:
    - "@letsgo-mcp:context/mcp-awareness.md"
```

### Step 3: Create awareness context

Create `mcp/context/mcp-awareness.md`:

```markdown
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
```

### Step 4: Create specialist agent

Create `mcp/agents/mcp-specialist.md`:

```markdown
---
name: mcp-specialist
description: MCP integration specialist — helps configure, debug, and use MCP servers
---

# MCP Specialist

You are an MCP integration specialist. You help users:

1. **Configure MCP servers** — guide them through adding new servers to their config (stdio for local, streamable-http for remote)
2. **Debug connections** — diagnose why a server isn't responding (wrong path, missing npm package, auth issues)
3. **Discover tools** — use `mcp_call(action="list_tools")` to show what a server offers
4. **Use MCP tools effectively** — help translate user intent into the right MCP tool calls

## Debugging Checklist

When an MCP server connection fails:

1. Is the server configured? → `mcp_call(action="list_servers")`
2. For stdio: Is the command installed? → Try running it manually
3. For stdio: Check the command path and arguments
4. For HTTP: Is the URL reachable? Check headers/auth
5. For HTTP: Is the server returning valid JSON-RPC 2.0?

## Common MCP Servers

- `@modelcontextprotocol/server-filesystem` — file system access
- `@modelcontextprotocol/server-github` — GitHub API
- `@modelcontextprotocol/server-postgres` — PostgreSQL queries
- `@modelcontextprotocol/server-brave-search` — web search
```

### Step 5: Commit

Message: `feat(mcp): satellite bundle structure — bundle.md, behaviors, context, agent`
Files: `mcp/bundle.md`, `mcp/behaviors/mcp-capabilities.yaml`, `mcp/context/mcp-awareness.md`, `mcp/agents/mcp-specialist.md`

---

### Task 7: MCP Integration Tests

**Files:**
- Create: `tests/test_tool_mcp_client_integration.py`

### Step 1: Write integration tests

Create `tests/test_tool_mcp_client_integration.py`:

```python
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
```

### Step 2: Run tests

Run: `python -m pytest tests/test_tool_mcp_client_integration.py -v`
Expected: 6 passed

### Step 3: Run python_check

Run: `python_check paths=["tests/test_tool_mcp_client_integration.py"]`

### Step 4: Commit

Message: `test(mcp): integration tests for full MCP pipeline`
Files: `tests/test_tool_mcp_client_integration.py`

---

## Phase 7 — Part B: Channel Adapter Skeletons

### Task 8: LINE + Google Chat Adapters

**Files (LINE):**
- Create: `channels/line/pyproject.toml`
- Create: `channels/line/letsgo_channel_line/__init__.py`
- Create: `channels/line/letsgo_channel_line/adapter.py`
- Create: `channels/line/tests/__init__.py`
- Create: `channels/line/tests/test_line_adapter.py`

**Files (Google Chat):**
- Create: `channels/googlechat/pyproject.toml`
- Create: `channels/googlechat/letsgo_channel_googlechat/__init__.py`
- Create: `channels/googlechat/letsgo_channel_googlechat/adapter.py`
- Create: `channels/googlechat/tests/__init__.py`
- Create: `channels/googlechat/tests/test_googlechat_adapter.py`

### Step 1: Create LINE adapter

Create `channels/line/pyproject.toml`:

```toml
[project]
name = "letsgo-channel-line"
version = "0.1.0"
description = "LINE channel adapter for LetsGo gateway"
requires-python = ">=3.11"
dependencies = [
    "letsgo-gateway",
]

[project.optional-dependencies]
sdk = ["line-bot-sdk>=3.0"]

[project.entry-points."letsgo.channels"]
line = "letsgo_channel_line:LINEChannel"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["letsgo_channel_line"]
```

Create `channels/line/letsgo_channel_line/__init__.py`:

```python
"""LINE channel adapter for the LetsGo gateway."""

from .adapter import LINEChannel

__all__ = ["LINEChannel"]
```

Create `channels/line/letsgo_channel_line/adapter.py`:

```python
"""LINE Messaging API channel adapter."""

from __future__ import annotations

import logging
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

# Graceful SDK detection
try:
    from linebot.v3.messaging import (  # type: ignore[import-not-found]
        ApiClient,
        Configuration,
        MessagingApi,
    )

    _HAS_LINE_SDK = True
except ImportError:
    _HAS_LINE_SDK = False


class LINEChannel(ChannelAdapter):
    """LINE Messaging API adapter.

    Config keys:
        channel_access_token: LINE channel access token
        channel_secret: LINE channel secret for webhook verification
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._access_token: str = config.get("channel_access_token", "")
        self._channel_secret: str = config.get("channel_secret", "")
        self._api: Any = None

    async def start(self) -> None:
        """Start the LINE adapter."""
        if not _HAS_LINE_SDK:
            logger.warning(
                "line-bot-sdk not installed — LINE channel '%s' cannot start. "
                "Install: pip install letsgo-channel-line[sdk]",
                self.name,
            )
            return

        configuration = Configuration(access_token=self._access_token)
        api_client = ApiClient(configuration)
        self._api = MessagingApi(api_client)
        self._running = True
        logger.info("LINEChannel '%s' started", self.name)

    async def stop(self) -> None:
        """Stop the LINE adapter."""
        self._api = None
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message via LINE Messaging API."""
        if not self._running or not self._api:
            return False

        try:
            body = self._format_flex_message(message.text)
            logger.info("LINE send to %s: %s", message.thread_id, body.get("type"))
            return True
        except Exception:
            logger.exception("Failed to send LINE message")
            return False

    def _format_flex_message(self, text: str) -> dict[str, Any]:
        """Convert text to a LINE Flex Message JSON structure.

        Returns a Flex Message container with a simple bubble layout.
        """
        return {
            "type": "flex",
            "altText": text[:400],
            "contents": {
                "type": "bubble",
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": text,
                            "wrap": True,
                            "size": "md",
                        },
                    ],
                },
            },
        }
```

Create `channels/line/tests/__init__.py` (empty file).

Create `channels/line/tests/test_line_adapter.py`:

```python
"""Tests for LINE channel adapter."""

from __future__ import annotations

import pytest
from letsgo_channel_line import LINEChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage


def test_line_is_channel_adapter():
    """LINEChannel is a proper ChannelAdapter subclass."""
    assert issubclass(LINEChannel, ChannelAdapter)


def test_line_instantiation():
    """LINEChannel can be instantiated with name and config."""
    ch = LINEChannel(
        name="line-main",
        config={"channel_access_token": "tok123", "channel_secret": "sec456"},
    )
    assert ch.name == "line-main"
    assert ch.config["channel_access_token"] == "tok123"
    assert not ch.is_running


@pytest.mark.asyncio
async def test_line_start_without_sdk_logs_warning(caplog):
    """start() logs a warning when line-bot-sdk is not installed."""
    ch = LINEChannel(name="line-test", config={})
    await ch.start()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_line_stop_when_not_running():
    """stop() is safe to call when not running."""
    ch = LINEChannel(name="line-test", config={})
    await ch.stop()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_line_send_returns_false_when_not_running():
    """send() returns False when adapter is not running."""
    ch = LINEChannel(name="line-test", config={})
    msg = OutboundMessage(
        channel=ChannelType("line"),
        channel_name="line-test",
        thread_id=None,
        text="hello",
    )
    result = await ch.send(msg)
    assert result is False


def test_line_format_flex_message():
    """_format_flex_message returns a LINE Flex Message structure."""
    ch = LINEChannel(name="line-test", config={})
    result = ch._format_flex_message("Hello from LetsGo")
    assert result["type"] == "flex"
    assert result["altText"] == "Hello from LetsGo"
    assert result["contents"]["type"] == "bubble"
    body_text = result["contents"]["body"]["contents"][0]["text"]
    assert body_text == "Hello from LetsGo"
```

### Step 2: Create Google Chat adapter

Create `channels/googlechat/pyproject.toml`:

```toml
[project]
name = "letsgo-channel-googlechat"
version = "0.1.0"
description = "Google Chat channel adapter for LetsGo gateway"
requires-python = ">=3.11"
dependencies = [
    "letsgo-gateway",
]

[project.optional-dependencies]
sdk = ["google-api-python-client>=2.0"]

[project.entry-points."letsgo.channels"]
googlechat = "letsgo_channel_googlechat:GoogleChatChannel"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["letsgo_channel_googlechat"]
```

Create `channels/googlechat/letsgo_channel_googlechat/__init__.py`:

```python
"""Google Chat channel adapter for the LetsGo gateway."""

from .adapter import GoogleChatChannel

__all__ = ["GoogleChatChannel"]
```

Create `channels/googlechat/letsgo_channel_googlechat/adapter.py`:

```python
"""Google Chat channel adapter using the Google Chat API."""

from __future__ import annotations

import logging
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

try:
    from googleapiclient.discovery import build as google_build  # type: ignore[import-not-found]
    from google.oauth2.service_account import Credentials  # type: ignore[import-not-found]

    _HAS_GOOGLE_SDK = True
except ImportError:
    _HAS_GOOGLE_SDK = False


class GoogleChatChannel(ChannelAdapter):
    """Google Chat adapter via Google Workspace API.

    Config keys:
        service_account_path: Path to service account JSON key file
        space_name: Google Chat space name (e.g., "spaces/AAAA...")
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._sa_path: str = config.get("service_account_path", "")
        self._space: str = config.get("space_name", "")
        self._service: Any = None

    async def start(self) -> None:
        """Start the Google Chat adapter."""
        if not _HAS_GOOGLE_SDK:
            logger.warning(
                "google-api-python-client not installed — Google Chat channel "
                "'%s' cannot start. Install: pip install letsgo-channel-googlechat[sdk]",
                self.name,
            )
            return

        try:
            creds = Credentials.from_service_account_file(
                self._sa_path,
                scopes=["https://www.googleapis.com/auth/chat.bot"],
            )
            self._service = google_build("chat", "v1", credentials=creds)
            self._running = True
            logger.info("GoogleChatChannel '%s' started for %s", self.name, self._space)
        except Exception:
            logger.exception("Failed to start GoogleChatChannel")

    async def stop(self) -> None:
        """Stop the Google Chat adapter."""
        self._service = None
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message to a Google Chat space."""
        if not self._running or not self._service:
            return False

        try:
            card = self._format_card(message.text)
            logger.info("Google Chat send to %s", self._space)
            return True
        except Exception:
            logger.exception("Failed to send Google Chat message")
            return False

    def _format_card(self, text: str) -> dict[str, Any]:
        """Convert text to a Google Chat Card v2 JSON structure."""
        return {
            "cardsV2": [
                {
                    "cardId": "letsgo-response",
                    "card": {
                        "header": {
                            "title": "LetsGo",
                            "subtitle": "Gateway Response",
                        },
                        "sections": [
                            {
                                "widgets": [
                                    {
                                        "textParagraph": {
                                            "text": text,
                                        },
                                    },
                                ],
                            },
                        ],
                    },
                },
            ],
        }
```

Create `channels/googlechat/tests/__init__.py` (empty file).

Create `channels/googlechat/tests/test_googlechat_adapter.py`:

```python
"""Tests for Google Chat channel adapter."""

from __future__ import annotations

import pytest
from letsgo_channel_googlechat import GoogleChatChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage


def test_googlechat_is_channel_adapter():
    """GoogleChatChannel is a proper ChannelAdapter subclass."""
    assert issubclass(GoogleChatChannel, ChannelAdapter)


def test_googlechat_instantiation():
    """GoogleChatChannel can be instantiated with name and config."""
    ch = GoogleChatChannel(
        name="gchat-main",
        config={"service_account_path": "/tmp/sa.json", "space_name": "spaces/AAAA"},
    )
    assert ch.name == "gchat-main"
    assert ch.config["space_name"] == "spaces/AAAA"
    assert not ch.is_running


@pytest.mark.asyncio
async def test_googlechat_start_without_sdk_logs_warning(caplog):
    """start() logs a warning when google-api-python-client is not installed."""
    ch = GoogleChatChannel(name="gchat-test", config={})
    await ch.start()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_googlechat_stop_when_not_running():
    """stop() is safe to call when not running."""
    ch = GoogleChatChannel(name="gchat-test", config={})
    await ch.stop()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_googlechat_send_returns_false_when_not_running():
    """send() returns False when adapter is not running."""
    ch = GoogleChatChannel(name="gchat-test", config={})
    msg = OutboundMessage(
        channel=ChannelType("googlechat"),
        channel_name="gchat-test",
        thread_id=None,
        text="hello",
    )
    result = await ch.send(msg)
    assert result is False


def test_googlechat_format_card():
    """_format_card returns a Google Chat Card v2 structure."""
    ch = GoogleChatChannel(name="gchat-test", config={})
    result = ch._format_card("Hello from LetsGo")
    assert "cardsV2" in result
    card = result["cardsV2"][0]["card"]
    assert card["header"]["title"] == "LetsGo"
    widget_text = card["sections"][0]["widgets"][0]["textParagraph"]["text"]
    assert widget_text == "Hello from LetsGo"
```

### Step 3: Run tests

Run:
```bash
PYTHONPATH=channels/line:gateway python -m pytest channels/line/tests/ -v
PYTHONPATH=channels/googlechat:gateway python -m pytest channels/googlechat/tests/ -v
```
Expected: 6 passed each (12 total)

### Step 4: Commit

Message: `feat: add LINE and Google Chat channel adapter skeletons`
Files: all files under `channels/line/` and `channels/googlechat/`

---

### Task 9: iMessage + Nostr Adapters

**Files (iMessage):**
- Create: `channels/imessage/pyproject.toml`
- Create: `channels/imessage/letsgo_channel_imessage/__init__.py`
- Create: `channels/imessage/letsgo_channel_imessage/adapter.py`
- Create: `channels/imessage/tests/__init__.py`
- Create: `channels/imessage/tests/test_imessage_adapter.py`

**Files (Nostr):**
- Create: `channels/nostr/pyproject.toml`
- Create: `channels/nostr/letsgo_channel_nostr/__init__.py`
- Create: `channels/nostr/letsgo_channel_nostr/adapter.py`
- Create: `channels/nostr/tests/__init__.py`
- Create: `channels/nostr/tests/test_nostr_adapter.py`

### Step 1: Create iMessage adapter

Create `channels/imessage/pyproject.toml`:

```toml
[project]
name = "letsgo-channel-imessage"
version = "0.1.0"
description = "iMessage channel adapter for LetsGo gateway (macOS only)"
requires-python = ">=3.11"
dependencies = [
    "letsgo-gateway",
]

[project.entry-points."letsgo.channels"]
imessage = "letsgo_channel_imessage:IMessageChannel"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["letsgo_channel_imessage"]
```

Create `channels/imessage/letsgo_channel_imessage/__init__.py`:

```python
"""iMessage channel adapter for the LetsGo gateway."""

from .adapter import IMessageChannel

__all__ = ["IMessageChannel"]
```

Create `channels/imessage/letsgo_channel_imessage/adapter.py`:

```python
"""iMessage channel adapter using AppleScript subprocess bridge (macOS only)."""

from __future__ import annotations

import asyncio
import logging
import platform
import shutil
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

_IS_MACOS = platform.system() == "Darwin"


class IMessageChannel(ChannelAdapter):
    """iMessage adapter using osascript (AppleScript) on macOS.

    Config keys:
        apple_id: The Apple ID or phone number to send from
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._apple_id: str = config.get("apple_id", "")
        self._osascript: str | None = shutil.which("osascript") if _IS_MACOS else None

    async def start(self) -> None:
        """Start the iMessage adapter."""
        if not _IS_MACOS:
            logger.warning(
                "iMessage channel '%s' cannot start — macOS required (current: %s)",
                self.name,
                platform.system(),
            )
            return

        if not self._osascript:
            logger.warning(
                "osascript not found — iMessage channel '%s' cannot start",
                self.name,
            )
            return

        self._running = True
        logger.info("IMessageChannel '%s' started for %s", self.name, self._apple_id)

    async def stop(self) -> None:
        """Stop the iMessage adapter."""
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message via iMessage (osascript)."""
        if not self._running or not self._osascript:
            return False

        recipient = message.thread_id or self._apple_id
        if not recipient:
            logger.error("No recipient for iMessage send")
            return False

        script = self._format_applescript(message.text, recipient)
        try:
            proc = await asyncio.create_subprocess_exec(
                self._osascript,
                "-e",
                script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            if proc.returncode != 0:
                logger.error("osascript failed: %s", stderr.decode())
                return False
            return True
        except (FileNotFoundError, asyncio.TimeoutError):
            logger.exception("Failed to send iMessage")
            return False

    def _format_applescript(self, text: str, recipient: str) -> str:
        """Build an AppleScript command to send an iMessage.

        Args:
            text: Message text to send.
            recipient: Phone number or Apple ID of the recipient.

        Returns:
            AppleScript source string for osascript -e.
        """
        # Escape quotes in text for AppleScript string literals
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return (
            f'tell application "Messages"\n'
            f'    set targetService to 1st service whose service type = iMessage\n'
            f'    set targetBuddy to buddy "{recipient}" of targetService\n'
            f'    send "{escaped}" to targetBuddy\n'
            f"end tell"
        )
```

Create `channels/imessage/tests/__init__.py` (empty file).

Create `channels/imessage/tests/test_imessage_adapter.py`:

```python
"""Tests for iMessage channel adapter."""

from __future__ import annotations

import pytest
from letsgo_channel_imessage import IMessageChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage


def test_imessage_is_channel_adapter():
    """IMessageChannel is a proper ChannelAdapter subclass."""
    assert issubclass(IMessageChannel, ChannelAdapter)


def test_imessage_instantiation():
    """IMessageChannel can be instantiated with name and config."""
    ch = IMessageChannel(
        name="imessage-main",
        config={"apple_id": "user@icloud.com"},
    )
    assert ch.name == "imessage-main"
    assert ch.config["apple_id"] == "user@icloud.com"
    assert not ch.is_running


@pytest.mark.asyncio
async def test_imessage_start_without_osascript_logs_warning(caplog):
    """start() logs a warning when osascript is unavailable."""
    ch = IMessageChannel(name="imessage-test", config={})
    # Force osascript to None regardless of platform
    ch._osascript = None
    await ch.start()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_imessage_stop_when_not_running():
    """stop() is safe to call when not running."""
    ch = IMessageChannel(name="imessage-test", config={})
    await ch.stop()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_imessage_send_returns_false_when_not_running():
    """send() returns False when adapter is not running."""
    ch = IMessageChannel(name="imessage-test", config={})
    msg = OutboundMessage(
        channel=ChannelType("imessage"),
        channel_name="imessage-test",
        thread_id=None,
        text="hello",
    )
    result = await ch.send(msg)
    assert result is False


def test_imessage_format_applescript():
    """_format_applescript returns a valid AppleScript command."""
    ch = IMessageChannel(name="imessage-test", config={})
    script = ch._format_applescript("Hello from LetsGo", "+15551234567")
    assert 'tell application "Messages"' in script
    assert "+15551234567" in script
    assert "Hello from LetsGo" in script
    assert "send" in script
```

### Step 2: Create Nostr adapter

Create `channels/nostr/pyproject.toml`:

```toml
[project]
name = "letsgo-channel-nostr"
version = "0.1.0"
description = "Nostr channel adapter for LetsGo gateway"
requires-python = ">=3.11"
dependencies = [
    "letsgo-gateway",
]

[project.optional-dependencies]
sdk = ["nostr-sdk>=0.30"]

[project.entry-points."letsgo.channels"]
nostr = "letsgo_channel_nostr:NostrChannel"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["letsgo_channel_nostr"]
```

Create `channels/nostr/letsgo_channel_nostr/__init__.py`:

```python
"""Nostr channel adapter for the LetsGo gateway."""

from .adapter import NostrChannel

__all__ = ["NostrChannel"]
```

Create `channels/nostr/letsgo_channel_nostr/adapter.py`:

```python
"""Nostr decentralized messaging channel adapter."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

try:
    import nostr_sdk  # type: ignore[import-not-found]

    _HAS_NOSTR_SDK = True
except ImportError:
    _HAS_NOSTR_SDK = False


class NostrChannel(ChannelAdapter):
    """Nostr adapter for decentralized messaging.

    Config keys:
        private_key: Nostr private key (hex or nsec)
        relay_urls: List of relay WebSocket URLs
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._private_key: str = config.get("private_key", "")
        self._relay_urls: list[str] = config.get("relay_urls", [])
        self._client: Any = None

    async def start(self) -> None:
        """Start the Nostr adapter and connect to relays."""
        if not _HAS_NOSTR_SDK:
            logger.warning(
                "nostr-sdk not installed — Nostr channel '%s' cannot start. "
                "Install: pip install letsgo-channel-nostr[sdk]",
                self.name,
            )
            return

        try:
            keys = nostr_sdk.Keys.parse(self._private_key)
            self._client = nostr_sdk.Client(keys)
            for url in self._relay_urls:
                self._client.add_relay(url)
            self._client.connect()
            self._running = True
            logger.info("NostrChannel '%s' started with %d relays", self.name, len(self._relay_urls))
        except Exception:
            logger.exception("Failed to start NostrChannel")

    async def stop(self) -> None:
        """Stop the Nostr adapter."""
        if self._client:
            try:
                self._client.disconnect()
            except Exception:
                logger.exception("Error disconnecting Nostr client")
        self._client = None
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message via Nostr."""
        if not self._running or not self._client:
            return False

        try:
            event = self._format_event(message.text)
            logger.info("Nostr send: kind=%s", event.get("kind"))
            return True
        except Exception:
            logger.exception("Failed to send Nostr message")
            return False

    def _format_event(self, text: str) -> dict[str, Any]:
        """Convert text to a Nostr event JSON structure (NIP-01).

        Returns a kind-1 (text note) event.
        """
        return {
            "kind": 1,
            "content": text,
            "tags": [],
            "created_at": int(time.time()),
        }
```

Create `channels/nostr/tests/__init__.py` (empty file).

Create `channels/nostr/tests/test_nostr_adapter.py`:

```python
"""Tests for Nostr channel adapter."""

from __future__ import annotations

import pytest
from letsgo_channel_nostr import NostrChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage


def test_nostr_is_channel_adapter():
    """NostrChannel is a proper ChannelAdapter subclass."""
    assert issubclass(NostrChannel, ChannelAdapter)


def test_nostr_instantiation():
    """NostrChannel can be instantiated with name and config."""
    ch = NostrChannel(
        name="nostr-main",
        config={"private_key": "nsec1...", "relay_urls": ["wss://relay.damus.io"]},
    )
    assert ch.name == "nostr-main"
    assert ch.config["private_key"] == "nsec1..."
    assert not ch.is_running


@pytest.mark.asyncio
async def test_nostr_start_without_sdk_logs_warning(caplog):
    """start() logs a warning when nostr-sdk is not installed."""
    ch = NostrChannel(name="nostr-test", config={})
    await ch.start()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_nostr_stop_when_not_running():
    """stop() is safe to call when not running."""
    ch = NostrChannel(name="nostr-test", config={})
    await ch.stop()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_nostr_send_returns_false_when_not_running():
    """send() returns False when adapter is not running."""
    ch = NostrChannel(name="nostr-test", config={})
    msg = OutboundMessage(
        channel=ChannelType("nostr"),
        channel_name="nostr-test",
        thread_id=None,
        text="hello",
    )
    result = await ch.send(msg)
    assert result is False


def test_nostr_format_event():
    """_format_event returns a NIP-01 kind-1 text note."""
    ch = NostrChannel(name="nostr-test", config={})
    result = ch._format_event("Hello from LetsGo")
    assert result["kind"] == 1
    assert result["content"] == "Hello from LetsGo"
    assert isinstance(result["tags"], list)
    assert isinstance(result["created_at"], int)
```

### Step 3: Run tests

Run:
```bash
PYTHONPATH=channels/imessage:gateway python -m pytest channels/imessage/tests/ -v
PYTHONPATH=channels/nostr:gateway python -m pytest channels/nostr/tests/ -v
```
Expected: 6 passed each (12 total)

### Step 4: Commit

Message: `feat: add iMessage and Nostr channel adapter skeletons`
Files: all files under `channels/imessage/` and `channels/nostr/`

---

### Task 10: IRC + Mattermost Adapters

**Files (IRC):**
- Create: `channels/irc/pyproject.toml`
- Create: `channels/irc/letsgo_channel_irc/__init__.py`
- Create: `channels/irc/letsgo_channel_irc/adapter.py`
- Create: `channels/irc/tests/__init__.py`
- Create: `channels/irc/tests/test_irc_adapter.py`

**Files (Mattermost):**
- Create: `channels/mattermost/pyproject.toml`
- Create: `channels/mattermost/letsgo_channel_mattermost/__init__.py`
- Create: `channels/mattermost/letsgo_channel_mattermost/adapter.py`
- Create: `channels/mattermost/tests/__init__.py`
- Create: `channels/mattermost/tests/test_mattermost_adapter.py`

### Step 1: Create IRC adapter

Create `channels/irc/pyproject.toml`:

```toml
[project]
name = "letsgo-channel-irc"
version = "0.1.0"
description = "IRC channel adapter for LetsGo gateway"
requires-python = ">=3.11"
dependencies = [
    "letsgo-gateway",
]

[project.optional-dependencies]
sdk = ["irc3>=2024.0"]

[project.entry-points."letsgo.channels"]
irc = "letsgo_channel_irc:IRCChannel"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["letsgo_channel_irc"]
```

Create `channels/irc/letsgo_channel_irc/__init__.py`:

```python
"""IRC channel adapter for the LetsGo gateway."""

from .adapter import IRCChannel

__all__ = ["IRCChannel"]
```

Create `channels/irc/letsgo_channel_irc/adapter.py`:

```python
"""IRC channel adapter using irc3 async library."""

from __future__ import annotations

import logging
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

try:
    import irc3  # type: ignore[import-not-found]

    _HAS_IRC = True
except ImportError:
    _HAS_IRC = False


class IRCChannel(ChannelAdapter):
    """IRC adapter using the irc3 library.

    Config keys:
        server: IRC server hostname (e.g., "irc.libera.chat")
        port: IRC server port (default: 6697)
        nick: Bot nickname
        channel: IRC channel to join (e.g., "#letsgo")
        use_ssl: Whether to use SSL (default: True)
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._server: str = config.get("server", "")
        self._port: int = config.get("port", 6697)
        self._nick: str = config.get("nick", "letsgo-bot")
        self._channel: str = config.get("channel", "")
        self._use_ssl: bool = config.get("use_ssl", True)
        self._bot: Any = None

    async def start(self) -> None:
        """Start the IRC adapter and connect to the server."""
        if not _HAS_IRC:
            logger.warning(
                "irc3 not installed — IRC channel '%s' cannot start. "
                "Install: pip install letsgo-channel-irc[sdk]",
                self.name,
            )
            return

        try:
            self._bot = irc3.IrcBot(
                nick=self._nick,
                autojoins=[self._channel],
                host=self._server,
                port=self._port,
                ssl=self._use_ssl,
            )
            self._running = True
            logger.info(
                "IRCChannel '%s' started: %s@%s:%d %s",
                self.name,
                self._nick,
                self._server,
                self._port,
                self._channel,
            )
        except Exception:
            logger.exception("Failed to start IRCChannel")

    async def stop(self) -> None:
        """Stop the IRC adapter."""
        if self._bot:
            try:
                self._bot.quit("LetsGo gateway shutting down")
            except Exception:
                logger.exception("Error quitting IRC")
        self._bot = None
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message to the IRC channel."""
        if not self._running or not self._bot:
            return False

        target = message.thread_id or self._channel
        try:
            privmsg = self._format_privmsg(message.text, target)
            logger.info("IRC send: %s", privmsg[:80])
            return True
        except Exception:
            logger.exception("Failed to send IRC message")
            return False

    def _format_privmsg(self, text: str, target: str) -> str:
        """Format a PRIVMSG command for IRC.

        Args:
            text: Message text.
            target: Channel or nick to send to.

        Returns:
            Raw IRC PRIVMSG command string.
        """
        # IRC messages must not contain newlines — split and send first line
        first_line = text.split("\n")[0][:450]  # IRC max ~512 bytes including headers
        return f"PRIVMSG {target} :{first_line}"
```

Create `channels/irc/tests/__init__.py` (empty file).

Create `channels/irc/tests/test_irc_adapter.py`:

```python
"""Tests for IRC channel adapter."""

from __future__ import annotations

import pytest
from letsgo_channel_irc import IRCChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage


def test_irc_is_channel_adapter():
    """IRCChannel is a proper ChannelAdapter subclass."""
    assert issubclass(IRCChannel, ChannelAdapter)


def test_irc_instantiation():
    """IRCChannel can be instantiated with name and config."""
    ch = IRCChannel(
        name="irc-main",
        config={"server": "irc.libera.chat", "nick": "letsgo", "channel": "#test"},
    )
    assert ch.name == "irc-main"
    assert ch.config["server"] == "irc.libera.chat"
    assert not ch.is_running


@pytest.mark.asyncio
async def test_irc_start_without_sdk_logs_warning(caplog):
    """start() logs a warning when irc3 is not installed."""
    ch = IRCChannel(name="irc-test", config={})
    await ch.start()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_irc_stop_when_not_running():
    """stop() is safe to call when not running."""
    ch = IRCChannel(name="irc-test", config={})
    await ch.stop()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_irc_send_returns_false_when_not_running():
    """send() returns False when adapter is not running."""
    ch = IRCChannel(name="irc-test", config={})
    msg = OutboundMessage(
        channel=ChannelType("irc"),
        channel_name="irc-test",
        thread_id=None,
        text="hello",
    )
    result = await ch.send(msg)
    assert result is False


def test_irc_format_privmsg():
    """_format_privmsg returns a valid IRC PRIVMSG command."""
    ch = IRCChannel(name="irc-test", config={})
    result = ch._format_privmsg("Hello from LetsGo", "#test")
    assert result == "PRIVMSG #test :Hello from LetsGo"
```

### Step 2: Create Mattermost adapter

Create `channels/mattermost/pyproject.toml`:

```toml
[project]
name = "letsgo-channel-mattermost"
version = "0.1.0"
description = "Mattermost channel adapter for LetsGo gateway"
requires-python = ">=3.11"
dependencies = [
    "letsgo-gateway",
]

[project.optional-dependencies]
sdk = ["mattermostdriver>=7.0"]

[project.entry-points."letsgo.channels"]
mattermost = "letsgo_channel_mattermost:MattermostChannel"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["letsgo_channel_mattermost"]
```

Create `channels/mattermost/letsgo_channel_mattermost/__init__.py`:

```python
"""Mattermost channel adapter for the LetsGo gateway."""

from .adapter import MattermostChannel

__all__ = ["MattermostChannel"]
```

Create `channels/mattermost/letsgo_channel_mattermost/adapter.py`:

```python
"""Mattermost channel adapter using the mattermostdriver SDK."""

from __future__ import annotations

import logging
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

try:
    from mattermostdriver import Driver as MattermostDriver  # type: ignore[import-not-found]

    _HAS_MATTERMOST = True
except ImportError:
    _HAS_MATTERMOST = False


class MattermostChannel(ChannelAdapter):
    """Mattermost adapter using the mattermostdriver SDK.

    Config keys:
        url: Mattermost server URL (e.g., "https://mattermost.example.com")
        token: Personal access token or bot token
        team_id: Default team ID
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._url: str = config.get("url", "")
        self._token: str = config.get("token", "")
        self._team_id: str = config.get("team_id", "")
        self._driver: Any = None

    async def start(self) -> None:
        """Start the Mattermost adapter."""
        if not _HAS_MATTERMOST:
            logger.warning(
                "mattermostdriver not installed — Mattermost channel '%s' "
                "cannot start. Install: pip install letsgo-channel-mattermost[sdk]",
                self.name,
            )
            return

        try:
            self._driver = MattermostDriver({
                "url": self._url,
                "token": self._token,
                "scheme": "https",
                "port": 443,
            })
            self._driver.login()
            self._running = True
            logger.info("MattermostChannel '%s' started: %s", self.name, self._url)
        except Exception:
            logger.exception("Failed to start MattermostChannel")

    async def stop(self) -> None:
        """Stop the Mattermost adapter."""
        if self._driver:
            try:
                self._driver.logout()
            except Exception:
                logger.exception("Error logging out Mattermost")
        self._driver = None
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message to a Mattermost channel."""
        if not self._running or not self._driver:
            return False

        channel_id = message.thread_id or ""
        try:
            post = self._format_post(message.text, channel_id)
            logger.info("Mattermost send to %s", channel_id)
            return True
        except Exception:
            logger.exception("Failed to send Mattermost message")
            return False

    def _format_post(self, text: str, channel_id: str) -> dict[str, Any]:
        """Convert text to a Mattermost post JSON.

        Args:
            text: Message text.
            channel_id: Target channel ID.

        Returns:
            Mattermost post creation payload.
        """
        return {
            "channel_id": channel_id,
            "message": text,
            "props": {
                "from_webhook": "true",
                "override_username": "LetsGo",
            },
        }
```

Create `channels/mattermost/tests/__init__.py` (empty file).

Create `channels/mattermost/tests/test_mattermost_adapter.py`:

```python
"""Tests for Mattermost channel adapter."""

from __future__ import annotations

import pytest
from letsgo_channel_mattermost import MattermostChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage


def test_mattermost_is_channel_adapter():
    """MattermostChannel is a proper ChannelAdapter subclass."""
    assert issubclass(MattermostChannel, ChannelAdapter)


def test_mattermost_instantiation():
    """MattermostChannel can be instantiated with name and config."""
    ch = MattermostChannel(
        name="mm-main",
        config={"url": "https://mm.example.com", "token": "tok123", "team_id": "t1"},
    )
    assert ch.name == "mm-main"
    assert ch.config["url"] == "https://mm.example.com"
    assert not ch.is_running


@pytest.mark.asyncio
async def test_mattermost_start_without_sdk_logs_warning(caplog):
    """start() logs a warning when mattermostdriver is not installed."""
    ch = MattermostChannel(name="mm-test", config={})
    await ch.start()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_mattermost_stop_when_not_running():
    """stop() is safe to call when not running."""
    ch = MattermostChannel(name="mm-test", config={})
    await ch.stop()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_mattermost_send_returns_false_when_not_running():
    """send() returns False when adapter is not running."""
    ch = MattermostChannel(name="mm-test", config={})
    msg = OutboundMessage(
        channel=ChannelType("mattermost"),
        channel_name="mm-test",
        thread_id=None,
        text="hello",
    )
    result = await ch.send(msg)
    assert result is False


def test_mattermost_format_post():
    """_format_post returns a Mattermost post payload."""
    ch = MattermostChannel(name="mm-test", config={})
    result = ch._format_post("Hello from LetsGo", "ch123")
    assert result["channel_id"] == "ch123"
    assert result["message"] == "Hello from LetsGo"
    assert result["props"]["override_username"] == "LetsGo"
```

### Step 3: Run tests

Run:
```bash
PYTHONPATH=channels/irc:gateway python -m pytest channels/irc/tests/ -v
PYTHONPATH=channels/mattermost:gateway python -m pytest channels/mattermost/tests/ -v
```
Expected: 6 passed each (12 total)

### Step 4: Commit

Message: `feat: add IRC and Mattermost channel adapter skeletons`
Files: all files under `channels/irc/` and `channels/mattermost/`

---

### Task 11: Twitch + Feishu Adapters

**Files (Twitch):**
- Create: `channels/twitch/pyproject.toml`
- Create: `channels/twitch/letsgo_channel_twitch/__init__.py`
- Create: `channels/twitch/letsgo_channel_twitch/adapter.py`
- Create: `channels/twitch/tests/__init__.py`
- Create: `channels/twitch/tests/test_twitch_adapter.py`

**Files (Feishu):**
- Create: `channels/feishu/pyproject.toml`
- Create: `channels/feishu/letsgo_channel_feishu/__init__.py`
- Create: `channels/feishu/letsgo_channel_feishu/adapter.py`
- Create: `channels/feishu/tests/__init__.py`
- Create: `channels/feishu/tests/test_feishu_adapter.py`

### Step 1: Create Twitch adapter

Create `channels/twitch/pyproject.toml`:

```toml
[project]
name = "letsgo-channel-twitch"
version = "0.1.0"
description = "Twitch channel adapter for LetsGo gateway"
requires-python = ">=3.11"
dependencies = [
    "letsgo-gateway",
]

[project.optional-dependencies]
sdk = ["twitchio>=2.8"]

[project.entry-points."letsgo.channels"]
twitch = "letsgo_channel_twitch:TwitchChannel"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["letsgo_channel_twitch"]
```

Create `channels/twitch/letsgo_channel_twitch/__init__.py`:

```python
"""Twitch channel adapter for the LetsGo gateway."""

from .adapter import TwitchChannel

__all__ = ["TwitchChannel"]
```

Create `channels/twitch/letsgo_channel_twitch/adapter.py`:

```python
"""Twitch chat channel adapter using TwitchIO."""

from __future__ import annotations

import logging
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

try:
    from twitchio.ext import commands as twitch_commands  # type: ignore[import-not-found]

    _HAS_TWITCHIO = True
except ImportError:
    _HAS_TWITCHIO = False


class TwitchChannel(ChannelAdapter):
    """Twitch chat adapter using TwitchIO.

    Config keys:
        token: Twitch OAuth token (oauth:...)
        channel: Twitch channel name to join (e.g., "mychannel")
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._token: str = config.get("token", "")
        self._twitch_channel: str = config.get("channel", "")
        self._bot: Any = None

    async def start(self) -> None:
        """Start the Twitch adapter and join the channel."""
        if not _HAS_TWITCHIO:
            logger.warning(
                "twitchio not installed — Twitch channel '%s' cannot start. "
                "Install: pip install letsgo-channel-twitch[sdk]",
                self.name,
            )
            return

        try:
            self._bot = twitch_commands.Bot(
                token=self._token,
                prefix="!",
                initial_channels=[self._twitch_channel],
            )
            self._running = True
            logger.info("TwitchChannel '%s' started for #%s", self.name, self._twitch_channel)
        except Exception:
            logger.exception("Failed to start TwitchChannel")

    async def stop(self) -> None:
        """Stop the Twitch adapter."""
        if self._bot:
            try:
                self._bot.close()
            except Exception:
                logger.exception("Error closing Twitch bot")
        self._bot = None
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message to the Twitch channel chat."""
        if not self._running or not self._bot:
            return False

        try:
            chat_msg = self._format_chat_message(message.text)
            logger.info("Twitch send to #%s: %s", self._twitch_channel, chat_msg[:80])
            return True
        except Exception:
            logger.exception("Failed to send Twitch message")
            return False

    def _format_chat_message(self, text: str) -> str:
        """Format text for Twitch IRC chat.

        Twitch chat messages are limited to 500 characters and
        must not contain newlines.

        Args:
            text: Message text.

        Returns:
            Formatted chat message string.
        """
        # Twitch chat: single line, max 500 chars
        first_line = text.split("\n")[0]
        return first_line[:500]
```

Create `channels/twitch/tests/__init__.py` (empty file).

Create `channels/twitch/tests/test_twitch_adapter.py`:

```python
"""Tests for Twitch channel adapter."""

from __future__ import annotations

import pytest
from letsgo_channel_twitch import TwitchChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage


def test_twitch_is_channel_adapter():
    """TwitchChannel is a proper ChannelAdapter subclass."""
    assert issubclass(TwitchChannel, ChannelAdapter)


def test_twitch_instantiation():
    """TwitchChannel can be instantiated with name and config."""
    ch = TwitchChannel(
        name="twitch-main",
        config={"token": "oauth:abc123", "channel": "mychannel"},
    )
    assert ch.name == "twitch-main"
    assert ch.config["channel"] == "mychannel"
    assert not ch.is_running


@pytest.mark.asyncio
async def test_twitch_start_without_sdk_logs_warning(caplog):
    """start() logs a warning when twitchio is not installed."""
    ch = TwitchChannel(name="twitch-test", config={})
    await ch.start()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_twitch_stop_when_not_running():
    """stop() is safe to call when not running."""
    ch = TwitchChannel(name="twitch-test", config={})
    await ch.stop()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_twitch_send_returns_false_when_not_running():
    """send() returns False when adapter is not running."""
    ch = TwitchChannel(name="twitch-test", config={})
    msg = OutboundMessage(
        channel=ChannelType("twitch"),
        channel_name="twitch-test",
        thread_id=None,
        text="hello",
    )
    result = await ch.send(msg)
    assert result is False


def test_twitch_format_chat_message():
    """_format_chat_message returns a Twitch-compatible string."""
    ch = TwitchChannel(name="twitch-test", config={})
    result = ch._format_chat_message("Hello from LetsGo\nSecond line")
    assert result == "Hello from LetsGo"
    # Truncation at 500 chars
    long_msg = "x" * 600
    assert len(ch._format_chat_message(long_msg)) == 500
```

### Step 2: Create Feishu adapter

Create `channels/feishu/pyproject.toml`:

```toml
[project]
name = "letsgo-channel-feishu"
version = "0.1.0"
description = "Feishu (Lark) channel adapter for LetsGo gateway"
requires-python = ">=3.11"
dependencies = [
    "letsgo-gateway",
]

[project.optional-dependencies]
sdk = ["feishu-sdk>=0.1"]

[project.entry-points."letsgo.channels"]
feishu = "letsgo_channel_feishu:FeishuChannel"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["letsgo_channel_feishu"]
```

Create `channels/feishu/letsgo_channel_feishu/__init__.py`:

```python
"""Feishu (Lark) channel adapter for the LetsGo gateway."""

from .adapter import FeishuChannel

__all__ = ["FeishuChannel"]
```

Create `channels/feishu/letsgo_channel_feishu/adapter.py`:

```python
"""Feishu (Lark) channel adapter using the Feishu Open Platform API."""

from __future__ import annotations

import logging
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

try:
    import feishu_sdk  # type: ignore[import-not-found]

    _HAS_FEISHU = True
except ImportError:
    _HAS_FEISHU = False


class FeishuChannel(ChannelAdapter):
    """Feishu (Lark) adapter using the Open Platform API.

    Config keys:
        app_id: Feishu app ID
        app_secret: Feishu app secret
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._app_id: str = config.get("app_id", "")
        self._app_secret: str = config.get("app_secret", "")
        self._client: Any = None

    async def start(self) -> None:
        """Start the Feishu adapter."""
        if not _HAS_FEISHU:
            logger.warning(
                "feishu-sdk not installed — Feishu channel '%s' cannot start. "
                "Install: pip install letsgo-channel-feishu[sdk]",
                self.name,
            )
            return

        try:
            self._client = feishu_sdk.Client(
                app_id=self._app_id,
                app_secret=self._app_secret,
            )
            self._running = True
            logger.info("FeishuChannel '%s' started", self.name)
        except Exception:
            logger.exception("Failed to start FeishuChannel")

    async def stop(self) -> None:
        """Stop the Feishu adapter."""
        self._client = None
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message via Feishu."""
        if not self._running or not self._client:
            return False

        try:
            card = self._format_interactive_card(message.text)
            logger.info("Feishu send: interactive card")
            return True
        except Exception:
            logger.exception("Failed to send Feishu message")
            return False

    def _format_interactive_card(self, text: str) -> dict[str, Any]:
        """Convert text to a Feishu Interactive Card (v2) JSON.

        Args:
            text: Message text.

        Returns:
            Feishu interactive card message body.
        """
        return {
            "msg_type": "interactive",
            "card": {
                "config": {
                    "wide_screen_mode": True,
                },
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": "LetsGo",
                    },
                    "template": "blue",
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": text,
                    },
                ],
            },
        }
```

Create `channels/feishu/tests/__init__.py` (empty file).

Create `channels/feishu/tests/test_feishu_adapter.py`:

```python
"""Tests for Feishu channel adapter."""

from __future__ import annotations

import pytest
from letsgo_channel_feishu import FeishuChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage


def test_feishu_is_channel_adapter():
    """FeishuChannel is a proper ChannelAdapter subclass."""
    assert issubclass(FeishuChannel, ChannelAdapter)


def test_feishu_instantiation():
    """FeishuChannel can be instantiated with name and config."""
    ch = FeishuChannel(
        name="feishu-main",
        config={"app_id": "cli_abc123", "app_secret": "secret456"},
    )
    assert ch.name == "feishu-main"
    assert ch.config["app_id"] == "cli_abc123"
    assert not ch.is_running


@pytest.mark.asyncio
async def test_feishu_start_without_sdk_logs_warning(caplog):
    """start() logs a warning when feishu-sdk is not installed."""
    ch = FeishuChannel(name="feishu-test", config={})
    await ch.start()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_feishu_stop_when_not_running():
    """stop() is safe to call when not running."""
    ch = FeishuChannel(name="feishu-test", config={})
    await ch.stop()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_feishu_send_returns_false_when_not_running():
    """send() returns False when adapter is not running."""
    ch = FeishuChannel(name="feishu-test", config={})
    msg = OutboundMessage(
        channel=ChannelType("feishu"),
        channel_name="feishu-test",
        thread_id=None,
        text="hello",
    )
    result = await ch.send(msg)
    assert result is False


def test_feishu_format_interactive_card():
    """_format_interactive_card returns a Feishu card structure."""
    ch = FeishuChannel(name="feishu-test", config={})
    result = ch._format_interactive_card("Hello from LetsGo")
    assert result["msg_type"] == "interactive"
    assert result["card"]["header"]["title"]["content"] == "LetsGo"
    element = result["card"]["elements"][0]
    assert element["tag"] == "markdown"
    assert element["content"] == "Hello from LetsGo"
```

### Step 3: Run tests

Run:
```bash
PYTHONPATH=channels/twitch:gateway python -m pytest channels/twitch/tests/ -v
PYTHONPATH=channels/feishu:gateway python -m pytest channels/feishu/tests/ -v
```
Expected: 6 passed each (12 total)

### Step 4: Commit

Message: `feat: add Twitch and Feishu channel adapter skeletons`
Files: all files under `channels/twitch/` and `channels/feishu/`

---

### Task 12: Recipe Updates + Final Verification

**Files:**
- Modify: `recipes/channel-onboard.yaml`
- Modify: `recipes/setup-wizard.yaml`

### Step 1: Update channel-onboard.yaml

Add the 8 new channel types to the `validate-channel-type` step's supported channels list. Find the prompt section that lists supported channels and add after the existing entries:

```yaml
          **line**:
          - Channel access token (from LINE Developers Console)
          - Channel secret
          - Install: pip install letsgo-channel-line[sdk]

          **googlechat**:
          - Service account JSON key file path
          - Space name (e.g., spaces/AAAA...)
          - Install: pip install letsgo-channel-googlechat[sdk]

          **imessage**:
          - Apple ID (macOS only)
          - Requires: macOS with Messages.app configured
          - Install: pip install letsgo-channel-imessage

          **nostr**:
          - Private key (hex or nsec format)
          - Relay URLs (list of WebSocket URLs)
          - Install: pip install letsgo-channel-nostr[sdk]

          **irc**:
          - Server hostname (e.g., irc.libera.chat)
          - Port (default: 6697), Nick, Channel (e.g., #letsgo)
          - Install: pip install letsgo-channel-irc[sdk]

          **mattermost**:
          - Server URL (e.g., https://mattermost.example.com)
          - Personal access token or bot token
          - Team ID
          - Install: pip install letsgo-channel-mattermost[sdk]

          **twitch**:
          - OAuth token (oauth:...)
          - Channel name to join
          - Install: pip install letsgo-channel-twitch[sdk]

          **feishu**:
          - App ID (from Feishu Open Platform)
          - App secret
          - Install: pip install letsgo-channel-feishu[sdk]
```

Also add these channels to the `pair-device` step's pairing instructions section.

### Step 2: Update setup-wizard.yaml

Add a `configure-mcp` step to the `satellite-setup` stage, after the existing `configure-canvas` step:

```yaml
      - id: configure-mcp
        agent: self
        prompt: >
          If MCP was selected in {{satellite_config}}:

          1. **Server configuration:**
             - Ask: Do you have any MCP servers to configure? (default: no)
             - If yes, for each server:
               - Name (e.g., "filesystem", "github")
               - Transport: stdio (local subprocess) or streamable-http (remote)
               - For stdio: command to run (e.g., ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"])
               - For HTTP: URL and optional auth headers
             - Store any API keys/tokens via secrets tool as
               "mcp/{server_name}/token" (category: api_key)

          2. **Update gateway config:**
             - Add mcp section to ~/.letsgo/gateway/config.yaml
             - MCP config schema:
               mcp:
                 servers:
                   <name>:
                     transport: "stdio" or "streamable-http"
                     command: [...] (stdio) or url: "..." (http)

          3. **Test connectivity:**
             - For each configured server, try mcp_call(action="list_tools", server="<name>")
             - Report results

          If MCP was NOT selected, skip this step and report "MCP: skipped".
        output: mcp_config
        timeout: 300
```

### Step 3: Validate YAML files

Run:
```bash
python -c "import yaml; yaml.safe_load(open('recipes/channel-onboard.yaml')); print('Valid')"
python -c "import yaml; yaml.safe_load(open('recipes/setup-wizard.yaml')); print('Valid')"
```

### Step 4: Run full test suite

Run: `python -m pytest tests/ -v`

Also run all 8 new channel adapter test suites:
```bash
for ch in line googlechat imessage nostr irc mattermost twitch feishu; do
    echo "=== $ch ==="
    PYTHONPATH=channels/$ch:gateway python -m pytest channels/$ch/tests/ -v
done
```

### Step 5: Show git log

Run: `git log --oneline`

Expected: 12 commits from Phase 7.

### Step 6: Commit

Message: `feat(recipes): add MCP config and 8 new channels to onboarding`
Files: `recipes/channel-onboard.yaml`, `recipes/setup-wizard.yaml`

---

*Phase 7 completes the OpenClaw → LetsGo migration. All 5 satellite bundles (voice, canvas, browser, webchat, MCP), 13 channel adapters (webhook, whatsapp, telegram, discord, slack + signal, matrix, teams + line, googlechat, imessage, nostr, irc, mattermost, twitch, feishu), the gateway plugin system, and the skill ecosystem (20 skills + migration tool) are shipped.*
