"""Integration tests — WebChat channel through the gateway daemon."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from letsgo_gateway.daemon import GatewayDaemon
from letsgo_gateway.models import ChannelType, InboundMessage, OutboundMessage


def _make_daemon(tmp_path: Path, **config_overrides: Any) -> GatewayDaemon:
    config = {
        "channels": {},
        "auth": {"pairing_db_path": str(tmp_path / "pairing.json")},
        "cron": {"log_path": str(tmp_path / "cron.jsonl")},
        "files_dir": str(tmp_path / "files"),
        **config_overrides,
    }
    return GatewayDaemon(config=config)


class FakeWebChatChannel:
    def __init__(self, name="webchat"):
        self.name = name
        self.config = {"type": "webchat"}
        self._running = True
        self._on_message = None
        self.sent = []

    @property
    def is_running(self):
        return self._running

    def set_on_message(self, cb):
        self._on_message = cb

    async def start(self):
        self._running = True

    async def stop(self):
        self._running = False

    async def send(self, msg):
        self.sent.append(msg)
        return True


class TestWebChatDaemonIntegration:
    @pytest.mark.asyncio
    async def test_daemon_discovers_webchat_channel(self, tmp_path):
        fake_cls = MagicMock(side_effect=lambda name, config: FakeWebChatChannel(name))
        with patch(
            "letsgo_gateway.daemon.discover_channels",
            return_value={"webchat": fake_cls},
        ):
            daemon = _make_daemon(tmp_path, channels={"webchat": {"type": "webchat"}})
        assert "webchat" in daemon.channels

    @pytest.mark.asyncio
    async def test_daemon_without_webchat_works(self, tmp_path):
        daemon = _make_daemon(tmp_path)
        assert "webchat" not in daemon.channels

    @pytest.mark.asyncio
    async def test_webchat_inbound_routes_through_daemon(self, tmp_path):
        daemon = _make_daemon(tmp_path)
        msg = InboundMessage(
            channel=ChannelType("webchat"),
            channel_name="webchat",
            sender_id="web-user-1",
            sender_label="web-user-1",
            text="hello",
        )
        response = await daemon._on_message(msg)
        assert "pairing" in response.lower() or "code" in response.lower()

    @pytest.mark.asyncio
    async def test_webchat_outbound_to_fake_channel(self, tmp_path):
        fake = FakeWebChatChannel()
        daemon = _make_daemon(tmp_path)
        daemon.channels["webchat"] = fake
        outbound = OutboundMessage(
            channel=ChannelType("webchat"),
            channel_name="webchat",
            thread_id=None,
            text="Hello from the agent!",
        )
        await fake.send(outbound)
        assert len(fake.sent) == 1
        assert fake.sent[0].text == "Hello from the agent!"
