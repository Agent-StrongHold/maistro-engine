"""The generic Repertoire protocol (SPEC-258 / ADR-070)."""

from __future__ import annotations

from typing import Protocol, TypeVar

from maistro.repertoire.types import Verdict

InputT = TypeVar("InputT", contravariant=True)
S = TypeVar("S")
E = TypeVar("E")


class Repertoire(Protocol[InputT, S, E]):
    def recall(self, input_class: str) -> E | None: ...

    def nearest(self, input_class: str) -> tuple[E, ...]: ...

    def improvise(self, inp: InputT, priors: tuple[E, ...]) -> S: ...

    def rehearse(self, candidate: S) -> Verdict: ...

    def compose(self, verified: S, input_class: str) -> E: ...

    def class_of(self, inp: InputT) -> str: ...
