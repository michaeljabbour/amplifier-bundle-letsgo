# OpenClaw → LetsGo Migration: Phase 0 & Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the shared plugin foundation (Phase 0) and harden the gateway with new channel adapters (Phase 1) for the OpenClaw → LetsGo migration.

**Architecture:** Replace the gateway daemon's hardcoded channel registry (`_CHANNEL_CLASSES` + `_STUB_CHANNELS`) with a `discover_channels()` function that combines lazy built-in imports with Python entry-point plugin discovery (`importlib.metadata.entry_points(group="letsgo.channels")`). Make `ChannelType` extensible so plugin channels work without modifying the enum. Add a `DisplaySystem` protocol for canvas/chat routing. Create three new channel adapter packages (Signal, Matrix, Teams) as separate pip-installable packages with entry-point registration.

**Tech Stack:** Python 3.11+, pytest + pytest-asyncio, importlib.metadata, aiohttp, hatchling (build backend)

---

## Phase 0: Shared Foundation

### Task 1: Channel Registry with Entry-Point Discovery

**Files:**
- Create: `gateway/letsgo_gateway/channels/registry.py`
- Test: `tests/test_gateway/test_registry.py`

**Step 1: Write the failing tests**

Create `tests/test_gateway/test_registry.py`:

```python
"""Tests for channel registry discovery."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from letsgo_gateway.channels.registry import discover_channels
from letsgo_gateway.channels.base import ChannelAdapter


def test_discover_builtins_includes_webhook():
    """Webhook is always discovered (no optional deps)."""
    channels = discover_channels()
    assert "webhook" in channels
    from letsgo_gateway.channels.webhook import WebhookChannel

    assert channels["webhook"] is WebhookChannel


def test_discover_builtins_includes_whatsapp():
    """WhatsApp is always discovered (no optional deps)."""
    channels = discover_channels()
    assert "whatsapp" in channels
    from letsgo_gateway.channels.whatsapp import WhatsAppChannel

    assert channels["whatsapp"] is WhatsAppChannel


def test_discover_builtins_graceful_degradation():
    """Missing SDK channels are silently skipped."""
    with patch(
        "letsgo_gateway.channels.registry._lazy_import",
        side_effect=ImportError("no module"),
    ):
        channels = discover_channels()
    # Should return empty dict when ALL imports fail
    assert isinstance(channels, dict)


def test_discover_entry_points_loads_plugin():
    """Entry-point plugins are discovered and loaded."""
    # Create a mock entry point
    mock_ep = MagicMock()
    mock_ep.name = "fakechat"
    mock_ep.load.return_value = type(
        "FakeChannel",
        (ChannelAdapter,),
        {
            "start": lambda self: None,
            "stop": lambda self: None,
            "send": lambda self, msg: True,
        },
    )

    with patch(
        "letsgo_gateway.channels.registry.entry_points",
        return_value=[mock_ep],
    ):
        channels = discover_channels()

    assert "fakechat" in channels
    mock_ep.load.assert_called_once()


def test_discover_entry_point_overrides_builtin():
    """Entry-point plugin with same name as built-in overrides it."""

    class CustomWebhook(ChannelAdapter):
        async def start(self) -> None: ...
        async def stop(self) -> None: ...
        async def send(self, message) -> bool:
            return True

    mock_ep = MagicMock()
    mock_ep.name = "webhook"
    mock_ep.load.return_value = CustomWebhook

    with patch(
        "letsgo_gateway.channels.registry.entry_points",
        return_value=[mock_ep],
    ):
        channels = discover_channels()

    assert channels["webhook"] is CustomWebhook
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/dev/amplifier-bundle-letsgo && python -m pytest tests/test_gateway/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'letsgo_gateway.channels.registry'`

**Step 3: Write minimal implementation**

Create `gateway/letsgo_gateway/channels/registry.py`:

```python
"""Channel adapter discovery: built-ins + entry-point plugins."""

from __future__ import annotations

import importlib
import logging
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import ChannelAdapter

logger = logging.getLogger(__name__)

# Built-in channels: name -> fully-qualified class path
# Webhook and WhatsApp have no optional deps (always available).
# Telegram, Discord, Slack require optional SDK packages.
_BUILTINS: dict[str, str] = {
    "webhook": "letsgo_gateway.channels.webhook.WebhookChannel",
    "whatsapp": "letsgo_gateway.channels.whatsapp.WhatsAppChannel",
    "telegram": "letsgo_gateway.channels.telegram.TelegramChannel",
    "discord": "letsgo_gateway.channels.discord.DiscordChannel",
    "slack": "letsgo_gateway.channels.slack.SlackChannel",
}


def _lazy_import(dotpath: str) -> type[ChannelAdapter]:
    """Import a class by its fully-qualified dotted path.

    Raises ImportError if the module or its SDK dependencies are missing.
    """
    module_path, class_name = dotpath.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def discover_channels() -> dict[str, type[ChannelAdapter]]:
    """Discover channel adapters from built-ins + entry points.

    1. Lazy-imports built-in channels (graceful degradation on missing SDK).
    2. Discovers entry-point plugins via ``letsgo.channels`` group.
       Entry points override built-ins with the same name.

    Returns:
        Mapping of channel name -> adapter class.
    """
    channels: dict[str, type[ChannelAdapter]] = {}

    # 1. Built-in channels (lazy import, graceful degradation)
    for name, dotpath in _BUILTINS.items():
        try:
            channels[name] = _lazy_import(dotpath)
        except ImportError:
            logger.debug("Channel '%s' SDK not installed — skipping", name)

    # 2. Entry-point channels (group="letsgo.channels")
    for ep in entry_points(group="letsgo.channels"):
        try:
            channels[ep.name] = ep.load()
        except Exception:
            logger.warning(
                "Failed to load channel plugin '%s' from entry point",
                ep.name,
                exc_info=True,
            )

    return channels
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/dev/amplifier-bundle-letsgo && python -m pytest tests/test_gateway/test_registry.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add gateway/letsgo_gateway/channels/registry.py tests/test_gateway/test_registry.py
git commit -m "feat(gateway): add channel registry with entry-point discovery"
```

---

### Task 2: Migrate daemon.py to Use Registry

**Files:**
- Modify: `gateway/letsgo_gateway/daemon.py` (lines 1-30 and 185-211)
- Test: `tests/test_gateway/test_daemon.py` (existing tests must keep passing)
- Test: `tests/test_gateway/test_registry.py` (add daemon integration test)

**Step 1: Write the failing test**

Append to `tests/test_gateway/test_registry.py`:

```python
def test_daemon_uses_registry(tmp_path):
    """GatewayDaemon uses discover_channels() instead of hardcoded maps."""
    from letsgo_gateway.daemon import GatewayDaemon

    config = {
        "auth": {
            "pairing_db_path": str(tmp_path / "pairing.json"),
            "max_messages_per_minute": 60,
            "code_ttl_seconds": 300,
        },
        "channels": {
            "my-hook": {"type": "webhook", "port": 9999},
        },
        "cron": {
            "log_path": str(tmp_path / "cron.jsonl"),
        },
    }
    d = GatewayDaemon(config=config)
    assert "my-hook" in d.channels
    # Verify the adapter is a WebhookChannel (from registry discovery)
    from letsgo_gateway.channels.webhook import WebhookChannel

    assert isinstance(d.channels["my-hook"], WebhookChannel)
```

**Step 2: Run test to verify it passes (baseline)**

Run: `cd ~/dev/amplifier-bundle-letsgo && python -m pytest tests/test_gateway/test_registry.py::test_daemon_uses_registry -v`
Expected: PASS (existing code still works — this is a refactor safety net)

**Step 3: Run existing daemon tests (baseline)**

Run: `cd ~/dev/amplifier-bundle-letsgo && python -m pytest tests/test_gateway/test_daemon.py -v`
Expected: All existing tests PASS

**Step 4: Refactor daemon.py to use registry**

In `gateway/letsgo_gateway/daemon.py`, make these changes:

**4a.** Replace the top-of-file imports and constants (lines 11-30). Remove these lines:

```python
from .channels.webhook import WebhookChannel
from .channels.whatsapp import WhatsAppChannel
```

