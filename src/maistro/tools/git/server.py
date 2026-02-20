"""Git operations MCP server — clone, branch, commit, push, PR, diff.

Exposes git and GitHub operations as MCP tools for agents to use.
"""

from __future__ import annotations

import asyncio

from fastmcp import FastMCP

from maistro.tools.git.github import create_pr, get_pr, list_issues

mcp = FastMCP("git", instructions="Git and GitHub operations")


async def _git(workspace: str, *args: str, timeout: int = 60) -> str:
    """Run a git command in the given workspace."""
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", workspace, *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    output = stdout.decode("utf-8", errors="replace") if stdout else ""
    code = proc.returncode or 0
    return f"[exit {code}]\n{output}" if code != 0 else output


@mcp.tool()
async def git_clone(url: str, dest: str) -> str:
    """Clone a git repository.

    Args:
        url: Repository URL (HTTPS or SSH)
        dest: Destination directory path
    """
    proc = await asyncio.create_subprocess_exec(
        "git", "clone", "--depth=1", url, dest,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    return stdout.decode() if stdout else "Cloned"


@mcp.tool()
async def git_branch(workspace: str, name: str, checkout: bool = True) -> str:
    """Create and optionally checkout a new branch.

    Args:
        workspace: Path to the git repository
        name: Branch name
        checkout: Whether to checkout the branch after creation
    """
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
async def git_commit(workspace: str, message: str, add_all: bool = True) -> str:
    """Stage and commit changes.

    Args:
        workspace: Path to the git repository
        message: Commit message
        add_all: Whether to stage all changes first
    """
    if add_all:
        await _git(workspace, "add", "-A")
        # Unstage sensitive files if accidentally staged
        for pattern in _SENSITIVE_PATTERNS:
            await _git(workspace, "reset", "HEAD", "--", pattern)
    return await _git(workspace, "commit", "-m", message)


@mcp.tool()
async def git_push(workspace: str, branch: str | None = None, set_upstream: bool = True) -> str:
    """Push commits to remote.

    Args:
        workspace: Path to the git repository
        branch: Branch to push (defaults to current)
        set_upstream: Set upstream tracking
    """
    args = ["push"]
    if set_upstream:
        args.extend(["-u", "origin"])
    if branch:
        args.append(branch)
    return await _git(workspace, *args)


@mcp.tool()
async def git_diff(workspace: str, staged: bool = False) -> str:
    """Show diff of changes.

    Args:
        workspace: Path to the git repository
        staged: Show staged changes only
    """
    args = ["diff"]
    if staged:
        args.append("--staged")
    return await _git(workspace, *args)


@mcp.tool()
async def git_status(workspace: str) -> str:
    """Show repository status.

    Args:
        workspace: Path to the git repository
    """
    return await _git(workspace, "status", "--short")


@mcp.tool()
async def git_log(workspace: str, limit: int = 10) -> str:
    """Show recent commit log.

    Args:
        workspace: Path to the git repository
        limit: Number of commits to show
    """
    return await _git(workspace, "log", "--oneline", f"-{limit}")


@mcp.tool()
async def github_create_pr(
    repo: str,
    branch: str,
    title: str,
    body: str,
    base: str = "main",
) -> str:
    """Create a GitHub pull request.

    Args:
        repo: Repository in owner/name format
        branch: Source branch
        title: PR title
        body: PR description
        base: Target branch
    """
    result = await create_pr(repo, branch, title, body, base)
    return result.get("output", str(result))


@mcp.tool()
async def github_get_pr(repo: str, number: int) -> str:
    """Get details of a GitHub pull request.

    Args:
        repo: Repository in owner/name format
        number: PR number
    """
    result = await get_pr(repo, number)
    return str(result)


@mcp.tool()
async def github_list_issues(repo: str, limit: int = 10) -> str:
    """List open GitHub issues.

    Args:
        repo: Repository in owner/name format
        limit: Max number of issues to return
    """
    issues = await list_issues(repo, limit)
    return str(issues)
