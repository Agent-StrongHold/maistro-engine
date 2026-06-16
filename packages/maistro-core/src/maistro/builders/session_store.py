"""Durable replay artifacts for secure Builders sessions."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SESSION_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]{0,127}$")
_COMMIT_SHA = re.compile(r"^[0-9a-fA-F]{40,64}$")
_MAX_PATCH_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class SavedBuilderSession:
    """Minimal durable state that can be replayed into a fresh sandbox."""

    session_id: str
    repo_url: str
    base_commit: str
    created_at: str
    updated_at: str
    patch_file: str


class BuilderSessionStore:
    """Persist replay artifacts atomically without retaining sandbox state."""

    def __init__(self, root: Path | None = None) -> None:
        configured = os.environ.get("MAISTRO_BUILDERS_STATE_DIR")
        self._root = (
            root
            or (Path(configured).expanduser() if configured else None)
            or Path.home() / ".local" / "share" / "maistro" / "builders"
        ).resolve()

    def save(
        self,
        *,
        session_id: str,
        repo_url: str,
        base_commit: str,
        patch: str,
    ) -> SavedBuilderSession:
        self._validate_session_id(session_id)
        if not _COMMIT_SHA.fullmatch(base_commit):
            raise ValueError("Builders session base commit must be a full hexadecimal object ID")
        patch_bytes = patch.encode("utf-8")
        if len(patch_bytes) > _MAX_PATCH_BYTES:
            raise ValueError(f"Builders replay patch exceeds {_MAX_PATCH_BYTES} bytes")

        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(UTC).isoformat()
        existing = self.get(session_id)
        record = SavedBuilderSession(
            session_id=session_id,
            repo_url=repo_url,
            base_commit=base_commit,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            patch_file="changes.patch",
        )
        self._atomic_write(session_dir / record.patch_file, patch_bytes)
        self._atomic_write(
            session_dir / "session.json",
            json.dumps(asdict(record), indent=2, sort_keys=True).encode("utf-8"),
        )
        return record

    def get(self, session_id: str) -> SavedBuilderSession | None:
        self._validate_session_id(session_id)
        manifest = self._session_dir(session_id) / "session.json"
        if not manifest.is_file():
            return None
        data: dict[str, Any] = json.loads(manifest.read_text(encoding="utf-8"))
        record = SavedBuilderSession(**data)
        if record.session_id != session_id:
            raise ValueError("Builders session manifest ID does not match its directory")
        if record.patch_file != "changes.patch":
            raise ValueError("Builders session manifest contains an invalid patch path")
        if not _COMMIT_SHA.fullmatch(record.base_commit):
            raise ValueError("Builders session manifest contains an invalid base commit")
        return record

    def load_patch(self, session_id: str) -> str:
        record = self.get(session_id)
        if record is None:
            raise KeyError(f"Builders session {session_id!r} does not exist")
        patch_path = self._session_dir(session_id) / record.patch_file
        data = patch_path.read_bytes()
        if len(data) > _MAX_PATCH_BYTES:
            raise ValueError(f"Builders replay patch exceeds {_MAX_PATCH_BYTES} bytes")
        return data.decode("utf-8")

    def list_sessions(self) -> list[SavedBuilderSession]:
        if not self._root.is_dir():
            return []
        sessions = []
        for manifest in self._root.glob("*/session.json"):
            try:
                session_id = manifest.parent.name
                record = self.get(session_id)
                if record is not None:
                    sessions.append(record)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        return sorted(sessions, key=lambda record: record.updated_at, reverse=True)

    def _session_dir(self, session_id: str) -> Path:
        target = (self._root / session_id).resolve()
        try:
            target.relative_to(self._root)
        except ValueError:
            raise ValueError("Builders session path escapes the state directory") from None
        return target

    @staticmethod
    def _validate_session_id(session_id: str) -> None:
        if not _SESSION_ID.fullmatch(session_id):
            raise ValueError(f"Invalid Builders session ID: {session_id!r}")

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)