```python
# Channel type -> adapter class mapping
_CHANNEL_CLASSES: dict[str, type[ChannelAdapter]] = {
    "webhook": WebhookChannel,
    "whatsapp": WhatsAppChannel,
}

# Lazy imports for stub channels to avoid requiring their deps at import time
_STUB_CHANNELS = {"telegram", "discord", "slack"}
```

Replace with this single import:

```python
from .channels.registry import discover_channels
```

**4b.** Replace the `_init_channels` method (lines 185-210) with:

```python
    def _init_channels(self) -> None:
        """Instantiate channel adapters from config using the registry."""
        available = discover_channels()
        channels_cfg: dict[str, Any] = self._config.get("channels", {})
        for name, ch_cfg in channels_cfg.items():
            ch_type = ch_cfg.get("type", name)
            cls = available.get(ch_type)
            if cls is None:
                logger.warning(
                    "Unknown channel type '%s' — not built-in and no plugin found",
                    ch_type,
                )
                continue

            adapter = cls(name=name, config=ch_cfg)
            adapter.set_on_message(self._on_message)
            self.channels[name] = adapter
```

**Step 5: Run all tests to verify nothing broke**

Run: `cd ~/dev/amplifier-bundle-letsgo && python -m pytest tests/test_gateway/test_daemon.py tests/test_gateway/test_registry.py -v`
Expected: All tests PASS (existing daemon tests + new registry tests)

**Step 6: Commit**

```bash
git add gateway/letsgo_gateway/daemon.py tests/test_gateway/test_registry.py
git commit -m "refactor(gateway): migrate daemon to use channel registry"
```

---

### Task 3: Make ChannelType Extensible

**Files:**
- Modify: `gateway/letsgo_gateway/models.py` (lines 11-16, 27, 40, 49, 61)
- Test: `tests/test_gateway/test_channels.py` (existing tests must keep passing)
- Test: `tests/test_gateway/test_registry.py` (add extensibility test)

**Step 1: Write the failing test**

Append to `tests/test_gateway/test_registry.py`:

```python
def test_channel_type_accepts_custom_string():
    """ChannelType accepts arbitrary strings for plugin channels."""
    from letsgo_gateway.models import ChannelType, InboundMessage

    # Built-in values still work
    assert ChannelType.WEBHOOK == "webhook"
    assert ChannelType.TELEGRAM == "telegram"

    # Custom plugin channel type can be created
    custom = ChannelType("signal")
    assert custom == "signal"
    assert str(custom) == "signal"

    # Can be used in InboundMessage
    msg = InboundMessage(
        channel=ChannelType("signal"),
        channel_name="my-signal",
        sender_id="user1",
        sender_label="User",
        text="hello from signal",
    )
    assert msg.channel == "signal"
```

**Step 2: Run test to verify it fails**

Run: `cd ~/dev/amplifier-bundle-letsgo && python -m pytest tests/test_gateway/test_registry.py::test_channel_type_accepts_custom_string -v`
Expected: FAIL — `ValueError: 'signal' is not a valid ChannelType`

**Step 3: Write minimal implementation**

In `gateway/letsgo_gateway/models.py`, replace the `ChannelType` class (lines 11-16):

Replace:
```python
class ChannelType(str, Enum):
    WEBHOOK = "webhook"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    WHATSAPP = "whatsapp"
```

With:
```python
class ChannelType(str, Enum):
    """Channel type identifier.

    Built-in values are defined as enum members. Plugin channels can use
    arbitrary strings — call ``ChannelType("signal")`` and it returns
    the string as-is when the value is not a known member.
    """

    WEBHOOK = "webhook"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    WHATSAPP = "whatsapp"

    @classmethod
    def _missing_(cls, value: object) -> ChannelType | None:
        """Accept arbitrary string values for plugin channel types."""
        if isinstance(value, str):
            obj = str.__new__(cls, value)
            obj._value_ = value
            obj._name_ = value.upper()
            return obj
        return None
```

**Step 4: Run all model-dependent tests to verify nothing broke**

Run: `cd ~/dev/amplifier-bundle-letsgo && python -m pytest tests/test_gateway/test_registry.py::test_channel_type_accepts_custom_string tests/test_gateway/test_channels.py tests/test_gateway/test_daemon.py -v`
Expected: All tests PASS — existing tests use `ChannelType.WEBHOOK` etc. which still work, and the new custom string test passes.

**Step 5: Commit**

```bash
git add gateway/letsgo_gateway/models.py tests/test_gateway/test_registry.py
git commit -m "feat(gateway): make ChannelType extensible for plugin channels"
```

---

### Task 4: Add Entry Points to pyproject.toml

**Files:**
- Modify: `gateway/pyproject.toml`

**Step 1: Add entry-point section**

In `gateway/pyproject.toml`, add a new section after the `[project.scripts]` block (after line 18). Add:

```toml
[project.entry-points."letsgo.channels"]
webhook = "letsgo_gateway.channels.webhook:WebhookChannel"
whatsapp = "letsgo_gateway.channels.whatsapp:WhatsAppChannel"
telegram = "letsgo_gateway.channels.telegram:TelegramChannel"
discord = "letsgo_gateway.channels.discord:DiscordChannel"
slack = "letsgo_gateway.channels.slack:SlackChannel"
```

Also add `whatsapp` to the optional-dependencies section. Replace the existing `[project.optional-dependencies]` block:

```toml
[project.optional-dependencies]
discord = ["discord.py>=2.3"]
telegram = ["python-telegram-bot>=20.0"]
slack = ["slack-sdk>=3.21"]
whatsapp = ["aiohttp>=3.9"]
all-channels = [
    "discord.py>=2.3",
    "python-telegram-bot>=20.0",
    "slack-sdk>=3.21",
]
```

**Step 2: Verify TOML is valid**

Run: `cd ~/dev/amplifier-bundle-letsgo && python -c "import tomllib; tomllib.load(open('gateway/pyproject.toml', 'rb')); print('Valid TOML')"`
Expected: `Valid TOML`

**Step 3: Commit**

```bash
git add gateway/pyproject.toml
git commit -m "feat(gateway): register built-in channels as entry points"
```

---

### Task 5: DisplaySystem Protocol

**Files:**
- Create: `gateway/letsgo_gateway/display.py`
- Test: `tests/test_gateway/test_display.py`

**Step 1: Write the failing tests**

Create `tests/test_gateway/test_display.py`:

```python
"""Tests for GatewayDisplaySystem."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.display import GatewayDisplaySystem
from letsgo_gateway.models import ChannelType, OutboundMessage


class FakeChannel(ChannelAdapter):
    """Minimal channel adapter for testing."""

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(name, config or {})
        self.sent: list[OutboundMessage] = []

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        self.sent.append(message)
        return True


@pytest.mark.asyncio
async def test_display_routes_to_canvas_channel():
    """When a canvas channel exists, display routes content to it."""
    canvas = FakeChannel("canvas")
    chat = FakeChannel("general")
    channels = {"canvas": canvas, "general": chat}

    ds = GatewayDisplaySystem(channels)
    await ds.display("# Hello World", metadata={"content_type": "markdown"})

    assert len(canvas.sent) == 1
    assert canvas.sent[0].text == "# Hello World"
    # Chat channel should NOT receive the display content
    assert len(chat.sent) == 0


@pytest.mark.asyncio
async def test_display_fallback_to_chat():
    """Without a canvas channel, display falls back to chat channels."""
    chat = FakeChannel("general")
    channels = {"general": chat}

    ds = GatewayDisplaySystem(channels)
    await ds.display("Some content")

    assert len(chat.sent) == 1
    assert chat.sent[0].text == "Some content"


@pytest.mark.asyncio
async def test_display_with_no_channels():
    """Display with no channels does not crash."""
    ds = GatewayDisplaySystem({})
    # Should not raise
    await ds.display("orphaned content")


@pytest.mark.asyncio
async def test_display_updates_canvas_state():
    """Display updates internal canvas state tracking."""
    canvas = FakeChannel("canvas")
    ds = GatewayDisplaySystem({"canvas": canvas})

    await ds.display("<svg>...</svg>", metadata={"content_type": "svg", "id": "chart-1"})

    assert ds.canvas_state.get("chart-1") == {
        "content_type": "svg",
        "content": "<svg>...</svg>",
    }


@pytest.mark.asyncio
async def test_display_without_metadata():
    """Display works when metadata is None."""
    chat = FakeChannel("general")
    ds = GatewayDisplaySystem({"general": chat})

    await ds.display("plain text")

    assert len(chat.sent) == 1
    assert chat.sent[0].text == "plain text"
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/dev/amplifier-bundle-letsgo && python -m pytest tests/test_gateway/test_display.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'letsgo_gateway.display'`

