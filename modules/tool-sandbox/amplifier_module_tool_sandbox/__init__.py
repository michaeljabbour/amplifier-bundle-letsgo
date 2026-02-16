"""Sandboxed command execution with resource limits and isolation.

Provides a Tool module that executes commands in either a Docker container
(preferred) or a restricted native subprocess, with enforced timeouts,
resource limits, and output truncation.

Sandbox strategy (layered fallback):
  1. Docker — ephemeral container with memory/cpu limits and network isolation
  2. Native — restricted subprocess with minimal PATH and stripped environment

Security controls:
  - ``native_fallback`` — "deny" (refuse), "warn" (execute with warning),
    or "allow" (silent fallback).  Default: ``"warn"``.
  - ``mount_mode`` — Docker volume mount mode: ``"ro"`` (read-only, default)
    or ``"rw"`` (read-write).
  - ``workdir`` is validated and resolved to prevent path traversal.
  - Network mode is restricted to ``"none"`` only.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
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
_ALLOWED_NETWORKS = frozenset({"none"})
_ALLOWED_NATIVE_FALLBACK = frozenset({"deny", "warn", "allow"})
_ALLOWED_MOUNT_MODES = frozenset({"ro", "rw"})


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

    Security controls:
      - ``native_fallback`` controls behavior when Docker is unavailable:
        ``"deny"`` refuses execution, ``"warn"`` executes with a warning
        (default), ``"allow"`` silently falls back.
      - ``mount_mode`` controls Docker volume permissions: ``"ro"``
        (read-only, default) or ``"rw"`` (read-write).
      - ``workdir`` is validated against path traversal.
      - Network mode is restricted to ``"none"`` only.
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
        native_fallback: str = "warn",
        mount_mode: str = "ro",
    ) -> None:
        self._docker_available = docker_available
        self._image = image
        self._memory_limit = memory_limit
        self._cpu_limit = cpu_limit
        self._default_network = default_network
        self._timeout_seconds = timeout_seconds
        self._max_output_bytes = max_output_bytes

        # Security controls
        if native_fallback not in _ALLOWED_NATIVE_FALLBACK:
            raise ValueError(
                f"native_fallback must be one of {sorted(_ALLOWED_NATIVE_FALLBACK)}, "
                f"got {native_fallback!r}"
            )
        self._native_fallback = native_fallback

        if mount_mode not in _ALLOWED_MOUNT_MODES:
            raise ValueError(
                f"mount_mode must be one of {sorted(_ALLOWED_MOUNT_MODES)}, "
                f"got {mount_mode!r}"
            )
        self._mount_mode = mount_mode

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
                    "enum": ["none"],
                    "description": "Docker network mode. Only 'none' (isolated)"
                    " is permitted.",
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
                "native_fallback": self._native_fallback,
                "mount_mode": self._mount_mode if self._docker_available else None,
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

    @staticmethod
    def _validate_workdir(workdir: str) -> str | None:
        """Resolve *workdir* and reject path-traversal attempts.

        Returns the resolved absolute path string, or ``None`` if the
        path is invalid (contains ``..`` after resolution, does not exist,
        or is not a directory).
        """
        try:
            resolved = str(Path(workdir).resolve())
        except (OSError, ValueError):
            return None
        # Reject if the raw input contained ".." sequences that could
        # indicate traversal intent, even if resolve() normalised them.
        if ".." in workdir:
            logger.warning("sandbox: rejected workdir with '..' sequence: %s", workdir)
            return None
        if not Path(resolved).is_dir():
            return None
        return resolved

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

        # Validate network mode — only isolated networking is allowed.
        if network not in _ALLOWED_NETWORKS:
            return ToolResult(
                success=False,
                error={
                    "message": f"Network mode {network!r} is not allowed. "
                    f"Permitted values: {sorted(_ALLOWED_NETWORKS)}.",
                },
            )

        # Validate and sanitise workdir.
        if workdir is not None:
            validated = self._validate_workdir(workdir)
            if validated is None:
                return ToolResult(
                    success=False,
                    error={
                        "message": "Invalid workdir: must be an existing directory "
                        "without path-traversal sequences.",
                    },
                )
            workdir = validated

        if self._docker_available:
            return await self._run_docker(
                command, timeout=timeout, network=network, workdir=workdir
            )

        # -- Native fallback gated by policy --------------------------------
        if self._native_fallback == "deny":
            logger.warning(
                "sandbox: Docker unavailable and native_fallback='deny' — "
                "refusing execution"
            )
            return ToolResult(
                success=False,
                error={
                    "message": "Docker is not available and native_fallback='deny'. "
                    "Sandbox execution refused — native mode provides only "
                    "timeout enforcement and environment stripping, not full "
                    "resource isolation.  Install Docker or set "
                    "native_fallback='warn' to proceed with reduced isolation.",
                    "sandbox_type": "none",
                },
            )

        if self._native_fallback == "warn":
            logger.warning(
                "sandbox: Docker unavailable — executing in native mode "
                "with LIMITED isolation"
            )

        result = await self._run_native(command, timeout=timeout, workdir=workdir)

        # Inject a warning into the output for 'warn' mode.
        if self._native_fallback == "warn" and isinstance(result.output, dict):
            result.output["isolation_warning"] = (
                "Executed in native mode (no Docker).  Native sandbox provides "
                "only timeout enforcement and environment stripping — no memory, "
                "CPU, or network isolation.  Consider installing Docker for "
                "full sandboxing."
            )

        return result

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
            f"{host_cwd}:{container_workdir}:{self._mount_mode}",
            "-w",
            container_workdir,
            self._image,
            "sh",
            "-c",
            command,
        ]

        logger.info(
            "sandbox.docker: executing command (timeout=%ds, network=%s, "
            "mount=%s, image=%s)",
            timeout,
            network,
            self._mount_mode,
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
        native_fallback   "deny" | "warn" | "allow" (default: "warn")
        mount_mode        Docker volume mount mode: "ro" | "rw" (default: "ro")
    """
    config = config or {}

    docker_available = await _check_docker_available()
    native_fallback = config.get("native_fallback", "warn")
    sandbox_type = "docker" if docker_available else "native"
    logger.info(
        "tool-sandbox: Docker %s — using %s sandbox (native_fallback=%s)",
        "available" if docker_available else "unavailable",
        sandbox_type,
        native_fallback,
    )

    tool = SandboxTool(
        docker_available=docker_available,
        image=config.get("image", _DEFAULT_IMAGE),
        memory_limit=config.get("memory_limit", _DEFAULT_MEMORY_LIMIT),
        cpu_limit=str(config.get("cpu_limit", _DEFAULT_CPU_LIMIT)),
        default_network=config.get("default_network", _DEFAULT_NETWORK),
        timeout_seconds=int(config.get("timeout_seconds", _DEFAULT_TIMEOUT)),
        max_output_bytes=int(config.get("max_output_bytes", _DEFAULT_MAX_OUTPUT_BYTES)),
        native_fallback=native_fallback,
        mount_mode=config.get("mount_mode", "ro"),
    )

    await coordinator.mount("tools", tool, name="tool-sandbox")
    logger.info(
        "tool-sandbox: mounted (sandbox_type=%s, mount_mode=%s)",
        sandbox_type,
        tool._mount_mode,
    )
