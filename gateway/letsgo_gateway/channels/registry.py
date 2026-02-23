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
