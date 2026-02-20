"""Docker container lifecycle management for sandbox execution.

Creates isolated containers for code execution, with resource limits,
network isolation, and environment sanitization.
"""

from __future__ import annotations

import asyncio
import shlex
import uuid

import structlog

from maistro.config.settings import SandboxSettings
from maistro.security.dangerous_tools import is_dangerous_command
from maistro.tools.sandbox.env_sanitize import sanitize_env
from maistro.tools.sandbox.workspace import CONTAINER_WORKSPACE, ensure_workspace

logger = structlog.get_logger()


class SandboxContainer:
    """Manages a Docker container for sandboxed code execution."""

    def __init__(
        self,
        container_id: str,
        workspace_host: str,
        workspace_container: str = CONTAINER_WORKSPACE,
    ) -> None:
        self.container_id = container_id
        self.workspace_host = workspace_host
        self.workspace_container = workspace_container

    async def exec(self, command: str, timeout: int = 60) -> tuple[int, str]:
        """Execute a command in the container. Returns (exit_code, output)."""
        # MAJ-04: Check for dangerous commands before execution
        dangers = is_dangerous_command(command)
        if dangers:
            await logger.awarn(
                "dangerous_command_blocked",
                command=command[:200],
                patterns=dangers,
                container=self.container_id[:12],
            )
            return 1, f"Command blocked by safety filter: {', '.join(dangers[:3])}"

        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "exec", self.container_id,
                "bash", "-c", command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stdout.decode("utf-8", errors="replace") if stdout else ""
            return proc.returncode or 0, output
        except TimeoutError:
            return 124, f"Command timed out after {timeout}s"
        except Exception as exc:
            return 1, f"Exec error: {exc}"

    async def read_file(self, path: str) -> str:
        """Read a file from the container workspace."""
        # MAJ-01: Sanitize path to prevent injection
        if path.startswith("/") and not path.startswith(self.workspace_container):
            raise ValueError(f"Path must be within workspace: {path}")
        full_path = f"{self.workspace_container}/{path}" if not path.startswith("/") else path
        safe_path = shlex.quote(full_path)
        exit_code, output = await self.exec(f"cat {safe_path}")
        if exit_code != 0:
            raise FileNotFoundError(f"Cannot read {path}: {output}")
        return output

    async def write_file(self, path: str, content: str) -> None:
        """Write a file in the container workspace via docker cp stdin."""
        if path.startswith("/") and not path.startswith(self.workspace_container):
            raise ValueError(f"Path must be within workspace: {path}")
        full_path = f"{self.workspace_container}/{path}" if not path.startswith("/") else path
        safe_path = shlex.quote(full_path)
        # Ensure parent directory exists
        parent = "/".join(full_path.rsplit("/", 1)[:-1])
        if parent:
            await self.exec(f"mkdir -p {shlex.quote(parent)}")
        # MAJ-02: Use randomized heredoc delimiter to prevent injection
        delimiter = f"MAISTRO_EOF_{uuid.uuid4().hex[:8]}"
        exit_code, output = await self.exec(
            f"cat > {safe_path} << '{delimiter}'\n{content}\n{delimiter}"
        )
        if exit_code != 0:
            raise OSError(f"Cannot write {path}: {output}")

    async def destroy(self) -> None:
        """Stop and remove the container."""
        proc = await asyncio.create_subprocess_exec(
            "docker", "rm", "-f", self.container_id,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        await logger.ainfo("sandbox_destroyed", container_id=self.container_id[:12])


async def create_sandbox(
    workspace: str,
    settings: SandboxSettings | None = None,
    env: dict[str, str] | None = None,
) -> SandboxContainer:
    """Create and start a new sandbox container.

    Args:
        workspace: Host path to mount as /workspace
        settings: Sandbox configuration (image, limits, etc.)
        env: Environment variables to pass (will be sanitized)
    """
    if settings is None:
        settings = SandboxSettings()

    host_path = ensure_workspace(workspace)
    safe_env = sanitize_env(env or {})

    # MIN-02: Use UUID for unique, unpredictable container names
    container_name = f"maistro-sandbox-{uuid.uuid4().hex[:12]}"

    cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        # Resource limits
        f"--memory={settings.memory_limit}",
        f"--cpus={settings.cpu_count}",
        # Security
        "--security-opt=no-new-privileges",
        "--cap-drop=ALL",
        "--cap-add=CHOWN",
        "--cap-add=SETUID",
        "--cap-add=SETGID",
        # Filesystem
        "-v", f"{host_path}:{CONTAINER_WORKSPACE}",
        "-w", CONTAINER_WORKSPACE,
    ]

    # Network isolation (MAJ-05: now defaults to True in settings)
    if settings.network_disabled:
        cmd.append("--network=none")

    # Environment variables
    for k, v in safe_env.items():
        cmd.extend(["-e", f"{k}={v}"])

    # Image and keep-alive command
    cmd.extend([settings.image, "sleep", str(settings.timeout)])

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        error = stderr.decode() if stderr else "Unknown error"
        raise RuntimeError(f"Failed to create sandbox: {error}")

    container_id = stdout.decode().strip()
    await logger.ainfo("sandbox_created", container_id=container_id[:12], image=settings.image)

    return SandboxContainer(
        container_id=container_id,
        workspace_host=str(host_path),
    )
