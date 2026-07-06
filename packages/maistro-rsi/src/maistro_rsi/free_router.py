"""Turn the OpenRouter *free router* into stable, gateway-routable genome models.

The free router (``openrouter/free``) picks a RANDOM ``:free`` model per call —
ideal as a $0 random-model SELECTOR, useless as a genome model directly: it
re-randomises every call, so a genome could never be scored against a *stable*
model. This module converts one router pick into a pinned, routable alias:

  1. RESOLVE — ask OpenRouter *directly* which concrete ``:free`` model the router
     serves. The litellm gateway can't tell us: it echoes the requested alias
     (``model == "openrouter/free"``) and caches, so the pick is invisible in-band.
  2. REGISTER — add that concrete model to the litellm gateway via the admin API
     as a first-class alias ``openrouter/<model>`` bound to the OpenRouter
     credential. Required, not cosmetic: the bare ``openrouter/*`` wildcard carries
     no credential and 401s on tag config, whereas an explicit registration (the
     same shape as the hand-added ``:free`` aliases) routes cleanly.
  3. PIN — hand back the routable alias for the caller to pin onto a genome node.

Every step degrades to ``None`` (and the caller to a known-good default), so a
seeding run never breaks on a gateway or network hiccup — it just falls back to
its configured roster. All calls are synchronous (seeding is synchronous); the
credential/keys are read from the environment at call time, never baked in.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence

import httpx
import structlog

from maistro_rsi.gateway import _gateway_base, _gateway_key

logger = structlog.get_logger()

# Roster tokens that mean "use the free router as a random-model selector" rather
# than a model to score directly. Matched against --models entries.
FREE_ROUTER_ALIASES = frozenset({"openrouter/free", "openrouter/openrouter/free", "or-free-router"})

# A concrete, verified-routable free model used when resolution/registration is
# unavailable (no OpenRouter key, gateway down) — keeps a free-only roster from
# collapsing to the un-pinnable sentinel.
DEFAULT_FREE_MODEL = "openrouter/openai/gpt-oss-120b:free"

_OPENROUTER_DIRECT = "https://openrouter.ai/api/v1/chat/completions"
# What we send to OpenRouter-direct to make it pick a random free model. The
# gateway registers this under the `or-free-router` / `openrouter/openrouter/free`
# aliases; direct, it is just `openrouter/free`.
_FREE_ROUTER_PRESET = "openrouter/free"

FreeSelector = Callable[[], "str | None"]


def resolve_concrete_free_model(
    *, preset: str = _FREE_ROUTER_PRESET, timeout: float = 60.0
) -> str | None:
    """Ask OpenRouter *directly* for one random ``:free`` model id (its ``data.model``).

    Returns ``None`` if ``OPENROUTER_API_KEY`` is unset, the call fails, or the
    response names no concrete model (or just echoes the preset back).
    """
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return None
    try:
        resp = httpx.post(
            _OPENROUTER_DIRECT,
            json={
                "model": preset,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
            },
            headers={"Authorization": f"Bearer {key}"},
            timeout=timeout,
        )
        resp.raise_for_status()
        served = resp.json().get("model")
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("free_router_resolve_failed", error=str(exc))
        return None
    if not isinstance(served, str) or not served or served == preset:
        return None
    return served


def _discover_openrouter_credential(base: str, key: str, timeout: float) -> str | None:
    """The litellm credential name new aliases must bind to (else they 401 on the
    tag-gated wildcard). Overridable via ``LITELLM_OPENROUTER_CREDENTIAL``;
    otherwise the first credential named ``openrouter/*``."""
    override = os.environ.get("LITELLM_OPENROUTER_CREDENTIAL")
    if override:
        return override
    try:
        resp = httpx.get(
            f"{base}/credentials", headers={"Authorization": f"Bearer {key}"}, timeout=timeout
        )
        resp.raise_for_status()
        payload = resp.json()
    except (httpx.HTTPError, ValueError):
        return None
    creds = payload.get("credentials") or payload.get("data") or []
    for c in creds:
        name = c.get("credential_name", "") if isinstance(c, dict) else ""
        if name.startswith("openrouter/"):
            return name
    return None


def fetch_known_models(
    *, base: str | None = None, key: str | None = None, timeout: float = 15.0
) -> set[str]:
    """Model ids already registered on the gateway — so seeding skips re-registering
    a concrete model that is already routable (and avoids duplicate rows)."""
    base = (base or _gateway_base()).rstrip("/")
    key = key or _gateway_key()
    if not base or not key:
        return set()
    try:
        resp = httpx.get(
            f"{base}/v1/models", headers={"Authorization": f"Bearer {key}"}, timeout=timeout
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except (httpx.HTTPError, ValueError):
        return set()
    return {m["id"] for m in data if isinstance(m, dict) and m.get("id")}


def register_gateway_alias(
    concrete: str,
    *,
    base: str | None = None,
    key: str | None = None,
    credential: str | None = None,
    timeout: float = 30.0,
    known: set[str] | None = None,
) -> str | None:
    """Register ``openrouter/<concrete>`` on the gateway bound to the OpenRouter
    credential and return the routable alias. A no-op (returns the alias) when it
    is already present in ``known``. Returns ``None`` only if the gateway/credential
    is unreachable or registration is rejected for a reason other than "exists"."""
    alias = concrete if concrete.startswith("openrouter/") else f"openrouter/{concrete}"
    base = (base or _gateway_base()).rstrip("/")
    key = key or _gateway_key()
    if not base or not key:
        return None
    if known is not None and alias in known:
        return alias
    credential = credential or _discover_openrouter_credential(base, key, timeout)
    if not credential:
        return None
    body = {
        "model_name": alias,
        "litellm_params": {"model": alias, "litellm_credential_name": credential},
    }
    try:
        resp = httpx.post(
            f"{base}/model/new",
            json=body,
            headers={"Authorization": f"Bearer {key}"},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        logger.warning("free_alias_register_failed", alias=alias, error=str(exc))
        return None
    if resp.status_code >= 400:
        # A duplicate name is fine — the model is already routable. Anything else
        # is a real failure the caller should fall back from.
        already = resp.status_code == 409 or "exist" in resp.text.lower()
        logger.warning("free_alias_register_status", alias=alias, status=resp.status_code)
        return alias if already else None
    if known is not None:
        known.add(alias)
    logger.info("free_alias_registered", alias=alias)
    return alias


def select_and_pin_free_model(
    *, known: set[str] | None = None, timeout: float = 60.0
) -> str | None:
    """One end-to-end pick: resolve a random concrete free model and make it
    routable. ``None`` if any leg is unavailable (caller falls back)."""
    concrete = resolve_concrete_free_model(timeout=timeout)
    if not concrete:
        return None
    return register_gateway_alias(concrete, known=known, timeout=timeout)


def make_free_selector(*, timeout: float = 60.0) -> FreeSelector:
    """Build the per-genome selector used at seeding: each call yields a freshly
    resolved-and-pinned concrete free alias (or ``None`` to trigger the default).
    The gateway's current model set is fetched once and shared, so repeats of the
    finite free catalog don't re-register."""
    known = fetch_known_models()

    def selector() -> str | None:
        return select_and_pin_free_model(known=known, timeout=timeout)

    return selector


def expand_free_router(
    models: Sequence[str] | None,
    selector: FreeSelector | None,
    *,
    resolved: set[str] | None = None,
) -> list[str] | None:
    """Return ``models`` with every free-router sentinel replaced by a concrete,
    pinned free alias (one fresh pick per sentinel occurrence — so distinct
    genomes seed onto distinct random models). A no-op when no sentinel is present.
    Falls back to ``DEFAULT_FREE_MODEL`` when the selector yields nothing."""
    if not models:
        return list(models) if models is not None else None
    if not any(m in FREE_ROUTER_ALIASES for m in models):
        return list(models)
    out: list[str] = []
    for m in models:
        if m in FREE_ROUTER_ALIASES:
            pick = (selector() if selector else None) or DEFAULT_FREE_MODEL
            out.append(pick)
            if resolved is not None:
                resolved.add(pick)
        else:
            out.append(m)
    return out
