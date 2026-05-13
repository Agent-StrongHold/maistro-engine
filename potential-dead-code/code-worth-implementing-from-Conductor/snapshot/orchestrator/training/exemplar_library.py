"""Exemplar library — Training-Free GRPO via curated best completions."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Exemplar:
    task_category: str
    task_description: str
    solution: str
    score: float


class ExemplarLibrary:
    """Maintains a curated library of best completions for few-shot prompting."""

    CATEGORIES = ["test_writing", "bug_fix", "new_feature", "refactor", "documentation"]
    MAX_PER_CATEGORY = 50

    def __init__(self, data_dir: str | Path) -> None:
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "exemplars.jsonl"
        self._cache: dict[str, list[Exemplar]] = {cat: [] for cat in self.CATEGORIES}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        for line in self._path.read_text().strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                ex = Exemplar(**data)
                if ex.task_category in self._cache:
                    self._cache[ex.task_category].append(ex)
            except Exception:
                continue
        for cat in self._cache:
            self._cache[cat].sort(key=lambda e: -e.score)
            self._cache[cat] = self._cache[cat][: self.MAX_PER_CATEGORY]
        logger.info("Exemplar library loaded: %d total", sum(len(v) for v in self._cache.values()))

    def add(self, exemplar: Exemplar) -> None:
        cat = exemplar.task_category
        if cat not in self._cache:
            cat = "new_feature"
        self._cache[cat].append(exemplar)
        self._cache[cat].sort(key=lambda e: -e.score)
        self._cache[cat] = self._cache[cat][: self.MAX_PER_CATEGORY]
        self._save()

    def _save(self) -> None:
        with open(self._path, "w") as f:
            for cat, exemplars in self._cache.items():
                for ex in exemplars:
                    f.write(json.dumps(asdict(ex)) + "\n")

    def get_exemplars(self, category: str, n: int = 2) -> list[Exemplar]:
        """Return top N exemplars for a category."""
        cat = category if category in self._cache else "new_feature"
        return self._cache[cat][:n]
