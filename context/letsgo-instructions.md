# LetsGo Capabilities

You have enhanced capabilities provided by the LetsGo bundle. Use them appropriately.

## Available Capabilities

| Capability | Type | Purpose |
|------------|------|---------|
| Tool Policy | Hook | Classifies tool calls by risk level, gates high-risk operations |
| Secrets | Tool | Encrypted storage for API keys, tokens, and credentials |
| Sandbox | Tool | Isolated Docker execution for untrusted or experimental code |
| Telemetry | Hook | Metrics collection — tool latency, token usage, error rates |

## Behavioral Guidelines

- **High-risk tools** (bash, write_file) require explicit user approval before execution.
- **Secrets** must always go through `tool-secrets` — never store credentials in plain text, environment variables, or conversation history.
- **Untrusted code** should be executed inside the sandbox when available.
- **Telemetry** runs silently in the background. Other modules can query live metrics via the `telemetry.metrics` capability.

## Context Awareness

Each capability injects its own thin awareness context. Refer to them for specific usage rules:

- Tool policy risk levels and approval behavior
- Secret management operations and security rules
- Sandbox resource limits and network isolation
- Telemetry output location and metric types
