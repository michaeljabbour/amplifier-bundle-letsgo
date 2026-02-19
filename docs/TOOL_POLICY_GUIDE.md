# Tool Policy Guide

## Overview

The `hooks-tool-policy` module intercepts every `tool:pre` event at priority 5, classifying and gating tool executions based on risk level. It is the first line of defense in the LetsGo security model — every tool call passes through policy evaluation before execution.

The module operates transparently in normal use. Most tool calls are classified as low-risk and execute without interference. Higher-risk operations (bash commands, file writes) are logged and, depending on configuration, may require explicit approval.

## Risk Classification

Tool calls are classified into a 4-tier risk system. Classification is evaluated in order — the first matching rule wins:

```
  Tool Call
      |
      v
  +----------+    match    +---------+
  | Blocked? +------------>|  DENY   |
  +----+-----+             +---------+
       | no match
       v
  +----------+    match    +---------------------+
  |  High?   +------------>| ALLOW (or gate if   |
  +----+-----+             | careful_mode=true)   |
       | no match          +---------------------+
       v
  +----------+    match    +---------------------+
  | Medium?  +------------>| ALLOW + audit log   |
  +----+-----+             +---------------------+
       | no match
       v
  +----------+    match    +---------------------+
  |  Low?    +------------>| ALLOW (no logging)  |
  +----+-----+             +---------------------+
       | no match
       v
  +--------------+
  | Unclassified +--> default_action (continue/deny/ask_user)
  +--------------+
```

### Tier Details

| Tier             | Tools                            | Default Behavior                              |
|------------------|----------------------------------|-----------------------------------------------|
| **Blocked**      | Explicitly denied tools          | Always denied, no override                    |
| **High**         | `bash`, `write_file`             | Auto-allowed; approval-gated when `careful_mode=true` |
| **Medium**       | `edit_file`, filesystem ops      | Allowed with full audit trail                 |
| **Low**          | `search`, `glob`, `grep`, `todo` | Execute freely, no logging                    |
| **Unclassified** | Everything else                  | Controlled by `default_action` setting        |

### Classification Logic

**High-risk tools** are those that can execute arbitrary code or create new files:
- `bash` — Arbitrary shell execution
- `write_file` — Creates new files (potentially overwriting)

**Medium-risk tools** modify existing files or traverse the filesystem:
- `edit_file` — Modifies existing file content
- Filesystem operations — Directory creation, file moves, etc.

**Low-risk tools** are read-only or organizational:
- `search`, `glob`, `grep` — Read-only search operations
- `todo` — Task list management (no filesystem impact)

## Allowlists

### Command Allowlist

For `bash` tool calls, the command allowlist provides fine-grained control over which shell commands are permitted.

**Matching method:** Prefix matching with word boundaries. The command string is checked against each allowlist entry. A match requires the entry to appear at the start of the command and be followed by a word boundary (space, end-of-string, pipe, semicolon).

**Example configuration:**
```yaml
command_allowlist:
  - git
  - npm
  - pytest
  - ruff
  - python -m
  - docker compose
```

With this allowlist:
- `git status` — allowed (prefix match on `git`)
- `git push origin main` — allowed
- `gitconfig` — denied (no word boundary after `git`)
- `npm install` — allowed
- Dangerous commands like recursive deletes — denied (not in allowlist)

### Path Allowlist

For `write_file` and `edit_file` tool calls, the path allowlist controls which filesystem paths are writable.

**Matching method:** Prefix matching with path-traversal protection. The target path is resolved to an absolute path, and `../` sequences are resolved before matching.

**Path-traversal protection:** Paths containing `..` that would escape the allowed prefix are denied even if the literal string matches. For example, if `/home/user/project` is allowed, `/home/user/project/../../etc/passwd` is denied.

**Example configuration:**
```yaml
path_allowlist:
  - /home/user/project
  - /tmp/scratch
```

## Careful Mode

When `careful_mode=true`, high-risk tool calls require explicit user approval before execution.

### Activation

Careful mode can be activated through:
1. **Runtime mode**: Set the `careful` mode via Amplifier's mode system
2. **Configuration**: Set `careful_mode: true` in the behavior configuration
3. **Environment**: Set `LETSGO_CAREFUL_MODE=true`

### Approval Flow

```
  High-Risk Tool Call
         |
         v
  +-------------------------+
  |  Present approval prompt |
  |  to user with details:   |
  |  - Tool name             |
  |  - Arguments/command     |
  |  - Risk classification   |
  +------------+------------+
               |
               v
  +-------------------------+
  |  Wait for user response  |
  |  (timeout: 30s)          |
  +------------+------------+
               |
       +-------+--------+
       v                v
    Response         Timeout
       |                |
       v                v
    Parse action    Default action
                    (allow)
```

### User Responses

| Input                          | Action    | Scope                                       |
|--------------------------------|-----------|---------------------------------------------|
| `a`, `y`, `yes`, `allow`      | Allow     | This tool call only                         |
| `d`, `n`, `no`, `deny`        | Deny      | This tool call only                         |
| `aaa`, `all`                   | Allow all | All subsequent high-risk calls this session |

### Configuration

```yaml
careful_mode:
  enabled: true
  timeout: 30              # Seconds to wait for response
  default_on_timeout: allow # Action when timeout expires: allow or deny
```

## Automation Mode

Detected automatically for unattended runs (CI/CD, cron jobs, daemon processes) where no human is available to respond to approval prompts.

### Detection

Automation mode activates when:
- The session is marked as non-interactive
- No TTY is attached
- The `automation` runtime mode is explicitly set

