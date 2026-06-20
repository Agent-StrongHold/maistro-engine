"""Repertoire Pattern core types (SPEC-258 / ADR-070)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reason: str = ""


class RehearsalFailed(Exception):
    def __init__(self, verdict: Verdict) -> None:
        super().__init__(verdict.reason or "rehearsal failed")
        self.verdict = verdict


class PerformGate(Protocol):
    def should_perform(self, entry: Any, *, stakes: float) -> bool: ...
