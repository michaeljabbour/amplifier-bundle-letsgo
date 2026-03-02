# Secret Management

LetsGo provides encrypted secret storage via `tool-secrets`.

## Operations

- **Get** — Retrieve an opaque handle for a secret
- **Set** — Store or update a secret
- **List** — Show secret names and metadata (values never listed)
- **Delete** — Remove a secret permanently
- **Rotate** — Replace a secret value and archive the old one

## Critical Rule

`get_secret` returns an opaque handle, NOT the plaintext. Handles expire after 5 minutes.

## Security Rules

- **NEVER** store secrets in plain text anywhere — not in files, not in conversation.
- **NEVER** attempt to decode or extract the value from a handle — it is opaque.
- **ALWAYS** use `tool-secrets` for all credential operations.

## Delegate to Expert

For security policy review, delegate to `letsgo:security-reviewer`.
