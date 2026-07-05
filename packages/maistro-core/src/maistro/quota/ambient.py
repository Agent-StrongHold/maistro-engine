"""Ambient reconciliation signals — parsed for free from a response already
in hand, no extra network call.

**`LiteLLMHeaderParser` is the one that matters for this platform's actual
traffic.** Every real call goes through the shared LiteLLM proxy
(`maistro_llm_call`) — never a provider directly — and LiteLLM standardizes
whichever backend served the call into its own `x-ratelimit-remaining-
{requests,tokens}` headers, the same two header names regardless of whether
Groq, Cerebras, SambaNova, Mistral, or Gemini answered. (It also preserves the
untouched originals under an `llm_provider-` prefix, and has a known gap where
these headers are dropped on streaming responses — both are fine to be silent
about here, since an absent header just means an empty list, not a crash.)

The five provider-specific parsers below (`GroqHeaderParser` etc.) document
each provider's *raw, direct* API header conventions — correct only for a
hypothetical future call path that talks to a provider without going through
LiteLLM. They are not what `maistro_llm_call` traffic actually carries today;
don't wire them into `build_quota_recording_hook` for this platform's real
usage. Groq/Cerebras happen to already match LiteLLM's own convention by
coincidence (both use the `x-ratelimit-remaining-{requests,tokens}` shape),
but Mistral/Gemini/SambaNova's raw conventions differ from LiteLLM's
normalized one and would silently look for the wrong header if used here.

A response can carry more than one simultaneous dimension (both requests and
tokens remaining at once), so `parse` returns a list, not a single snapshot.

Cohere is deliberately not here at all: its response body carries
`meta.billed_units` — what *this call* cost, not what's *remaining* — which
is a usage report to record directly (see `recorder.py`), not a balance to
reconcile against. It's also Cohere-specific JSON shape that LiteLLM's
OpenAI-compatible normalization has no obligation to preserve, so the
standard `usage` object (always present, see `recorder.extract_usage`) is
the reliable signal for Cohere calls too, not `billed_units`.
"""

from __future__ import annotations

import time
from typing import Protocol, runtime_checkable

import httpx

from maistro.quota.rate_profile import LimitUnit
from maistro.quota.reconciliation import ProviderQuotaSnapshot


@runtime_checkable
class AmbientSignalParser(Protocol):
    """Extracts whatever remaining-capacity snapshots a real response
    carries. Returns an empty list if the response has none (malformed,
    missing headers, wrong endpoint) — never raises for a merely-absent
    signal, since ambient parsing is opportunistic by nature."""

    def parse(self, scope_key: str, response: httpx.Response) -> list[ProviderQuotaSnapshot]: ...


class LiteLLMHeaderParser:
    """The correct ambient parser for `maistro_llm_call` traffic: LiteLLM's
    own standardized `x-ratelimit-remaining-{requests,tokens}` headers,
    populated by its `parallel_request_limiter` regardless of which backend
    provider actually served the call. Use this one, not a provider-specific
    parser, for anything that goes through this platform's shared gateway.
    """

    def parse(self, scope_key: str, response: httpx.Response) -> list[ProviderQuotaSnapshot]:
        snapshots = []
        for header, unit in (
            ("x-ratelimit-remaining-requests", LimitUnit.REQUESTS),
            ("x-ratelimit-remaining-tokens", LimitUnit.TOTAL_TOKENS),
        ):
            snap = _snapshot_from_header(scope_key, response, header, unit)
            if snap is not None:
                snapshots.append(snap)
        return snapshots


def _snapshot_from_header(
    scope_key: str, response: httpx.Response, header: str, unit: LimitUnit
) -> ProviderQuotaSnapshot | None:
    raw = response.headers.get(header)
    if raw is None:
        return None
    try:
        remaining = float(raw)
    except ValueError:
        return None
    return ProviderQuotaSnapshot(
        scope_key=scope_key,
        unit=unit,
        remaining=remaining,
        checked_at=time.time(),
    )


class GroqHeaderParser:
    """Per Groq's own docs: `x-ratelimit-remaining-requests` is always RPD
    (not RPM, despite the generic-looking name); `x-ratelimit-remaining-tokens`
    is always TPM."""

    def parse(self, scope_key: str, response: httpx.Response) -> list[ProviderQuotaSnapshot]:
        snapshots = []
        for header, unit in (
            ("x-ratelimit-remaining-requests", LimitUnit.REQUESTS),
            ("x-ratelimit-remaining-tokens", LimitUnit.TOTAL_TOKENS),
        ):
            snap = _snapshot_from_header(scope_key, response, header, unit)
            if snap is not None:
                snapshots.append(snap)
        return snapshots


class SambaNovaHeaderParser:
    """Per-minute request headroom only — SambaNova's per-model RPD/TPD
    credit-style limits aren't exposed in response headers."""

    def parse(self, scope_key: str, response: httpx.Response) -> list[ProviderQuotaSnapshot]:
        snap = _snapshot_from_header(
            scope_key, response, "x-ratelimit-remaining-requests", LimitUnit.REQUESTS
        )
        return [snap] if snap is not None else []


class MistralHeaderParser:
    """A single generic `X-RateLimit-Remaining` header — Mistral's docs don't
    split it by requests vs. tokens, so this is read as REQUESTS (the more
    literal reading of an undifferentiated "rate limit" figure)."""

    def parse(self, scope_key: str, response: httpx.Response) -> list[ProviderQuotaSnapshot]:
        snap = _snapshot_from_header(
            scope_key, response, "X-RateLimit-Remaining", LimitUnit.REQUESTS
        )
        return [snap] if snap is not None else []


class CerebrasHeaderParser:
    """Cerebras's docs confirm custom real-time usage headers exist but don't
    name them precisely in what's publicly documented — this assumes the same
    `x-ratelimit-remaining-{requests,tokens}` convention Groq/OpenAI-compatible
    backends use, since Cerebras's API is itself OpenAI-compatible. Flagged as
    an assumption to verify against real traffic, not confirmed from official
    header-name docs the way Groq/Gemini's parsers are.
    """

    def parse(self, scope_key: str, response: httpx.Response) -> list[ProviderQuotaSnapshot]:
        snapshots = []
        for header, unit in (
            ("x-ratelimit-remaining-requests", LimitUnit.REQUESTS),
            ("x-ratelimit-remaining-tokens", LimitUnit.TOTAL_TOKENS),
        ):
            snap = _snapshot_from_header(scope_key, response, header, unit)
            if snap is not None:
                snapshots.append(snap)
        return snapshots


class GeminiHeaderParser:
    """`x-ratelimit-remaining` — a single figure per response, not split by
    dimension in the header name itself. Read as REQUESTS; Gemini also has a
    TPM and (for image models) IPM dimension this header doesn't distinguish,
    so a caller relying solely on this signal is only getting the RPM/RPD
    picture, not the full multi-dimension one `rate_profile.py` can model.
    """

    def parse(self, scope_key: str, response: httpx.Response) -> list[ProviderQuotaSnapshot]:
        snap = _snapshot_from_header(
            scope_key, response, "x-ratelimit-remaining", LimitUnit.REQUESTS
        )
        return [snap] if snap is not None else []
