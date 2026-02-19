---
name: send-user-message
version: 2.0.0
description: >-
    Proactive outbound messaging through the letsgo gateway. Use when the agent
    needs to notify, alert, or send an unsolicited message to a user --
    especially during scheduled tasks, recipe execution, or when the agent wants
    to reach out without a prior user message. Triggers: "send message to user",
    "notify user", "alert user", "message the user on discord/telegram/slack",
    or any need to proactively communicate with a paired sender.
---

# Send User Message

Send proactive outbound messages to paired users through the letsgo gateway's channel adapters. Messages are delivered via the configured channel (webhook, Telegram, Discord, or Slack) to users who have completed the pairing flow.

All methods below use **bash** -- no Python imports or gateway package on PYTHONPATH required.

## When to Use

- Proactively notify a user (task completion, status update, alert)
- Send a message during a scheduled recipe execution (no active user conversation)
- Reach a specific user on a specific channel when multiple pairings exist
- Deliver results from background work (heartbeat checks, cron jobs)

## List Targets

If you already know the target from the current conversation context (channel and sender ID from the inbound message), skip straight to **Send the Message**.

If running from a scheduled task or unsure which user to message, list approved pairings:

```bash
letsgo-gateway pairing list --approved
```

Each pairing includes:
- `channel` -- Channel type (webhook, telegram, discord, slack)
- `sender_id` -- Channel-specific user identifier
- `display_name` -- Human-readable name
- `approved_at` -- When the pairing was approved

Pick the appropriate target based on task context, user name, or channel preference.

### Choosing a target when multiple pairings exist

- If the task or context specifies a user by name, match against the `display_name` field
- If the task specifies a channel, filter by `channel`
- If ambiguous, prefer the most recently approved pairing
- If still ambiguous, send to all relevant targets (one message per target)

## Send the Message

Three approaches, listed in order of preference. Use whichever is available in your environment.

### Approach 1 -- Gateway CLI (preferred)

The simplest option when the `letsgo-gateway` CLI is on PATH:

```bash
letsgo-gateway send \
  --channel telegram \
  --sender-id USER123 \
  --message "Hello from your assistant"
```

Optional flags:
- `--display-name "Alice"` -- human-readable recipient name
- `--agent-id builder` -- attribute the message to a specific agent

### Approach 2 -- Webhook HTTP POST (universal)

POST to the gateway daemon's outbound endpoint. Works from any environment that has `curl`:

```bash
curl -X POST http://localhost:8080/outbound \
  -H "Content-Type: application/json" \
  -d '{"channel": "telegram", "sender_id": "USER123", "text": "Hello from your assistant"}'
```

A fuller payload with optional fields:

```bash
curl -X POST http://localhost:8080/outbound \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "telegram",
    "sender_id": "USER123",
    "display_name": "Alice",
    "text": "Build completed successfully. All 47 tests passing.",
    "agent_id": "builder"
  }'
```

The daemon returns a JSON response with delivery status.

### Approach 3 -- Queue file drop (fallback)

Write a JSON file directly to the outbound queue directory for the gateway daemon to pick up. Use this when neither the CLI nor the HTTP endpoint is reachable (e.g., the daemon is running but only watching the filesystem):

```bash
MSG_ID="$(date +%s)-$$"
cat > ~/.letsgo/gateway/outbound/${MSG_ID}.json << 'EOF'
{
  "channel": "telegram",
  "sender_id": "USER123",
  "display_name": "Alice",
  "text": "Hello from your assistant",
  "agent_id": "builder"
}
EOF
```

The daemon polls `~/.letsgo/gateway/outbound/` and delivers any `.json` files it finds, then removes them after successful delivery.

## Channel Adapters

| Channel   | Status |
|-----------|--------|
| Webhook   | Full implementation (HMAC-SHA256 signatures, HTTP POST) |
| Telegram  | Stub (graceful no-op) |
| Discord   | Stub (graceful no-op) |
| Slack     | Stub (graceful no-op) |

Stub channels load without error and silently succeed on all operations. When a channel implementation is completed, messages will be delivered automatically without changes to your send commands.

## Use Cases

### Task completion alert

```bash
letsgo-gateway send \
  --channel webhook \
  --sender-id "$SENDER_ID" \
  --agent-id builder \
  --message "Build completed successfully. All 47 tests passing."
```

### Scheduled notification

Pair with the schedule skill to send periodic updates:

```bash
letsgo-gateway send \
  --channel telegram \
  --sender-id "$SENDER_ID" \
  --agent-id digest \
  --message "Daily digest: 3 PRs merged, 2 issues closed, 1 deployment."
```

### Health check results

```bash
letsgo-gateway send \
  --channel discord \
  --sender-id "$SENDER_ID" \
  --agent-id monitor \
  --message "Health check alert: API latency above threshold (>500ms) for 10 minutes."
```

## Tips

- Always check `letsgo-gateway pairing list --approved` before sending -- only approved pairings can receive messages
- Include `--agent-id` to attribute messages to the originating agent for traceability
- Stub channels silently succeed -- check which channels have full implementations before relying on delivery
- For scheduled notifications, pair this skill with the schedule skill and a recipe
- The pairing flow (code generation, approval) is managed by the gateway's auth module -- this skill only handles post-pairing message delivery
- For the queue file drop approach, use a unique filename (timestamp + PID) to avoid collisions
