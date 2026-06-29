"""Workspace mount management for sandbox containers."""

from __future__ import annotations

from pathlib import Path

import structlog

logger = structlog.get_logger()

# Base directory for workspaces inside containers
CONTAINER_WORKSPACE = "/workspace"

# Allowed host paths that can be mounted into containers.
# Include `/private/tmp/...` because macOS resolves `/tmp` → `/private/tmp`.
ALLOWED_HOST_ROOTS = (
    Path("/tmp/maistro-workspace"),  # nosec B108 — security allowlist, not a write target
    Path("/private/tmp/maistro-workspace"),  # nosec B108 — macOS symlink target of /tmp
    Path("/repos"),
)


def validate_workspace_path(path: str) -> Path:
    """Validate and resolve a workspace path.

    Ensures the path is within allowed prefixes to prevent
    arbitrary filesystem access via container mounts.
    """
    resolved = Path(path).resolve()
    allowed_roots = tuple(root.resolve() for root in ALLOWED_HOST_ROOTS)

    if not any(resolved == root or root in resolved.parents for root in allowed_roots):
        allowed = tuple(str(root) for root in allowed_roots)
        raise ValueError(
            f"Workspace path {path} is not in an allowed location. Allowed roots: {allowed}"
        )

    return resolved


def ensure_workspace(path: str) -> Path:
    """Validate workspace path and create directory if needed."""
    resolved = validate_workspace_path(path)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved
