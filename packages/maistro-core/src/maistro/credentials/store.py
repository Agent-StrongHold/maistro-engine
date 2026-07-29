"""Per-user credential store — Fernet-encrypted JSON at rest.

# SECURITY-REVIEW: secrets encrypted with deployment master key file (0o600).
Values are never returned from list APIs; use ``use_secret`` for server-side tool access.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("maistro.credentials")

T = TypeVar("T")

_MASTER_KEY_ENV = "HIVE_CREDENTIALS_MASTER_KEY"
_MASTER_KEY_FILENAME = "credential_master.key"
_STORE_FILENAME = "user_credentials.enc"

# Persona/Workspace system, Phase F: a credential is scoped by
# (user_id, provider, workspace_id, connection_name), not just (user_id,
# provider) -- so one workspace can hold two connections to the same
# provider (e.g. two Jira accounts). The default scope maps onto the exact
# bare-provider bucket key used before this phase, so every pre-Phase-F
# on-disk record keeps resolving unchanged -- no migration needed.
DEFAULT_WORKSPACE_ID = "default"
DEFAULT_CONNECTION_NAME = "default"
_SCOPE_SEPARATOR = "::"


def _bucket_key(provider: str, workspace_id: str, connection_name: str) -> str:
    if workspace_id == DEFAULT_WORKSPACE_ID and connection_name == DEFAULT_CONNECTION_NAME:
        return provider
    return f"{provider}{_SCOPE_SEPARATOR}{workspace_id}{_SCOPE_SEPARATOR}{connection_name}"


class CredentialStoreError(Exception):
    """Base error for credential storage."""


class CredentialStoreUnavailable(CredentialStoreError):
    """Store cannot be opened or decrypted."""


class CredentialNotFound(CredentialStoreError):
    """No secret stored for this user/provider."""


class UserCredentialStore:
    """Encrypts per-user integration secrets in a single file."""

    def __init__(self, data_dir: Path, *, master_key: bytes | None = None) -> None:
        self._data_dir = data_dir.expanduser()
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._master_key_path = self._data_dir / _MASTER_KEY_FILENAME
        self._store_path = self._data_dir / _STORE_FILENAME
        self._fernet = Fernet(self._resolve_master_key(master_key))
        self._cache: dict[str, dict[str, str]] | None = None

    def _resolve_master_key(self, explicit: bytes | None) -> bytes:
        if explicit is not None:
            return explicit
        env_key = os.getenv(_MASTER_KEY_ENV, "").strip()
        if env_key:
            return env_key.encode()
        if self._master_key_path.exists():
            return self._master_key_path.read_bytes()
        raise CredentialStoreUnavailable(
            f"Missing {_MASTER_KEY_FILENAME} under {self._data_dir} or {_MASTER_KEY_ENV}"
        )

    @classmethod
    def open(cls, data_dir: str | Path) -> UserCredentialStore:
        """Open or create the encrypted store under ``data_dir``."""
        path = Path(data_dir).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        key_path = path / _MASTER_KEY_FILENAME
        if not key_path.exists():
            key = Fernet.generate_key()
            key_path.write_bytes(key)
            os.chmod(key_path, 0o600)
            # stdlib logger — keyword args raise TypeError. Use % formatting.
            # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure -- logs the key FILE path, never the key material
            logger.info("credential_master_key_created path=%s", str(key_path))
        return cls(path, master_key=key_path.read_bytes())

    def _load(self) -> dict[str, dict[str, str]]:
        if self._cache is not None:
            return self._cache
        if not self._store_path.exists():
            self._cache = {}
            return self._cache
        try:
            raw = self._fernet.decrypt(self._store_path.read_bytes())
            data = json.loads(raw.decode())
        except (InvalidToken, json.JSONDecodeError) as exc:
            raise CredentialStoreUnavailable("Failed to decrypt credential store") from exc
        if not isinstance(data, dict):
            raise CredentialStoreUnavailable("Invalid credential store format")
        self._cache = {str(uid): dict(vals) for uid, vals in data.items() if isinstance(vals, dict)}
        return self._cache

    def _persist(self) -> None:
        assert self._cache is not None
        payload = json.dumps(self._cache).encode()
        self._store_path.write_bytes(self._fernet.encrypt(payload))
        os.chmod(self._store_path, 0o600)

    def list_providers_for_user(
        self,
        user_id: str,
        *,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
        connection_name: str = DEFAULT_CONNECTION_NAME,
    ) -> dict[str, dict[str, Any]]:
        """Return metadata only — never secret values — for one (workspace, connection) scope."""
        data = self._load()
        user_secrets = data.get(user_id, {})
        if workspace_id == DEFAULT_WORKSPACE_ID and connection_name == DEFAULT_CONNECTION_NAME:
            providers = [key for key in user_secrets if _SCOPE_SEPARATOR not in key]
        else:
            suffix = f"{_SCOPE_SEPARATOR}{workspace_id}{_SCOPE_SEPARATOR}{connection_name}"
            providers = [key[: -len(suffix)] for key in user_secrets if key.endswith(suffix)]
        return {
            provider: {
                "configured": True,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            for provider in providers
        }

    def set_secret(
        self,
        user_id: str,
        provider: str,
        secret: str,
        *,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
        connection_name: str = DEFAULT_CONNECTION_NAME,
    ) -> None:
        secret = secret.strip()
        if not secret:
            raise ValueError("Secret cannot be empty")
        data = self._load()
        bucket = data.setdefault(user_id, {})
        bucket[_bucket_key(provider, workspace_id, connection_name)] = secret
        self._persist()

    def delete_secret(
        self,
        user_id: str,
        provider: str,
        *,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
        connection_name: str = DEFAULT_CONNECTION_NAME,
    ) -> bool:
        data = self._load()
        bucket = data.get(user_id, {})
        key = _bucket_key(provider, workspace_id, connection_name)
        if key not in bucket:
            return False
        del bucket[key]
        if not bucket:
            data.pop(user_id, None)
        self._persist()
        return True

    def has_secret(
        self,
        user_id: str,
        provider: str,
        *,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
        connection_name: str = DEFAULT_CONNECTION_NAME,
    ) -> bool:
        data = self._load()
        return _bucket_key(provider, workspace_id, connection_name) in data.get(user_id, {})

    def use_secret(
        self,
        user_id: str,
        provider: str,
        callback: Callable[[str], T],
        *,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
        connection_name: str = DEFAULT_CONNECTION_NAME,
    ) -> T:
        """Pass decrypted secret to callback; never return it from this method."""
        data = self._load()
        bucket = data.get(user_id, {})
        key = _bucket_key(provider, workspace_id, connection_name)
        if key not in bucket:
            raise CredentialNotFound(f"No credential for provider {provider!r}")
        return callback(bucket[key])