**Step 3: Write minimal implementation**

Create `gateway/letsgo_gateway/display.py`:

```python
"""Gateway DisplaySystem — routes content to canvas or chat channels."""

from __future__ import annotations

import logging
from typing import Any

from .channels.base import ChannelAdapter
from .models import ChannelType, OutboundMessage

logger = logging.getLogger(__name__)

# Channel names that are treated as canvas surfaces
_CANVAS_CHANNEL_NAMES = {"canvas", "webchat-canvas"}


class GatewayDisplaySystem:
    """Routes display content to the appropriate channel surface.

    If a canvas channel is connected, content goes there.
    Otherwise, content is formatted and sent to chat channels as fallback.
    """

    def __init__(self, channels: dict[str, ChannelAdapter]) -> None:
        self._channels = channels
        self._canvas_state: dict[str, dict[str, Any]] = {}

    @property
    def canvas_state(self) -> dict[str, dict[str, Any]]:
        """Current canvas content state, keyed by content ID."""
        return self._canvas_state

    async def display(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Display content on the best available surface.

        Args:
            content: The content to display (markdown, SVG, HTML, etc.).
            metadata: Optional metadata including ``content_type`` and ``id``.
        """
        if not self._channels:
            logger.debug("DisplaySystem: no channels available, dropping content")
            return

        meta = metadata or {}
        content_type = meta.get("content_type", "text")
        content_id = meta.get("id")

        # Try canvas channel first
        canvas = self._find_canvas_channel()
        if canvas is not None:
            msg = OutboundMessage(
                channel=ChannelType(canvas.name),
                channel_name=canvas.name,
                thread_id=None,
                text=content,
            )
            await canvas.send(msg)

            # Track canvas state
            if content_id:
                self._canvas_state[content_id] = {
                    "content_type": content_type,
                    "content": content,
                }
            return

        # Fallback: send to first available chat channel
        for name, channel in self._channels.items():
            msg = OutboundMessage(
                channel=ChannelType(name),
                channel_name=name,
                thread_id=None,
                text=content,
            )
            await channel.send(msg)
            return  # Send to first channel only

    def _find_canvas_channel(self) -> ChannelAdapter | None:
        """Find a canvas-type channel if one is connected."""
        for name, channel in self._channels.items():
            if name in _CANVAS_CHANNEL_NAMES:
                return channel
        return None
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/dev/amplifier-bundle-letsgo && python -m pytest tests/test_gateway/test_display.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add gateway/letsgo_gateway/display.py tests/test_gateway/test_display.py
git commit -m "feat(gateway): add DisplaySystem protocol for canvas/chat routing"
```

---

### Task 6: Capability Contracts Documentation

**Files:**
- Create: `docs/CAPABILITY_CONTRACTS.md`

**Step 1: Write the documentation**

Create `docs/CAPABILITY_CONTRACTS.md`:

```markdown
# Capability Contracts

Capabilities registered by `amplifier-bundle-letsgo` (core) that satellite bundles may depend on.

## Registered Capabilities

### `memory.store`

- **Registered by:** `tool-memory-store` module
- **Required by:** None (optional for all satellites)
- **Interface:** Async function for storing and retrieving memories
- **Graceful degradation:** Satellites skip memory features when unavailable

### `display`

- **Registered by:** Gateway `DisplaySystem`
- **Required by:** `letsgo-canvas` (required)
- **Interface:** `async display(content: str, metadata: dict | None) -> None`
- **Graceful degradation:** Canvas bundle fails with clear error if missing

### `telemetry.metrics`

- **Registered by:** `hooks-telemetry` module
- **Required by:** None (optional for all satellites)
- **Interface:** Metrics recording functions (counters, histograms)
- **Graceful degradation:** Satellites skip telemetry when unavailable

### `secrets.redeem`

- **Registered by:** `tool-secrets` module
- **Required by:** None (optional for all satellites)
- **Interface:** `async redeem(handle: str) -> str` — decrypt a secret handle
- **Graceful degradation:** Satellites that need secrets fail with clear error

## Satellite Rules

1. **Lazy query:** Query capabilities at execution time, not mount time.
   This makes satellites ordering-resilient — doesn't matter if `letsgo-voice`
   comes before `letsgo` in the user's includes list.

2. **Graceful degradation:** If an optional capability is missing, skip
   the feature and log a debug message. Never crash.

3. **Clear error on required:** If a required capability is missing, raise
   `ModuleLoadError` with an actionable message:

   ```python
   display = coordinator.get_capability("display")
   if display is None:
       raise ModuleLoadError(
           "letsgo-canvas requires amplifier-bundle-letsgo (core). "
           "Add it to your root bundle's includes."
       )
   ```

4. **Never assume ordering:** Satellites don't include the core bundle.
   The user's root bundle includes both. Capabilities may be registered
   in any order.
```

**Step 2: Commit**

```bash
git add docs/CAPABILITY_CONTRACTS.md
git commit -m "docs: add capability contracts for satellite bundles"
```

---

## Phase 1: Gateway Hardening + New Channels

### Task 7: Extract channels/\_\_init\_\_.py to Lazy Imports

**Files:**
- Modify: `gateway/letsgo_gateway/channels/__init__.py`
- Test: `tests/test_gateway/test_registry.py` (add lazy import test)

**Step 1: Write the failing test**

Append to `tests/test_gateway/test_registry.py`:

```python
def test_channels_package_importable_without_sdks():
    """Importing letsgo_gateway.channels works even without optional SDKs."""
    # This test verifies that the __init__.py uses lazy imports.
    # If it eagerly imports discord/telegram/slack, it would fail
    # in environments without those packages installed.
    import importlib
    import letsgo_gateway.channels

    importlib.reload(letsgo_gateway.channels)
    # Should not raise ImportError
    assert hasattr(letsgo_gateway.channels, "ChannelAdapter")
    assert hasattr(letsgo_gateway.channels, "WebhookChannel")
```

**Step 2: Run test to verify it passes as baseline**

Run: `cd ~/dev/amplifier-bundle-letsgo && python -m pytest tests/test_gateway/test_registry.py::test_channels_package_importable_without_sdks -v`
Expected: PASS (currently works because all stubs handle missing SDKs)

**Step 3: Refactor channels/\_\_init\_\_.py to lazy imports**

Replace the entire contents of `gateway/letsgo_gateway/channels/__init__.py` with:

```python
"""Channel adapters package.

Uses lazy imports so missing optional SDKs (discord.py, python-telegram-bot,
slack-sdk) don't break the package on import.
"""

from .base import ChannelAdapter

# Lazy accessors — only import when accessed
_LAZY_MAP: dict[str, tuple[str, str]] = {
    "WebhookChannel": (".webhook", "WebhookChannel"),
    "WhatsAppChannel": (".whatsapp", "WhatsAppChannel"),
    "TelegramChannel": (".telegram", "TelegramChannel"),
    "DiscordChannel": (".discord", "DiscordChannel"),
    "SlackChannel": (".slack", "SlackChannel"),
}


def __getattr__(name: str):
    if name in _LAZY_MAP:
        module_path, class_name = _LAZY_MAP[name]
        import importlib

        module = importlib.import_module(module_path, __package__)
        cls = getattr(module, class_name)
        globals()[name] = cls  # Cache for subsequent access
        return cls
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ChannelAdapter",
    "WebhookChannel",
    "WhatsAppChannel",
    "TelegramChannel",
    "DiscordChannel",
    "SlackChannel",
]
```

**Step 4: Run all gateway tests to verify nothing broke**

