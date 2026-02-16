# Tool Execution Policy

All tool invocations are classified by risk level before execution.

## Risk Levels

| Level | Tools | Behavior |
|-------|-------|----------|
| Blocked | Explicitly blocked tools | Denied outright |
| High | bash, write_file | Requires user approval before execution |
| Medium | edit_file, filesystem | Logged with full audit trail |
| Low | search, glob, grep, todo | Executes freely |
| Unclassified | Any tool not in a risk tier | **Denied by default** |

## Default-Deny Invariant

Any tool not explicitly added to a risk tier is **denied**. This prevents silent
privilege escalation when new tools are added to a session. To allow a new tool,
it must be explicitly classified in the policy configuration.

The `default_action` config key controls this behavior:
- `"deny"` (default) — unclassified tools are blocked
- `"ask_user"` — unclassified tools require approval
- `"continue"` — unclassified tools pass through (not recommended)

## Automation Mode

When running under automation (scheduled tasks, cron jobs), the policy enforces
a restricted profile:
- Secrets tool is **blocked** entirely (no secret access without user present)
- High-risk tools are **denied** outright (no interactive approval possible)
- Unclassified tools are **denied** regardless of `default_action`

## How It Works

- The `hooks-tool-policy` hook intercepts every `tool:pre` event at priority 5.
- High-risk calls present an approval prompt to the user.
- If the user denies or the prompt times out (2 min), the call is blocked.
- In `sandbox_mode: enforce`, bash calls are rewritten to route through `tool-sandbox`.
- All decisions are logged to `~/.letsgo/logs/tool-policy-audit.jsonl`.

## What You Should Know

- Do not attempt to bypass policy by renaming or aliasing tools.
- If a tool call is denied, explain to the user what was blocked and why.
- Batch destructive operations when possible to reduce approval fatigue.
