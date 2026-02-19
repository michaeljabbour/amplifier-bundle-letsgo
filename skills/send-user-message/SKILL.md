---
name: send-user-message
version: 1.0.0
description: >-
    Proactive outbound messaging through the letsgo gateway. Use when the agent
    needs to notify, alert, or send an unsolicited message to a user --
    especially during scheduled tasks, recipe execution, or when the agent wants
    to reach out without a prior user message. Triggers: "send message to user",
    "notify user", "alert user", "message the user on discord/telegram/slack",
    or any need to proactively communicate with a paired sender.
# Send User Message

Send proactive outbound messages to paired users through the letsgo gateway's channel adapters. Messages are delivered via the configured channel (webhook, Telegram, Discord, or Slack) to users who have completed the pairing flow.

## When to Use

- Proactively notify a user (task completion, status update, alert)
- Send a message during a scheduled recipe execution (no active user conversation)
- Reach a specific user on a specific channel when multiple pairings exist
- Deliver results from background work (heartbeat checks, cron jobs)

## Architecture Overview

The letsgo gateway manages user relationships through the `PairingStore` (defined in `gateway/letsgo_gateway/auth.py`) and delivers outbound messages through `ChannelAdapter` implementations.

**Key components:**
- `PairingStore` -- JSON-backed store of approved sender/channel pairings with pairing codes, rate limiting, and approval status
- `OutboundMessage` -- Data model for outbound messages (defined in `gateway/letsgo_gateway/models.py`)
- `ChannelAdapter` -- Abstract base for channel delivery (`gateway/letsgo_gateway/channels/base.py`)
- `SessionRouter` -- Routes messages to/from sessions (`gateway/letsgo_gateway/router.py`)
- Channel implementations: `WebhookChannel`, `TelegramChannel`, `DiscordChannel`, `SlackChannel`

## Workflow

### 1. Identify the target

If you already know the target from the current conversation context (channel and sender ID from the inbound message), skip to step 2.

If running from a scheduled task or unsure which user to message, query the `PairingStore` for approved pairings:

```python
from letsgo_gateway.auth import PairingStore

store = PairingStore(base_dir)
approved = store.get_approved_senders()
# Returns list of SenderRecord objects with: channel, sender_id, display_name, approved_at
```

Each `SenderRecord` contains:
- `channel` -- Channel type (webhook, telegram, discord, slack)
- `sender_id` -- Channel-specific user identifier
- `display_name` -- Human-readable name
- `approved_at` -- When the pairing was approved

Pick the appropriate target based on task context, user name, or channel preference.

### 2. Send the message

Construct an `OutboundMessage` and route it through the gateway:

```python
from letsgo_gateway.models import OutboundMessage, ChannelType

message = OutboundMessage(
    channel=ChannelType.TELEGRAM,
    sender_id="123456",
    display_name="Alice",
    content="Here's the report you requested.",
    agent_id="analyst",          # optional: attribute to a specific agent
)
```

The gateway daemon's router dispatches the `OutboundMessage` to the appropriate `ChannelAdapter` for delivery.

### 3. Choosing a target when multiple pairings exist

When there are multiple approved pairings and you need to decide who to message:

- If the task or context specifies a user by name, match against the `display_name` field
- If the task specifies a channel, filter by `channel`
- If ambiguous, prefer the most recently approved pairing
- If still ambiguous, send to all relevant targets (one message per target)

## Channel Adapters

| Channel | Adapter | Status |
|---------|---------|--------|
| Webhook | `WebhookChannel` | Full implementation (HMAC-SHA256 signatures, HTTP POST) |
| Telegram | `TelegramChannel` | Stub (graceful no-op) |
| Discord | `DiscordChannel` | Stub (graceful no-op) |
| Slack | `SlackChannel` | Stub (graceful no-op) |

Stub channels load without error and silently succeed on all operations. When a channel implementation is completed, messages will be delivered automatically without code changes.

## Use Cases

### Task completion alert

Send a notification when a long-running recipe completes:

```python
OutboundMessage(
    channel=ChannelType.WEBHOOK,
    sender_id=sender_id,
    display_name=display_name,
    content="Build completed successfully. All 47 tests passing.",
    agent_id="builder",
)
```

### Scheduled notification

Pair with the schedule skill to send periodic updates:

```python
# In a recipe step or scheduled job:
OutboundMessage(
    channel=ChannelType.TELEGRAM,
    sender_id=sender_id,
    display_name=display_name,
    content="Daily digest: 3 PRs merged, 2 issues closed, 1 deployment.",
    agent_id="digest",
)
```

### Health check results

Deliver heartbeat/monitoring results:

```python
OutboundMessage(
    channel=ChannelType.DISCORD,
    sender_id=sender_id,
    display_name=display_name,
    content="Health check alert: API latency above threshold (>500ms) for 10 minutes.",
    agent_id="monitor",
)
```

## Gateway Module Reference

- `gateway/letsgo_gateway/models.py` -- `OutboundMessage`, `InboundMessage`, `ChannelType`, `SenderRecord`
- `gateway/letsgo_gateway/auth.py` -- `PairingStore`, `generate_pairing_code`
- `gateway/letsgo_gateway/router.py` -- `SessionRouter` (message routing)
- `gateway/letsgo_gateway/channels/base.py` -- `ChannelAdapter` (abstract base)
- `gateway/letsgo_gateway/channels/webhook.py` -- `WebhookChannel` (full implementation)
- `gateway/letsgo_gateway/channels/telegram.py` -- `TelegramChannel` (stub)
- `gateway/letsgo_gateway/channels/discord.py` -- `DiscordChannel` (stub)
- `gateway/letsgo_gateway/channels/slack.py` -- `SlackChannel` (stub)
- `gateway/letsgo_gateway/daemon.py` -- `GatewayDaemon` (orchestrates all components)

## Tips

- Always check `PairingStore.get_approved_senders()` before sending -- only approved pairings can receive messages
- Include `agent_id` to attribute messages to the originating agent for traceability
- Stub channels silently succeed -- check which channels have full implementations before relying on delivery
- For scheduled notifications, pair this skill with the schedule skill and a recipe
- Messages include the `sender_id` so channel adapters can route agent-initiated messages to the correct user
- The pairing flow (code generation, approval) is managed by the gateway's auth module -- this skill only handles post-pairing message delivery
