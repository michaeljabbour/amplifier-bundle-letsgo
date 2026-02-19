"""CLI entry point for the gateway daemon."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from pathlib import Path

from .daemon import GatewayDaemon

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = """\
# LetsGo Gateway configuration
# Created automatically on first run.

channels:
  whatsapp:
    type: whatsapp
    # QR code auth — no API keys needed.
    # Scan the code that appears in this terminal with your WhatsApp app.
    # Session persists in ~/.letsgo/whatsapp-session/ so you only scan once.
"""


def _ensure_config(config_path: str) -> str:
    """Create a default config file if none exists. Returns the resolved path."""
    path = Path(config_path).expanduser()
    if path.exists():
        return str(path)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_DEFAULT_CONFIG)
    logger.info("Created default config at %s (WhatsApp enabled)", path)
    return str(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="LetsGo Gateway Daemon")
    parser.add_argument(
        "--config",
        default="~/.letsgo/gateway/config.yaml",
        help="Config file path",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    config_path = _ensure_config(args.config)
    daemon = GatewayDaemon(config_path=config_path)

    loop = asyncio.new_event_loop()

    # Handle SIGINT/SIGTERM gracefully
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, lambda: asyncio.ensure_future(daemon.stop())
        )

    try:
        loop.run_until_complete(daemon.start())
        loop.run_forever()
    finally:
        loop.run_until_complete(daemon.stop())
        loop.close()


if __name__ == "__main__":
    main()
