# Gateway Awareness

The **LetsGo Gateway** is a standalone multi-channel messaging daemon that connects external platforms to Amplifier agent sessions.

## Key Facts

- **13 channel adapters** — Webhook, WhatsApp, Telegram, Discord, Slack, and 8 plugin channels (Signal, Matrix, Teams, LINE, Google Chat, iMessage, Nostr, IRC, Mattermost, Twitch, Feishu)
- **Sender pairing** — 6-character codes authenticate senders before routing begins
- **Session routing** — per-sender sessions with creation, resumption, and stale cleanup
- **Cron scheduling** — recipe-based scheduled tasks with standard cron expressions

## When This Activates

- User asks about connecting a messaging platform (Telegram, Discord, Slack, etc.)
- User needs to approve or manage sender pairings
- User wants to set up or manage scheduled tasks
- User reports message delivery or routing issues

## Delegate to Expert

For channel setup, pairing, cron management, or diagnostics, delegate to `letsgo:gateway-operator`.

The expert handles:
- Channel adapter configuration and testing
- Pairing code generation, approval, and revocation
- Cron job creation, management, and execution history
- Gateway daemon health and message pipeline diagnostics
