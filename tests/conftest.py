"""Shared fixtures for amplifier-bundle-letsgo tests.

Provides a MockCoordinator that mimics the kernel's ModuleCoordinator,
sys.path setup so each module package is importable, and a tmp_dir fixture.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Stub amplifier_core.models so tests run without the full amplifier install
# ---------------------------------------------------------------------------
if "amplifier_core" not in sys.modules:

    class _ToolResult:
        def __init__(
            self,
            success: bool = True,
            output: Any = None,
            error: Any = None,
        ):
            self.success = success
            self.output = output
            self.error = error

    class _HookResult:
        def __init__(self, action: str = "continue", **kwargs: Any):
            self.action = action
            # Defaults matching amplifier_core.models.HookResult
            self.data = None
            self.reason = None
            self.context_injection = None
            self.context_injection_role = "system"
            self.ephemeral = False
            self.approval_prompt = None
            self.approval_options = None
            self.approval_timeout = 300.0
            self.approval_default = "deny"
            self.suppress_output = False
            self.user_message = None
            self.user_message_level = "info"
            self.append_to_last_tool_result = False
            # Override with any explicitly passed kwargs
            for k, v in kwargs.items():
                setattr(self, k, v)

    _amp = types.ModuleType("amplifier_core")
    _models = types.ModuleType("amplifier_core.models")
    _models.ToolResult = _ToolResult  # type: ignore[attr-defined]
    _models.HookResult = _HookResult  # type: ignore[attr-defined]
    _amp.models = _models  # type: ignore[attr-defined]
    sys.modules["amplifier_core"] = _amp
    sys.modules["amplifier_core.models"] = _models

# ---------------------------------------------------------------------------
# Import path setup: add each module's parent dir so bare imports work
# ---------------------------------------------------------------------------

_BUNDLE_ROOT = Path(__file__).resolve().parent.parent

# Auto-discover module directories: any subdir of modules/ that contains a
# Python package
_MODULE_DIRS: list[Path] = []
_modules_root = _BUNDLE_ROOT / "modules"
if _modules_root.is_dir():
    for child in sorted(_modules_root.iterdir()):
        if child.is_dir() and not child.name.startswith((".", "_")):
            _MODULE_DIRS.append(child)

# Gateway package lives alongside modules/
_gateway_dir = _BUNDLE_ROOT / "gateway"
if _gateway_dir.is_dir():
    _MODULE_DIRS.append(_gateway_dir)

for d in _MODULE_DIRS:
    d_str = str(d)
    if d_str not in sys.path:
        sys.path.insert(0, d_str)


# ---------------------------------------------------------------------------
# MockCoordinator
# ---------------------------------------------------------------------------


class _MockHooks:
    """Records hook registrations made via coordinator.hooks.register()."""

    def __init__(self) -> None:
        self.registrations: list[dict[str, Any]] = []

    def register(
        self,
        event: str | None = None,
        handler: Any = None,
        *,
        priority: int = 50,
        name: str = "",
    ) -> Any:
        """Record the registration and return an unregister callable."""
        entry = {
            "event": event,
            "handler": handler,
            "priority": priority,
            "name": name,
        }
        self.registrations.append(entry)

        def _unregister() -> None:
            self.registrations.remove(entry)

        return _unregister


class MockCoordinator:
    """Minimal stand-in for the Amplifier ModuleCoordinator.

    Tracks:
      - hooks.register() calls
      - mount() calls
      - register_capability() / get_capability() calls
      - register_contributor() calls
    """

    def __init__(self) -> None:
        self.hooks = _MockHooks()
        self.mounts: list[dict[str, Any]] = []
        self.capabilities: dict[str, Any] = {}
        self.contributors: list[dict[str, Any]] = []

    async def mount(self, category: str, obj: Any, *, name: str = "") -> None:
        self.mounts.append({"category": category, "obj": obj, "name": name})

    def register_capability(self, name: str, func: Any) -> None:
        self.capabilities[name] = func

    def get_capability(self, name: str) -> Any:
        return self.capabilities.get(name)

    def register_contributor(self, name: str, func: Any) -> None:
        self.contributors.append({"name": name, "func": func})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_coordinator() -> MockCoordinator:
    """Return a fresh MockCoordinator for each test."""
    return MockCoordinator()


@pytest.fixture()
def tmp_dir(tmp_path: Path) -> Path:
    """Return pytest's tmp_path (convenience alias)."""
    return tmp_path
