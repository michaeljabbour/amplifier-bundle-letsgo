"""Security defaults loader for the LetsGo gateway.

Reads ``security_defaults.yaml`` and provides the blocked sender/recipient
patterns, channel safety defaults, and proactive send rules to the daemon
and channel adapters.

The YAML file lives alongside this module at::

    gateway/letsgo_gateway/security_defaults.yaml

Users can override any setting via the gateway config (``config.yaml``)
under a top-level ``security:`` key.  Gateway config values take
precedence over the defaults file.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULTS_PATH = Path(__file__).parent / "security_defaults.yaml"

# Minimal fallback if the YAML file is missing or unreadable.
_HARDCODED_FALLBACK: dict[str, Any] = {
    "blocked_sender_patterns": ["broadcast", "status@", "@newsletter"],
    "blocked_recipient_patterns": ["broadcast", "status@", "@g.us", "@newsletter"],
    "proactive_send": {
        "require_approved_sender": True,
        "allow_heartbeat_agents": True,
    },
    "global_dry_run": False,
    "rate_limit": {"messages_per_minute": 10},
    "outbound_rate_limit": {"sends_per_recipient_per_hour": 20},
    "channel_defaults": {
        "whatsapp": {
            "blocked_sender_patterns": ["status@broadcast", "@g.us", "@newsletter"],
            "blocked_recipient_patterns": ["broadcast", "@g.us", "@newsletter", "status@"],
        },
        "telegram": {"allow_groups": False},
        "discord": {"dm_only": True},
        "slack": {"dm_only": True},
    },
}


def load_security_defaults(config_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Load security defaults from YAML, with optional config overrides.

    Args:
        config_overrides: A ``security:`` section from the gateway config.
            Values here take precedence over the defaults file.

    Returns:
        Merged security configuration dict.
    """
    defaults = _load_yaml_defaults()

    # Merge overrides on top of defaults (shallow — override keys win)
    if config_overrides:
        for key, value in config_overrides.items():
            if isinstance(value, dict) and isinstance(defaults.get(key), dict):
                defaults[key] = {**defaults[key], **value}
            else:
                defaults[key] = value

    return defaults


def _load_yaml_defaults() -> dict[str, Any]:
    """Load the YAML defaults file, falling back to hardcoded values."""
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        logger.debug("PyYAML not available — using hardcoded security defaults")
        return dict(_HARDCODED_FALLBACK)

    if not _DEFAULTS_PATH.exists():
        logger.warning(
            "Security defaults file not found at %s — using hardcoded fallback",
            _DEFAULTS_PATH,
        )
        return dict(_HARDCODED_FALLBACK)

    try:
        with open(_DEFAULTS_PATH) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            logger.warning("Security defaults YAML is not a dict — using fallback")
            return dict(_HARDCODED_FALLBACK)
        return data
    except Exception:
        logger.exception("Failed to load security defaults — using fallback")
        return dict(_HARDCODED_FALLBACK)


def get_blocked_sender_patterns(security: dict[str, Any]) -> list[str]:
    """Return the list of blocked inbound sender patterns."""
    return security.get("blocked_sender_patterns", _HARDCODED_FALLBACK["blocked_sender_patterns"])


def get_blocked_recipient_patterns(security: dict[str, Any]) -> list[str]:
    """Return the list of blocked outbound recipient patterns."""
    return security.get("blocked_recipient_patterns", _HARDCODED_FALLBACK["blocked_recipient_patterns"])


def get_channel_defaults(security: dict[str, Any], channel_type: str) -> dict[str, Any]:
    """Return safety defaults for a specific channel type."""
    return security.get("channel_defaults", {}).get(channel_type, {})


def is_proactive_send_restricted(security: dict[str, Any]) -> bool:
    """Return True if proactive sends require an approved sender."""
    return security.get("proactive_send", {}).get("require_approved_sender", True)


def allow_heartbeat_agents(security: dict[str, Any]) -> bool:
    """Return True if heartbeat agent_ids bypass the approved sender check."""
    return security.get("proactive_send", {}).get("allow_heartbeat_agents", True)
