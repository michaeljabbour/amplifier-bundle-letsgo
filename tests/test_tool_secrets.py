"""Tests for tool-secrets module.

Exercises the SecretsStore (encryption, CRUD, rotation, audit), the
SecretHandleRegistry, and the SecretsTool wrapper — all using temporary
directories, no running session.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from amplifier_module_tool_secrets import SecretHandleRegistry, SecretsTool, SecretsStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store(tmp_path: Path) -> SecretsStore:
    """Create a SecretsStore backed by files in *tmp_path*."""
    return SecretsStore(
        passphrase="test-passphrase-42",
        salt=b"test-salt-0123456789abcdef0123456789abcdef",
        storage_path=tmp_path / "secrets.enc",
        audit_path=tmp_path / "logs" / "audit.jsonl",
    )


def _make_tool(tmp_path: Path) -> SecretsTool:
    """Create a SecretsTool wrapping a temp-backed SecretsStore."""
    store = _make_store(tmp_path)
    handles = SecretHandleRegistry()
    return SecretsTool(store, handles)


# ---------------------------------------------------------------------------
# SecretHandleRegistry tests
# ---------------------------------------------------------------------------


class TestSecretHandleRegistry:
    """Direct tests against the SecretHandleRegistry."""

    def test_handle_registry_create_and_redeem(self) -> None:
        """Create a handle and redeem it for the plaintext."""
        registry = SecretHandleRegistry()

        handle_id = registry.create("my_key", "my_secret_value")

        assert handle_id.startswith("sec_")
        plaintext = registry.redeem(handle_id)
        assert plaintext == "my_secret_value"

    def test_handle_registry_expiry(self) -> None:
        """Expired handles return None on redeem."""
        registry = SecretHandleRegistry(ttl_seconds=0)

        handle_id = registry.create("expiring_key", "expiring_value")
        time.sleep(0.01)  # ensure time.monotonic() advances past TTL

        result = registry.redeem(handle_id)
        assert result is None


# ---------------------------------------------------------------------------
# SecretsStore-level tests
# ---------------------------------------------------------------------------


class TestSecretsStore:
    """Direct tests against the SecretsStore class."""

    def test_set_and_get_secret(self, tmp_path: Path) -> None:
        """set_secret then get_secret returns the correct plaintext."""
        store = _make_store(tmp_path)
        store.set_secret("MY_API_KEY", "super-secret-value", category="api_key")

        retrieved = store.get_secret("MY_API_KEY")
        assert retrieved == "super-secret-value"

    def test_list_secrets_no_values(self, tmp_path: Path) -> None:
        """list_secrets returns metadata but NEVER includes values."""
        store = _make_store(tmp_path)
        store.set_secret("key_a", "val_a", category="token")
        store.set_secret("key_b", "val_b", category="password")

        entries = store.list_secrets()

        assert len(entries) == 2
        names = {e["name"] for e in entries}
        assert names == {"key_a", "key_b"}

        # No entry should contain a 'value' or 'encrypted_value' key
        for entry in entries:
            assert "value" not in entry
            assert "encrypted_value" not in entry

    def test_get_nonexistent_secret(self, tmp_path: Path) -> None:
        """Getting a non-existent secret must raise KeyError."""
        store = _make_store(tmp_path)

        with pytest.raises(KeyError, match="not found"):
            store.get_secret("does-not-exist")

    def test_delete_secret(self, tmp_path: Path) -> None:
        """delete_secret removes it; subsequent get raises KeyError."""
        store = _make_store(tmp_path)
        store.set_secret("temp_key", "temp_val")

        result = store.delete_secret("temp_key")
        assert result["action"] == "deleted"

        with pytest.raises(KeyError):
            store.get_secret("temp_key")

    def test_rotate_secret(self, tmp_path: Path) -> None:
        """rotate_secret updates the value; old value is archived."""
        store = _make_store(tmp_path)
        store.set_secret("rotating_key", "original_value")

        rotate_result = store.rotate_secret("rotating_key", "new_value")
        assert rotate_result["action"] == "rotated"
        assert rotate_result["archived_count"] == "1"

        # New value should be returned
        assert store.get_secret("rotating_key") == "new_value"

    def test_audit_log_written(self, tmp_path: Path) -> None:
        """Operations produce JSONL audit entries."""
        store = _make_store(tmp_path)
        store.set_secret("aud_key", "aud_val")
        store.get_secret("aud_key")

        audit_path = tmp_path / "logs" / "audit.jsonl"
        assert audit_path.exists()

        lines = audit_path.read_text().strip().splitlines()
        assert len(lines) >= 2  # at least set + get

        entries = [json.loads(line) for line in lines]
        operations = [e["operation"] for e in entries]
        assert "set_secret" in operations
        assert "get_secret" in operations

        # Audit entries must never contain the secret value
        raw_text = audit_path.read_text()
        assert "aud_val" not in raw_text

    def test_encryption_at_rest(self, tmp_path: Path) -> None:
        """The stored file must not contain the plaintext secret."""
        store = _make_store(tmp_path)
        plaintext = "super-duper-secret-value-12345"
        store.set_secret("enc_test", plaintext)

        storage_path = tmp_path / "secrets.enc"
        assert storage_path.exists()

        raw = storage_path.read_text(encoding="utf-8")
        assert plaintext not in raw

        # The encrypted_value field should be present and be a Fernet token
        data = json.loads(raw)
        assert "enc_test" in data
        assert "encrypted_value" in data["enc_test"]
        assert data["enc_test"]["encrypted_value"] != plaintext


# ---------------------------------------------------------------------------
# SecretsTool-level tests (async execute dispatch)
# ---------------------------------------------------------------------------


class TestSecretsTool:
    """Tests against the SecretsTool async execute() interface."""

    @pytest.mark.asyncio
    async def test_set_and_get_via_tool(self, tmp_path: Path) -> None:
        """Round-trip through the tool's execute() method.

        get_secret now returns an opaque handle, not the plaintext value.
        """
        tool = _make_tool(tmp_path)

        set_result = await tool.execute({
            "operation": "set_secret",
            "name": "tool_key",
            "value": "tool_val",
            "category": "api_key",
        })
        assert set_result.success is True

        get_result = await tool.execute({
            "operation": "get_secret",
            "name": "tool_key",
        })
        assert get_result.success is True
        assert get_result.output["handle"].startswith("sec_")
        assert "value" not in get_result.output

    @pytest.mark.asyncio
    async def test_list_via_tool(self, tmp_path: Path) -> None:
        """list_secrets through execute() returns count and entries."""
        tool = _make_tool(tmp_path)
        await tool.execute({
            "operation": "set_secret",
            "name": "k1",
            "value": "v1",
        })
        await tool.execute({
            "operation": "set_secret",
            "name": "k2",
            "value": "v2",
        })

        result = await tool.execute({"operation": "list_secrets"})
        assert result.success is True
        assert result.output["count"] == 2

    @pytest.mark.asyncio
    async def test_get_missing_returns_error(self, tmp_path: Path) -> None:
        """Getting a missing secret via execute() returns success=False."""
        tool = _make_tool(tmp_path)

        result = await tool.execute({
            "operation": "get_secret",
            "name": "ghost",
        })
        assert result.success is False
        assert "not found" in result.error["message"]

    @pytest.mark.asyncio
    async def test_delete_via_tool(self, tmp_path: Path) -> None:
        """Delete through execute() removes the secret."""
        tool = _make_tool(tmp_path)
        await tool.execute({
            "operation": "set_secret",
            "name": "del_me",
            "value": "bye",
        })

        result = await tool.execute({
            "operation": "delete_secret",
            "name": "del_me",
        })
        assert result.success is True
        assert result.output["action"] == "deleted"

    @pytest.mark.asyncio
    async def test_rotate_via_tool(self, tmp_path: Path) -> None:
        """Rotate through execute() updates the stored value.

        The subsequent get returns a handle, not the plaintext.
        """
        tool = _make_tool(tmp_path)
        await tool.execute({
            "operation": "set_secret",
            "name": "rot_key",
            "value": "old",
        })

        result = await tool.execute({
            "operation": "rotate_secret",
            "name": "rot_key",
            "new_value": "new",
        })
        assert result.success is True
        assert result.output["action"] == "rotated"

        get_result = await tool.execute({
            "operation": "get_secret",
            "name": "rot_key",
        })
        assert get_result.success is True
        assert get_result.output["handle"].startswith("sec_")
        assert "value" not in get_result.output

    @pytest.mark.asyncio
    async def test_unknown_operation(self, tmp_path: Path) -> None:
        """An unknown operation returns success=False."""
        tool = _make_tool(tmp_path)

        result = await tool.execute({"operation": "explode"})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_missing_name_returns_error(self, tmp_path: Path) -> None:
        """Operations requiring a name fail gracefully if name is missing."""
        tool = _make_tool(tmp_path)

        result = await tool.execute({"operation": "get_secret"})
        assert result.success is False
        assert "name" in result.error["message"].lower()

    @pytest.mark.asyncio
    async def test_get_secret_returns_handle_not_plaintext(self, tmp_path: Path) -> None:
        """get_secret output contains a handle but never a 'value' key."""
        tool = _make_tool(tmp_path)
        await tool.execute({
            "operation": "set_secret",
            "name": "handle_test",
            "value": "should-not-appear",
        })

        get_result = await tool.execute({
            "operation": "get_secret",
            "name": "handle_test",
        })
        assert get_result.success is True
        assert "handle" in get_result.output
        assert get_result.output["handle"].startswith("sec_")
        assert "ttl_seconds" in get_result.output
        assert "value" not in get_result.output
        assert "should-not-appear" not in str(get_result.output)
