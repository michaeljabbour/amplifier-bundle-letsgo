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
