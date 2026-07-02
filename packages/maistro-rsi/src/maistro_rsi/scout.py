"""Scout step: one model names the concrete improvement (SPEC-070126-9d37).

Before the competitors run, a scout reads the file and identifies a single,
bounded improvement. Every competitor then implements that *same* objective, so
the head-to-head is fair (they differ in how they fix it, not in what they fix).
If the scout returns nothing usable, fall back to the generic objective so a
cycle never stalls on a silent scout.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_SCOUT_SYSTEM = (
    "You are a meticulous code reviewer. Read the file and identify ONE small, "
    "safe, self-contained improvement worth making — a clearer or missing "
    "docstring, a tightened type hint, or an obvious minor issue. Reply with a "
    "single concrete instruction naming exactly what to change and where. Do not "
    "make the change yourself and do not add commentary."
)

LlmCall = Callable[..., dict[str, Any]]


def scout_objective(source: str, llm_call: LlmCall, *, fallback: str) -> str:
    """Ask ``llm_call`` to name one improvement for ``source``; return it stripped.

    Returns ``fallback`` if the call errors or yields empty/whitespace output.
    """
    messages = [
        {"role": "system", "content": _SCOUT_SYSTEM},
        {"role": "user", "content": f"Identify one improvement for this file:\n\n{source}"},
    ]
    try:
        result = llm_call(messages, max_tokens=400)
    except Exception:
        return fallback
    content = result.get("content", "") if isinstance(result, dict) else result
    text = content if isinstance(content, str) else str(content)
    return text.strip() or fallback
