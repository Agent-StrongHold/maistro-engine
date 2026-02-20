"""Sandbox MCP server — exposes Docker sandbox operations as MCP tools.

This FastMCP server provides tools for:
- exec: Run commands in the sandbox
- read: Read files from the workspace
- write: Write files to the workspace
- glob: Find files by pattern
- grep: Search file contents
"""

from __future__ import annotations

from typing import Any

import structlog
from fastmcp import FastMCP

from maistro.observability.metrics import sandbox_containers_active
from maistro.security.dangerous_tools import is_blocked_path, is_dangerous_command
from maistro.tools.result import fail, ok
from maistro.tools.sandbox.docker import SandboxContainer, create_sandbox

logger = structlog.get_logger()

mcp = FastMCP("sandbox", instructions="Docker sandbox for isolated code execution")

# Active sandbox containers, keyed by workspace path
_containers: dict[str, SandboxContainer] = {}


async def _get_or_create(workspace: str) -> SandboxContainer:
    """Get an existing container for this workspace or create one."""
    existing = _containers.get(workspace)
    if existing is not None:
        if existing.expired:
            logger.info("sandbox_ttl_expired", workspace=workspace)
            await existing.destroy()
            del _containers[workspace]
        else:
            return existing

    container = await create_sandbox(workspace)
    _containers[workspace] = container
    sandbox_containers_active.set(len(_containers))
    return container


async def cleanup_all_containers() -> None:
    """Destroy all active sandbox containers. Called during shutdown."""
    count = len(_containers)
    for workspace, container in list(_containers.items()):
        try:
            await container.destroy()
        except Exception:
            logger.exception("sandbox_cleanup_error", workspace=workspace)
    _containers.clear()
    sandbox_containers_active.set(0)
    logger.info("all_sandboxes_cleaned_up", count=count)


def _check_path(path: str) -> dict[str, Any] | None:
    """Return a fail result if path is blocked, else None."""
    if is_blocked_path(path):
        return fail(stdout=f"Blocked: access to '{path}' is not allowed")
    return None


@mcp.tool()
async def sandbox_exec(workspace: str, command: str, timeout: int = 60) -> dict[str, Any]:
    """Execute a shell command in the sandbox container."""
    violations = is_dangerous_command(command)
    if violations:
        logger.warning("dangerous_command_blocked", command=command, violations=violations)
        return fail(stdout=f"Blocked: command matched dangerous patterns: {', '.join(violations)}")

    container = await _get_or_create(workspace)
    exit_code, output = await container.exec(command, timeout=timeout)
    return ok(stdout=output, exit_code=exit_code) if exit_code == 0 else fail(stdout=output, exit_code=exit_code)


@mcp.tool()
async def sandbox_read(workspace: str, path: str) -> dict[str, Any]:
    """Read a file from the sandbox workspace."""
    if err := _check_path(path):
        return err
    container = await _get_or_create(workspace)
    try:
        content = await container.read_file(path)
        return ok(stdout=content, path=path)
    except FileNotFoundError as e:
        return fail(stdout=str(e), path=path)


@mcp.tool()
async def sandbox_write(workspace: str, path: str, content: str) -> dict[str, Any]:
    """Write a file to the sandbox workspace."""
    if err := _check_path(path):
        return err
    container = await _get_or_create(workspace)
    try:
        await container.write_file(path, content)
        return ok(stdout=f"Written: {path}", path=path)
    except OSError as e:
        return fail(stdout=str(e), path=path)


@mcp.tool()
async def sandbox_glob(workspace: str, pattern: str) -> dict[str, Any]:
    """Find files matching a glob pattern in the workspace."""
    if err := _check_path(pattern):
        return err
    container = await _get_or_create(workspace)
    exit_code, output = await container.exec(
        f"find /workspace -path '/workspace/{pattern}' -type f 2>/dev/null | head -100"
    )
    files = [f for f in output.strip().splitlines() if f] if output else []
    return ok(stdout=output or "No files found", files=files)


@mcp.tool()
async def sandbox_grep(workspace: str, pattern: str, path: str = ".") -> dict[str, Any]:
    """Search for a pattern in files within the workspace."""
    if err := _check_path(path):
        return err
    container = await _get_or_create(workspace)
    exit_code, output = await container.exec(
        f"grep -rn '{pattern}' /workspace/{path} 2>/dev/null | head -50"
    )
    return ok(stdout=output or "No matches found", match_count=output.count("\n") if output else 0)


@mcp.tool()
async def sandbox_destroy(workspace: str) -> dict[str, Any]:
    """Destroy the sandbox container for a workspace."""
    container = _containers.pop(workspace, None)
    if container:
        await container.destroy()
        return ok(stdout=f"Sandbox destroyed for {workspace}")
    return fail(stdout="No sandbox found for this workspace")
