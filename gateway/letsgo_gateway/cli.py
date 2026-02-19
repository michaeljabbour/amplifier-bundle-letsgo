"""CLI entry point for the gateway daemon."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
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
    """Create a default config file if none exists."""
    path = Path(config_path).expanduser()
    if path.exists():
        return str(path)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_DEFAULT_CONFIG)
    logger.info(
        "Created default config at %s (WhatsApp enabled)",
        path,
    )
    return str(path)


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        description="LetsGo Gateway Daemon",
    )
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

    sub = parser.add_subparsers(dest="command")

    # start (default)
    sub.add_parser("start", help="Start the gateway daemon")

    # send
    send_p = sub.add_parser("send", help="Send a proactive message")
    send_p.add_argument("--channel", required=True, help="Channel name")
    send_p.add_argument("--sender-id", required=True, help="Recipient ID")
    send_p.add_argument("--message", required=True, help="Message text")

    # pairing
    pairing_p = sub.add_parser("pairing", help="Manage paired senders")
    pairing_sub = pairing_p.add_subparsers(dest="pairing_command")

    list_p = pairing_sub.add_parser("list", help="List paired senders")
    list_group = list_p.add_mutually_exclusive_group()
    list_group.add_argument(
        "--approved",
        action="store_true",
        help="Show only approved senders",
    )
    list_group.add_argument(
        "--pending",
        action="store_true",
        help="Show only pending senders",
    )

    approve_p = pairing_sub.add_parser("approve", help="Approve a pairing code")
    approve_p.add_argument("code", help="The pairing code to approve")

    # cron
    cron_p = sub.add_parser("cron", help="Manage cron jobs")
    cron_sub = cron_p.add_subparsers(dest="cron_command")

    cron_sub.add_parser("list", help="List scheduled jobs")

    create_p = cron_sub.add_parser("create", help="Create a cron job")
    create_p.add_argument("--name", required=True, help="Job name")
    create_p.add_argument(
        "--cron",
        required=True,
        help="Cron expression (e.g. '@hourly', '30 9 * * *')",
    )
    create_p.add_argument("--recipe", required=True, help="Recipe path")

    delete_p = cron_sub.add_parser("delete", help="Delete a cron job")
    delete_p.add_argument("--name", required=True, help="Job name to delete")

    return parser


# ---- subcommand handlers ----


def _cmd_start(args: argparse.Namespace) -> None:
    """Start the gateway daemon (default command)."""
    config_path = _ensure_config(args.config)
    daemon = GatewayDaemon(config_path=config_path)

    loop = asyncio.new_event_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.ensure_future(daemon.stop()),
        )

    try:
        loop.run_until_complete(daemon.start())
        loop.run_forever()
    finally:
        loop.run_until_complete(daemon.stop())
        loop.close()


def _cmd_send(args: argparse.Namespace) -> None:
    """Send a proactive message."""
    config_path = _ensure_config(args.config)
    daemon = GatewayDaemon(config_path=config_path)

    async def _run() -> bool:
        await daemon.start()
        try:
            return await daemon.send_to_channel(
                args.channel, args.sender_id, args.message
            )
        finally:
            await daemon.stop()

    ok = asyncio.run(_run())
    if ok:
        print("Message sent.")
    else:
        print("Failed to send message.", file=sys.stderr)
        sys.exit(1)


def _cmd_pairing(args: argparse.Namespace) -> None:
    """Handle pairing subcommands."""
    from .auth import PairingStore
    from .daemon import _load_config

    config = _load_config(args.config)
    store = PairingStore(config.get("auth", {}))

    if args.pairing_command == "list":
        for key, rec in store._senders.items():
            status = rec.status.value
            if args.approved and status != "approved":
                continue
            if args.pending and status != "pending":
                continue
            print(
                f"  {key}  status={status}"
                f"  label={rec.label!r}"
                f"  messages={rec.message_count}"
            )
    elif args.pairing_command == "approve":
        code = args.code.strip().upper()
        # Find the pending request with this code
        found = False
        for key, pr in list(store._pairing_requests.items()):
            if pr.code == code:
                ok = store.verify_pairing(pr.sender_id, pr.channel, code)
                if ok:
                    print(f"Approved: {key}")
                else:
                    print(f"Failed to approve: {key} (expired?)")
                found = True
                break
        if not found:
            print(
                f"No pending pairing with code {code}",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        print(
            "Usage: letsgo-gateway pairing {list|approve}",
            file=sys.stderr,
        )
        sys.exit(1)


def _cmd_cron(args: argparse.Namespace) -> None:
    """Handle cron subcommands."""
    from .cron import CronScheduler
    from .daemon import _load_config

    config = _load_config(args.config)
    scheduler = CronScheduler(config.get("cron", {}))

    if args.cron_command == "list":
        jobs = scheduler.list_jobs()
        if not jobs:
            print("No cron jobs configured.")
            return
        for job in jobs:
            print(
                f"  {job['name']}"
                f"  cron={job['cron']!r}"
                f"  recipe={job['recipe']}"
                f"  next={job['next_run']}"
            )
    elif args.cron_command == "create":
        scheduler.schedule(
            name=args.name,
            cron_expression=args.cron,
            recipe_path=args.recipe,
        )
        print(f"Created job: {args.name}")
        # Persist to config
        _persist_cron_job(args.config, args.name, args.cron, args.recipe)
    elif args.cron_command == "delete":
        if scheduler.unschedule(args.name):
            print(f"Deleted job: {args.name}")
        else:
            print(
                f"Job not found: {args.name}",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        print(
            "Usage: letsgo-gateway cron {list|create|delete}",
            file=sys.stderr,
        )
        sys.exit(1)


def _persist_cron_job(
    config_path: str,
    name: str,
    cron_expr: str,
    recipe: str,
) -> None:
    """Append a new cron job to the config file."""
    path = Path(config_path).expanduser()
    if not path.exists():
        return

    try:
        import yaml

        data = yaml.safe_load(path.read_text()) or {}
        cron_cfg = data.setdefault("cron", {})
        jobs = cron_cfg.setdefault("jobs", [])
        jobs.append({"name": name, "cron": cron_expr, "recipe": recipe})
        path.write_text(yaml.dump(data, default_flow_style=False))
    except ImportError:
        # No yaml — write JSON fallback
        data = json.loads(path.read_text())
        cron_cfg = data.setdefault("cron", {})
        jobs = cron_cfg.setdefault("jobs", [])
        jobs.append({"name": name, "cron": cron_expr, "recipe": recipe})
        path.write_text(json.dumps(data, indent=2))


# ---- main ----


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    command = args.command or "start"

    if command == "start":
        _cmd_start(args)
    elif command == "send":
        _cmd_send(args)
    elif command == "pairing":
        if not hasattr(args, "pairing_command"):
            parser.parse_args(["pairing", "--help"])
        _cmd_pairing(args)
    elif command == "cron":
        if not hasattr(args, "cron_command"):
            parser.parse_args(["cron", "--help"])
        _cmd_cron(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
