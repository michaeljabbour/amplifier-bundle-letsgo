"""Encrypted secret storage and retrieval tool for Amplifier.

Provides Fernet-based (AES-128-CBC + HMAC-SHA256) encryption at rest for
API keys, tokens, passwords, and other credentials.  Every operation is
recorded in an append-only JSONL audit log.  Secret values are **never**
written to logs, telemetry, or listing output.

Encryption pipeline
-------------------
master passphrase  ->  PBKDF2-HMAC-SHA256 (480 000 iterations)  ->  Fernet key
                       fixed salt (module-scoped)

Storage format
--------------
A single JSON file where each top-level key is a secret name mapping to::

    {
        "name":             str,
        "category":         str,       # api_key | token | password | credential | other
        "encrypted_value":  str,          # Fernet token
        "created_at":       str,          # ISO-8601 UTC
        "updated_at":       str,
        "accessed_at":      str | null,
        "access_count":     int,
        "archived_values":  list[dict],   # populated by rotate_secret
    }
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import secrets as stdlib_secrets
import tempfile
from base64 import urlsafe_b64encode
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from amplifier_core.models import ToolResult  # type: ignore[import-not-found]
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# ---------------------------------------------------------------------------
# Amplifier module marker
# ---------------------------------------------------------------------------

__amplifier_module_type__ = "tool"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

VALID_CATEGORIES: frozenset[str] = frozenset(
    {"api_key", "token", "password", "credential", "other"},
)

DEFAULT_PASSPHRASE_ENV = "LETSGO_SECRETS_KEY"
DEFAULT_STORAGE_PATH = "~/.letsgo/secrets.enc"
DEFAULT_AUDIT_LOG = "~/.letsgo/logs/secrets-audit.jsonl"
DEFAULT_KEY_PATH = "~/.letsgo/secrets.key"

PBKDF2_ITERATIONS = 480_000
KDF_SALT = b"amplifier-tool-secrets-v1"  # fixed; passphrase provides entropy

_DIR_PERMS = 0o700
_FILE_PERMS = 0o600


# ---------------------------------------------------------------------------
# Encrypted store
# ---------------------------------------------------------------------------


class SecretsStore:
    """Fernet-encrypted secret store backed by a JSON file on disk.

    All mutations use atomic writes (write to temp file, then ``os.replace``)
    so the store is never left in a partially-written state.
    """

    def __init__(
        self,
        passphrase: str,
        storage_path: Path,
        audit_path: Path,
    ) -> None:
        self._storage_path = storage_path
        self._audit_path = audit_path
        self._fernet = self._derive_fernet(passphrase)
        self._ensure_directories()

    # -- key derivation -------------------------------------------------------

    @staticmethod
    def _derive_fernet(passphrase: str) -> Fernet:
        """Derive a Fernet key from *passphrase* via PBKDF2-HMAC-SHA256."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=KDF_SALT,
            iterations=PBKDF2_ITERATIONS,
        )
        raw_key = kdf.derive(passphrase.encode("utf-8"))
        return Fernet(urlsafe_b64encode(raw_key))

    # -- filesystem helpers ---------------------------------------------------

    def _ensure_directories(self) -> None:
        """Create storage and audit directories with ``0o700`` permissions."""
        for directory in (self._storage_path.parent, self._audit_path.parent):
            directory.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(directory, _DIR_PERMS)
            except OSError:
                logger.debug("Could not set permissions on %s", directory)

    @staticmethod
    def _atomic_write(path: Path, data: str) -> None:
        """Write *data* to *path* atomically via temp-file + rename."""
        tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                fh.write(data)
            os.chmod(tmp_path, _FILE_PERMS)
            os.replace(tmp_path, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise

    # -- encryption -----------------------------------------------------------

    def _encrypt(self, value: str) -> str:
        """Encrypt *value* and return the Fernet token as an ASCII string."""
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def _decrypt(self, token: str) -> str:
        """Decrypt a Fernet *token* and return the original plaintext."""
        return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")

    # -- persistence ----------------------------------------------------------

    def _load(self) -> dict[str, dict[str, Any]]:
        """Load the store from disk.  Returns ``{}`` when the file is absent."""
        if not self._storage_path.exists():
            return {}
        text = self._storage_path.read_text(encoding="utf-8").strip()
        if not text:
            return {}
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            msg = f"Corrupted secrets store at {self._storage_path}"
            raise ValueError(msg) from exc
        if not isinstance(data, dict):
            msg = f"Invalid secrets store format at {self._storage_path}"
            raise ValueError(msg)
        return data

    def _save(self, store: dict[str, dict[str, Any]]) -> None:
        """Persist *store* to disk with an atomic write."""
        self._atomic_write(
            self._storage_path,
            json.dumps(store, indent=2, sort_keys=True),
        )

    # -- audit ----------------------------------------------------------------

    def _audit(
        self,
        operation: str,
        secret_name: str | None = None,
        category: str | None = None,
        result: str = "success",
    ) -> None:
        """Append an audit entry.  **Never** logs secret values."""
        entry = {
            "timestamp": _now(),
            "operation": operation,
            "secret_name": secret_name,
            "category": category,
            "result": result,
        }
        try:
            with open(self._audit_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, separators=(",", ":")) + "\n")
        except OSError:
            logger.warning("Failed to write audit entry for %s", operation)

    # -- public operations ----------------------------------------------------

    def get_secret(self, name: str) -> str:
        """Decrypt and return the value of *name*.

        Updates access metadata and writes an audit record.
        The secret name (but **never** its value) is logged.
        """
        store = self._load()
        if name not in store:
            self._audit("get_secret", name, result="not_found")
            msg = f"Secret '{name}' not found"
            raise KeyError(msg)

        entry = store[name]
        try:
            value = self._decrypt(entry["encrypted_value"])
        except InvalidToken as exc:
            self._audit("get_secret", name, entry.get("category"), "decryption_failed")
            msg = f"Failed to decrypt secret '{name}'"
            raise ValueError(msg) from exc

        entry["accessed_at"] = _now()
        entry["access_count"] = entry.get("access_count", 0) + 1
        self._save(store)

        logger.info("Secret accessed: %s", name)
        self._audit("get_secret", name, entry.get("category"))
        return value

    def set_secret(
        self,
        name: str,
        value: str,
        category: str = "other",
    ) -> dict[str, str]:
        """Encrypt and store a secret.  Returns metadata (never the value)."""
        if category not in VALID_CATEGORIES:
            msg = (
                f"Invalid category '{category}'. "
                f"Must be one of: {', '.join(sorted(VALID_CATEGORIES))}"
            )
            raise ValueError(msg)

        store = self._load()
        now = _now()
        existing = store.get(name)

        store[name] = {
            "name": name,
            "category": category,
            "encrypted_value": self._encrypt(value),
            "created_at": existing["created_at"] if existing else now,
            "updated_at": now,
            "accessed_at": existing.get("accessed_at") if existing else None,
            "access_count": existing.get("access_count", 0) if existing else 0,
        }
        self._save(store)

        action = "updated" if existing else "created"
        logger.info("Secret %s: %s (category=%s)", action, name, category)
        self._audit("set_secret", name, category)
        return {"name": name, "category": category, "action": action, "updated_at": now}

    def list_secrets(self) -> list[dict[str, Any]]:
        """Return metadata for every stored secret.

        **Never** includes secret values -- only names, categories, and
        timestamps.
        """
        store = self._load()
        entries = [
            {
                "name": e["name"],
                "category": e.get("category", "other"),
                "created_at": e.get("created_at"),
                "updated_at": e.get("updated_at"),
                "accessed_at": e.get("accessed_at"),
                "access_count": e.get("access_count", 0),
            }
            for e in store.values()
        ]
        self._audit("list_secrets")
        return entries

    def delete_secret(self, name: str) -> dict[str, str]:
        """Remove a secret by *name*."""
        store = self._load()
        if name not in store:
            self._audit("delete_secret", name, result="not_found")
            msg = f"Secret '{name}' not found"
            raise KeyError(msg)

        category = store[name].get("category")
        del store[name]
        self._save(store)

        logger.info("Secret deleted: %s", name)
        self._audit("delete_secret", name, category)
        return {"name": name, "action": "deleted"}

    def rotate_secret(self, name: str, new_value: str) -> dict[str, str]:
        """Rotate a secret: encrypt *new_value* and archive the old one."""
        store = self._load()
        if name not in store:
            self._audit("rotate_secret", name, result="not_found")
            msg = f"Secret '{name}' not found"
            raise KeyError(msg)

        entry = store[name]
        now = _now()

        # Archive the current encrypted value before overwriting.
        archived: list[dict[str, str]] = entry.get("archived_values", [])
        archived.append(
            {"encrypted_value": entry["encrypted_value"], "rotated_at": now},
        )

        entry["encrypted_value"] = self._encrypt(new_value)
        entry["updated_at"] = now
        entry["archived_values"] = archived
        self._save(store)

        logger.info("Secret rotated: %s", name)
        self._audit("rotate_secret", name, entry.get("category"))
        return {
            "name": name,
            "action": "rotated",
            "archived_count": str(len(archived)),
            "updated_at": now,
        }


