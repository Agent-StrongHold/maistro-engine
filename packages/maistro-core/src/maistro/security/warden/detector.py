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
import signal
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

        max_scan_size = 50 * 1024
        if len(content) > max_scan_size:
            scan_content = unicodedata.normalize("NFKD", content[:max_scan_size])
        else:
            scan_content = unicodedata.normalize("NFKD", content)
        for pattern, description in REJECT_PATTERNS:
            try:
                if _pattern_search(pattern, scan_content):
                    flags.append(description)
            except Exception:
                logger.warning("Regex error on pattern: %s", description)
                flags.append(f"regex_error:{description}")

        if flags:
            return WardenVerdict(
                clean=False,
                blocked=len(flags) >= 2,
                flags=tuple(flags),
                confidence=0.9,
            )

        suspicious, heuristic_flags = heuristic_scan(scan_content)
        if suspicious:
            flags.extend(heuristic_flags)
            return WardenVerdict(
                clean=False,
                blocked=False,
                flags=tuple(flags),
                confidence=0.6,
            )

        poisoned, semantic_flags = semantic_tool_poisoning_scan(scan_content)
        if poisoned:
            flags.extend(semantic_flags)
            return WardenVerdict(
                clean=False,
                blocked=False,
                flags=tuple(flags),
                confidence=0.7,
            )

        if boundary == "tool_result" and self._llm is not None:
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

        return WardenVerdict(clean=True)
