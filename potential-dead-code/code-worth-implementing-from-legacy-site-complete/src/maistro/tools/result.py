"""Structured result types for MCP tool returns.

Replaces plain string returns so agents don't need to parse formatted strings.
"""

from __future__ import annotations

from typing import Any


def ok(stdout: str = "", exit_code: int = 0, **extra: Any) -> dict[str, Any]:
    """Build a successful tool result."""
    return {"success": True, "exit_code": exit_code, "stdout": stdout, **extra}


def fail(stdout: str = "", exit_code: int = 1, **extra: Any) -> dict[str, Any]:
    """Build a failed tool result."""
    return {"success": False, "exit_code": exit_code, "stdout": stdout, **extra}
