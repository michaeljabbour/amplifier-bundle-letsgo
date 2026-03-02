# WebChat Capabilities

The LetsGo gateway includes a browser-based web chat interface and admin dashboard for managing the gateway.

## Features

- **Web chat at `/chat`** — Real-time WebSocket messaging with the gateway agent; supports text with markdown rendering
- **Admin dashboard at `/admin/` with 6 views** — Sessions, Channels, Senders, Cron, Usage, Agents

## When This Activates

- User asks about browser-based messaging or testing the gateway without configuring a platform channel
- User wants to monitor or manage the gateway (sessions, channels, senders, cron, usage, agents)
- User needs to troubleshoot channel connectivity, pairing status, or scheduled tasks

## Delegate to Expert

For webchat setup or admin configuration, delegate to `letsgo:gateway-operator`.

The expert handles:
- Webchat server installation and configuration
- Admin token setup and authentication
- Reading and interpreting each dashboard view
