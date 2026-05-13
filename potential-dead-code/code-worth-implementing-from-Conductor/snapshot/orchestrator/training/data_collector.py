"""Training data collector — records every Ultra Think cycle for future training.

Features:
- Append-only JSONL storage
- File rotation when size exceeds threshold
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Maximum training data file size before rotation (50 MB)
MAX_TRAINING_FILE_SIZE = 50 * 1024 * 1024


@dataclass
class CandidateRecord:
    candidate_id: str
    content_hash: str
    sampling_params: dict
    tokens_generated: int
    generation_time_ms: float


@dataclass
class ReviewerScoreRecord:
    candidate_id: str
    scores: dict
    overall: float
    verdict: str


@dataclass
class TestResultRecord:
    candidate_id: str
    passed: bool
    summary: str


@dataclass
class TrainingRecord:
    task_id: str
    timestamp: float
    prompt_hash: str
    tier: int
    candidates: list[CandidateRecord]
    reviewer_scores: list[ReviewerScoreRecord]
    test_results: list[TestResultRecord]
    accepted_candidate_id: str | None
    human_accepted: bool | None = None


class TrainingDataCollector:
    """Collects training examples from operational cycles.

    Files are rotated when they exceed MAX_TRAINING_FILE_SIZE.
    Rotated files are renamed with a timestamp suffix.
    """

    def __init__(self, project_id: str, data_dir: str | Path) -> None:
        self._project_id = project_id
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / f"{project_id}-training.jsonl"

    def record(self, entry: TrainingRecord) -> None:
        """Record a training entry, rotating file if necessary."""
        self._maybe_rotate()

        row = json.dumps(asdict(entry))
        with open(self._path, "a") as f:
            f.write(row + "\n")
        logger.info("Training data: recorded task %s", entry.task_id)

    def _maybe_rotate(self) -> None:
        """Rotate the training file if it exceeds the size threshold."""
        if not self._path.exists():
            return

        if self._path.stat().st_size <= MAX_TRAINING_FILE_SIZE:
            return

        # Rotate with timestamp
        timestamp = int(time.time())
        rotated = self._dir / f"{self._project_id}-training.{timestamp}.jsonl"

        try:
            self._path.rename(rotated)
            logger.info("Rotated training data to %s", rotated.name)
        except OSError as e:
            logger.warning("Failed to rotate training file: %s", e)

    @staticmethod
    def hash_content(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()[:16]
