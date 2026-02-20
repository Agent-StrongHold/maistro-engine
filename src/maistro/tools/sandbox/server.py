"""Sandbox MCP server — exposes Docker sandbox operations as MCP tools.

This FastMCP server provides tools for:
- exec: Run commands in the sandbox
- read: Read files from the workspace
- write: Write files to the workspace
- glob: Find files by pattern
- grep: Search file contents
"""

from __future__ import annotations

import shlex

from fastmcp import FastMCP

from maistro.tools.sandbox.docker import SandboxContainer, create_sandbox

mcp = FastMCP("sandbox", instructions="Docker sandbox for isolated code execution")

# Active sandbox containers, keyed by workspace path
_containers: dict[str, SandboxContainer] = {}


async def _get_or_create(workspace: str) -> SandboxContainer:
    """Get an existing container for this workspace or create one."""
    if workspace not in _containers:
        _containers[workspace] = await create_sandbox(workspace)
    return _containers[workspace]


@mcp.tool()
async def sandbox_exec(workspace: str, command: str, timeout: int = 60) -> str:
    """Execute a shell command in the sandbox container.

    Args:
        workspace: Path to the workspace directory
        command: Shell command to execute
        timeout: Maximum execution time in seconds
    """
    container = await _get_or_create(workspace)
    exit_code, output = await container.exec(command, timeout=timeout)
    return f"[exit {exit_code}]\n{output}"


@mcp.tool()
async def sandbox_read(workspace: str, path: str) -> str:
    """Read a file from the sandbox workspace.

    Args:
        workspace: Path to the workspace directory
        path: Relative path to the file within the workspace
    """
    container = await _get_or_create(workspace)
    return await container.read_file(path)


@mcp.tool()
async def sandbox_write(workspace: str, path: str, content: str) -> str:
    """Write a file to the sandbox workspace.

    Args:
        workspace: Path to the workspace directory
        path: Relative path to the file within the workspace
        content: File content to write
    """
    container = await _get_or_create(workspace)
    await container.write_file(path, content)
    return f"Written: {path}"


@mcp.tool()
async def sandbox_glob(workspace: str, pattern: str) -> str:
    """Find files matching a glob pattern in the workspace.

    Args:
        workspace: Path to the workspace directory
        pattern: Glob pattern (e.g., '**/*.py', 'src/**/*.ts')
    """
    container = await _get_or_create(workspace)
    # MAJ-01: Sanitize pattern to prevent shell injection
    safe_pattern = shlex.quote(f"/workspace/{pattern}")
    _, output = await container.exec(
        f"find /workspace -path {safe_pattern} -type f 2>/dev/null | head -100"
    )
    return output or "No files found"


@mcp.tool()
async def sandbox_grep(workspace: str, pattern: str, path: str = ".") -> str:
    """Search for a pattern in files within the workspace.

    Args:
        workspace: Path to the workspace directory
        pattern: Search pattern (regex)
        path: Directory or file to search in (relative to workspace)
    """
    container = await _get_or_create(workspace)
    # MAJ-01: Sanitize pattern and path to prevent shell injection
    safe_pattern = shlex.quote(pattern)
    safe_path = shlex.quote(f"/workspace/{path}")
    _, output = await container.exec(
        f"grep -rn {safe_pattern} {safe_path} 2>/dev/null | head -50"
    )
    return output or "No matches found"


@mcp.tool()
async def sandbox_destroy(workspace: str) -> str:
    """Destroy the sandbox container for a workspace.

    Args:
        workspace: Path to the workspace directory
    """
    container = _containers.pop(workspace, None)
    if container:
        await container.destroy()
        return f"Sandbox destroyed for {workspace}"
    return "No sandbox found for this workspace"
