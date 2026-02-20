"""Dangerous command and tool detection.

Identifies commands and tool invocations that could be destructive
or security-sensitive. Ported from OpenClaw's dangerous-tools.ts.
"""

from __future__ import annotations

import re

# Regex patterns for dangerous commands
_DANGEROUS_COMMAND_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"rm\s+-rf\s+[/~]",          # rm -rf / or ~
        r"sudo\s+",                    # any sudo usage
        r"chmod\s+777",                # world-writable permissions
        r"\|\s*(ba)?sh\b",            # piping to shell
        r"eval\s*\(",                  # eval execution
        r">/dev/sd[a-z]",             # writing to block devices
        r"mkfs\.",                     # filesystem creation
        r"dd\s+if=",                   # raw disk operations
        r"curl\s+.*\|\s*(ba)?sh",     # curl | bash patterns
        r"wget\s+.*\|\s*(ba)?sh",     # wget | bash patterns
        r"python\s+-c\s+",            # inline python execution
        r"nc\s+-l",                    # netcat listener
        r"nmap\s+",                    # network scanning
        r"iptables\s+",               # firewall modification
        r"systemctl\s+(stop|disable)", # stopping services
        r"kill\s+-9",                  # force kill
        r"docker\s+rm\s+-f",          # force remove containers
        r"docker\s+system\s+prune",   # prune docker
        r"git\s+push\s+.*--force",    # force push
        r"git\s+reset\s+--hard",      # hard reset
        r"DROP\s+(TABLE|DATABASE)",    # SQL destructive
        r"TRUNCATE\s+",               # SQL truncate
    ]
]

# Tools that are high-risk and require explicit approval
DANGEROUS_TOOL_NAMES = frozenset({
    "exec",
    "spawn",
    "shell",
    "sessions_spawn",
    "sessions_send",
    "fs_delete",
    "fs_move",
    "apply_patch",
    "sandbox_destroy",
})

# Blocked host paths that should never be mounted or accessed
BLOCKED_HOST_PATHS = frozenset({
    "/etc",
    "/proc",
    "/sys",
    "/dev",
    "/root",
    "/boot",
    "/var/run/docker.sock",
    "/run/docker.sock",
})


def is_dangerous_command(command: str) -> list[str]:
    """Check if a command matches any dangerous patterns.

    Returns list of matched pattern descriptions. Empty = safe.
    """
    matches: list[str] = []
    for pattern in _DANGEROUS_COMMAND_PATTERNS:
        if pattern.search(command):
            matches.append(pattern.pattern)
    return matches


def is_dangerous_tool(tool_name: str) -> bool:
    """Check if a tool name is in the dangerous tools set."""
    return tool_name.lower() in DANGEROUS_TOOL_NAMES


def is_blocked_path(path: str) -> bool:
    """Check if a path is in the blocked host paths set."""
    normalized = path.rstrip("/")
    return any(
        normalized == blocked or normalized.startswith(f"{blocked}/")
        for blocked in BLOCKED_HOST_PATHS
    )