# ---------------------------------------------------------------------------
# Passphrase resolution
# ---------------------------------------------------------------------------


def _resolve_passphrase(config: dict[str, Any]) -> str:
    """Obtain the master passphrase.

    Resolution order:

    1. Environment variable (name from *config["passphrase_env"]*, default
       ``LETSGO_SECRETS_KEY``).
    2. Key file on disk (*config["key_path"]*, default
       ``~/.letsgo/secrets.key``).
    3. Auto-generate a cryptographically random passphrase and persist it
       to the key file for future runs.
    """
    env_var = config.get("passphrase_env", DEFAULT_PASSPHRASE_ENV)
    passphrase = os.environ.get(env_var)
    if passphrase:
        logger.debug("Using passphrase from environment variable %s", env_var)
        return passphrase

    key_path = Path(config.get("key_path", DEFAULT_KEY_PATH)).expanduser()

    if key_path.exists():
        passphrase = key_path.read_text(encoding="utf-8").strip()
        if passphrase:
            logger.debug("Using passphrase from key file %s", key_path)
            return passphrase

    # Auto-generate and persist a new passphrase.
    logger.info("Generating new master passphrase at %s", key_path)
    passphrase = stdlib_secrets.token_urlsafe(48)

    key_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(key_path.parent, _DIR_PERMS)
    except OSError:
        logger.debug("Could not set permissions on %s", key_path.parent)

    tmp_fd, tmp_path = tempfile.mkstemp(dir=key_path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(passphrase + "\n")
        os.chmod(tmp_path, _FILE_PERMS)
        os.replace(tmp_path, key_path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise

    return passphrase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Amplifier Tool
# ---------------------------------------------------------------------------


class SecretsTool:
    """Amplifier Tool providing encrypted secret management.

    Exposes five operations via a unified JSON-Schema input:
    ``get_secret``, ``set_secret``, ``list_secrets``, ``delete_secret``,
    and ``rotate_secret``.
    """

    def __init__(self, store: SecretsStore) -> None:
        self._store = store

    # -- Amplifier Tool protocol ----------------------------------------------

    @property
    def name(self) -> str:
        """Stable tool identifier exposed to the LLM."""
        return "secrets"

    @property
    def description(self) -> str:
        """Human-readable summary shown in tool listings."""
        return (
            "Encrypted secret storage and retrieval. "
            "Supports get, set, list, delete, and rotate operations "
            "for API keys, tokens, passwords, and other credentials. "
            "All values are encrypted at rest and every access is audited."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        """JSON Schema describing the accepted input object."""
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "get_secret",
                        "set_secret",
                        "list_secrets",
                        "delete_secret",
                        "rotate_secret",
                    ],
                    "description": "The operation to perform.",
                },
                "name": {
                    "type": "string",
                    "description": (
                        "The secret name. Required for all operations "
                        "except list_secrets."
                    ),
                },
                "value": {
                    "type": "string",
                    "description": ("The secret value. Required for set_secret."),
                },
                "new_value": {
                    "type": "string",
                    "description": (
                        "The new secret value. Required for rotate_secret."
                    ),
                },
                "category": {
                    "type": "string",
                    "enum": sorted(VALID_CATEGORIES),
                    "description": (
                        "Category of the secret (optional for set_secret, "
                        "defaults to 'other')."
                    ),
                },
            },
            "required": ["operation"],
        }

    async def execute(self, input: dict[str, Any]) -> ToolResult:  # noqa: A002
        """Dispatch to the requested operation and return a ``ToolResult``."""
        operation: str = input.get("operation", "")
        name: str | None = input.get("name")

        try:
            if operation == "get_secret":
                return self._get(name)
            if operation == "set_secret":
                return self._set(
                    name,
                    input.get("value"),
                    input.get("category", "other"),
                )
            if operation == "list_secrets":
                return self._list()
            if operation == "delete_secret":
                return self._delete(name)
            if operation == "rotate_secret":
                return self._rotate(name, input.get("new_value"))
            return ToolResult(
                success=False,
                error={"message": f"Unknown operation: '{operation}'"},
            )
        except (KeyError, ValueError) as exc:
            return ToolResult(success=False, error={"message": str(exc)})
        except Exception:
            logger.exception("Unexpected error in secrets tool")
            return ToolResult(
                success=False,
                error={"message": "An internal error occurred. Check logs."},
            )

    # -- operation handlers ---------------------------------------------------

    def _require_name(self, name: str | None, operation: str) -> ToolResult | None:
        """Return a failure ``ToolResult`` if *name* is missing or empty."""
        if not name or not name.strip():
            return ToolResult(
                success=False,
                error={
                    "message": f"Parameter 'name' is required for {operation}.",
                },
            )
        return None

    def _get(self, name: str | None) -> ToolResult:
        if err := self._require_name(name, "get_secret"):
            return err
        assert name is not None  # narrowing for type checker
        value = self._store.get_secret(name)
        return ToolResult(
            success=True,
            output={
                "name": name,
                "value": value,
                "warning": "Secret value retrieved. Handle with care.",
            },
        )

    def _set(
        self,
        name: str | None,
        value: str | None,
        category: str,
    ) -> ToolResult:
        if err := self._require_name(name, "set_secret"):
            return err
        if not value:
            return ToolResult(
                success=False,
                error={"message": "Parameter 'value' is required for set_secret."},
            )
        assert name is not None
        result = self._store.set_secret(name, value, category)
        return ToolResult(success=True, output=result)

    def _list(self) -> ToolResult:
        entries = self._store.list_secrets()
        return ToolResult(
            success=True,
            output={"secrets": entries, "count": len(entries)},
        )

    def _delete(self, name: str | None) -> ToolResult:
        if err := self._require_name(name, "delete_secret"):
            return err
        assert name is not None
        result = self._store.delete_secret(name)
        return ToolResult(success=True, output=result)

    def _rotate(self, name: str | None, new_value: str | None) -> ToolResult:
        if err := self._require_name(name, "rotate_secret"):
            return err
        if not new_value:
            return ToolResult(
                success=False,
                error={
                    "message": "Parameter 'new_value' is required for rotate_secret.",
                },
            )
        assert name is not None
        result = self._store.rotate_secret(name, new_value)
        return ToolResult(success=True, output=result)


