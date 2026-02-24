# WebChat Capabilities

You have access to a web chat interface and admin dashboard through the LetsGo gateway.

## Web Chat Interface

A browser-based chat UI is available at `/chat` on the webchat server (default: `http://localhost:8090/chat`). Users connect via WebSocket for real-time messaging with the gateway agent.

- Messages are routed through the gateway's standard auth and routing pipeline
- New users go through the pairing flow just like any other channel
- The chat supports text messages with markdown rendering

## Admin Dashboard

A 6-view admin dashboard is available at `/admin/` on the webchat server. All admin endpoints require Bearer token authentication with a **fail-closed** model — if the token is missing, invalid, or the auth check errors, access is denied.

### Dashboard Views

1. **Sessions** (`/admin/`) — Active and recent gateway sessions with sender info, channel, and message counts
2. **Channels** (`/admin/channels`) — Connected channels with status, type, and message throughput
3. **Senders** (`/admin/senders`) — Known senders with pairing status, approval state, and last activity
4. **Cron** (`/admin/cron`) — Scheduled tasks and heartbeat log with execution history
5. **Usage** (`/admin/usage`) — Token usage, message volume, and cost tracking over time
6. **Agents** (`/admin/agents`) — Registered agents and their capabilities, tool access, and session assignments

### Admin Authentication

- All `/admin/` routes require a `Bearer <token>` in the `Authorization` header
- The admin token is stored via the secrets tool as `webchat/admin/token`
- Auth is **fail-closed**: any error in token validation results in a 401 response
- The dashboard SPA fetches data from `/admin/api/` JSON endpoints using the same token

## When to Mention These Features

**Mention the web chat when:**
- A user asks about browser-based or web-based messaging options
- Setting up the gateway and choosing channels — webchat is a channel option
- The user wants a quick way to test the gateway without configuring Telegram/Discord/etc.

**Mention the admin dashboard when:**
- A user asks about monitoring or managing the gateway
- Troubleshooting channel connectivity — the Channels view shows status
- Checking who is paired/approved — the Senders view shows pairing state
- Reviewing scheduled tasks — the Cron view shows heartbeat and task history
- Understanding usage/costs — the Usage view tracks token and message volumes
- Managing agents — the Agents view shows registered agents and their tools

**Do NOT mention these features when:**
- The user is working on unrelated tasks (code review, file editing, etc.)
- The webchat satellite bundle is not installed
- The user already knows about and is actively using these features