# Gateway Awareness

The **LetsGo Gateway** is a standalone daemon that manages multi-channel messaging between external platforms and Amplifier agent sessions. It acts as the front door — receiving messages from various channels, authenticating senders, routing conversations to per-sender sessions, and executing scheduled tasks.

## Architecture Overview

The gateway is a long-running process that listens for inbound messages, processes them through a pipeline, and dispatches them to Amplifier sessions. It does not contain agent logic itself — it is infrastructure that connects external messaging platforms to the agent runtime.

## Channel Adapters

The gateway supports multiple messaging platforms through a pluggable adapter system:

- **Webhook** — Generic HTTP endpoint for custom integrations. Accepts POST requests with a standard message payload. Useful for connecting internal tools, custom bots, or testing.
- **Telegram** — Telegram Bot API adapter. Handles long-polling or webhook-based message receipt, message formatting (Markdown), and media attachments.
- **Discord** — Discord bot adapter. Manages guild connections, channel routing, slash commands, and rich embeds.
- **Slack** — Slack app adapter. Handles Events API subscriptions, interactive messages, slash commands, and thread-based conversations.
- **WhatsApp** — WhatsApp Cloud API adapter. Receives messages via Meta webhook, sends responses via the Graph API. Supports text, images, documents, audio, and video. Verifies webhook signatures when app_secret is configured. Splits long messages at paragraph boundaries.

Each adapter normalizes inbound messages into a common internal format before passing them to the authentication and routing pipeline.

## PairingStore Authentication

The gateway uses a pairing-based authentication model rather than static API keys:

1. **Pairing code generation** — The gateway generates a 6-character alphanumeric code for a new sender.
2. **Code presentation** — The code is displayed to the administrator (via CLI, dashboard, or log output).
3. **Sender submission** — The sender sends their pairing code through their channel.
4. **Admin approval** — The administrator approves the pairing, binding the sender identity to an authorized session.
5. **Persistent binding** — Once paired, the sender is recognized on future messages without re-pairing.

Pairing codes are single-use and time-limited. Unpaired senders receive a rejection message directing them to request access.

## SessionRouter

The SessionRouter maintains a mapping of sender identities to Amplifier sessions:

- **Per-sender sessions** — Each authenticated sender gets their own session, maintaining conversation continuity across messages.
- **Session creation** — New sessions are created on first contact after successful pairing.
- **Session resumption** — Returning senders resume their existing session with full history.
- **Stale cleanup** — Sessions inactive beyond a configurable threshold are marked stale and eventually cleaned up. This prevents unbounded resource growth.
- **Routing logic** — Inbound messages are matched to sessions by sender identity (platform + user ID).

## CronScheduler

The gateway includes a built-in scheduler for recurring tasks:

- **Recipe-based execution** — Scheduled tasks are defined as Amplifier recipes, enabling complex multi-step workflows on a timer.
- **Cron expressions** — Standard cron syntax for scheduling (e.g., `0 9 * * MON-FRI` for weekday mornings).
- **Job management** — Create, list, pause, resume, and delete scheduled jobs via CLI or API.
- **Execution context** — Each cron job runs in its own session with the recipe's defined context.
- **Error handling** — Failed jobs are logged with error details. Configurable retry policies.

## Rate Limiting

The gateway enforces rate limits to prevent abuse and protect downstream resources:

- **Sliding window** — 10 messages per minute per sender, using a sliding window algorithm.
- **Graceful rejection** — Rate-limited messages receive a friendly "slow down" response rather than silent drops.
- **Per-sender tracking** — Limits are tracked per authenticated sender identity, not per IP or channel.

## CLI Interface

The gateway daemon is started and configured via the `letsgo-gateway` CLI:

```
letsgo-gateway --config <path>   # Path to gateway configuration file
               --host <addr>     # Bind address (default: 0.0.0.0)
               --port <port>     # Listen port (default: 8080)
               --log-level <lvl> # Log verbosity: debug, info, warn, error
```

## Message Flow

Every inbound message follows this pipeline:

```
Channel Adapter (normalize)
    → Authentication Check (is sender paired?)
        → If not paired: check for pairing code submission
        → If paired: continue
    → Rate Limit Check (within sliding window?)
        → If exceeded: reject with rate limit message
        → If within: continue
    → Session Router (find or create session)
    → Dispatch to Amplifier Session
    → Response returned through channel adapter
```

Each stage can short-circuit the pipeline with an appropriate response. Errors at any stage are logged with the sender identity and channel context.