Run: `cd ~/dev/amplifier-bundle-letsgo && python -m pytest tests/test_gateway/ -v`
Expected: All tests PASS — existing test files import channels by their direct module paths (e.g., `from letsgo_gateway.channels.webhook import WebhookChannel`), so they bypass `__init__.py`. The `__init__.py` re-exports still work via `__getattr__`.

**Step 5: Commit**

```bash
git add gateway/letsgo_gateway/channels/__init__.py tests/test_gateway/test_registry.py
git commit -m "refactor(gateway): lazy imports in channels package"
```

---

### Task 8: Signal Channel Adapter Skeleton

**Files:**
- Create: `channels/signal/pyproject.toml`
- Create: `channels/signal/letsgo_channel_signal/__init__.py`
- Create: `channels/signal/letsgo_channel_signal/adapter.py`
- Test: `channels/signal/tests/__init__.py`
- Test: `channels/signal/tests/test_signal_adapter.py`

**Step 1: Write the failing tests**

Create `channels/signal/tests/__init__.py` (empty file).

Create `channels/signal/tests/test_signal_adapter.py`:

```python
"""Tests for Signal channel adapter."""

from __future__ import annotations

import pytest

from letsgo_channel_signal import SignalChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage


def test_signal_is_channel_adapter():
    """SignalChannel is a proper ChannelAdapter subclass."""
    assert issubclass(SignalChannel, ChannelAdapter)


def test_signal_instantiation():
    """SignalChannel can be instantiated with name and config."""
    ch = SignalChannel(
        name="signal-main",
        config={"phone_number": "+15551234567"},
    )
    assert ch.name == "signal-main"
    assert ch.config["phone_number"] == "+15551234567"
    assert not ch.is_running


@pytest.mark.asyncio
async def test_signal_start_without_cli_logs_warning(caplog):
    """start() logs a warning when signal-cli is not found."""
    ch = SignalChannel(
        name="signal-test",
        config={"phone_number": "+15551234567", "signal_cli_path": None},
    )
    await ch.start()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_signal_stop_when_not_running():
    """stop() is safe to call when not running."""
    ch = SignalChannel(name="signal-test", config={})
    await ch.stop()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_signal_send_returns_false_when_not_running():
    """send() returns False when adapter is not running."""
    ch = SignalChannel(name="signal-test", config={})
    msg = OutboundMessage(
        channel=ChannelType("signal"),
        channel_name="signal-test",
        thread_id=None,
        text="hello",
    )
    result = await ch.send(msg)
    assert result is False


def test_signal_format_outbound():
    """_format_outbound converts OutboundMessage to signal-cli args."""
    ch = SignalChannel(
        name="signal-test",
        config={"phone_number": "+15551234567"},
    )
    msg = OutboundMessage(
        channel=ChannelType("signal"),
        channel_name="signal-test",
        thread_id="+15559876543",
        text="Hello from LetsGo",
    )
    args = ch._format_outbound(msg)
    assert "+15559876543" in args
    assert "Hello from LetsGo" in args
```

**Step 2: Create project structure and verify tests fail**

Run: `cd ~/dev/amplifier-bundle-letsgo && mkdir -p channels/signal/letsgo_channel_signal channels/signal/tests && touch channels/signal/tests/__init__.py`
Run: `cd ~/dev/amplifier-bundle-letsgo && PYTHONPATH=channels/signal:gateway python -m pytest channels/signal/tests/test_signal_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'letsgo_channel_signal'`

**Step 3: Write the pyproject.toml**

Create `channels/signal/pyproject.toml`:

```toml
[project]
name = "letsgo-channel-signal"
version = "0.1.0"
description = "Signal channel adapter for LetsGo gateway"
requires-python = ">=3.11"
dependencies = [
    "letsgo-gateway",
]

[project.entry-points."letsgo.channels"]
signal = "letsgo_channel_signal:SignalChannel"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["letsgo_channel_signal"]
```

**Step 4: Write the adapter implementation**

Create `channels/signal/letsgo_channel_signal/__init__.py`:

```python
"""LetsGo Signal channel adapter."""

from .adapter import SignalChannel

__all__ = ["SignalChannel"]
```

Create `channels/signal/letsgo_channel_signal/adapter.py`:

```python
"""Signal channel adapter using signal-cli subprocess bridge."""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)


class SignalChannel(ChannelAdapter):
    """Signal messaging adapter backed by signal-cli.

    Config keys:
        phone_number: The Signal phone number (e.g., "+15551234567")
        signal_cli_path: Path to signal-cli binary (default: auto-detect)
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._phone: str = config.get("phone_number", "")
        explicit_path = config.get("signal_cli_path")
        # Allow explicit None to mean "not found"
        if explicit_path is None and "signal_cli_path" in config:
            self._cli_path: str | None = None
        else:
            self._cli_path = explicit_path or shutil.which("signal-cli")
        self._process: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        """Start listening for Signal messages via signal-cli daemon."""
        if not self._cli_path:
            logger.warning(
                "signal-cli not found — Signal channel '%s' cannot start",
                self.name,
            )
            return

        try:
            self._process = await asyncio.create_subprocess_exec(
                self._cli_path,
                "-u",
                self._phone,
                "daemon",
                "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._running = True
            logger.info("SignalChannel '%s' started for %s", self.name, self._phone)
            # Start reading messages in background
            asyncio.create_task(self._read_messages())
        except FileNotFoundError:
            logger.error("signal-cli binary not found at %s", self._cli_path)

    async def stop(self) -> None:
        """Stop the signal-cli subprocess."""
        if self._process:
            self._process.terminate()
            await self._process.wait()
            self._process = None
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message via signal-cli."""
        if not self._running or not self._cli_path:
            return False

        args = self._format_outbound(message)
        try:
            proc = await asyncio.create_subprocess_exec(
                self._cli_path,
                "-u",
                self._phone,
                "send",
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode != 0:
                logger.error("signal-cli send failed: %s", stderr.decode())
                return False
            return True
        except (FileNotFoundError, asyncio.TimeoutError):
            logger.exception("Failed to send Signal message")
            return False

    def _format_outbound(self, message: OutboundMessage) -> list[str]:
        """Convert an OutboundMessage to signal-cli send arguments."""
        args: list[str] = []
        if message.thread_id:
            args.extend([message.thread_id])
        args.extend(["-m", message.text])
        return args

    async def _read_messages(self) -> None:
        """Read JSON lines from signal-cli daemon stdout."""
        if not self._process or not self._process.stdout:
            return

        import json

        while self._running:
            try:
                line = await self._process.stdout.readline()
                if not line:
                    break
                data = json.loads(line)
                envelope = data.get("envelope", {})
                data_msg = envelope.get("dataMessage")
                if data_msg and self._on_message:
                    msg = InboundMessage(
                        channel=ChannelType("signal"),
                        channel_name=self.name,
                        sender_id=envelope.get("source", "unknown"),
                        sender_label=envelope.get("sourceName", ""),
                        text=data_msg.get("message", ""),
                        thread_id=envelope.get("source"),
                    )
                    await self._on_message(msg)
            except Exception:
                logger.exception("Error reading Signal message")
```

**Step 5: Run tests to verify they pass**

Run: `cd ~/dev/amplifier-bundle-letsgo && PYTHONPATH=channels/signal:gateway python -m pytest channels/signal/tests/test_signal_adapter.py -v`
Expected: All 6 tests PASS

**Step 6: Commit**

```bash
git add channels/signal/
git commit -m "feat: add Signal channel adapter skeleton with entry-point registration"
```

---

### Task 9: Matrix Channel Adapter Skeleton

**Files:**
- Create: `channels/matrix/pyproject.toml`
- Create: `channels/matrix/letsgo_channel_matrix/__init__.py`
- Create: `channels/matrix/letsgo_channel_matrix/adapter.py`
- Test: `channels/matrix/tests/__init__.py`
- Test: `channels/matrix/tests/test_matrix_adapter.py`

**Step 1: Write the failing tests**

Create `channels/matrix/tests/__init__.py` (empty file).

Create `channels/matrix/tests/test_matrix_adapter.py`:

