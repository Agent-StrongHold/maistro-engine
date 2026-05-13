"""GitHub API operations via gh CLI."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

logger = structlog.get_logger()


async def _run_gh(*args: str, timeout: int = 30) -> tuple[int, str]:
    """Run a gh CLI command and return (exit_code, output)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "gh",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode("utf-8", errors="replace") if stdout else ""
        return proc.returncode or 0, output
    except FileNotFoundError:
        return 1, "gh CLI binary not found — install GitHub CLI"
    except TimeoutError:
        return 1, f"gh command timed out after {timeout}s"


async def create_pr(
    repo: str,
    branch: str,
    title: str,
    body: str,
    base: str = "main",
) -> dict[str, Any]:
    """Create a pull request via gh CLI."""
    code, output = await _run_gh(
        "pr",
        "create",
        "--repo",
        repo,
        "--head",
        branch,
        "--base",
        base,
        "--title",
        title,
        "--body",
        body,
    )
    return {"exit_code": code, "output": output}


async def get_pr(repo: str, number: int) -> dict[str, Any]:
    """Get PR details."""
    code, output = await _run_gh(
        "pr",
        "view",
        str(number),
        "--repo",
        repo,
        "--json",
        "title,body,state,files,reviews",
    )
    if code == 0:
        try:
            return dict(json.loads(output))
        except json.JSONDecodeError:
            logger.warning("gh_pr_invalid_json", repo=repo, number=number, output=output[:200])
            return {"error": f"Invalid JSON from gh: {output[:200]}"}
    return {"error": output}


async def list_issues(repo: str, limit: int = 10) -> list[dict[str, Any]]:
    """List open issues."""
    code, output = await _run_gh(
        "issue",
        "list",
        "--repo",
        repo,
        "--limit",
        str(limit),
        "--json",
        "number,title,body,labels",
    )
    if code == 0:
        try:
            return list(json.loads(output))
        except json.JSONDecodeError:
            logger.warning("gh_issues_invalid_json", repo=repo, output=output[:200])
            return []
    return []
