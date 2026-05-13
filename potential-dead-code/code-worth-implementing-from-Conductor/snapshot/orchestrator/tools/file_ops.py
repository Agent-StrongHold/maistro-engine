"""File operations — sandboxed read/write/create.

Security:
- All paths are resolved and validated to be within the project root
- Uses Path.is_relative_to() for robust path traversal prevention
- File sizes are limited to prevent DoS
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Maximum file size for reads/writes (5 MB)
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024

# Forbidden path patterns
FORBIDDEN_PATTERNS = [
    r"\.\.[\\/]",  # Path traversal attempts
    r"^[\\/]",  # Absolute paths
    r"[<>:\"|?*]",  # Invalid filename characters (Windows)
]

# Forbidden filenames (security-sensitive paths)
# Note: .gitignore is blocked to prevent accidentally exposing secrets via ignore changes
# To customize, subclass FileOps and override FORBIDDEN_NAMES
FORBIDDEN_NAMES = {
    ".git",
    ".env",
    ".envrc",
    ".gitignore",
    "__pycache__",
    "node_modules",
}


class FileOps:
    """Scoped file operations within a project directory.

    All operations are sandboxed to the project root.
    Path traversal attempts are blocked.
    """

    def __init__(self, project_dir: str | Path) -> None:
        self._root = Path(project_dir).resolve()
        if not self._root.exists():
            raise ValueError(f"Project directory does not exist: {self._root}")

    def _resolve(self, relpath: str) -> Path:
        """Resolve a path and ensure it's within the project root.

        Raises:
            PermissionError: If path escapes project root or is forbidden
            ValueError: If path is malformed
        """
        # Check for forbidden patterns in the raw path
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, relpath):
                raise PermissionError(f"Forbidden path pattern: {relpath}")

        # Check path components for forbidden names
        parts = Path(relpath).parts
        for part in parts:
            if part in FORBIDDEN_NAMES:
                raise PermissionError(f"Forbidden path component: {part}")

        # Resolve and validate containment
        target = (self._root / relpath).resolve()

        # Use is_relative_to for robust containment check (Python 3.9+)
        try:
            target.relative_to(self._root)
        except ValueError:
            raise PermissionError(f"Path escapes project root: {relpath}")

        return target

    def read(self, relpath: str, encoding: str = "utf-8") -> str:
        """Read a file's contents.

        Args:
            relpath: Relative path within project directory
            encoding: Text encoding (default: utf-8). Use 'latin-1' for binary-ish text.

        Raises:
            FileNotFoundError: If file doesn't exist
            PermissionError: If path escapes project root
            ValueError: If file is too large or not decodable
        """
        p = self._resolve(relpath)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {relpath}")
        if not p.is_file():
            raise ValueError(f"Not a file: {relpath}")

        # Check file size before reading
        size = p.stat().st_size
        if size > MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"File too large: {relpath} ({size} bytes > {MAX_FILE_SIZE_BYTES} max)"
            )

        try:
            return p.read_text(encoding=encoding)
        except UnicodeDecodeError as e:
            # Try with error handling for mixed-encoding files
            logger.warning("Encoding error reading %s with %s: %s", relpath, encoding, e)
            return p.read_text(encoding=encoding, errors="replace")

    def write(self, relpath: str, content: str, encoding: str = "utf-8") -> None:
        """Write content to a file.

        Args:
            relpath: Relative path within project directory
            content: Text content to write
            encoding: Text encoding (default: utf-8)

        Raises:
            PermissionError: If path escapes project root
            ValueError: If content is too large
        """
        # Check content size before writing
        try:
            content_bytes = len(content.encode(encoding))
        except UnicodeEncodeError:
            # Fallback to UTF-8 with replacement for unencodable chars
            content_bytes = len(content.encode("utf-8", errors="replace"))
            encoding = "utf-8"

        if content_bytes > MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"Content too large: {content_bytes} bytes > {MAX_FILE_SIZE_BYTES} max"
            )

        p = self._resolve(relpath)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding=encoding)
        logger.info("Wrote %d chars to %s", len(content), relpath)

    def exists(self, relpath: str) -> bool:
        """Check if a path exists within the project."""
        try:
            return self._resolve(relpath).exists()
        except PermissionError:
            return False

    def list_dir(self, relpath: str = ".") -> list[str]:
        """List directory contents.

        Returns relative paths from project root.
        """
        try:
            p = self._resolve(relpath)
        except PermissionError:
            return []

        if not p.is_dir():
            return []

        result = []
        for f in p.iterdir():
            # Skip hidden and forbidden entries
            if f.name.startswith(".") or f.name in FORBIDDEN_NAMES:
                continue
            try:
                result.append(str(f.relative_to(self._root)))
            except ValueError:
                continue
        return result