```python
"""Tests for Matrix channel adapter."""

from __future__ import annotations

import pytest

from letsgo_channel_matrix import MatrixChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage


def test_matrix_is_channel_adapter():
    """MatrixChannel is a proper ChannelAdapter subclass."""
    assert issubclass(MatrixChannel, ChannelAdapter)


def test_matrix_instantiation():
    """MatrixChannel can be instantiated with name and config."""
    ch = MatrixChannel(
        name="matrix-main",
        config={
            "homeserver": "https://matrix.org",
            "user_id": "@letsgo:matrix.org",
            "access_token": "fake-token",
        },
    )
    assert ch.name == "matrix-main"
    assert ch.config["homeserver"] == "https://matrix.org"
    assert not ch.is_running


@pytest.mark.asyncio
async def test_matrix_start_without_nio_logs_warning(caplog):
    """start() logs a warning when matrix-nio is not installed."""
    ch = MatrixChannel(
        name="matrix-test",
        config={"homeserver": "https://matrix.org"},
    )
    await ch.start()
    # Without nio, should not be running
    assert not ch.is_running


@pytest.mark.asyncio
async def test_matrix_stop_when_not_running():
    """stop() is safe to call when not running."""
    ch = MatrixChannel(name="matrix-test", config={})
    await ch.stop()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_matrix_send_returns_false_when_not_running():
    """send() returns False when adapter is not running."""
    ch = MatrixChannel(name="matrix-test", config={})
    msg = OutboundMessage(
        channel=ChannelType("matrix"),
        channel_name="matrix-test",
        thread_id="!room:matrix.org",
        text="hello",
    )
    result = await ch.send(msg)
    assert result is False


def test_matrix_format_outbound_html():
    """_format_message converts text to Matrix-compatible format."""
    ch = MatrixChannel(name="matrix-test", config={})
    body, formatted = ch._format_message("**bold** and _italic_")
    assert body == "**bold** and _italic_"
    assert isinstance(formatted, str)
```

**Step 2: Create project structure and verify tests fail**

Run: `cd ~/dev/amplifier-bundle-letsgo && mkdir -p channels/matrix/letsgo_channel_matrix channels/matrix/tests && touch channels/matrix/tests/__init__.py`
Run: `cd ~/dev/amplifier-bundle-letsgo && PYTHONPATH=channels/matrix:gateway python -m pytest channels/matrix/tests/test_matrix_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'letsgo_channel_matrix'`

**Step 3: Write the pyproject.toml**

Create `channels/matrix/pyproject.toml`:

```toml
[project]
name = "letsgo-channel-matrix"
version = "0.1.0"
description = "Matrix channel adapter for LetsGo gateway"
requires-python = ">=3.11"
dependencies = [
    "letsgo-gateway",
]

[project.optional-dependencies]
nio = ["matrix-nio>=0.21"]

[project.entry-points."letsgo.channels"]
matrix = "letsgo_channel_matrix:MatrixChannel"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["letsgo_channel_matrix"]
```

**Step 4: Write the adapter implementation**

Create `channels/matrix/letsgo_channel_matrix/__init__.py`:

```python
"""LetsGo Matrix channel adapter."""

from .adapter import MatrixChannel

__all__ = ["MatrixChannel"]
```

Create `channels/matrix/letsgo_channel_matrix/adapter.py`:

```python
"""Matrix channel adapter using matrix-nio."""

from __future__ import annotations

import logging
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

# Graceful degradation
_HAS_NIO = False
try:
    from nio import AsyncClient, MatrixRoom, RoomMessageText

    _HAS_NIO = True
except ImportError:
    pass


class MatrixChannel(ChannelAdapter):
    """Matrix messaging adapter using matrix-nio.

    Config keys:
        homeserver: Matrix homeserver URL (e.g., "https://matrix.org")
        user_id: Bot user ID (e.g., "@letsgo:matrix.org")
        access_token: Access token for authentication
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._homeserver: str = config.get("homeserver", "")
        self._user_id: str = config.get("user_id", "")
        self._access_token: str = config.get("access_token", "")
        self._client: Any = None  # AsyncClient when nio is available

    async def start(self) -> None:
        """Connect to the Matrix homeserver and start syncing."""
        if not _HAS_NIO:
            logger.warning(
                "matrix-nio not installed — Matrix channel '%s' cannot start. "
                "Install with: pip install letsgo-channel-matrix[nio]",
                self.name,
            )
            return

        if not self._homeserver:
            logger.error("No homeserver configured for Matrix channel '%s'", self.name)
            return

        try:
            self._client = AsyncClient(self._homeserver, self._user_id)
            self._client.access_token = self._access_token

            # Register message callback
            self._client.add_event_callback(self._on_room_message, RoomMessageText)

            self._running = True
            logger.info(
                "MatrixChannel '%s' connected to %s", self.name, self._homeserver
            )
            # Note: sync_forever() would be called in the daemon's event loop
        except Exception:
            logger.exception("Failed to start Matrix channel '%s'", self.name)

    async def stop(self) -> None:
        """Disconnect from the Matrix homeserver."""
        if self._client and _HAS_NIO:
            await self._client.close()
            self._client = None
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message to a Matrix room."""
        if not self._running or not self._client:
            return False

        room_id = message.thread_id
        if not room_id:
            logger.warning("No room_id (thread_id) for Matrix message")
            return False

        body, formatted_body = self._format_message(message.text)
        try:
            await self._client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content={
                    "msgtype": "m.text",
                    "body": body,
                    "format": "org.matrix.custom.html",
                    "formatted_body": formatted_body,
                },
            )
            return True
        except Exception:
            logger.exception("Failed to send Matrix message to %s", room_id)
            return False

    def _format_message(self, text: str) -> tuple[str, str]:
        """Convert text to Matrix message format (plain + HTML).

        Returns:
            Tuple of (plain_body, html_formatted_body).
        """
        # Plain body is the text as-is
        plain = text
        # Simple HTML: preserve newlines as <br>, escape HTML chars
        html = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = html.replace("\n", "<br>")
        return plain, html

    async def _on_room_message(self, room: Any, event: Any) -> None:
        """Handle incoming Matrix room messages."""
        # Ignore own messages
        if event.sender == self._user_id:
            return

        if self._on_message:
            msg = InboundMessage(
                channel=ChannelType("matrix"),
                channel_name=self.name,
                sender_id=event.sender,
                sender_label=event.sender,
                text=event.body,
                thread_id=room.room_id,
            )
            await self._on_message(msg)
```

**Step 5: Run tests to verify they pass**

Run: `cd ~/dev/amplifier-bundle-letsgo && PYTHONPATH=channels/matrix:gateway python -m pytest channels/matrix/tests/test_matrix_adapter.py -v`
Expected: All 6 tests PASS

**Step 6: Commit**

```bash
git add channels/matrix/
git commit -m "feat: add Matrix channel adapter skeleton with entry-point registration"
```

---

### Task 10: Teams Channel Adapter Skeleton

**Files:**
- Create: `channels/teams/pyproject.toml`
- Create: `channels/teams/letsgo_channel_teams/__init__.py`
- Create: `channels/teams/letsgo_channel_teams/adapter.py`
- Test: `channels/teams/tests/__init__.py`
- Test: `channels/teams/tests/test_teams_adapter.py`

**Step 1: Write the failing tests**

Create `channels/teams/tests/__init__.py` (empty file).

Create `channels/teams/tests/test_teams_adapter.py`:

