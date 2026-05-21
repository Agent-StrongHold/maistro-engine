"""Git operations — sandboxed git commands."""

from __future__ import annotations

import logging

from orchestrator.tools.shell import Shell

logger = logging.getLogger(__name__)


class Git:
    """Basic git operations scoped to a project directory."""

    def __init__(self, shell: Shell) -> None:
        self._shell = shell

    async def status(self) -> str:
        result = await self._shell.run("git status --porcelain")
        return result.stdout

    async def diff(self) -> str:
        result = await self._shell.run("git diff")
        return result.stdout

    async def add_all(self) -> None:
        await self._shell.run("git add -A")

    async def commit(self, message: str) -> str:
        result = await self._shell.run(f'git commit -m "{message}"')
        return result.stdout
