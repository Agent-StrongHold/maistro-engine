"""Git operations MCP server — clone, branch, commit, push, PR, diff.

Exposes git and GitHub operations as MCP tools for agents to use.
All tools return structured dicts with {success, exit_code, stdout}.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastmcp import FastMCP

from maistro.tools.git.github import create_pr, get_pr, list_issues
from maistro.tools.result import fail, ok

mcp = FastMCP("git", instructions="Git and GitHub operations")

GIT_CLONE_TIMEOUT = 300


async def _git(workspace: str, *args: str, timeout: int = 60) -> dict[str, Any]:
    """Run a git command in the given workspace. Returns structured result."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", workspace, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode("utf-8", errors="replace") if stdout else ""
        code = proc.returncode or 0
        return ok(stdout=output, exit_code=code) if code == 0 else fail(stdout=output, exit_code=code)
    except FileNotFoundError:
        return fail(stdout="git binary not found")
    except TimeoutError:
        return fail(stdout=f"git command timed out after {timeout}s", exit_code=124)


@mcp.tool()
async def git_clone(url: str, dest: str, timeout: int = GIT_CLONE_TIMEOUT) -> dict[str, Any]:
    """Clone a git repository."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth=1", url, dest,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode() if stdout else "Cloned"
        code = proc.returncode or 0
        return ok(stdout=output, exit_code=code) if code == 0 else fail(stdout=output, exit_code=code)
    except FileNotFoundError:
        return fail(stdout="git binary not found")
    except TimeoutError:
        return fail(stdout=f"git clone timed out after {timeout}s", exit_code=124)


@mcp.tool()
async def git_branch(workspace: str, name: str, checkout: bool = True) -> dict[str, Any]:
    """Create and optionally checkout a new branch."""
    if checkout:
        return await _git(workspace, "checkout", "-b", name)
    return await _git(workspace, "branch", name)


# File patterns that should never be staged
_SENSITIVE_PATTERNS = (
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx",
    "credentials.json", "service-account.json", "secrets.yaml",
    "id_rsa", "id_ed25519", ".npmrc", ".pypirc",
)


@mcp.tool()
async def git_commit(workspace: str, message: str, add_all: bool = True) -> dict[str, Any]:
    """Stage and commit changes."""
    if add_all:
        await _git(workspace, "add", "-A")
        # Unstage sensitive files if accidentally staged
        for pattern in _SENSITIVE_PATTERNS:
            await _git(workspace, "reset", "HEAD", "--", pattern)
    return await _git(workspace, "commit", "-m", message)


@mcp.tool()
async def git_push(workspace: str, branch: str | None = None, set_upstream: bool = True) -> dict[str, Any]:
    """Push commits to remote."""
    args = ["push"]
    if set_upstream:
        args.extend(["-u", "origin"])
    if branch:
        args.append(branch)
    return await _git(workspace, *args)


@mcp.tool()
async def git_diff(workspace: str, staged: bool = False) -> dict[str, Any]:
    """Show diff of changes."""
    args = ["diff"]
    if staged:
        args.append("--staged")
    return await _git(workspace, *args)


@mcp.tool()
async def git_status(workspace: str) -> dict[str, Any]:
    """Show repository status."""
    return await _git(workspace, "status", "--short")


@mcp.tool()
async def git_log(workspace: str, limit: int = 10) -> dict[str, Any]:
    """Show recent commit log."""
    return await _git(workspace, "log", "--oneline", f"-{limit}")


@mcp.tool()
async def github_create_pr(
    repo: str, branch: str, title: str, body: str, base: str = "main",
) -> dict[str, Any]:
    """Create a GitHub pull request."""
    return await create_pr(repo, branch, title, body, base)


@mcp.tool()
async def github_get_pr(repo: str, number: int) -> dict[str, Any]:
    """Get details of a GitHub pull request."""
    return await get_pr(repo, number)


@mcp.tool()
async def github_list_issues(repo: str, limit: int = 10) -> dict[str, Any]:
    """List open GitHub issues."""
    issues = await list_issues(repo, limit)
    return ok(stdout=str(issues), issues=issues)
