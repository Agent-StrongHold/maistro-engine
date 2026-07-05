"""OpenRouter `QuotaVerifier` — the one provider in the roster with a real,
standalone, zero-cost balance-check endpoint (`GET /api/v1/key`), no separate
management credential needed: the same bearer key used for chat completions.
"""

from __future__ import annotations

import time

import httpx

from maistro.quota.rate_profile import LimitUnit
from maistro.quota.reconciliation import ProviderQuotaSnapshot

_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterKeyVerifier:
    """Calls `GET /api/v1/key` and reports the account's remaining credit balance."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport  # test seam: inject an httpx.MockTransport

    async def verify(self, scope_key: str) -> ProviderQuotaSnapshot:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.get(f"{self._base_url}/key", headers=headers)
            response.raise_for_status()
            payload = response.json().get("data", {})

        limit_remaining = payload.get("limit_remaining")
        # `null` means "unlimited" per OpenRouter's docs, not "zero left" —
        # surfacing that distinction is the caller's job, not this verifier's;
        # infinity keeps "unconstrained" and "exhausted" from looking the same.
        remaining = float(limit_remaining) if limit_remaining is not None else float("inf")

        return ProviderQuotaSnapshot(
            scope_key=scope_key,
            unit=LimitUnit.CREDITS_USD,
            remaining=remaining,
            checked_at=time.time(),
        )
