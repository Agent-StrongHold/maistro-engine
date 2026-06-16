"""Kata Containers backend for hardware-VM-isolated sandbox execution.

The Docker-compatible CLI is used only as the trusted control plane. Sandbox
instances use a Kata runtime, no host bind mounts, a read-only root filesystem,
and fresh tmpfs-backed workspace and temporary directories.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import time
from pathlib import PurePosixPath
from uuid import uuid4

from maistro.sandbox.protocol import ExecResult, SandboxConfig, SandboxInstance
from maistro.tools.sandbox.env_sanitize import sanitize_env

_ALLOWED_FILE_ROOTS = (PurePosixPath("/workspace"), PurePosixPath("/tmp"))  # nosec B108 — access-control allowlist, not a file creation; the /tmp entry defines what the sandbox is *permitted* to access, not a predictable temp path on the host


class KataSandboxBackend:
    """Run sandbox instances through a configured Kata OCI runtime."""

    _tier = "vm"

    def __init__(
        self,
        *,
        engine: str | None = None,
        runtime: str | None = None,
    ) -> None:
        self._engine = engine or os.environ.get("MAISTRO_KATA_ENGINE", "docker")
        self._runtime = runtime or os.environ.get("MAISTRO_KATA_RUNTIME", "io.containerd.kata.v2")
        if "kata" not in self._runtime.lower():
            raise ValueError("KataSandboxBackend requires a Kata runtime name")

    @property
    def runtime(self) -> str:
        return self._runtime

    def is_available(self) -> bool:
        """Return whether the configured engine advertises the Kata runtime."""
        try:
            result = subprocess.run(  # nosec B603 - trusted operator config, shell=False
                [self._engine, "info", "--format", "{{json .Runtimes}}"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            return False
        if result.returncode != 0:
            return False
        try:
            runtimes = json.loads(result.stdout)
        except json.JSONDecodeError:
            return self._runtime in result.stdout
        return isinstance(runtimes, dict) and self._runtime in runtimes

    async def spawn(self, *, config: SandboxConfig) -> SandboxInstance:
        name = f"maistro-vm-{uuid4().hex[:12]}"
        workspace = self._safe_workspace(config.workspace_path)
        safe_env = sanitize_env(config.env)
        command = [
            self._engine,
            "run",
            "--detach",
            "--rm",
            "--name",
            name,
            "--runtime",
            self._runtime,
            "--read-only",
            "--security-opt=no-new-privileges",
            "--cap-drop=ALL",
            f"--memory={config.memory_mb}m",
            f"--cpus={config.cpu_cores}",
            f"--pids-limit={config.pids_limit}",
            "--user=65532:65532",
            "--workdir",
            workspace,
            "--tmpfs",
            (f"{workspace}:rw,nosuid,nodev,size={config.disk_mb}m,uid=65532,gid=65532,mode=0700"),
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=256m,uid=65532,gid=65532,mode=0700",  # nosec B108 — Docker --tmpfs mount spec for the container filesystem, not a host path; the /tmp here belongs to the isolated container, not the host
            "--label",
            "maistro.sandbox=true",
            "--label",
            "maistro.isolation=vm",
        ]
        if not config.network:
            command.append("--network=none")
        for key, value in safe_env.items():
            command.extend(["--env", f"{key}={value}"])
        command.extend([config.image_ref, "sleep", str(config.lifetime_s)])

        return_code, stdout, stderr = await self._run(command, timeout_s=60)
        if return_code != 0:
            raise RuntimeError(f"Failed to spawn Kata sandbox: {stderr.decode(errors='replace')}")
        container_id = stdout.decode().strip()
        return SandboxInstance(
            id=container_id,
            backend="kata",
            isolation_tier="vm",
            metadata={
                "name": name,
                "runtime": self._runtime,
                "workspace_path": workspace,
                "network": config.network,
                "image_ref": config.image_ref,
            },
        )

    async def exec(
        self, instance: SandboxInstance, command: list[str], *, timeout_s: int = 120
    ) -> ExecResult:
        if not command:
            raise ValueError("Sandbox command must not be empty")
        self._require_instance(instance)
        workspace = str(instance.metadata.get("workspace_path", "/workspace"))
        started = time.monotonic()
        engine_command = [
            self._engine,
            "exec",
            "--workdir",
            workspace,
            instance.id,
            "timeout",
            "--signal=KILL",
            str(timeout_s),
            *command,
        ]
        try:
            return_code, stdout, stderr = await self._run(engine_command, timeout_s=timeout_s + 10)
        except TimeoutError:
            return ExecResult(
                exit_code=124,
                stdout="",
                stderr=f"Command timed out after {timeout_s}s",
                duration_ms=int((time.monotonic() - started) * 1000),
                timed_out=True,
            )
        return ExecResult(
            exit_code=return_code,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
            duration_ms=int((time.monotonic() - started) * 1000),
            timed_out=return_code == 124,
        )

    async def write_file(self, instance: SandboxInstance, path: str, content: bytes) -> None:
        self._require_instance(instance)
        safe_path = self._safe_file_path(path)
        parent = str(PurePosixPath(safe_path).parent)
        command = [
            self._engine,
            "exec",
            "--interactive",
            instance.id,
            "sh",
            "-c",
            'mkdir -p -- "$1" && base64 -d > "$2"',
            "maistro-write",
            parent,
            safe_path,
        ]
        return_code, _, stderr = await self._run(
            command,
            input_data=base64.b64encode(content),
            timeout_s=120,
        )
        if return_code != 0:
            raise OSError(f"Cannot write sandbox file {path}: {stderr.decode(errors='replace')}")

    async def read_file(self, instance: SandboxInstance, path: str) -> bytes:
        self._require_instance(instance)
        safe_path = self._safe_file_path(path)
        return_code, stdout, stderr = await self._run(
            [self._engine, "exec", instance.id, "cat", "--", safe_path],
            timeout_s=120,
        )
        if return_code != 0:
            raise FileNotFoundError(
                f"Cannot read sandbox file {path}: {stderr.decode(errors='replace')}"
            )
        return stdout

    async def destroy(self, instance: SandboxInstance) -> None:
        self._require_instance(instance)
        await self._run([self._engine, "rm", "--force", instance.id], timeout_s=60)

    def _require_instance(self, instance: SandboxInstance) -> None:
        if instance.backend != "kata" or instance.isolation_tier != "vm":
            raise ValueError("Instance was not created by the Kata VM backend")

    @staticmethod
    def _safe_workspace(path: str) -> str:
        parsed = PurePosixPath(path)
        if not parsed.is_absolute() or ".." in parsed.parts or str(parsed) != "/workspace":
            raise ValueError("Kata backend workspace must be /workspace")
        return str(parsed)

    @staticmethod
    def _safe_file_path(path: str) -> str:
        parsed = PurePosixPath(path)
        if not parsed.is_absolute() or ".." in parsed.parts:
            raise ValueError(f"Sandbox file path must be absolute and normalized: {path!r}")
        if not any(parsed == root or root in parsed.parents for root in _ALLOWED_FILE_ROOTS):
            raise ValueError(f"Sandbox file path is outside allowed roots: {path!r}")
        return str(parsed)

    async def _run(
        self,
        command: list[str],
        *,
        input_data: bytes | None = None,
        timeout_s: int,
    ) -> tuple[int, bytes, bytes]:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE if input_data is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(input_data), timeout=timeout_s)
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            raise
        return proc.returncode or 0, stdout or b"", stderr or b""