# ---------------------------------------------------------------------------
# Module mount point
# ---------------------------------------------------------------------------


async def mount(
    coordinator: Any,
    config: dict[str, Any] | None = None,
) -> None:
    """Mount the secrets tool into the Amplifier coordinator.

    Configuration keys (all optional):

    ``passphrase_env``
        Environment variable holding the master passphrase.
        Default: ``LETSGO_SECRETS_KEY``.
    ``storage_path``
        Path to the encrypted JSON store.
        Default: ``~/.letsgo/secrets.enc``.
    ``audit_log``
        Path to the JSONL audit log.
        Default: ``~/.letsgo/logs/secrets-audit.jsonl``.
    ``key_path``
        Path for the auto-generated key file (used when the env var is
        not set).  Default: ``~/.letsgo/secrets.key``.
    """
    config = config or {}

    passphrase = _resolve_passphrase(config)
    storage_path = Path(
        config.get("storage_path", DEFAULT_STORAGE_PATH),
    ).expanduser()
    audit_path = Path(
        config.get("audit_log", DEFAULT_AUDIT_LOG),
    ).expanduser()

    store = SecretsStore(passphrase, storage_path, audit_path)
    tool = SecretsTool(store)

    await coordinator.mount("tools", tool, name="tool-secrets")
    logger.info("tool-secrets mounted (storage=%s)", storage_path)
