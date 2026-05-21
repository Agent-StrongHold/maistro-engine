"""Workspace mount management for sandbox containers."""

from __future__ import annotations

from pathlib import Path

import structlog

logger = structlog.get_logger()

# Base directory for workspaces inside containers
CONTAINER_WORKSPACE = "/workspace"

# Allowed host paths that can be mounted into containers.
# Include `/private/tmp/...` because macOS resolves `/tmp` → `/private/tmp`.
ALLOWED_HOST_PREFIXES = (
    "/tmp/maistro-workspace",
    "/private/tmp/maistro-workspace",
    "/repos/",
)


def validate_workspace_path(path: str) -> Path:
    """Validate and resolve a workspace path.

    Ensures the path is within allowed prefixes to prevent
    arbitrary filesystem access via container mounts.
    """
    resolved = Path(path).resolve()
    path_str = str(resolved)

    if not any(path_str.startswith(prefix) for prefix in ALLOWED_HOST_PREFIXES):
        raise ValueError(
            f"Workspace path {path} is not in an allowed location. "
            f"Allowed prefixes: {ALLOWED_HOST_PREFIXES}"
        )

    return resolved


def ensure_workspace(path: str) -> Path:
    """Validate workspace path and create directory if needed."""
    resolved = validate_workspace_path(path)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved
