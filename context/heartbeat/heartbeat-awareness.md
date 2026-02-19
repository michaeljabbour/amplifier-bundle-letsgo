# Heartbeat System

The LetsGo gateway includes a **heartbeat engine** that proactively checks in with agents on a configurable schedule.

## How It Works

The heartbeat is a **direct programmatic session** — not a recipe, not a hook. The gateway daemon's CronScheduler fires the HeartbeatEngine on a schedule. For each configured agent:

1. **Build prompt** from context files (`context/heartbeat/heartbeat-system.md` + per-agent focus)
2. **Create an Amplifier session** via the prepared bundle (all hooks fire, all tools available)
3. **Execute the prompt** — memory injection loads relevant context automatically
4. **Route the response** to designated channels (proactive outbound messaging)
5. **Log the result** with timing and status

## Key Properties

- **Proactive, not reactive** — fires on a schedule without user interaction
- **Memory-aware** — memory hooks fire automatically, so the heartbeat session sees past context
- **Per-agent prompts** — each agent can have a custom focus in `context/heartbeat/agents/{id}.md`
- **Channel routing** — responses can be pushed to any configured channel adapter
- **Sessions are sessions** — a heartbeat session is identical to a user session; all capabilities load

## Configuration

Heartbeat is configured through the gateway's config:

```yaml
# ~/.letsgo/gateway/config.yaml
cron:
  jobs:
    - name: heartbeat
      cron: "0 * * * *"        # Every hour at minute 0
      recipe: __heartbeat__    # Special: routes to HeartbeatEngine, not recipe runner

agents:
  coder:
    workspace: ~/.letsgo/agents/coder
    heartbeat_channels: [telegram, discord]
  researcher:
    workspace: ~/.letsgo/agents/researcher
    heartbeat_channels: [webhook]

heartbeat:
  default_channels: [webhook]
```

## Per-Agent Focus

Create `context/heartbeat/agents/{agent_id}.md` to customize what each agent focuses on during heartbeat. Falls back to `context/heartbeat/agents/default.md`.
