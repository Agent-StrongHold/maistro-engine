"""Warden: threat detection at two ingress points.

Scans user input and tool results for hostile content.
Four layers (cheap to expensive, short-circuit on detection):
1. Regex patterns (zero cost, sub-millisecond)
2. Heuristic scoring (lightweight statistical check)
2.5. Semantic tool-poisoning (action+object+prescriptive, sub-millisecond)
3. LLM classification (few-shot, ~100ms, costs tokens -- optional)
"""

from __future__ import annotations

import logging
import unicodedata
from typing import TYPE_CHECKING

from maistro.security._types import WardenVerdict
from maistro.security.warden.heuristics import heuristic_scan
from maistro.security.warden.patterns import REJECT_PATTERNS
from maistro.security.warden.semantic import semantic_tool_poisoning_scan

if TYPE_CHECKING:
    from maistro.security._types import LLMClient

logger = logging.getLogger("maistro.warden")

_PATTERN_TIMEOUT_S = 0.5

_HAS_REGEX_TIMEOUT = hasattr(REJECT_PATTERNS[0][0].search, "__code__") if REJECT_PATTERNS else False


def _pattern_search(pattern: object, text: str) -> bool:
    import re as _re

    p: _re.Pattern[str] = pattern  # type: ignore[assignment]
    try:
        return bool(p.search(text))
    except Exception:
        return False


def _scan_reject_patterns(scan_content: str) -> list[str]:
    """Run every reject pattern against ``scan_content``, collecting flag
    descriptions (and ``regex_error:`` markers for patterns that raise)."""
    flags: list[str] = []
    for pattern, description in REJECT_PATTERNS:
        try:
            if _pattern_search(pattern, scan_content):
                flags.append(description)
        except Exception:
            logger.warning("Regex error on pattern: %s", description)
            flags.append(f"regex_error:{description}")
    return flags


class Warden:
    """Threat detector. Runs at user_input and tool_result boundaries only.

    Layers 1-2.5 are always active (free, instant).
    Layer 3 (LLM) is optional -- requires an LLM client and model to be configured.
    """

    def __init__(
        self,
        *,
        llm: LLMClient | None = None,
        classifier_model: str = "auto",
    ) -> None:
        self._llm = llm
        self._classifier_model = classifier_model

    async def scan(
        self,
        content: str,
        boundary: str,
    ) -> WardenVerdict:
        flags: list[str] = []

        # Fix #4: scan in overlapping windows — no unscanned tail.
        # Window: 50KB with 2KB overlap so patterns spanning a boundary are caught.
        window_size = 50 * 1024
        overlap = 2 * 1024
        content_norm = unicodedata.normalize("NFKD", content)

        if len(content_norm) <= window_size:
            flags.extend(_scan_reject_patterns(content_norm))
        else:
            offset = 0
            while offset < len(content_norm):
                chunk = content_norm[offset : offset + window_size]
                flags.extend(_scan_reject_patterns(chunk))
                if flags:
                    break  # Found something — no need to continue
                offset += window_size - overlap

        if flags:
            return WardenVerdict(
                clean=False,
                blocked=len(flags) >= 2,
                flags=tuple(flags),
                confidence=0.9,
            )

        suspicious, heuristic_flags = heuristic_scan(content_norm)
        if suspicious:
            flags.extend(heuristic_flags)
            return WardenVerdict(
                clean=False,
                blocked=False,
                flags=tuple(flags),
                confidence=0.6,
            )

        poisoned, semantic_flags = semantic_tool_poisoning_scan(content_norm)
        if poisoned:
            flags.extend(semantic_flags)
            return WardenVerdict(
                clean=False,
                blocked=False,
                flags=tuple(flags),
                confidence=0.7,
            )

        if boundary == "tool_result" and self._llm is not None:
            llm_verdict = await self._scan_llm_classification(content, flags)
            if llm_verdict is not None:
                return llm_verdict

        return WardenVerdict(clean=True)

    async def _scan_llm_classification(
        self, content: str, flags: list[str]
    ) -> WardenVerdict | None:
        """L3 LLM tool-result classification. Returns a verdict if the content is
        classified suspicious, otherwise ``None``. Only called when ``self._llm``
        is set."""
        assert self._llm is not None
        try:
            from maistro.security.warden.llm_classifier import classify_tool_result

            result = await classify_tool_result(
                content,
                self._llm,
                self._classifier_model,
            )

            if result.get("label") == "suspicious":
                model = result.get("model", "?")
                flags.append(f"llm_classification:suspicious (model={model}, mode=binary)")
                return WardenVerdict(
                    clean=False,
                    blocked=False,
                    flags=tuple(flags),
                    confidence=0.8,
                    reasoning_trace=result.get("reasoning_trace"),
                )
        except Exception:
            logger.warning("L3 LLM classification failed", exc_info=True)
        return None
