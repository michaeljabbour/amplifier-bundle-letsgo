# Tool Execution Policy

All tool invocations are classified by risk level before execution.

## Risk Levels

| Level | Tools | Behavior |
|-------|-------|----------|
| High | bash, write_file | Requires user approval before execution |
| Medium | edit_file, filesystem | Logged with full audit trail |
| Low | search, glob, grep, todo | Executes freely |

## How It Works

- The `hooks-tool-policy` hook intercepts every `tool:pre` event.
- High-risk calls present an approval prompt to the user.
- If the user denies or the prompt times out (5 min), the call is blocked.
- All decisions are logged to `~/.letsgo/logs/tool-policy-audit.jsonl`.

## What You Should Know

- Do not attempt to bypass policy by renaming or aliasing tools.
- If a tool call is denied, explain to the user what was blocked and why.
- Batch destructive operations when possible to reduce approval fatigue.
