"""Tests for tool-sandbox module.

Exercises the SandboxTool class directly — simple command execution,
timeouts, status reporting, output truncation, and native environment
stripping. All tests use the native (non-Docker) sandbox for portability.
"""

from __future__ import annotations

import pytest

from amplifier_module_tool_sandbox import SandboxTool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sandbox(**overrides) -> SandboxTool:
    """Create a SandboxTool configured for native execution."""
    defaults = {
        "docker_available": False,
        "timeout_seconds": 30,
        "max_output_bytes": 1_048_576,
    }
    defaults.update(overrides)
    return SandboxTool(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_simple_command() -> None:
    """Run 'echo hello' and verify stdout contains 'hello'."""
    sandbox = _make_sandbox()

    result = await sandbox.execute({
        "operation": "execute",
        "command": "echo hello",
    })

    assert result.success is True
    assert result.output is not None
    assert "hello" in result.output["stdout"]
    assert result.output["exit_code"] == 0
    assert result.output["sandbox_type"] == "native"


@pytest.mark.asyncio
async def test_execute_timeout() -> None:
    """A command exceeding the timeout should be killed and return success=False."""
    sandbox = _make_sandbox(timeout_seconds=1)

    result = await sandbox.execute({
        "operation": "execute",
        "command": "sleep 60",
        "timeout": 1,
    })

    assert result.success is False
    assert result.error is not None
    assert "timed out" in result.error["message"].lower()


@pytest.mark.asyncio
async def test_status_operation() -> None:
    """The 'status' operation reports sandbox type and configuration."""
    sandbox = _make_sandbox()

    result = await sandbox.execute({"operation": "status"})

    assert result.success is True
    assert result.output["sandbox_type"] == "native"
    assert result.output["docker_available"] is False
    assert result.output["timeout_seconds"] == 30


@pytest.mark.asyncio
async def test_status_docker_mode() -> None:
    """Status with docker_available=True should report 'docker' type."""
    sandbox = _make_sandbox(docker_available=True)

    result = await sandbox.execute({"operation": "status"})

    assert result.success is True
    assert result.output["sandbox_type"] == "docker"
    assert result.output["docker_available"] is True
    assert result.output["image"] is not None


@pytest.mark.asyncio
async def test_output_truncation() -> None:
    """Large output should be truncated to max_output_bytes."""
    sandbox = _make_sandbox(max_output_bytes=64)

    # Generate output larger than 64 bytes
    result = await sandbox.execute({
        "operation": "execute",
        "command": "python3 -c \"print('A' * 500)\"",
    })

    assert result.success is True
    stdout = result.output["stdout"]
    assert "truncated" in stdout.lower()


@pytest.mark.asyncio
async def test_restricted_environment() -> None:
    """Native sandbox should strip most env vars — HOME, PATH, LANG only."""
    sandbox = _make_sandbox()

    result = await sandbox.execute({
        "operation": "execute",
        "command": "env",
    })

    assert result.success is True
    stdout = result.output["stdout"]
    env_lines = [line for line in stdout.strip().splitlines() if "=" in line]
    env_keys = {line.split("=", 1)[0] for line in env_lines}

    # Native sandbox sets exactly PATH, HOME, LANG
    assert "PATH" in env_keys
    assert "HOME" in env_keys
    assert "LANG" in env_keys

    # Typical host-leaked vars should NOT be present
    for leaked in ("USER", "SHELL", "LOGNAME", "TERM"):
        assert leaked not in env_keys, f"Env var {leaked} should be stripped"


@pytest.mark.asyncio
async def test_execute_missing_command() -> None:
    """execute with no command returns a validation error."""
    sandbox = _make_sandbox()

    result = await sandbox.execute({
        "operation": "execute",
    })

    assert result.success is False
    assert "command" in result.error["message"].lower()


@pytest.mark.asyncio
async def test_unknown_operation() -> None:
    """An unknown operation returns an error."""
    sandbox = _make_sandbox()

    result = await sandbox.execute({"operation": "fly"})

    assert result.success is False
    assert "unknown" in result.error["message"].lower()


@pytest.mark.asyncio
async def test_nonzero_exit_code() -> None:
    """A command with non-zero exit populates error and success=False."""
    sandbox = _make_sandbox()

    result = await sandbox.execute({
        "operation": "execute",
        "command": "exit 42",
    })

    assert result.success is False
    assert result.output is None or result.error is not None
    assert result.error is not None
