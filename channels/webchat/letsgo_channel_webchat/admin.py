"""Admin auth middleware and API route registration for WebChatChannel."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

logger = logging.getLogger(__name__)

# Typed app keys to avoid NotAppKeyWarning
_admin_token_key: web.AppKey[str] = web.AppKey("admin_token")
_daemon_key: web.AppKey[Any] = web.AppKey("daemon")


@web.middleware
async def admin_auth_middleware(
    request: web.Request,
    handler: Any,
) -> web.StreamResponse:
    """Check Bearer token for /admin/ routes; pass through non-admin routes."""
    if not request.path.startswith("/admin/"):
        return await handler(request)

    expected_token: str | None = request.app.get(_admin_token_key)
    if not expected_token:
        raise web.HTTPUnauthorized(text="Admin not configured")

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise web.HTTPUnauthorized(text="Missing or invalid Authorization header")

    token = auth_header[len("Bearer ") :]
    if token != expected_token:
        raise web.HTTPUnauthorized(text="Invalid token")

    return await handler(request)


def setup_admin_routes(app: web.Application, daemon: Any, token: str) -> None:
    """Register admin API endpoints and auth middleware on the app."""
    app[_admin_token_key] = token
    app[_daemon_key] = daemon
    app.middlewares.insert(0, admin_auth_middleware)

    app.router.add_get("/admin/sessions", _handle_sessions)
    app.router.add_delete("/admin/sessions", _handle_delete_session)
    app.router.add_get("/admin/channels", _handle_channels)
    app.router.add_get("/admin/senders", _handle_senders)
    app.router.add_post("/admin/senders/block", _handle_block_sender)
    app.router.add_post("/admin/senders/unblock", _handle_unblock_sender)
    app.router.add_get("/admin/cron", _handle_cron)
    app.router.add_get("/admin/usage", _handle_usage)
    app.router.add_get("/admin/agents", _handle_agents)


# ---------------------------------------------------------------------------
# Admin API handlers
# ---------------------------------------------------------------------------


async def _handle_sessions(request: web.Request) -> web.Response:
    """GET /admin/sessions — list active sessions."""
    daemon = request.app[_daemon_key]
    sessions = daemon.router.active_sessions()
    data = []
    for key, sess in sessions.items():
        data.append({"session_id": key, **{k: str(v) for k, v in sess.items()}})
    return web.json_response({"sessions": data})


async def _handle_delete_session(request: web.Request) -> web.Response:
    """DELETE /admin/sessions?id=... — close a session."""
    daemon = request.app[_daemon_key]
    session_id = request.query.get("id", "")
    if not session_id:
        return web.json_response({"error": "id parameter required"}, status=400)
    closed = daemon.router.close_session(session_id)
    return web.json_response({"closed": closed})


async def _handle_channels(request: web.Request) -> web.Response:
    """GET /admin/channels — list registered channels."""
    daemon = request.app[_daemon_key]
    channels = []
    for name, adapter in daemon.channels.items():
        channels.append(
            {
                "name": name,
                "running": adapter.is_running,
                "type": adapter.config.get("type", name),
            }
        )
    return web.json_response({"channels": channels})


async def _handle_senders(request: web.Request) -> web.Response:
    """GET /admin/senders — list all senders."""
    daemon = request.app[_daemon_key]
    senders = daemon.auth.get_all_senders()
    data = []
    for rec in senders:
        data.append(
            {
                "sender_id": rec.sender_id,
                "channel": rec.channel.value,
                "status": rec.status.value,
                "label": rec.label,
                "message_count": rec.message_count,
            }
        )
    return web.json_response({"senders": data})


async def _handle_block_sender(request: web.Request) -> web.Response:
    """POST /admin/senders/block — block a sender."""
    daemon = request.app[_daemon_key]
    body = await request.json()
    sender_id = body.get("sender_id", "")
    channel = body.get("channel", "")
    if not sender_id or not channel:
        return web.json_response(
            {"error": "sender_id and channel required"}, status=400
        )
    from letsgo_gateway.models import ChannelType

    daemon.auth.block_sender(sender_id, ChannelType(channel))
    return web.json_response({"blocked": True})


async def _handle_unblock_sender(request: web.Request) -> web.Response:
    """POST /admin/senders/unblock — unblock a sender."""
    daemon = request.app[_daemon_key]
    body = await request.json()
    sender_id = body.get("sender_id", "")
    channel = body.get("channel", "")
    if not sender_id or not channel:
        return web.json_response(
            {"error": "sender_id and channel required"}, status=400
        )
    from letsgo_gateway.models import ChannelType

    daemon.auth.unblock_sender(sender_id, ChannelType(channel))
    return web.json_response({"unblocked": True})


async def _handle_cron(request: web.Request) -> web.Response:
    """GET /admin/cron — list cron jobs."""
    daemon = request.app[_daemon_key]
    jobs = []
    if hasattr(daemon.cron, "_jobs"):
        for name, job in daemon.cron._jobs.items():
            jobs.append({"name": name, **{k: str(v) for k, v in job.items()}})
    return web.json_response({"jobs": jobs})


async def _handle_usage(request: web.Request) -> web.Response:
    """GET /admin/usage — usage statistics."""
    daemon = request.app[_daemon_key]
    senders = daemon.auth.get_all_senders()
    total_messages = sum(r.message_count for r in senders)
    return web.json_response(
        {
            "total_senders": len(senders),
            "total_messages": total_messages,
            "active_sessions": len(daemon.router.active_sessions()),
        }
    )


async def _handle_agents(request: web.Request) -> web.Response:
    """GET /admin/agents — list configured agents."""
    daemon = request.app[_daemon_key]
    agents_config = getattr(daemon, "_config", {}).get("agents", {})
    return web.json_response({"agents": agents_config})
