"""Builds the ``PermissionTable`` consumed by ``Sentinel.pre_call`` / ``authorize``.

An absent entry means *permitted* by design (formal invariant I6,
``formal/models/test_sentinel_policy.py:219-221``). This module therefore
only *adds* entries and never inverts that default -- see
``docs/adr/ADR-072726-0d6b-sentinel-permission-table-fail-closed.md`` for the
(proposed, not implemented) fail-closed alternative and its preconditions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from maistro.security.patterns import DANGEROUS_TOOL_NAMES

if TYPE_CHECKING:
    from maistro.security._types import PermissionTable

# "none" is handled by absence (an empty table), not by an explicit entry
# here -- see build_permission_table's default.
PERMISSION_PRESETS: dict[str, frozenset[str]] = {
    "dangerous_tools_admin": DANGEROUS_TOOL_NAMES,
}


def build_permission_table(
    *,
    preset: str = "none",
    permissions: dict[str, list[str]] | None = None,
) -> PermissionTable:
    """Build a ``PermissionTable`` from an optional preset plus explicit overrides.

    - ``preset="none"`` (the default) yields an empty table: every tool is
      permitted for every role, identical to today's behavior.
    - A known preset seeds every tool name in that preset's set to
      ``frozenset({"admin"})``.
    - An unknown preset (not ``"none"`` and not a ``PERMISSION_PRESETS`` key)
      raises ``ValueError`` -- a silently-ignored typo'd preset name is
      exactly the class of bug this module exists to fix.
    - ``permissions`` (``tool_name -> [role, ...]``) is applied last and
      overrides any preset entry for the same tool name. An explicit entry
      with an empty role list produces ``frozenset()``, which denies
      *everyone* -- this is a deliberate hard deny, not a bug to "fix" into
      a no-op.
    """
    table: dict[str, frozenset[str]] = {}

    if preset != "none":
        seed = PERMISSION_PRESETS.get(preset)
        if seed is None:
            valid = ", ".join(["none", *sorted(PERMISSION_PRESETS)])
            msg = f"Unknown permission preset '{preset}'. Valid values: {valid}."
            raise ValueError(msg)
        for name in seed:
            table[name] = frozenset({"admin"})

    for tool_name, roles in (permissions or {}).items():
        table[tool_name] = frozenset(roles)

    return table


def describe_permission_table(table: PermissionTable) -> str:
    """Single log-safe line summarizing an armed (or empty) permission table."""
    names = ", ".join(sorted(table))
    return f"{len(table)} tool(s) restricted: [{names}]"
