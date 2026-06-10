"""Canvas Studio standalone auth — simple API key check."""

from __future__ import annotations

from dataclasses import dataclass, field

# Default tenant for the single-tenant standalone deployment. The
# canvas v1 routes scope every query by ``auth.org_id``; using a stable
# non-empty value keeps create/list/get consistent for one deployment.
DEFAULT_ORG_ID = "default"


@dataclass(frozen=True)
class CurrentUser:
    """Authenticated principal for the standalone canvas deployment.

    Exposes attribute access (``auth.org_id``) used throughout the
    canvas v1 routes. ``org_id`` defaults to the single-tenant
    placeholder so multi-tenant code paths stay consistent until proper
    auth (Conductor Seed, DID) is wired in.
    """

    user_id: str = "default"
    org_id: str = DEFAULT_ORG_ID
    roles: tuple[str, ...] = field(default_factory=lambda: ("admin",))


async def get_current_user(
    api_key: str = "",
) -> CurrentUser:
    """Standalone auth: accept any API key and return the default user.

    For the standalone mini-PC deployment, auth is a simple API key
    shared between the React frontend and the Python backend.
    Replace with proper auth (Conductor Seed, DID) when integrating
    with Agent Conductor.
    """
    return CurrentUser()
