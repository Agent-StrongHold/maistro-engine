"""Per-request "is this the pm_fleet workspace" resolution.

Persona/Workspace system, Phase H. Recon for the originally-scoped "full
migration" (re-point all ~26 `is_pm_poc_mode()`/`HIVE_POC_MODE` call sites,
then delete the env var) found that framing was too broad: several of those
call sites are legitimately global, process-level defaults resolved once at
boot -- `services/engine.py`'s executor selection, `settings_defaults.py`'s
default log level/temperature, `logging_setup.py`'s default verbosity --
with no per-request "active workspace" to resolve against even in
principle. Those are deliberately left alone; deleting `is_pm_poc_mode()`/
`HIVE_POC_MODE` entirely would break them, not just rename something.

`routes/agents.py`'s branching (PM Fleet roster vs the general `stores.agents`
registry) is also deliberately NOT migrated here: it would require a
workspace's persona to actually be materialized into real `stores.agents`
records via `maistro.personas.expander.expand_persona()`, which has zero
call sites anywhere in hive-conductor today. Migrating the read without that
write would make `/v1/agents` return an empty/wrong roster for every
non-pm_fleet workspace -- a regression, not a fix. That's its own
substantial feature (materializing a workspace's persona into governed,
review-gated agent records), not a mechanical rename.

What *is* safely, mechanically migratable: pure request-time gates that
decide "is this feature area reachable at all" (e.g. `require_pm_poc()`),
and context lookups that already have a per-project store
(`services/program_store.py`) but were never given a project_id other than
the hardcoded "default". Both are additive and backward compatible -- this
module (given no `workspace_id`, every pre-Phase-H caller) still falls back
to the legacy global `is_pm_poc_mode()` flag exactly, so behavior for any
caller that doesn't pass one is unchanged.
"""

from __future__ import annotations

import stores

from services.pm_fleet import is_pm_poc_mode


def is_pm_fleet_workspace(workspace_id: str | None) -> bool:
    """True if `workspace_id` names a real workspace whose persona is
    `pm_fleet`; otherwise falls back to the legacy global `is_pm_poc_mode()`
    flag (covers both "no workspace_id given" and "unknown workspace_id").
    No membership check -- internal/trusted callers only. Request-time
    gating should use `is_pm_fleet_workspace_for()` instead."""
    if workspace_id is not None:
        workspace = stores.workspaces.get(workspace_id)
        if workspace is not None:
            return workspace.persona_template_id == "pm_fleet"
    return is_pm_poc_mode()


def is_workspace_request_authorized(
    user_id: str, workspace_id: str | None, *, require_pm_fleet_persona: bool = True
) -> bool:
    """Membership-checked request-time gate.

    Two different things live behind `is_pm_poc_mode()` today, and they need
    different per-workspace semantics, not one blanket check:

    - `require_pm_fleet_persona=True` (default) -- for surfaces genuinely
      specific to the PM Fleet persona (e.g. `routes/work_items.py`'s Jira
      epic/story drafting; there's no equivalent concept for a
      `content_creator` workspace). The resolved workspace's persona must
      literally be `pm_fleet`.
    - `require_pm_fleet_persona=False` -- for surfaces `program_context.py`
      already generalized to any persona via its per-`use_case`
      `INTERVIEW_TEMPLATES` (the onboarding interview). Any real workspace
      the caller is a member of is enough, regardless of persona.

    Either way: a caller may only borrow a workspace's identity to decide
    what a request is allowed to do if they actually belong to it --
    otherwise one user could probe another user's private workspace_id to
    flip gated behavior for themselves. Falls back to the legacy global
    `is_pm_poc_mode()` flag for no workspace_id, an unresolvable one, or one
    the caller isn't a member of.
    """
    if workspace_id is not None:
        workspace = stores.workspaces.get(workspace_id)
        if workspace is not None and any(m.user_id == user_id for m in workspace.members):
            if require_pm_fleet_persona:
                return workspace.persona_template_id == "pm_fleet"
            return True
    return is_pm_poc_mode()
