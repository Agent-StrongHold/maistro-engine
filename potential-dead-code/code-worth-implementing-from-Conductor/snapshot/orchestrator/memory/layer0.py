"""Layer 0 — Pinned constraints.

Read from a Markdown file in the project directory.
Never summarized, never compressed, always included verbatim.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class Layer0:
    """Immutable project constraints loaded from constraints.md."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._content: str = ""
        self.reload()

    def reload(self) -> None:
        """(Re)load constraints from disk."""
        if self._path.exists():
            self._content = self._path.read_text()
            logger.info("Layer 0 loaded: %d chars from %s", len(self._content), self._path)
        else:
            self._content = ""
            logger.warning("Layer 0 file not found: %s", self._path)

    @property
    def content(self) -> str:
        return self._content

    @property
    def path(self) -> Path:
        return self._path
