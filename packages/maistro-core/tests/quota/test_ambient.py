"""Tests for ambient (free, per-call) reconciliation signal parsers."""

from __future__ import annotations

import httpx

from maistro.quota.ambient import (
    AmbientSignalParser,
    CerebrasHeaderParser,
    GeminiHeaderParser,
    GroqHeaderParser,
    LiteLLMHeaderParser,
    MistralHeaderParser,
    SambaNovaHeaderParser,
)
from maistro.quota.rate_profile import LimitUnit


def _response(headers: dict[str, str]) -> httpx.Response:
    return httpx.Response(200, headers=headers, request=httpx.Request("GET", "https://example.com"))


def test_groq_parser_satisfies_protocol() -> None:
    assert isinstance(GroqHeaderParser(), AmbientSignalParser)


def test_groq_parses_both_dimensions() -> None:
    response = _response(
        {"x-ratelimit-remaining-requests": "950", "x-ratelimit-remaining-tokens": "4500"}
    )
    snapshots = GroqHeaderParser().parse("groq:kimi-k2", response)

    by_unit = {s.unit: s.remaining for s in snapshots}
    assert by_unit[LimitUnit.REQUESTS] == 950.0
    assert by_unit[LimitUnit.TOTAL_TOKENS] == 4500.0
    assert all(s.scope_key == "groq:kimi-k2" for s in snapshots)


def test_groq_parses_partial_headers() -> None:
    response = _response({"x-ratelimit-remaining-requests": "10"})
    snapshots = GroqHeaderParser().parse("groq:kimi-k2", response)
    assert len(snapshots) == 1
    assert snapshots[0].unit == LimitUnit.REQUESTS


def test_groq_returns_empty_list_when_headers_absent() -> None:
    response = _response({})
    assert GroqHeaderParser().parse("groq:kimi-k2", response) == []


def test_groq_ignores_unparseable_header_value() -> None:
    response = _response({"x-ratelimit-remaining-requests": "not-a-number"})
    assert GroqHeaderParser().parse("groq:kimi-k2", response) == []


def test_sambanova_parses_requests_only() -> None:
    response = _response({"x-ratelimit-remaining-requests": "18"})
    snapshots = SambaNovaHeaderParser().parse("sambanova:deepseek-r1", response)
    assert len(snapshots) == 1
    assert snapshots[0].unit == LimitUnit.REQUESTS
    assert snapshots[0].remaining == 18.0


def test_sambanova_empty_when_absent() -> None:
    assert SambaNovaHeaderParser().parse("sambanova:deepseek-r1", _response({})) == []


def test_mistral_parses_generic_header() -> None:
    response = _response({"X-RateLimit-Remaining": "42"})
    snapshots = MistralHeaderParser().parse("mistral:mistral-small", response)
    assert len(snapshots) == 1
    assert snapshots[0].unit == LimitUnit.REQUESTS
    assert snapshots[0].remaining == 42.0


def test_cerebras_parses_both_dimensions() -> None:
    response = _response(
        {"x-ratelimit-remaining-requests": "25", "x-ratelimit-remaining-tokens": "55000"}
    )
    snapshots = CerebrasHeaderParser().parse("cerebras:qwen3-235b", response)
    by_unit = {s.unit: s.remaining for s in snapshots}
    assert by_unit[LimitUnit.REQUESTS] == 25.0
    assert by_unit[LimitUnit.TOTAL_TOKENS] == 55000.0


def test_gemini_parses_generic_remaining() -> None:
    response = _response({"x-ratelimit-remaining": "12"})
    snapshots = GeminiHeaderParser().parse("gemini:gemini-2-5-flash", response)
    assert len(snapshots) == 1
    assert snapshots[0].unit == LimitUnit.REQUESTS
    assert snapshots[0].remaining == 12.0


def test_all_parsers_satisfy_protocol() -> None:
    for parser in (
        GroqHeaderParser(),
        SambaNovaHeaderParser(),
        MistralHeaderParser(),
        CerebrasHeaderParser(),
        GeminiHeaderParser(),
        LiteLLMHeaderParser(),
    ):
        assert isinstance(parser, AmbientSignalParser)


class TestLiteLLMHeaderParser:
    """The parser that actually matters for `maistro_llm_call` traffic --
    LiteLLM standardizes every backend provider into this same header shape,
    regardless of whether Groq/Cerebras/SambaNova/Mistral/Gemini served it."""

    def test_parses_both_dimensions_regardless_of_backend_provider(self) -> None:
        response = _response(
            {"x-ratelimit-remaining-requests": "1200", "x-ratelimit-remaining-tokens": "88000"}
        )
        snapshots = LiteLLMHeaderParser().parse("cerebras:qwen3-235b", response)

        by_unit = {s.unit: s.remaining for s in snapshots}
        assert by_unit[LimitUnit.REQUESTS] == 1200.0
        assert by_unit[LimitUnit.TOTAL_TOKENS] == 88000.0

    def test_empty_when_headers_absent(self) -> None:
        """Matches LiteLLM's own documented gap: these headers are dropped on
        streaming responses -- an absent header must be a no-op, not a crash."""
        assert LiteLLMHeaderParser().parse("cerebras:qwen3-235b", _response({})) == []
