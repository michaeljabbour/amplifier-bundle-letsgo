"""Shared fixtures for amplifier-bundle-letsgo tests.

Provides a MockCoordinator that mimics the kernel's ModuleCoordinator,
sys.path setup so each module package is importable, and a tmp_dir fixture.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Import path setup: add each module's parent dir so bare imports work
# ---------------------------------------------------------------------------

_BUNDLE_ROOT = Path(__file__).resolve().parent.parent
_MODULE_DIRS = [
    _BUNDLE_ROOT / "modules" / "hooks-tool-policy",
    _BUNDLE_ROOT / "modules" / "hooks-telemetry",
    _BUNDLE_ROOT / "modules" / "hooks-memory-inject",
    _BUNDLE_ROOT / "modules" / "tool-sandbox",
    _BUNDLE_ROOT / "modules" / "tool-secrets",
]

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
