"""CLI entry point for the gateway daemon."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from .daemon import GatewayDaemon


def main() -> None:
    parser = argparse.ArgumentParser(description="LetsGo Gateway Daemon")
    parser.add_argument(
        "--config",
        default="~/.letsgo/gateway/config.yaml",
        help="Config file path",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Bind host"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Bind port"
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

    daemon = GatewayDaemon(config_path=args.config)

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