### Behavior Changes

In automation mode, the policy becomes significantly more restrictive:

| Tool Category  | Normal Mode         | Automation Mode  |
|----------------|---------------------|------------------|
| Blocked        | DENIED              | DENIED           |
| High-risk      | ALLOWED (or gated)  | **DENIED**       |
| Medium-risk    | ALLOWED + audit     | ALLOWED + audit  |
| Low-risk       | ALLOWED             | ALLOWED          |
| Unclassified   | `default_action`    | **DENIED**       |
| `secrets` tool | ALLOWED             | **BLOCKED**      |

Key differences:
- **Secrets tool is BLOCKED entirely** — No secret access in unattended runs
- **High-risk tools are DENIED outright** — No bash or write_file without a human
- **Unclassified tools are DENIED** — Fail-closed regardless of `default_action` setting
- **No interactive approval possible** — Prompts cannot be presented

### Rationale

Automation mode prevents:
- Credential theft from unattended sessions
- Arbitrary code execution without human oversight
- Unknown tools executing in production environments

## Sandbox Rewrite

When `sandbox_mode=enforce`, the tool policy module automatically rewrites `bash` tool calls to route through `tool-sandbox` instead.

### Rewrite Process

```
  bash(command="npm test")
         |
         v (sandbox_mode=enforce)
         |
  sandbox(command="npm test",
          operation="execute",
          network="none")
```

The rewrite:
1. Intercepts the `bash` tool call at `tool:pre`
2. Replaces the tool name with `sandbox`
3. Wraps the command in sandbox parameters
4. Adds resource limits (memory, CPU, timeout)
5. Enforces network isolation

### Configuration

```yaml
sandbox_mode: enforce   # off | audit | enforce
sandbox_defaults:
  memory: 512m
  cpu: 1.0
  timeout: 120
  network: none
  read_only: true
```

## Audit Trail

All medium-risk and higher tool calls are logged to a JSONL audit file.

### Log Location

`~/.letsgo/logs/tool-policy-audit.jsonl`

### Log Entry Schema

```json
{
  "timestamp": "2025-01-15T14:32:01.123Z",
  "session_id": "abc123",
  "tool": "bash",
  "operation": "execute",
  "arguments": {
    "command": "git push origin main"
  },
  "classification": "high",
  "verdict": "allowed",
  "rationale": "Command matches allowlist entry: git",
  "careful_mode": false,
  "automation_mode": false,
  "duration_ms": null
}
```

### Log Fields

| Field            | Type     | Description                                       |
|------------------|----------|---------------------------------------------------|
| `timestamp`      | ISO 8601 | When the policy evaluation occurred               |
| `session_id`     | string   | Amplifier session identifier                      |
| `tool`           | string   | Tool name being evaluated                         |
| `operation`      | string   | Tool operation (if applicable)                    |
| `arguments`      | object   | Tool arguments (sanitized — secrets redacted)     |
| `classification` | string   | Risk tier: blocked, high, medium, low, unclassified |
| `verdict`        | string   | Policy decision: allowed, denied, gated           |
| `rationale`      | string   | Human-readable explanation of the decision        |
| `careful_mode`   | boolean  | Whether careful mode was active                   |
| `automation_mode`| boolean  | Whether automation mode was detected              |
| `duration_ms`    | number   | Time spent on approval gate (null if no gate)     |

### Log Rotation

Audit logs are not automatically rotated. For long-running deployments, configure external log rotation (e.g., `logrotate`).

## Configuration

### Base Directory Resolution

The tool policy module resolves its base directory in order:

1. `config.base_dir` — Explicit configuration in the behavior
2. `LETSGO_HOME` environment variable
3. `~/.letsgo` — Default fallback

### Behavior Configuration

```yaml
# behaviors/security-policy.yaml
modules:
  - type: hook
    name: hooks-tool-policy
    config:
      # Risk classification overrides
      blocked_tools: []
      high_risk_tools: [bash, write_file]
      medium_risk_tools: [edit_file]
      low_risk_tools: [search, glob, grep, todo]

      # Default action for unclassified tools
      default_action: continue  # continue | deny | ask_user

      # Allowlists
      command_allowlist:
        - git
        - npm
        - pytest
        - ruff
        - python
        - pip
        - docker
      path_allowlist:
        - .  # Current project directory

      # Careful mode
      careful_mode:
        enabled: false
        timeout: 30
        default_on_timeout: allow

      # Sandbox integration
      sandbox_mode: off  # off | audit | enforce

      # Audit trail
      audit:
        enabled: true
        log_path: null  # null = {base_dir}/logs/tool-policy-audit.jsonl
```

## Modes Integration

The careful and automation behaviors are formalized as Amplifier runtime modes with tool policy frontmatter:

### Careful Mode

```yaml
# modes/careful.yaml
name: careful
description: Require approval for high-risk tool calls
activation:
  tool_policy:
    careful_mode: true
```

When this mode is active, all high-risk tool calls present an approval prompt. The mode can be toggled at runtime without restarting the session.

### Automation Mode

```yaml
# modes/automation.yaml
name: automation
description: Restrict tool access for unattended execution
activation:
  tool_policy:
    automation_mode: true
```

When this mode is active, the restrictive automation policy applies. This mode is also auto-detected based on environment signals (no TTY, CI environment variables).

### Mode Precedence

When both modes are active (which would be unusual), automation mode takes precedence. The more restrictive policy wins:
- Automation mode's outright denial overrides careful mode's approval gate
- Blocked and denied tools remain denied regardless of mode combination
