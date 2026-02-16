# Secret Management

LetsGo provides encrypted secret storage via `tool-secrets`.

## Operations

| Operation | Description |
|-----------|-------------|
| Get | Retrieve a secret by name (value returned, access logged) |
| Set | Store or update a secret (encrypted at rest with AES-256-GCM) |
| List | Show secret names and metadata (values are never listed) |
| Delete | Remove a secret permanently |

## Security Rules

- **NEVER** store secrets in plain text anywhere — not in files, not in conversation.
- **NEVER** echo secret values back to the user unless they explicitly request it.
- **ALWAYS** use `tool-secrets` for all credential operations.
- Secrets are encrypted with AES-256-GCM and keys derived via Argon2id.
- All access is logged to `~/.letsgo/logs/secrets-audit.jsonl`.

## When to Use

- Storing API keys, tokens, database passwords, or any sensitive credential.
- Retrieving credentials needed for tool integrations or API calls.
- Rotating secrets that are approaching their expiration policy (90 days).
