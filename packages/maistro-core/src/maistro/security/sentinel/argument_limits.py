"""Pre-schema resource limits for model/tool-call arguments.

Tool-call arguments are already materialized Python objects by the time they
reach Sentinel, so this gate cannot protect the upstream JSON parser. It does
bound the work Sentinel and the tool executor will perform: structural depth is
checked iteratively before serialization, then the compact UTF-8 JSON size is
bounded before schema validation or execution.
"""

from __future__ import annotations

import json
from typing import Any

from maistro.constants import TOOL_ARGUMENT_MAX_BYTES, TOOL_ARGUMENT_MAX_DEPTH
from maistro.security._types import Violation


def _structural_depth(value: object, *, stop_after: int) -> int:
    """Return container depth, stopping as soon as ``stop_after`` is exceeded."""
    max_seen = 0
    stack: list[tuple[object, int]] = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        if not isinstance(current, (dict, list)):
            continue
        max_seen = max(max_seen, depth)
        if depth > stop_after:
            return depth
        children = current.values() if isinstance(current, dict) else current
        stack.extend((child, depth + 1) for child in children if isinstance(child, (dict, list)))
    return max_seen


def check_argument_limits(
    args: dict[str, Any],
    *,
    max_bytes: int = TOOL_ARGUMENT_MAX_BYTES,
    max_depth: int = TOOL_ARGUMENT_MAX_DEPTH,
) -> Violation | None:
    """Return an error violation when tool arguments exceed configured limits.

    Depth is checked first without recursion so deeply nested payloads are
    rejected before JSON serialization. Size is measured as compact UTF-8 JSON,
    matching the wire representation closely enough to make ASCII, Unicode, and
    encoded-string payloads obey the same byte ceiling.
    """
    depth = _structural_depth(args, stop_after=max_depth)
    if depth > max_depth:
        return Violation(
            boundary="system_to_tool",
            rule="tool_argument_depth_limit",
            severity="error",
            detail=f"Tool arguments depth {depth} exceeds configured maximum {max_depth}",
        )

    try:
        encoded = json.dumps(
            args,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError):
        return Violation(
            boundary="system_to_tool",
            rule="tool_argument_not_json",
            severity="error",
            detail="Tool arguments are not valid JSON-compatible data",
        )

    size = len(encoded)
    if size > max_bytes:
        return Violation(
            boundary="system_to_tool",
            rule="tool_argument_size_limit",
            severity="error",
            detail=f"Tool arguments size {size} bytes exceeds configured maximum {max_bytes}",
        )
    return None
