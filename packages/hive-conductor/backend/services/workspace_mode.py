"""Per-request "is this the pm_fleet workspace" resolution.

Persona/Workspace system, Phase H sub-step 2 -- the resolver half only, not
the call-site migration. Recon found the full migration (re-pointing the 26
call sites gated on `is_pm_poc_mode()`/`HIVE_POC_MODE`, then deleting that
env-var gate) needs a real per-request "active workspace" concept threaded
through routes/services/frontend that doesn't exist yet, and touches live
PM Fleet routing behavior -- real production risk, not a mechanical rename.
That migration is deliberately deferred to its own dedicated pass.

This module is the safe, additive building block that migration will use:
given a `workspace_id`, resolve whether it's really the `pm_fleet` persona
from the real `Workspace` record, instead of the global env-var flag. Given
no `workspace_id` (every existing caller today), it falls back to
`is_pm_poc_mode()` exactly, so behavior for every current call site is
unchanged -- this module changes nothing on its own, it only makes the next
step possible.
"""

from __future__ import annotations

import stores

from services.pm_fleet import is_pm_poc_mode


def is_pm_fleet_workspace(workspace_id: str | None) -> bool:
    """True if `workspace_id` names a real workspace whose persona is
    `pm_fleet`; otherwise falls back to the legacy global `is_pm_poc_mode()`
    flag (covers both "no workspace_id given" and "unknown workspace_id")."""
    if workspace_id is not None:
        workspace = stores.workspaces.get(workspace_id)
        if workspace is not None:
            return workspace.persona_template_id == "pm_fleet"
    return is_pm_poc_mode()