```python
"""Tests for Microsoft Teams channel adapter."""

from __future__ import annotations

import pytest

from letsgo_channel_teams import TeamsChannel
from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, OutboundMessage


def test_teams_is_channel_adapter():
    """TeamsChannel is a proper ChannelAdapter subclass."""
    assert issubclass(TeamsChannel, ChannelAdapter)


def test_teams_instantiation():
    """TeamsChannel can be instantiated with name and config."""
    ch = TeamsChannel(
        name="teams-main",
        config={
            "app_id": "fake-app-id",
            "app_password": "fake-app-password",
        },
    )
    assert ch.name == "teams-main"
    assert ch.config["app_id"] == "fake-app-id"
    assert not ch.is_running


@pytest.mark.asyncio
async def test_teams_start_without_botbuilder_logs_warning(caplog):
    """start() logs a warning when botbuilder-core is not installed."""
    ch = TeamsChannel(
        name="teams-test",
        config={"app_id": "fake", "app_password": "fake"},
    )
    await ch.start()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_teams_stop_when_not_running():
    """stop() is safe to call when not running."""
    ch = TeamsChannel(name="teams-test", config={})
    await ch.stop()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_teams_send_returns_false_when_not_running():
    """send() returns False when adapter is not running."""
    ch = TeamsChannel(name="teams-test", config={})
    msg = OutboundMessage(
        channel=ChannelType("teams"),
        channel_name="teams-test",
        thread_id=None,
        text="hello",
    )
    result = await ch.send(msg)
    assert result is False


def test_teams_format_adaptive_card():
    """_format_as_card wraps text in an Adaptive Card structure."""
    ch = TeamsChannel(name="teams-test", config={})
    card = ch._format_as_card("Hello **world**")
    assert card["type"] == "AdaptiveCard"
    assert len(card["body"]) >= 1
    assert card["body"][0]["text"] == "Hello **world**"
```

**Step 2: Create project structure and verify tests fail**

Run: `cd ~/dev/amplifier-bundle-letsgo && mkdir -p channels/teams/letsgo_channel_teams channels/teams/tests && touch channels/teams/tests/__init__.py`
Run: `cd ~/dev/amplifier-bundle-letsgo && PYTHONPATH=channels/teams:gateway python -m pytest channels/teams/tests/test_teams_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'letsgo_channel_teams'`

**Step 3: Write the pyproject.toml**

Create `channels/teams/pyproject.toml`:

```toml
[project]
name = "letsgo-channel-teams"
version = "0.1.0"
description = "Microsoft Teams channel adapter for LetsGo gateway"
requires-python = ">=3.11"
dependencies = [
    "letsgo-gateway",
]

[project.optional-dependencies]
botbuilder = ["botbuilder-core>=4.14"]

[project.entry-points."letsgo.channels"]
teams = "letsgo_channel_teams:TeamsChannel"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["letsgo_channel_teams"]
```

**Step 4: Write the adapter implementation**

Create `channels/teams/letsgo_channel_teams/__init__.py`:

```python
"""LetsGo Microsoft Teams channel adapter."""

from .adapter import TeamsChannel

__all__ = ["TeamsChannel"]
```

Create `channels/teams/letsgo_channel_teams/adapter.py`:

```python
"""Microsoft Teams channel adapter using botbuilder-core."""

from __future__ import annotations

import logging
from typing import Any

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

# Graceful degradation
_HAS_BOTBUILDER = False
try:
    from botbuilder.core import (
        BotFrameworkAdapter,
        BotFrameworkAdapterSettings,
        TurnContext,
    )
    from botbuilder.schema import Activity, ActivityTypes

    _HAS_BOTBUILDER = True
except ImportError:
    pass


class TeamsChannel(ChannelAdapter):
    """Microsoft Teams adapter using Bot Framework.

    Config keys:
        app_id: Microsoft App ID from Azure Bot registration
        app_password: Microsoft App Password
        host: Bind address for the webhook server (default: "127.0.0.1")
        port: Bind port (default: 3978)
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._app_id: str = config.get("app_id", "")
        self._app_password: str = config.get("app_password", "")
        self._host: str = config.get("host", "127.0.0.1")
        self._port: int = int(config.get("port", 3978))
        self._adapter: Any = None  # BotFrameworkAdapter when available
        self._runner: Any = None  # aiohttp AppRunner

    async def start(self) -> None:
        """Start the Teams bot webhook server."""
        if not _HAS_BOTBUILDER:
            logger.warning(
                "botbuilder-core not installed — Teams channel '%s' cannot start. "
                "Install with: pip install letsgo-channel-teams[botbuilder]",
                self.name,
            )
            return

        try:
            settings = BotFrameworkAdapterSettings(self._app_id, self._app_password)
            self._adapter = BotFrameworkAdapter(settings)

            # Set up aiohttp web server for Bot Framework messages
            from aiohttp import web

            app = web.Application()
            app.router.add_post("/api/messages", self._handle_messages)
            self._runner = web.AppRunner(app)
            await self._runner.setup()
            site = web.TCPSite(self._runner, self._host, self._port)
            await site.start()

            self._running = True
            logger.info(
                "TeamsChannel '%s' listening on %s:%s",
                self.name,
                self._host,
                self._port,
            )
        except Exception:
            logger.exception("Failed to start Teams channel '%s'", self.name)

    async def stop(self) -> None:
        """Stop the Teams bot webhook server."""
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        self._adapter = None
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message via Teams Bot Framework."""
        if not self._running or not self._adapter:
            return False

        # Teams messages are typically sent as replies via TurnContext,
        # which is handled during the on_turn callback flow.
        # For proactive messages, we'd need a conversation reference.
        logger.warning(
            "Proactive Teams messaging not yet implemented for '%s'", self.name
        )
        return False

    def _format_as_card(self, text: str) -> dict[str, Any]:
        """Wrap text in an Adaptive Card structure for Teams.

        Returns:
            Adaptive Card JSON dict.
        """
        return {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.4",
            "body": [
                {
                    "type": "TextBlock",
                    "text": text,
                    "wrap": True,
                }
            ],
        }

    async def _handle_messages(self, request: Any) -> Any:
        """Handle incoming Bot Framework messages."""
        from aiohttp import web

        if not self._adapter:
            return web.Response(status=503)

        body = await request.json()

        async def _on_turn(turn_context: Any) -> None:
            if turn_context.activity.type == "message":
                if self._on_message:
                    msg = InboundMessage(
                        channel=ChannelType("teams"),
                        channel_name=self.name,
                        sender_id=turn_context.activity.from_property.id,
                        sender_label=turn_context.activity.from_property.name or "",
                        text=turn_context.activity.text or "",
                        thread_id=turn_context.activity.conversation.id,
                    )
                    response_text = await self._on_message(msg)
                    if response_text:
                        await turn_context.send_activity(response_text)

        try:
            auth_header = request.headers.get("Authorization", "")
            activity = Activity().deserialize(body)
            await self._adapter.process_activity(activity, auth_header, _on_turn)
            return web.Response(status=200)
        except Exception:
            logger.exception("Error processing Teams message")
            return web.Response(status=500)
```

**Step 5: Run tests to verify they pass**

Run: `cd ~/dev/amplifier-bundle-letsgo && PYTHONPATH=channels/teams:gateway python -m pytest channels/teams/tests/test_teams_adapter.py -v`
Expected: All 6 tests PASS

**Step 6: Commit**

```bash
git add channels/teams/
git commit -m "feat: add Microsoft Teams channel adapter skeleton with entry-point registration"
```

---

### Task 11: Enhanced Onboarding Recipe (Setup Wizard 4-Stage)

**Files:**
- Modify: `recipes/setup-wizard.yaml`

**Step 1: Write the enhanced recipe**

Replace the entire contents of `recipes/setup-wizard.yaml` with:

