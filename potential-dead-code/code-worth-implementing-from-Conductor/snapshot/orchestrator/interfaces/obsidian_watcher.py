"""Obsidian watcher — monitors inbox folder for new tasks.

Security:
- File size limits on reads
- Safe filename handling
- Exception isolation per task
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import Callable, Awaitable

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent

logger = logging.getLogger(__name__)

# Maximum task file size (1 MB)
MAX_TASK_FILE_SIZE = 1 * 1024 * 1024

# Valid task filename pattern (alphanumeric, hyphens, underscores, spaces)
VALID_FILENAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\- ]{0,200}\.md$")


class _InboxHandler(FileSystemEventHandler):
    """Handles file creation events in the inbox folder."""

    def __init__(
        self,
        callback: Callable[[Path], Awaitable[None]],
        loop: asyncio.AbstractEventLoop,
        debounce_ms: int = 500,
    ) -> None:
        self._callback = callback
        self._loop = loop
        self._debounce_ms = debounce_ms
        self._pending: dict[str, float] = {}

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        # event.src_path can be bytes or str
        src_path = event.src_path
        if isinstance(src_path, bytes):
            src_path = src_path.decode("utf-8", errors="replace")
        path = Path(src_path)
        if path.suffix != ".md":
            return

        # Validate filename
        if not VALID_FILENAME_PATTERN.match(path.name):
            logger.warning("Ignoring file with invalid name: %s", path.name)
            return

        # Debounce: record timestamp, schedule check
        self._pending[str(path)] = time.monotonic()
        self._loop.call_later(
            self._debounce_ms / 1000, self._check_and_dispatch, str(path)
        )

    def _check_and_dispatch(self, path_str: str) -> None:
        path = Path(path_str)
        last_seen = self._pending.get(path_str, 0)
        # If file was modified again recently, skip (still writing)
        if time.monotonic() - last_seen < (self._debounce_ms / 1000):
            # Reschedule
            self._loop.call_later(
                self._debounce_ms / 1000, self._check_and_dispatch, path_str
            )
            return
        if not path.exists():
            self._pending.pop(path_str, None)
            return
        self._pending.pop(path_str, None)
        coro = self._callback(path)
        asyncio.run_coroutine_threadsafe(coro, self._loop)  # type: ignore[arg-type]


class ObsidianWatcher:
    """Watches an Obsidian vault's conductor/inbox folder for tasks.

    Security:
    - Validates filenames before processing
    - Limits file sizes to prevent DoS
    - Isolates exceptions per task
    """

    def __init__(
        self,
        vault_path: str | Path,
        on_task: Callable[[str, str], Awaitable[str]],
    ) -> None:
        """
        Args:
            vault_path: Path to the Obsidian vault root
            on_task: Async callback(task_id, task_content) -> result_markdown
        """
        self._vault = Path(vault_path).resolve()
        self._inbox = self._vault / "conductor" / "inbox"
        self._completed = self._vault / "conductor" / "completed"
        self._failed = self._vault / "conductor" / "failed"
        self._on_task = on_task
        # Observer type from watchdog — use Any to avoid import issues with mypy
        from typing import Any
        self._observer: Any = None

        # Ensure folders exist
        for folder in [self._inbox, self._completed, self._failed]:
            folder.mkdir(parents=True, exist_ok=True)

    async def _handle_file(self, path: Path) -> None:
        """Process a single task file."""
        # Validate that path is within inbox
        try:
            path.relative_to(self._inbox)
        except ValueError:
            logger.error("Attempted to process file outside inbox: %s", path)
            return

        # Sanitize task_id from filename
        task_id = self._sanitize_task_id(path.stem)
        if not task_id:
            logger.warning("Invalid task filename: %s", path.name)
            return

        logger.info("New task file: %s", task_id)

        try:
            # Check file size
            size = path.stat().st_size
            if size > MAX_TASK_FILE_SIZE:
                raise ValueError(
                    f"Task file too large: {size} bytes (max {MAX_TASK_FILE_SIZE})"
                )

            content = path.read_text()
            result = await self._on_task(task_id, content)

            # Write to completed
            output = f"{content}\n\n---\n\n## Result\n\n{result}"
            dest = self._completed / f"{task_id}.md"
            dest.write_text(output)
            path.unlink()
            logger.info("Task %s completed, moved to %s", task_id, dest)

        except Exception as e:
            logger.exception("Task %s failed: %s", task_id, e)
            # Write to failed — sanitize error message
            try:
                original_content = path.read_text() if path.exists() else "(file unavailable)"
            except Exception:
                original_content = "(could not read file)"

            error_msg = str(e)[:1000]  # Limit error message length
            output = f"{original_content}\n\n---\n\n## Error\n\n{error_msg}"
            dest = self._failed / f"{task_id}.md"
            dest.write_text(output)
            try:
                path.unlink()
            except Exception:
                pass

    @staticmethod
    def _sanitize_task_id(stem: str) -> str:
        """Sanitize a filename stem into a valid task ID."""
        # Replace spaces and special chars with hyphens
        sanitized = re.sub(r"[^a-zA-Z0-9_-]", "-", stem)
        # Remove consecutive hyphens
        sanitized = re.sub(r"-+", "-", sanitized)
        # Remove leading/trailing hyphens
        sanitized = sanitized.strip("-")
        # Limit length
        sanitized = sanitized[:128]
        return sanitized if sanitized else ""

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """Start watching the inbox folder."""
        handler = _InboxHandler(self._handle_file, loop)
        self._observer = Observer()
        self._observer.schedule(handler, str(self._inbox), recursive=False)
        self._observer.start()
        logger.info("Obsidian watcher started: %s", self._inbox)

    def stop(self) -> None:
        """Stop the watcher."""
        if self._observer is not None:
            self._observer.stop()  # type: ignore[union-attr]
            self._observer.join()  # type: ignore[union-attr]
            logger.info("Obsidian watcher stopped")
