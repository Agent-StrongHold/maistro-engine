"""Local passthrough ``MicroVmSandbox`` — for when the RSI cycle already runs
*inside* an isolated microVM.

When maistro-rsi is launched as a Docker Sandboxes (``sbx``) agent, ``sbx`` has
already booted an isolated microVM (own kernel, ephemeral FS, deny-by-default
egress) and runs the RSI entrypoint inside it. Creating a *nested*
``DockerMicroVmSandbox`` there would be redundant Docker-in-Docker: the microVM
is the isolation boundary. ``LocalSandbox`` satisfies the same ``MicroVmSandbox``
protocol by running the cycle's commands directly against the (already-isolated)
local workspace.

Everything downstream of the sandbox is unchanged — the RSI quarantine gate
(Warden + adversarial review) still governs what may leave the sandbox as a PR,
so "run directly on the local FS" is safe precisely because that FS is the
disposable microVM ``sbx`` handed us.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from pathlib import Path

import structlog

logger = structlog.get_logger()

_TIMEOUT_EXIT_CODE = 124
#: Cap on how long we wait to reap a killed process after a timeout, so `exec`
#: never blocks unboundedly if the host is slow to reap (SIGKILL is already sent).
_REAP_GRACE_SECONDS = 1.0


class LocalSandbox:
    """Run RSI commands on the local filesystem (already inside an sbx microVM)."""

    def __init__(self, workspace: str) -> None:
        self._workspace = workspace
        self._snapshots: dict[str, str] = {}
        Path(workspace).mkdir(parents=True, exist_ok=True)

    def _resolve(self, path: str) -> Path:
        candidate = Path(path)
        return candidate if candidate.is_absolute() else Path(self._workspace) / candidate

    async def exec(self, command: str, timeout: int = 60) -> tuple[int, str]:
        # argv into ``/bin/sh -c`` (not shell=True) so shell operators in RSI
        # test commands work; runs inside the isolated sbx microVM, which is the
        # trust boundary — the RSI quarantine gate governs what may leave it.
        proc = await asyncio.create_subprocess_exec(  # nosec B603
            "/bin/sh",
            "-c",
            command,
            cwd=self._workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            # SIGKILL is delivered; bound the reap so a slow host can't wedge us.
            with contextlib.suppress(Exception):
                await asyncio.wait_for(proc.wait(), timeout=_REAP_GRACE_SECONDS)
            return _TIMEOUT_EXIT_CODE, f"timeout after {timeout}s"
        return proc.returncode or 0, stdout.decode(errors="replace")

    async def read_file(self, path: str) -> str:
        return self._resolve(path).read_text(encoding="utf-8")

    async def write_file(self, path: str, content: str) -> None:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    async def snapshot(self, label: str) -> str:
        snapshot_id = f"{label}-{uuid.uuid4().hex[:8]}"
        self._snapshots[snapshot_id] = label
        await logger.ainfo("rsi_local_snapshot_recorded", snapshot_id=snapshot_id, label=label)
        return snapshot_id

    async def restore(self, snapshot_id: str) -> None:
        if snapshot_id not in self._snapshots:
            raise KeyError(f"Unknown snapshot: {snapshot_id}")
        raise NotImplementedError(
            "LocalSandbox cannot restore snapshots; rebuild from the labeled git ref instead."
        )

    async def destroy(self) -> None:
        # sbx owns the microVM lifecycle; there is nothing to tear down locally.
        return None

    async def __aenter__(self) -> LocalSandbox:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.destroy()
