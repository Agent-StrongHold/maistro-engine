"""Layer 1 — Working memory for the active task.

Resets with each new top-level task.
Accumulates subtask results, reviewer feedback, and plan context.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class Layer1:
    """Ephemeral working memory for a single task lifecycle."""

    def __init__(self, max_tokens: int = 8000) -> None:
        self._max_tokens = max_tokens
        self._entries: list[str] = []

    def reset(self) -> None:
        self._entries.clear()

    def add(self, label: str, content: str) -> None:
        self._entries.append(f"### {label}\n{content}")
        logger.debug("Layer 1 += %s (%d chars)", label, len(content))

    def update_subtask(self, subtask_id: str, result_summary: str) -> None:
        self.add(f"Subtask {subtask_id} result", result_summary)

    @property
    def content(self) -> str:
        text = "\n\n".join(self._entries)
        # Crude token estimate (1 token ≈ 4 chars)
        est_tokens = len(text) // 4
        if est_tokens > self._max_tokens:
            # Keep most recent entries that fit
            kept: list[str] = []
            total = 0
            for entry in reversed(self._entries):
                total += len(entry) // 4
                if total > self._max_tokens:
                    break
                kept.append(entry)
            text = "\n\n".join(reversed(kept))
            logger.info("Layer 1 trimmed from %d to %d estimated tokens", est_tokens, total)
        return text
