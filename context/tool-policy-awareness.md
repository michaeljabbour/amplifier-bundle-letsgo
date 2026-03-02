# Tool Execution Policy

All tool invocations are classified by risk level before execution.

## Risk Levels

| Level | Example Tools |
|-------|---------------|
| Blocked | Explicitly blocked tools |
| High | bash, write_file |
| Medium | edit_file, filesystem |
| Low | search, glob, grep, todo |

## Default Behavior

Default is allow-all (`careful_mode: false`). Enable `careful_mode` for approval gates.

## What You Should Know

- Do not attempt to bypass policy by renaming or aliasing tools.
- If a tool call is denied, explain to the user what was blocked and why.

## Delegate to Expert

For policy review, risk reclassification, or allowlist changes, delegate to `letsgo:security-reviewer`.
