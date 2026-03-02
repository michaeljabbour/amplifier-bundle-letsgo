# Secrets System Guide

Comprehensive reference for the LetsGo secret management system. Intended for the `letsgo:security-reviewer` agent and policy review tasks.

## Encryption Specification

Secrets are encrypted at rest using **Fernet (AES-128-CBC + HMAC-SHA256)**:

- **Algorithm**: Fernet symmetric encryption
  - Cipher: AES-128-CBC
  - Authentication: HMAC-SHA256
- **Key Derivation**: PBKDF2-HMAC-SHA256
  - Iterations: 480,000 (NIST SP 800-132 compliant)
  - Salt: per-installation random salt (32 bytes)
  - Salt storage: `~/.letsgo/secrets/.salt`
- **Key storage**: Derived key held in memory only; never written to disk

## Handle Lifecycle

`get_secret` returns a short-lived opaque handle (e.g. `sec_a1b2c3...`) instead of the plaintext value.

| Property | Value |
|----------|-------|
| Format | `sec_` prefix + 8 hex chars |
| Expiry | 5 minutes (configurable via `secrets.handle_ttl`) |
| Redemption | Only inside sandbox execution via `secrets.redeem` capability |
| Scope | Handles are session-scoped and non-transferable |
| Plaintext exposure | Never appears in model context, conversation, or logs |

Handle expiry is enforced at redemption time. Expired handles return a `SecretHandleExpired` error. Handles cannot be renewed — callers must issue a fresh `get_secret` call.

## Audit Trail

All secret access is logged to `~/.letsgo/logs/secrets-audit.jsonl`.

Each log entry includes:

```json
{
  "timestamp": "<ISO-8601>",
  "operation": "get|set|list|delete|rotate",
  "secret_name": "<name>",
  "caller": "<agent-or-session-id>",
  "handle_id": "<sec_...> (get operations only)",
  "outcome": "success|denied|error",
  "reason": "<optional denial reason>"
}
```

- Log entries are append-only and never deleted by the system.
- Log rotation is handled by the host OS log rotation policy.
- Audit logs do **not** contain secret values or key material.

## Rotation Mechanics

`rotate_secret` atomically replaces a secret value:

1. New value is encrypted and written to the active slot.
2. Old value is moved to the archive slot with a rotation timestamp.
3. Archive is retained for the configurable `rotation_archive_ttl` (default: 30 days).
4. All existing handles for the old value are immediately invalidated.
5. A rotation event is written to the audit log.

Archive slots are accessible only to the `letsgo:security-reviewer` agent for audit purposes. Normal agents cannot retrieve archived values.

## Automation Mode Restrictions

When running under automation (scheduled tasks, cron jobs):

- `tool-secrets` is **blocked entirely** — no secret access without user present.
- This prevents unattended exfiltration of credentials.
- Automation tasks requiring secrets must use pre-issued handles scoped to a specific execution window.

## Security Boundaries

- Secrets are stored in `~/.letsgo/secrets/` with `0600` file permissions.
- The secrets directory is excluded from all backup and sync operations by default.
- Cross-agent secret sharing is not supported — handles are session-scoped.
- The `secrets.redeem` capability is gated behind sandbox execution to prevent plaintext leakage into model context.

## Policy Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `secrets.handle_ttl` | `300` (5 min) | Handle expiry in seconds |
| `secrets.rotation_archive_ttl` | `2592000` (30 days) | How long to retain rotated secrets |
| `secrets.audit_log` | `~/.letsgo/logs/secrets-audit.jsonl` | Audit log path |
| `secrets.allow_automation` | `false` | Allow secret access in automation mode |
