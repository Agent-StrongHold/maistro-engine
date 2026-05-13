"""Tests for orchestrator utilities."""

from __future__ import annotations

import pytest

from orchestrator.utils import LLMParseError, parse_json_response, clamp


class TestParseJsonResponse:
    """JSON parsing utility tests."""

    def test_parses_plain_json(self):
        """Plain JSON should parse directly."""
        result = parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parses_json_with_markdown_fence(self):
        """JSON wrapped in ```json fence should parse."""
        content = '```json\n{"key": "value"}\n```'
        result = parse_json_response(content)
        assert result == {"key": "value"}

    def test_parses_json_with_plain_fence(self):
        """JSON wrapped in plain ``` fence should parse."""
        content = '```\n{"key": "value"}\n```'
        result = parse_json_response(content)
        assert result == {"key": "value"}

    def test_parses_json_with_surrounding_text(self):
        """JSON embedded in text should be extracted."""
        content = 'Here is the result:\n{"scores": {"a": 1}}\nDone!'
        result = parse_json_response(content)
        assert result == {"scores": {"a": 1}}

    def test_raises_on_invalid_json(self):
        """Invalid JSON should raise LLMParseError."""
        with pytest.raises(LLMParseError):
            parse_json_response("this is not json at all")

    def test_raises_on_truncated_json(self):
        """Truncated JSON should raise LLMParseError."""
        with pytest.raises(LLMParseError):
            parse_json_response('{"key": "val')

    def test_handles_nested_json(self):
        """Nested JSON structures should parse."""
        content = '{"outer": {"inner": [1, 2, 3]}}'
        result = parse_json_response(content)
        assert result["outer"]["inner"] == [1, 2, 3]

    def test_handles_whitespace(self):
        """JSON with extra whitespace should parse."""
        content = '\n\n  {"key": "value"}  \n\n'
        result = parse_json_response(content)
        assert result == {"key": "value"}


class TestClamp:
    """Clamp utility tests."""

    def test_clamp_below_min(self):
        """Value below min should return min."""
        assert clamp(-5, 0, 10) == 0

    def test_clamp_above_max(self):
        """Value above max should return max."""
        assert clamp(15, 0, 10) == 10

    def test_clamp_in_range(self):
        """Value in range should be unchanged."""
        assert clamp(5, 0, 10) == 5

    def test_clamp_at_boundaries(self):
        """Values at boundaries should be unchanged."""
        assert clamp(0, 0, 10) == 0
        assert clamp(10, 0, 10) == 10
