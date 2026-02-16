"""Sandboxed command execution with resource limits and isolation.

Provides a Tool module that executes commands in either a Docker container
(preferred) or a restricted native subprocess, with enforced timeouts,
resource limits, and output truncation.

Sandbox strategy (layered fallback):
  1. Docker — ephemeral container with memory/cpu limits and network isolation
  2. Native — restricted subprocess with minimal PATH and stripped environment
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import time
from typing import Any

from amplifier_core.models import ToolResult

__amplifier_module_type__ = "tool"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_IMAGE = "python:3.11-slim"
_DEFAULT_MEMORY_LIMIT = "512m"
_DEFAULT_CPU_LIMIT = "1.0"
_DEFAULT_NETWORK = "none"
_DEFAULT_TIMEOUT = 120
_DEFAULT_MAX_OUTPUT_BYTES = 1_048_576  # 1 MB
_NATIVE_PATH = "/usr/local/bin:/usr/bin:/bin"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _check_docker_available() -> bool:
    """Return True if the Docker daemon is reachable."""
    docker_bin = shutil.which("docker")
    if docker_bin is None:
        return False
    try:
        proc = await asyncio.create_subprocess_exec(
            docker_bin,
            "info",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=10)
        return proc.returncode == 0
    except (asyncio.TimeoutError, OSError):
        return False


def _truncate(data: bytes, limit: int) -> str:
    """Decode bytes to UTF-8, truncating to *limit* bytes if needed."""
    if len(data) <= limit:
        return data.decode("utf-8", errors="replace")
    truncated = data[:limit].decode("utf-8", errors="replace")
    return (
        truncated
        + f"\n\n... [truncated — {len(data)} bytes total, showing first {limit}]"
    )


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------


class SandboxTool:
    """Execute commands inside a sandboxed environment.

    Prefers Docker when available; falls back to a restricted native
    subprocess otherwise.  All executions are subject to a hard timeout,
    output size cap, and environment stripping.
    """

    def __init__(
        self,
        *,
        docker_available: bool,
        image: str = _DEFAULT_IMAGE,
        memory_limit: str = _DEFAULT_MEMORY_LIMIT,
        cpu_limit: str = _DEFAULT_CPU_LIMIT,
        default_network: str = _DEFAULT_NETWORK,
        timeout_seconds: int = _DEFAULT_TIMEOUT,
        max_output_bytes: int = _DEFAULT_MAX_OUTPUT_BYTES,
    ) -> None:
        self._docker_available = docker_available
        self._image = image
        self._memory_limit = memory_limit
        self._cpu_limit = cpu_limit
        self._default_network = default_network
        self._timeout_seconds = timeout_seconds
        self._max_output_bytes = max_output_bytes

    # -- Tool protocol ------------------------------------------------------

    @property
    def name(self) -> str:
        return "sandbox"

    @property
    def description(self) -> str:
        return (
            "Execute a shell command in a sandboxed environment with resource "
            "limits and isolation.  Uses Docker when available, otherwise falls "
            "back to a restricted native subprocess."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["execute", "status"],
                    "description": "Operation to perform.",
                },
                "command": {
                    "type": "string",
                    "description": "Shell command to execute (required for 'execute').",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Per-execution timeout in seconds"
                    " (overrides default).",
                },
                "network": {
                    "type": "string",
                    "enum": ["none", "host"],
                    "description": "Docker network mode. Ignored in native fallback.",
                },
                "workdir": {
                    "type": "string",
                    "description": "Working directory for the command.",
                },
            },
            "required": ["operation"],
        }

    async def execute(self, input: dict[str, Any]) -> ToolResult:
        """Dispatch to the requested operation."""
        operation = input.get("operation")
        if operation == "status":
            return self._handle_status()
        if operation == "execute":
            return await self._handle_execute(input)
        return ToolResult(
            success=False,
            error={
                "message": f"Unknown operation: {operation!r}."
                " Use 'execute' or 'status'.",
            },
        )

    # -- Operations ---------------------------------------------------------

    def _handle_status(self) -> ToolResult:
        sandbox_type = "docker" if self._docker_available else "native"
        return ToolResult(
            success=True,
            output={
                "sandbox_type": sandbox_type,
                "docker_available": self._docker_available,
                "image": self._image if self._docker_available else None,
                "memory_limit": self._memory_limit if self._docker_available else None,
                "cpu_limit": self._cpu_limit if self._docker_available else None,
                "default_network": self._default_network
                if self._docker_available
                else None,
                "timeout_seconds": self._timeout_seconds,
                "max_output_bytes": self._max_output_bytes,
            },
        )

    async def _handle_execute(self, input: dict[str, Any]) -> ToolResult:
        command = input.get("command")
        if not command or not isinstance(command, str):
            return ToolResult(
                success=False,
                error={
                    "message": "The 'command' field is required"
                    " and must be a non-empty string."
                },
            )

        timeout = input.get("timeout", self._timeout_seconds)
        network = input.get("network", self._default_network)
        workdir = input.get("workdir")

        if self._docker_available:
            return await self._run_docker(
                command, timeout=timeout, network=network, workdir=workdir
            )
        return await self._run_native(command, timeout=timeout, workdir=workdir)

    # -- Docker execution ---------------------------------------------------

    async def _run_docker(
        self,
        command: str,
        *,
        timeout: int,
        network: str,
        workdir: str | None,
    ) -> ToolResult:
        host_cwd = workdir or os.getcwd()
        container_workdir = "/workspace"

        cmd = [
            "docker",
            "run",
            "--rm",
            f"--memory={self._memory_limit}",
            f"--cpus={self._cpu_limit}",
            f"--network={network}",
            "-v",
            f"{host_cwd}:{container_workdir}:rw",
            "-w",
            container_workdir,
            self._image,
            "sh",
            "-c",
            command,
        ]

        logger.info(
            "sandbox.docker: executing command (timeout=%ds, network=%s, image=%s)",
            timeout,
            network,
            self._image,
        )

        return await self._run_subprocess(cmd, timeout=timeout, sandbox_type="docker")

    # -- Native execution ---------------------------------------------------

    async def _run_native(
        self,
        command: str,
        *,
        timeout: int,
        workdir: str | None,
    ) -> ToolResult:
        cwd = workdir or os.getcwd()

        # Build a minimal, stripped environment.
        tmp_home = tempfile.mkdtemp(prefix="sandbox_home_")
        env = {
            "PATH": _NATIVE_PATH,
            "HOME": tmp_home,
            "LANG": "C.UTF-8",
        }

        logger.info(
            "sandbox.native: executing command (timeout=%ds, workdir=%s)", timeout, cwd
        )

        try:
            return await self._run_subprocess(
                ["sh", "-c", command],
                timeout=timeout,
                sandbox_type="native",
                env=env,
                cwd=cwd,
            )
        finally:
            # Best-effort cleanup of the temp HOME directory.
            shutil.rmtree(tmp_home, ignore_errors=True)

    # -- Shared subprocess runner -------------------------------------------

    async def _run_subprocess(
        self,
        cmd: list[str],
        *,
        timeout: int,
        sandbox_type: str,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> ToolResult:
        start = time.monotonic()
        timed_out = False

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=cwd,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                timed_out = True
                # Attempt graceful termination, then hard kill.
                try:
                    proc.terminate()
                    # Give it a moment to clean up before killing.
                    await asyncio.sleep(0.5)
                    if proc.returncode is None:
                        proc.kill()
                except ProcessLookupError:
                    pass
                # Collect whatever output was produced.
                stdout_bytes = b""
                stderr_bytes = b""
                try:
                    stdout_bytes, stderr_bytes = await asyncio.wait_for(
                        proc.communicate(),
                        timeout=5,
                    )
                except (asyncio.TimeoutError, ProcessLookupError):
                    pass

        except FileNotFoundError:
            duration_ms = int((time.monotonic() - start) * 1000)
            executable = cmd[0]
            logger.error(
                "sandbox.%s: executable not found: %s", sandbox_type, executable
            )
            return ToolResult(
                success=False,
                error={
                    "message": f"Executable not found: {executable}",
                    "duration_ms": duration_ms,
                    "sandbox_type": sandbox_type,
                },
            )
        except OSError as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.error("sandbox.%s: OS error: %s", sandbox_type, exc)
            return ToolResult(
                success=False,
                error={
                    "message": f"OS error launching process: {exc}",
                    "duration_ms": duration_ms,
                    "sandbox_type": sandbox_type,
                },
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        exit_code = proc.returncode if proc.returncode is not None else -1

        stdout = _truncate(stdout_bytes, self._max_output_bytes)
        stderr = _truncate(stderr_bytes, self._max_output_bytes)

        if timed_out:
            logger.warning(
                "sandbox.%s: command timed out after %ds (exit_code=%s)",
                sandbox_type,
                timeout,
                exit_code,
            )
            return ToolResult(
                success=False,
                error={
                    "message": f"Command timed out after {timeout}s",
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": exit_code,
                    "duration_ms": duration_ms,
                    "sandbox_type": sandbox_type,
                },
            )

        logger.info(
            "sandbox.%s: command completed (exit_code=%d, duration=%dms)",
            sandbox_type,
            exit_code,
            duration_ms,
        )

        return ToolResult(
            success=exit_code == 0,
            output={
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "sandbox_type": sandbox_type,
            },
            error=(
                {"message": f"Command exited with code {exit_code}", "stderr": stderr}
                if exit_code != 0
                else None
            ),
        )


# ---------------------------------------------------------------------------
# Module mount
# ---------------------------------------------------------------------------


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> None:
    """Mount the sandbox tool into the Amplifier coordinator.

    Config keys:
        image             Docker image (default: python:3.11-slim)
        memory_limit      Docker memory limit (default: 512m)
        cpu_limit          Docker CPU limit (default: 1.0)
        default_network   Docker network mode (default: none)
        timeout_seconds   Max seconds per execution (default: 120)
        max_output_bytes  Truncate output beyond this size (default: 1 MB)
    """
    config = config or {}

    docker_available = await _check_docker_available()
    sandbox_type = "docker" if docker_available else "native"
    logger.info(
        "tool-sandbox: Docker %s — using %s sandbox",
        "available" if docker_available else "unavailable",
        sandbox_type,
    )

    tool = SandboxTool(
        docker_available=docker_available,
        image=config.get("image", _DEFAULT_IMAGE),
        memory_limit=config.get("memory_limit", _DEFAULT_MEMORY_LIMIT),
        cpu_limit=str(config.get("cpu_limit", _DEFAULT_CPU_LIMIT)),
        default_network=config.get("default_network", _DEFAULT_NETWORK),
        timeout_seconds=int(config.get("timeout_seconds", _DEFAULT_TIMEOUT)),
        max_output_bytes=int(config.get("max_output_bytes", _DEFAULT_MAX_OUTPUT_BYTES)),
    )

    await coordinator.mount("tools", tool, name="tool-sandbox")
    logger.info("tool-sandbox: mounted (sandbox_type=%s)", sandbox_type)
