# Heartbeat System

The LetsGo gateway includes a **heartbeat engine** for proactive scheduled agent check-ins via the gateway.

## Key Facts

- **CronScheduler fires HeartbeatEngine** on a configurable schedule without user interaction
- **Per-agent prompts** — each agent can have a custom focus file; falls back to a default
- **Full Amplifier sessions** — heartbeat sessions are identical to user sessions; all hooks and tools load
- **Channel routing** — responses are pushed to designated channel adapters (e.g., Telegram, webhook)

## When This Activates

- User asks about proactive agent check-ins or scheduled agent outreach
- User wants to configure which agents run heartbeats and on what schedule
- A heartbeat is failing or not firing as expected

## Delegate to Expert

For heartbeat configuration, delegate to `letsgo:gateway-operator`.

The expert handles:
- Configuring heartbeat schedule and target agents
- Setting up per-agent focus files
- Routing heartbeat output to specific channels
- Diagnosing heartbeat execution failures