```yaml
schema: v1.7.0

name: setup-wizard
description: Interactive 4-stage setup wizard for LetsGo — provider, channels, satellites, daemon
version: 2.0.0
author: letsgo
tags:
  - setup
  - onboarding
  - wizard

context:
  variables: {}

stages:
  - name: provider-setup
    description: Welcome user and configure AI provider with encrypted secret storage
    steps:
      - id: detect-existing
        agent: self
        prompt: >
          Check for existing LetsGo configuration:
          1. Look for ~/.letsgo/gateway/config.yaml
          2. Check if any secrets are already stored (use secrets tool list_secrets)
          3. If returning user, show what's already configured and ask what to update.
          4. If fresh install, welcome the user and proceed to provider selection.
        output: existing_config
        timeout: 120

      - id: configure-provider
        agent: self
        prompt: >
          Based on detection results: {{existing_config}}

          Walk the user through AI provider setup:
          1. Provider selection: Anthropic / OpenAI / Azure OpenAI / Ollama / Other
          2. Collect the API key or endpoint URL
          3. Store the API key using the secrets tool (set_secret, category: api_key)
          4. Test the provider connection by making a simple API call
          5. Present a summary of the configured provider

          IMPORTANT: Never echo back API keys. Store immediately, confirm storage only.
        output: provider_config
        timeout: 300

    approval:
      required: true
      prompt: |
        Provider configuration complete:

        {{provider_config}}

        Proceed to channel setup?

  - name: channel-setup
    description: Select, install, and configure messaging channels
    steps:
      - id: select-channels
        agent: self
        prompt: >
          Present available messaging channels to the user:

          **Built-in (no extra install):**
          - Webhook — HTTP endpoint for integrations
          - WhatsApp — Personal WhatsApp via QR code

          **Optional (pip install required):**
          - Telegram — Bot via @BotFather token
          - Discord — Bot via Developer Portal
          - Slack — Bot via Socket Mode or Events API

          **Plugin channels (separate packages):**
          - Signal — Via signal-cli
          - Matrix — Via matrix-nio
          - Teams — Via Bot Framework

          Ask which channels they want to enable.
          For each selected channel, install dependencies if needed:
          - Telegram: pip install letsgo-gateway[telegram]
          - Discord: pip install letsgo-gateway[discord]
          - Slack: pip install letsgo-gateway[slack]
          - Signal: pip install letsgo-channel-signal
          - Matrix: pip install letsgo-channel-matrix[nio]
          - Teams: pip install letsgo-channel-teams[botbuilder]
        output: selected_channels
        timeout: 300

      - id: configure-channels
        agent: self
        prompt: >
          For each selected channel ({{selected_channels}}), collect credentials:

          **Telegram:** Bot token from @BotFather
          **Discord:** Bot token + Guild ID from Developer Portal
          **Slack:** Bot token (xoxb-) + signing secret + optional app token (xapp-)
          **Webhook:** Endpoint URL + optional shared secret
          **WhatsApp:** No credentials needed (QR code auth at start)
          **Signal:** Phone number for signal-cli registration
          **Matrix:** Homeserver URL + user ID + access token
          **Teams:** Microsoft App ID + App Password from Azure

          Store each credential using secrets tool:
          - Name format: channel/{type}/{name}/{credential}
          - Category: api_key

          Test each channel connection after storing credentials.
          Report results per channel.
        output: channel_config
        timeout: 600

    approval:
      required: true
      prompt: |
        Channel configuration complete:

        {{channel_config}}

        Proceed to satellite bundle selection?

  - name: satellite-setup
    description: Select and install optional satellite bundles
    steps:
      - id: select-satellites
        agent: self
        prompt: >
          Present optional satellite capabilities:

          **Voice** (amplifier-bundle-letsgo-voice)
          - Transcribe inbound voice messages
          - Text-to-speech responses
          - Works across all channels with voice support

          **Canvas** (amplifier-bundle-letsgo-canvas)
          - Rich visual output (charts, HTML, SVG)
          - Web UI at localhost:8080/canvas
          - Auto-render tool outputs

          **WebChat** (amplifier-bundle-letsgo-webchat)
          - Web chat interface
          - Admin dashboard (sessions, channels, cron, usage)

          **Browser** (amplifier-bundle-letsgo-browser)
          - Browser automation via Playwright
          - QR code scanning for WhatsApp setup

          **MCP** (amplifier-bundle-letsgo-mcp)
          - Connect to MCP tool servers
          - Bridge external tools into Amplifier

          Ask which satellites they want. For each selected:
          1. pip install the satellite bundle
          2. Note that the user will need to add it to their root bundle.md includes

          Report which satellites were installed.
        output: satellite_config
        timeout: 300

    approval:
      required: true
      prompt: |
        Satellite setup:

        {{satellite_config}}

        Proceed to daemon startup?

  - name: daemon-activate
    description: Start the gateway daemon and verify everything works
    steps:
      - id: create-config
        agent: self
        prompt: >
          Create the gateway daemon configuration file at ~/.letsgo/gateway/config.yaml.

          Include configuration for:
          - All channels from stage 2: {{channel_config}}
          - Heartbeat settings (ask user for interval, default 3600 seconds)
          - Heartbeat channels (which channels should receive heartbeat messages)
          - Tool policy settings (ask if they want careful_mode)

          Write the config file. Report the final configuration (without secrets).
        output: daemon_config
        timeout: 180

      - id: start-daemon
        agent: self
        prompt: >
          Start the LetsGo gateway daemon:

          1. Run: letsgo-gateway --config ~/.letsgo/gateway/config.yaml
          2. Verify all configured channels connect successfully
          3. Send a welcome message through each enabled channel:
             "LetsGo is connected and ready to assist!"
          4. If heartbeat is enabled, verify the heartbeat schedule is active

          Report: daemon status, channel connection status, test message delivery.
        output: daemon_status
        timeout: 300
```

**Step 2: Validate the recipe YAML**

Run: `cd ~/dev/amplifier-bundle-letsgo && python -c "import yaml; yaml.safe_load(open('recipes/setup-wizard.yaml')); print('Valid YAML')"`
Expected: `Valid YAML`

**Step 3: Commit**

```bash
git add recipes/setup-wizard.yaml
git commit -m "feat(recipes): enhance setup-wizard to 4-stage onboarding"
```

---

### Task 12: Update channel-onboard.yaml for All Channels

**Files:**
- Modify: `recipes/channel-onboard.yaml`

**Step 1: Update the recipe to support all channel types**

In `recipes/channel-onboard.yaml`, replace the `validate-channel-type` step's prompt (the step starting at line 22). Replace the `prompt:` content of the `validate-channel-type` step with:

```yaml
      - id: validate-channel-type
        agent: self
        prompt: |
          Validate the channel configuration request.

          Channel type: {{channel_type}}
          Channel name: {{channel_name}}

          Supported channels and their requirements:

          **Built-in channels (no extra install):**

          **webhook**:
          - Endpoint URL
          - Shared secret for HMAC verification
          - Optional: custom headers, retry policy

          **whatsapp**:
          - No API credentials needed (QR code auth)
          - Optional: session_dir, files_dir paths
          - Requires: Node.js installed on system

          **Optional built-in (require pip install letsgo-gateway[name]):**

          **telegram**:
          - Bot token (from @BotFather)
          - Optional: webhook URL, allowed user IDs
          - Install: pip install letsgo-gateway[telegram]

          **discord**:
          - Bot token (from Discord Developer Portal)
          - Guild ID (server to connect to)
          - Optional: channel ID, role permissions
          - Install: pip install letsgo-gateway[discord]

          **slack**:
          - Bot token (xoxb-...)
          - Signing secret
          - Optional: App-Level Token for Socket Mode (xapp-...)
          - Install: pip install letsgo-gateway[slack]

          **Plugin channels (separate packages):**

          **signal**:
          - Phone number registered with Signal
          - Requires: signal-cli installed on system
          - Install: pip install letsgo-channel-signal

          **matrix**:
          - Homeserver URL (e.g., https://matrix.org)
          - User ID (e.g., @letsgo:matrix.org)
          - Access token
          - Install: pip install letsgo-channel-matrix[nio]

          **teams**:
          - Microsoft App ID (from Azure Bot registration)
          - Microsoft App Password
          - Install: pip install letsgo-channel-teams[botbuilder]

          If channel_type is empty or unsupported, list all supported types and ask the user to choose.
          If the channel is a plugin channel, check if the package is installed. If not, install it.
          If channel_type is valid, list the required credentials for this channel type.
          Validate the format of any provided values (don't test connectivity yet).

          Report: channel type confirmed, credentials needed, any values already provided.
        output: channel_config
        timeout: 300
```

Also update the `pair-device` step prompt to include the new channel types. Replace the pairing steps section:

```yaml
      - id: pair-device
        agent: self
        prompt: |
          Perform device pairing for the {{channel_type}} channel "{{channel_name}}".

          Authentication result: {{auth_result}}

          Pairing steps by channel type:
          - **Telegram**: Send a test message to the bot, verify receipt
          - **Discord**: Send a message in the configured guild, verify receipt
          - **Slack**: Post a test message to a channel, verify receipt
          - **Webhook**: Send a test payload to the endpoint, verify response
          - **WhatsApp**: Generate QR code, wait for scan, verify connection
          - **Signal**: Send a test message to the registered number, verify receipt
          - **Matrix**: Join a test room, send a message, verify receipt
          - **Teams**: Send a test message via Bot Framework, verify receipt

          Report: pairing status, test message sent/received, any issues.
        output: pairing_result
        timeout: 120
```

