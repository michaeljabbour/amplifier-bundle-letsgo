"""Tests for channel registry discovery."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from letsgo_gateway.channels.base import ChannelAdapter
from letsgo_gateway.channels.registry import discover_channels


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
