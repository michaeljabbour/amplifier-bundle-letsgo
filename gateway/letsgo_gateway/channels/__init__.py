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
