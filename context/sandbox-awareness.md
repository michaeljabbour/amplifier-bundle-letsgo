# Sandboxed Execution

LetsGo provides isolated Docker containers for running untrusted code via `tool-sandbox`.

## Configuration

| Setting | Value |
|---------|-------|
| Runtime | Docker |
| Memory limit | 512 MB |
| CPU limit | 1.0 core |
| Timeout | 120 seconds |
| Network | Disabled |
| Working directory | Mounted from host CWD |

## When to Use the Sandbox

- Running user-provided scripts or code snippets you have not reviewed.
- Executing build commands for untrusted repositories.
- Testing potentially destructive operations before applying them to the host.
- Any execution where failure could affect the host system.

## What You Should Know

- Network access is disabled inside the sandbox — no downloads or API calls.
- The working directory is bind-mounted, so file reads and writes affect the host CWD.
- Execution is killed after 120 seconds with no extension.
- Prefer the sandbox for experimental or exploratory code execution.
