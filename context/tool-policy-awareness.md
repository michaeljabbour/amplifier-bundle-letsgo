# Tool Execution Policy

All tool invocations are classified by risk level before execution.

## Risk Levels

| Level | Tools | Behavior |
|-------|-------|----------|
| Blocked | Explicitly blocked tools | Denied outright |
| High | bash, write_file | Auto-allowed by default; approval-gated when `careful_mode=true` |
| Medium | edit_file, filesystem | Logged with full audit trail |
| Low | search, glob, grep, todo | Executes freely |
| Unclassified | Any tool not in a risk tier | Controlled by `default_action` (bundle default: continue) |

## Default Action

Any tool not explicitly added to a risk tier uses `default_action`.
The letsgo bundle defaults to allow-all:
- `default_action: continue`
- `careful_mode: false`

The `default_action` config key controls this behavior:
- `"deny"` — unclassified tools are blocked
- `"ask_user"` — unclassified tools require approval
- `"continue"` (default) — unclassified tools pass through

## Automation Mode

When running under automation (scheduled tasks, cron jobs), the policy enforces
a restricted profile:
- Secrets tool is **blocked** entirely (no secret access without user present)
- High-risk tools are **denied** outright (no interactive approval possible)
- Unclassified tools are **denied** regardless of `default_action`

## How It Works

- The `hooks-tool-policy` hook intercepts every `tool:pre` event at priority 5.
- High-risk calls only present approval prompts when `careful_mode=true`.
- Approval prompts default to a 30s timeout and `allow` on timeout.
- In `sandbox_mode: enforce`, bash calls are rewritten to route through `tool-sandbox`.
- All decisions are logged to `~/.letsgo/logs/tool-policy-audit.jsonl`.

## What You Should Know

- Do not attempt to bypass policy by renaming or aliasing tools.
- If a tool call is denied, explain to the user what was blocked and why.
- If `careful_mode=true`, users can answer approvals with:
  `a/y/yes/allow` (allow), `d/n/no/deny` (deny), `aaa/all` (allow all).
