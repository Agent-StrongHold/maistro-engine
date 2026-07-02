"""microVM sandbox backend (SPEC-190): stronger-than-container isolation for harnesses.

The container backend (``docker.py``) shares the host kernel; a microVM backend
(Firecracker / Cloud-Hypervisor / QEMU) gives each run its own kernel, which is
the isolation SPEC-208's foreign harnesses want. Rather than bind to one VMM, the
launch step is an injected seam (``VMMLauncher``): production wires a real VMM,
tests inject a fake — the same pattern ``SubprocessHarnessRunner`` uses for its
sandbox.

``MicroVMSandbox.exec(command, timeout)`` matches the ``SandboxExec`` shape the
HarnessRunner provider expects, so a harness can run inside a microVM with no code
change — just a different backend. Network is default-deny; memory/vCPU are capped.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from maistro.config.settings import SandboxSettings
from maistro.security.dangerous_tools import is_dangerous_command
from maistro.tools.sandbox.env_sanitize import sanitize_env
from maistro.tools.sandbox.workspace import ensure_workspace

NetworkMode = Literal["none", "restricted"]


def _parse_mib(memory_limit: str) -> int:
    """Parse a docker-style memory string ('512m', '1g') into MiB."""
    text = memory_limit.strip().lower()
    if text.endswith("g"):
        return int(float(text[:-1]) * 1024)
    if text.endswith("m"):
        return int(float(text[:-1]))
    if text.endswith("k"):
        return max(1, int(float(text[:-1]) / 1024))
    return max(1, int(float(text)) // (1024 * 1024))  # bare bytes


@dataclass(frozen=True)
class MicroVMConfig:
    kernel_image: str = "vmlinux"
    rootfs_image: str = "rootfs.ext4"
    vcpus: int = 2
    memory_mib: int = 512
    network: NetworkMode = "none"
    timeout: int = 300
    backend: str = "firecracker"

    @classmethod
    def from_settings(cls, settings: SandboxSettings) -> MicroVMConfig:
        # Use the VM-specific kernel/rootfs, NOT settings.image (a Docker/OCI
        # ref) — Firecracker & Cloud-Hypervisor boot a kernel + ext4 rootfs and
        # can't boot from an image reference.
        return cls(
            kernel_image=settings.vm_kernel_image,
            rootfs_image=settings.vm_rootfs_image,
            vcpus=settings.cpu_count,
            memory_mib=_parse_mib(settings.memory_limit),
            network="none" if settings.network_disabled else "restricted",
            timeout=settings.timeout,
        )


@dataclass(frozen=True)
class MicroVMRunSpec:
    """Everything a launcher needs to boot a VM, run one command, and tear down."""

    command: str
    workspace: str
    timeout: int
    config: MicroVMConfig
    env: dict[str, str] = field(default_factory=dict)


@runtime_checkable
class VMMLauncher(Protocol):
    """Boot a microVM per the spec, run its command, return ``(exit_code, output)``."""

    async def run(self, spec: MicroVMRunSpec) -> tuple[int, str]: ...


# A plain async function is also a valid launcher.
LauncherFn = Callable[[MicroVMRunSpec], Awaitable[tuple[int, str]]]

_BLOCKED_EXIT_CODE = 126


class MicroVMSandbox:
    """SandboxExec-compatible backend that runs each command inside a microVM."""

    def __init__(
        self,
        launcher: VMMLauncher | LauncherFn,
        *,
        config: MicroVMConfig | None = None,
        workspace: str = ".",
        env: dict[str, str] | None = None,
    ) -> None:
        self._launcher = launcher
        self._config = config or MicroVMConfig()
        self._workspace = workspace
        self._env = dict(env or {})

    @property
    def config(self) -> MicroVMConfig:
        return self._config

    async def exec(self, command: str, timeout: int = 60) -> tuple[int, str]:
        """Run ``command`` in a fresh microVM. Refuses obviously-dangerous commands."""
        dangers = is_dangerous_command(command)
        if dangers:
            return _BLOCKED_EXIT_CODE, f"blocked dangerous command: {', '.join(dangers)}"
        # Validate/translate the (untrusted) workspace and allowlist-sanitize the
        # env BEFORE handing them to a real VMM — same host-path-escape and
        # secret-leak guarantees the container backend enforces (docker.py). A
        # caller-supplied path like "/" or "/etc" is refused here, not mounted;
        # ambient secrets (API keys) never cross into the guest.
        try:
            workspace = str(ensure_workspace(self._workspace))
        except ValueError as exc:
            return _BLOCKED_EXIT_CODE, f"blocked: workspace not permitted: {exc}"
        spec = MicroVMRunSpec(
            command=command,
            workspace=workspace,
            timeout=min(timeout, self._config.timeout),
            config=self._config,
            env=sanitize_env(self._env),
        )
        if isinstance(self._launcher, VMMLauncher):
            return await self._launcher.run(spec)
        return await self._launcher(spec)
