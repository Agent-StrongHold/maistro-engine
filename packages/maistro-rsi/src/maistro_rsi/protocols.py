"""MicroVM sandbox protocol — abstraction over isolated execution backends.

Defines the contract an RSI cycle needs from its execution environment without
committing to a specific microVM technology yet (Firecracker vs. E2B vs.
gVisor is an open ADR). `maistro_rsi.sandbox.microvm` ships a Docker-backed
implementation that satisfies this protocol today; everything else in this
package — including `selfbranch` and `runner` — depends only on the protocol,
so swapping the backend later touches one factory function, not call sites.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class MicroVmSandbox(Protocol):
    """An isolated, ephemeral execution environment for one RSI attempt."""

    async def exec(self, command: str, timeout: int = 60) -> tuple[int, str]:
        """Run a command inside the sandbox. Returns (exit_code, output)."""
        ...

    async def read_file(self, path: str) -> str:
        """Read a file from the sandbox workspace."""
        ...

    async def write_file(self, path: str, content: str) -> None:
        """Write a file in the sandbox workspace."""
        ...

    async def snapshot(self, label: str) -> str:
        """Capture restorable state and return a snapshot id.

        True microVMs (Firecracker/E2B) can pause and snapshot a running
        instance for fast restore; container-based backends approximate this
        or decline — see `restore` for the contract each backend must honor.
        """
        ...

    async def restore(self, snapshot_id: str) -> None:
        """Restore previously captured state. Raises if the backend can't."""
        ...

    async def destroy(self) -> None:
        """Tear down the sandbox and release its resources."""
        ...


# Supplied by the RSI runner: given a sandbox and a checked-out workspace,
# produce the actual code modification (typically by driving an agent).
# Kept out of `selfbranch` so the git/sandbox plumbing stays testable
# independent of any particular agent strategy.
ApplyPatchFn = Callable[[MicroVmSandbox, str], Awaitable[None]]
