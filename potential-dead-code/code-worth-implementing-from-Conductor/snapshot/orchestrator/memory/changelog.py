"""Layer 3 — Annotated changelog.

Append-only JSONL log of all changes made by Conductor.
Serves as audit trail, context for future tasks, and training data source.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Maximum changelog file size to read (10 MB)
MAX_CHANGELOG_READ_SIZE = 10 * 1024 * 1024


@dataclass
class ChangelogEntry:
    timestamp: float
    task_id: str
    original_request: str
    plan_summary: str
    files_modified: list[str]
    test_passed: bool
    attempts: int
    tier_used: int
    reviewer_score: float
    human_accepted: bool | None = None  # filled later


class Changelog:
    """Append-only JSONL changelog per project."""

    def __init__(self, project_id: str, data_dir: str | Path = "./training-data") -> None:
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / f"{project_id}-changelog.jsonl"

    def record(self, entry: ChangelogEntry) -> None:
        row = json.dumps(asdict(entry))
        with open(self._path, "a") as f:
            f.write(row + "\n")
        logger.info("Changelog: recorded task %s", entry.task_id)

    def recent(self, n: int = 10) -> list[ChangelogEntry]:
        """Return the N most recent entries.

        Uses tail-reading to avoid loading entire file into memory.
        """
        if not self._path.exists():
            return []

        # Check file size
        file_size = self._path.stat().st_size
        if file_size > MAX_CHANGELOG_READ_SIZE:
            logger.warning(
                "Changelog file too large (%d bytes), reading last %d bytes only",
                file_size,
                MAX_CHANGELOG_READ_SIZE,
            )
            # Read only the tail of the file
            with open(self._path, "rb") as f:
                f.seek(max(0, file_size - MAX_CHANGELOG_READ_SIZE))
                # Skip partial first line
                if f.tell() > 0:
                    f.readline()
                content = f.read().decode(errors="replace")
        else:
            content = self._path.read_text()

        lines = content.strip().split("\n")
        entries = []
        for line in lines[-n:]:
            if not line:
                continue
            try:
                entries.append(ChangelogEntry(**json.loads(line)))
            except Exception:
                continue
        return entries

    @property
    def content(self) -> str:
        """Render recent changelog as context string."""
        entries = self.recent(5)
        if not entries:
            return ""
        lines = ["## Recent Changes"]
        for e in entries:
            lines.append(
                f"- [{e.task_id}] {e.original_request[:80]} "
                f"(tier {e.tier_used}, {e.attempts} attempts, "
                f"score {e.reviewer_score:.1f}, tests {'pass' if e.test_passed else 'fail'})"
            )
        return "\n".join(lines)