**Step 2: Validate the recipe YAML**

Run: `cd ~/dev/amplifier-bundle-letsgo && python -c "import yaml; yaml.safe_load(open('recipes/channel-onboard.yaml')); print('Valid YAML')"`
Expected: `Valid YAML`

**Step 3: Commit**

```bash
git add recipes/channel-onboard.yaml
git commit -m "feat(recipes): add whatsapp, signal, matrix, teams to channel-onboard"
```

---

### Task 13: Integration Test — Full Plugin Discovery Flow

**Files:**
- Create: `tests/test_gateway/test_integration_plugin.py`

**Step 1: Write the integration test**

Create `tests/test_gateway/test_integration_plugin.py`:

```python
"""Integration test: end-to-end plugin channel discovery and usage."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.channels.registry import discover_channels
from letsgo_gateway.daemon import GatewayDaemon
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage


# ---------------------------------------------------------------------------
# Fake plugin channel
# ---------------------------------------------------------------------------


class FakePluginChannel(ChannelAdapter):
    """A fake channel adapter that simulates a plugin channel."""

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self.started = False
        self.stopped = False
        self.sent_messages: list[OutboundMessage] = []

    async def start(self) -> None:
        self.started = True
        self._running = True

    async def stop(self) -> None:
        self.stopped = True
        self._running = False

    async def send(self, message: OutboundMessage) -> bool:
        self.sent_messages.append(message)
        return True


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _mock_entry_point(name: str, cls: type) -> MagicMock:
    """Create a mock entry point that loads the given class."""
    ep = MagicMock()
    ep.name = name
    ep.load.return_value = cls
    return ep


def test_plugin_discovered_via_entry_point():
    """A plugin channel registered via entry point is discovered."""
    mock_ep = _mock_entry_point("fakechat", FakePluginChannel)

    with patch(
        "letsgo_gateway.channels.registry.entry_points",
        return_value=[mock_ep],
    ):
        channels = discover_channels()

    assert "fakechat" in channels
    assert channels["fakechat"] is FakePluginChannel


def test_daemon_initializes_plugin_channel(tmp_path: Path):
    """Daemon creates a plugin channel instance from registry discovery."""
    mock_ep = _mock_entry_point("fakechat", FakePluginChannel)

    config = {
        "auth": {
            "pairing_db_path": str(tmp_path / "pairing.json"),
            "max_messages_per_minute": 60,
            "code_ttl_seconds": 300,
        },
        "channels": {
            "my-fakechat": {"type": "fakechat", "api_key": "test123"},
        },
        "cron": {
            "log_path": str(tmp_path / "cron.jsonl"),
        },
    }

    with patch(
        "letsgo_gateway.channels.registry.entry_points",
        return_value=[mock_ep],
    ):
        daemon = GatewayDaemon(config=config)

    assert "my-fakechat" in daemon.channels
    adapter = daemon.channels["my-fakechat"]
    assert isinstance(adapter, FakePluginChannel)
    assert adapter.name == "my-fakechat"
    assert adapter.config["api_key"] == "test123"


@pytest.mark.asyncio
async def test_plugin_channel_send_receive(tmp_path: Path):
    """Full flow: discover plugin → init daemon → send message."""
    mock_ep = _mock_entry_point("fakechat", FakePluginChannel)

    config = {
        "auth": {
            "pairing_db_path": str(tmp_path / "pairing.json"),
            "max_messages_per_minute": 60,
            "code_ttl_seconds": 300,
        },
        "channels": {
            "my-fakechat": {"type": "fakechat"},
        },
        "cron": {
            "log_path": str(tmp_path / "cron.jsonl"),
        },
    }

    with patch(
        "letsgo_gateway.channels.registry.entry_points",
        return_value=[mock_ep],
    ):
        daemon = GatewayDaemon(config=config)

    adapter: FakePluginChannel = daemon.channels["my-fakechat"]

    # Verify send works
    msg = OutboundMessage(
        channel=ChannelType("fakechat"),
        channel_name="my-fakechat",
        thread_id=None,
        text="Hello from integration test",
    )
    await adapter.start()
    result = await adapter.send(msg)

    assert result is True
    assert len(adapter.sent_messages) == 1
    assert adapter.sent_messages[0].text == "Hello from integration test"


@pytest.mark.asyncio
async def test_plugin_channel_receives_inbound(tmp_path: Path):
    """Plugin channel can trigger on_message callback from daemon."""
    mock_ep = _mock_entry_point("fakechat", FakePluginChannel)

    config = {
        "auth": {
            "pairing_db_path": str(tmp_path / "pairing.json"),
            "max_messages_per_minute": 60,
            "code_ttl_seconds": 300,
        },
        "channels": {
            "my-fakechat": {"type": "fakechat"},
        },
        "cron": {
            "log_path": str(tmp_path / "cron.jsonl"),
        },
    }

    with patch(
        "letsgo_gateway.channels.registry.entry_points",
        return_value=[mock_ep],
    ):
        daemon = GatewayDaemon(config=config)

    adapter: FakePluginChannel = daemon.channels["my-fakechat"]

    # The daemon should have set on_message callback
    assert adapter._on_message is not None

    # Simulate an inbound message through the callback
    msg = InboundMessage(
        channel=ChannelType("fakechat"),
        channel_name="my-fakechat",
        sender_id="test-user",
        sender_label="Test User",
        text="hello from plugin",
    )
    response = await adapter._on_message(msg)
    # Daemon routes to its _on_message handler (pairing/routing logic)
    assert isinstance(response, str)


def test_custom_channel_type_in_messages():
    """Plugin channels can use custom ChannelType strings in messages."""
    msg = InboundMessage(
        channel=ChannelType("fakechat"),
        channel_name="my-fakechat",
        sender_id="u1",
        sender_label="User",
        text="test",
    )
    assert msg.channel == "fakechat"
    assert isinstance(msg.channel, ChannelType)

    out = OutboundMessage(
        channel=ChannelType("fakechat"),
        channel_name="my-fakechat",
        thread_id=None,
        text="reply",
    )
    assert out.channel == "fakechat"
```

**Step 2: Run tests to verify they pass**

Run: `cd ~/dev/amplifier-bundle-letsgo && python -m pytest tests/test_gateway/test_integration_plugin.py -v`
Expected: All 5 tests PASS

**Step 3: Run the full gateway test suite**

Run: `cd ~/dev/amplifier-bundle-letsgo && python -m pytest tests/test_gateway/ -v`
Expected: All tests PASS across all test files

**Step 4: Commit**

```bash
git add tests/test_gateway/test_integration_plugin.py
git commit -m "test: add integration tests for full plugin channel discovery flow"
```

---

## Summary

| Task | Phase | Type | Files Changed |
|------|-------|------|---------------|
| 1. Channel Registry | 0 | Create | `registry.py`, `test_registry.py` |
| 2. Daemon Migration | 0 | Modify | `daemon.py`, `test_registry.py` |
| 3. Extensible ChannelType | 0 | Modify | `models.py`, `test_registry.py` |
| 4. Entry Points in pyproject | 0 | Modify | `pyproject.toml` |
| 5. DisplaySystem Protocol | 0 | Create | `display.py`, `test_display.py` |
| 6. Capability Contracts Doc | 0 | Create | `CAPABILITY_CONTRACTS.md` |
| 7. Lazy \_\_init\_\_.py | 1 | Modify | `channels/__init__.py`, `test_registry.py` |
| 8. Signal Adapter | 1 | Create | `channels/signal/*` (4 files) |
| 9. Matrix Adapter | 1 | Create | `channels/matrix/*` (4 files) |
| 10. Teams Adapter | 1 | Create | `channels/teams/*` (4 files) |
| 11. Setup Wizard Recipe | 1 | Modify | `setup-wizard.yaml` |
| 12. Channel Onboard Recipe | 1 | Modify | `channel-onboard.yaml` |
| 13. Integration Test | 1 | Create | `test_integration_plugin.py` |

**Total: 13 tasks, ~25 new/modified files, ~38 individual steps**
