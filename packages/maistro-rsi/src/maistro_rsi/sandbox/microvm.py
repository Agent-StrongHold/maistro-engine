"""Docker-backed development implementation of `MicroVmSandbox`.

Wraps the existing `maistro.tools.sandbox.docker.SandboxContainer` (ADR-054:
one sandbox per task, ephemeral FS, durable state in Postgres/git) so RSI
cycles are runnable today without a real microVM host. `create_microvm_sandbox`
is the single seam to replace once a microVM backend is selected — Firecracker
gives the fastest boot/snapshot story, E2B wraps Firecracker as a hosted SDK
with no host KVM setup, gVisor trades some isolation strength for deployability
on existing container infra. None of the rest of `maistro_rsi` depends on which
one wins; it only depends on `MicroVmSandbox`.
"""

from __future__ import annotations

import uuid

import structlog

from maistro.config.settings import SandboxSettings
from maistro.tools.sandbox.docker import SandboxContainer, create_sandbox

logger = structlog.get_logger()


class DockerMicroVmSandbox:
    """Adapts `SandboxContainer` to the `MicroVmSandbox` protocol.

    Containers can't pause/resume the way microVMs can, so `snapshot` records
    a label for bookkeeping but `restore` raises — callers should rebuild the
    sandbox from the labeled git ref instead. A real microVM backend can offer
    genuine pause/resume here without changing this class's interface.
    """

    def __init__(self, container: SandboxContainer) -> None:
        self._container = container
        self._snapshots: dict[str, str] = {}

    async def exec(self, command: str, timeout: int = 60) -> tuple[int, str]:
        return await self._container.exec(command, timeout=timeout)

    async def read_file(self, path: str) -> str:
        return await self._container.read_file(path)

    async def write_file(self, path: str, content: str) -> None:
        await self._container.write_file(path, content)

    async def snapshot(self, label: str) -> str:
        snapshot_id = f"{label}-{uuid.uuid4().hex[:8]}"
        self._snapshots[snapshot_id] = label
        await logger.ainfo("rsi_sandbox_snapshot_recorded", snapshot_id=snapshot_id, label=label)
        return snapshot_id

    async def restore(self, snapshot_id: str) -> None:
        if snapshot_id not in self._snapshots:
            raise KeyError(f"Unknown snapshot: {snapshot_id}")
        raise NotImplementedError(
            "Docker backend cannot restore microVM-style snapshots; "
            "rebuild the sandbox from the labeled git ref instead."
        )

    async def destroy(self) -> None:
        await self._container.destroy()

    async def __aenter__(self) -> DockerMicroVmSandbox:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.destroy()


async def create_microvm_sandbox(
    workspace: str,
    settings: SandboxSettings | None = None,
    env: dict[str, str] | None = None,
) -> DockerMicroVmSandbox:
    """Create a sandbox satisfying the `MicroVmSandbox` protocol.

    Currently Docker-backed; swap the body of this function for a Firecracker/
    E2B/gVisor-backed implementation when that decision is made.
    """
    container = await create_sandbox(workspace, settings=settings, env=env)
    return DockerMicroVmSandbox(container)
