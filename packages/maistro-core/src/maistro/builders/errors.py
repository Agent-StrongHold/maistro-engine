"""Builder safety layer errors (SPEC-200)."""

from __future__ import annotations

from pathlib import Path


class SandboxEscapeError(Exception):
    """A command argument resolves to a path outside the sandbox root."""

    def __init__(self, arg: str, root: Path) -> None:
        self.arg = arg
        self.root = root
        super().__init__(f"Path {arg!r} escapes sandbox root {root}")


class BlockedCommandError(Exception):
    """A command is on the blocked list and must not execute in a sandbox."""

    def __init__(self, cmd: list[str]) -> None:
        self.cmd = cmd
        super().__init__(f"Blocked command: {cmd!r}")


class CommandTimeoutError(Exception):
    """A sandboxed command exceeded its timeout."""

    def __init__(self, cmd: list[str], timeout: float) -> None:
        self.cmd = cmd
        self.timeout = timeout
        super().__init__(f"Command timed out after {timeout}s: {cmd[0]!r}")


class ContextViolation(Exception):
    """An agent stage handler attempted to use an undeclared execution context."""

    def __init__(self, agent: str, declared: str, attempted: str) -> None:
        self.agent = agent
        self.declared = declared
        self.attempted = attempted
        super().__init__(
            f"Agent {agent!r} declared context {declared!r} but attempted {attempted!r}"
        )


class UnconfirmedRepoAction(Exception):
    """A destructive repo action was attempted without a valid confirmation token."""

    def __init__(self, action: str) -> None:
        self.action = action
        super().__init__(f"Repo action {action!r} requires a valid confirmation token")


class UnconfirmedDiffApply(Exception):
    """apply_diff() was called without confirmed=True."""

    def __init__(self) -> None:
        super().__init__("apply_diff() requires confirmed=True — review the diff first")


class DiffApplyError(Exception):
    """git apply --check failed; the real repo was not touched."""

    def __init__(self, check_output: str) -> None:
        self.check_output = check_output
        super().__init__(f"Diff does not apply cleanly: {check_output[:200]}")


class OutputTruncatedWarning(UserWarning):
    """Informational: sandbox command output exceeded 1 MB and was truncated."""

    def __init__(self, bytes_dropped: int) -> None:
        self.bytes_dropped = bytes_dropped
        super().__init__(f"Output truncated: {bytes_dropped} bytes dropped")


class WorkspaceTeardownError(Exception):
    """git worktree remove failed (non-fatal, but the caller should log it)."""

    def __init__(self, path: Path, detail: str) -> None:
        self.path = path
        self.detail = detail
        super().__init__(f"Teardown of {path} failed: {detail}")
