"""DAG-flow progress model for builder-session monitoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from maistro_bootstrap.builders.message_board import MessageBoard
from maistro_bootstrap.builders.quality import QualityGateReport

DagStage = Literal["spec", "plan", "implement", "test", "audit"]

_STAGE_LABELS: dict[DagStage, str] = {
    "spec": "Spec",
    "plan": "Plan",
    "implement": "Implement",
    "test": "Test",
    "audit": "Audit",
}


@dataclass
class DagFlow:
    """A monitorable autonomous builder DAG projection."""

    board: MessageBoard = field(default_factory=MessageBoard)
    quality: QualityGateReport | None = None
    _cards_by_stage: dict[DagStage, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for stage, label in _STAGE_LABELS.items():
            card = self.board.add_todo(title=label, owner=stage)
            self._cards_by_stage[stage] = card.card_id

    def start(self, stage: DagStage) -> None:
        self.board.start(self._cards_by_stage[stage])

    def finish(self, stage: DagStage, *, summary: str) -> None:
        self.board.finish(self._cards_by_stage[stage], summary=summary)

    def record_quality(self, report: QualityGateReport) -> None:
        self.quality = report

    @property
    def is_complete(self) -> bool:
        columns = self.board.columns()
        return (
            len(columns["todo"]) == 0
            and len(columns["wip"]) == 0
            and len(columns["done"]) == len(_STAGE_LABELS)
            and self.quality is not None
            and self.quality.passed
        )

    def snapshot(self) -> dict[str, object]:
        columns = self.board.columns()
        quality = None
        if self.quality is not None:
            quality = {
                "passed": self.quality.passed,
                "failures": self.quality.failures(),
                "coverage_pct": self.quality.coverage_pct,
                "mutation_score_pct": self.quality.mutation_score_pct,
            }
        return {
            "columns": {name: len(cards) for name, cards in columns.items()},
            "quality": quality,
            "complete": self.is_complete,
        }
