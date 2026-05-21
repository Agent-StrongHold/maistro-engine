"""Input validation utilities for the gateway.

Security: Validates and sanitizes external input before use.
"""

from __future__ import annotations

import re

# Valid project ID pattern: alphanumeric, hyphens, underscores, 1-64 chars
PROJECT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")

# Valid task ID pattern: alphanumeric, hyphens, underscores, 1-128 chars
TASK_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$")


class ValidationError(ValueError):
    """Raised when input validation fails."""

    pass


def validate_project_id(project_id: str) -> str:
    """Validate and return a sanitized project ID.

    Raises:
        ValidationError: If project_id is invalid
    """
    if not project_id:
        raise ValidationError("Project ID cannot be empty")

    if not PROJECT_ID_PATTERN.match(project_id):
        raise ValidationError(
            f"Invalid project ID: {project_id!r}. "
            "Must be 1-64 alphanumeric characters, hyphens, or underscores, "
            "starting with alphanumeric."
        )

    # Additional safety: no path traversal components
    if ".." in project_id or "/" in project_id or "\\" in project_id:
        raise ValidationError(f"Project ID contains forbidden characters: {project_id!r}")

    return project_id


def validate_task_id(task_id: str) -> str:
    """Validate and return a sanitized task ID.

    Raises:
        ValidationError: If task_id is invalid
    """
    if not task_id:
        raise ValidationError("Task ID cannot be empty")

    if not TASK_ID_PATTERN.match(task_id):
        raise ValidationError(
            f"Invalid task ID: {task_id!r}. "
            "Must be 1-128 alphanumeric characters, hyphens, or underscores, "
            "starting with alphanumeric."
        )

    return task_id


def sanitize_for_log(text: str, max_length: int = 200) -> str:
    """Sanitize text for safe logging.

    - Replaces newlines and control characters
    - Truncates to max_length
    """
    # Replace control characters and newlines
    sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    # Truncate
    if len(sanitized) > max_length:
        sanitized = sanitized[: max_length - 3] + "..."
    return sanitized
