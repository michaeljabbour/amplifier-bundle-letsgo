# Secret Management

LetsGo provides encrypted secret storage via `tool-secrets`.

## Operations

| Operation | Description |
|-----------|-------------|
| Get | Retrieve an **opaque handle** for a secret (value is never returned directly) |
| Set | Store or update a secret (encrypted at rest with Fernet / AES-128-CBC + HMAC-SHA256) |
| List | Show secret names and metadata (values are never listed) |
| Delete | Remove a secret permanently |
| Rotate | Replace a secret value and archive the old one |

## Handle-Based Access

`get_secret` returns a short-lived opaque handle (e.g. `sec_a1b2c3...`), **not** the
plaintext value. Handles:

- Expire after 5 minutes (configurable).
- Are redeemable only inside sandbox execution via the `secrets.redeem` capability.
- Never appear as plaintext in model context, conversation, or logs.

To use a secret in a command, pass the handle to sandbox execution.

## Security Rules

- **NEVER** store secrets in plain text anywhere — not in files, not in conversation.
- **NEVER** attempt to decode or extract the value from a handle — it is opaque.
- **ALWAYS** use `tool-secrets` for all credential operations.
- Secrets are encrypted with Fernet (AES-128-CBC + HMAC-SHA256), keys derived via
  PBKDF2-HMAC-SHA256 (480,000 iterations) with a per-installation random salt.
- All access is logged to `~/.letsgo/logs/secrets-audit.jsonl`.

## When to Use

- Storing API keys, tokens, database passwords, or any sensitive credential.
- Retrieving credentials needed for tool integrations or API calls (via handles).
- Rotating secrets that are approaching their expiration policy.
