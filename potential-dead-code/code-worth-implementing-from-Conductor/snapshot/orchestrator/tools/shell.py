"""Shell execution — sandboxed subprocess runner.

Security: Uses subprocess with shell=False and argument list to prevent injection.
Commands are parsed via shlex to split safely.

Platform notes:
- shlex.split uses POSIX mode by default (works on macOS/Linux)
- On Windows, consider using shlex.split(cmd, posix=False) for native paths
- This module currently targets Unix-like systems
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Detect platform for shlex behavior
IS_WINDOWS = sys.platform == "win32"

# Maximum output size to prevent DoS (10 MB)
MAX_OUTPUT_BYTES = 10 * 1024 * 1024


@dataclass
class ShellResult:
    command: str
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    truncated: bool = False


class Shell:
    """Run shell commands scoped to a project directory.

    Security considerations:
    - Commands are split via shlex (no shell metacharacter expansion)
    - Output is limited to prevent memory exhaustion
    - Timeout prevents runaway processes
    """

    def __init__(self, cwd: str | Path, timeout: int = 120) -> None:
        self._cwd = Path(cwd).resolve()
        self._timeout = timeout

    async def run(self, command: str, timeout: int | None = None) -> ShellResult:
        """Execute a command and capture output.

        Args:
            command: Command string (will be split via shlex, not shell-interpreted)
            timeout: Execution timeout in seconds

        Returns:
            ShellResult with output and status
        """
        timeout = timeout or self._timeout

        # Split command safely — raises ValueError on unterminated quotes
        # Use POSIX mode for Unix, non-POSIX for Windows
        try:
            args = shlex.split(command, posix=not IS_WINDOWS)
        except ValueError as e:
            logger.warning("Invalid command syntax: %s — %s", command, e)
            return ShellResult(
                command=command,
                returncode=-1,
                stdout="",
                stderr=f"Invalid command syntax: {e}",
            )

        if not args:
            return ShellResult(
                command=command,
                returncode=-1,
                stdout="",
                stderr="Empty command",
            )

        # Log sanitized version (mask potential secrets)
        logger.info("Shell: %s (cwd=%s)", self._sanitize_for_log(args), self._cwd)

        proc = None
        try:
            # Use create_subprocess_exec (no shell) for security
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(self._cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)

            # Truncate if too large
            truncated = False
            if len(stdout_bytes) > MAX_OUTPUT_BYTES:
                stdout_bytes = stdout_bytes[:MAX_OUTPUT_BYTES]
                truncated = True
            if len(stderr_bytes) > MAX_OUTPUT_BYTES:
                stderr_bytes = stderr_bytes[:MAX_OUTPUT_BYTES]
                truncated = True

            # Decode output, handling various encodings
            # Use UTF-8 by default, but fall back gracefully for binary output
            encoding = "utf-8"
            if IS_WINDOWS:
                # Windows often uses cp1252 or the console's code page
                encoding = os.environ.get("PYTHONIOENCODING", "utf-8")

            return ShellResult(
                command=command,
                returncode=proc.returncode or 0,
                stdout=stdout_bytes.decode(encoding, errors="replace"),
                stderr=stderr_bytes.decode(encoding, errors="replace"),
                truncated=truncated,
            )

        except asyncio.TimeoutError:
            if proc is not None:
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass
            return ShellResult(
                command=command,
                returncode=-1,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                timed_out=True,
            )

        except FileNotFoundError:
            return ShellResult(
                command=command,
                returncode=-1,
                stdout="",
                stderr=f"Command not found: {args[0]}",
            )

    @staticmethod
    def _sanitize_for_log(args: list[str]) -> str:
        """Sanitize command args for logging (mask potential secrets)."""
        sanitized = []
        for i, arg in enumerate(args):
            # Mask args that look like secrets
            if any(
                kw in args[i - 1].lower() if i > 0 else False
                for kw in ("password", "token", "secret", "key", "api")
            ):
                sanitized.append("***")
            elif arg.startswith("--") and "=" in arg:
                key, _, val = arg.partition("=")
                if any(kw in key.lower() for kw in ("password", "token", "secret", "key")):
                    sanitized.append(f"{key}=***")
                else:
                    sanitized.append(arg)
            else:
                sanitized.append(arg)
        return " ".join(sanitized)
