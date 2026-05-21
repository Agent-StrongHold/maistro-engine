"""Shared utilities for the orchestrator."""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)


class LLMParseError(ValueError):
    """Raised when LLM output cannot be parsed as expected format."""

    pass


def parse_json_response(content: str) -> dict:
    """Parse JSON from LLM response, handling common markdown wrapping.

    Args:
        content: Raw LLM response text

    Returns:
        Parsed JSON as dict

    Raises:
        LLMParseError: If content cannot be parsed as JSON
    """
    # First try direct parsing
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try stripping markdown code fences
    cleaned = content.strip()

    # Remove ```json or ``` prefix
    if cleaned.startswith("```"):
        # Find the first newline after opening fence
        first_newline = cleaned.find("\n")
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1 :]

    # Remove trailing ```
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]

    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        # One more attempt: find JSON object boundaries
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        raise LLMParseError(
            f"Could not parse LLM response as JSON: {e}. "
            f"Content (first 500 chars): {content[:500]}"
        )


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value to a range."""
    return max(min_val, min(max_val, value))
