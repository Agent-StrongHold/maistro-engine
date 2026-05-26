"""Lightweight OS / runtime detection for the install wizard."""

from __future__ import annotations

import os
import platform
import re
from pathlib import Path


def uname_summary() -> str:
    u = platform.uname()
    return f"{u.system} {u.release} ({u.machine})"


def is_wsl() -> bool:
    rel = platform.release().lower()
    if "microsoft" in rel or "wsl" in rel:
        return True
    try:
        return (
            "microsoft"
            in Path("/proc/version").read_text(encoding="utf-8", errors="replace").lower()
        )
    except OSError:
        return False


def linux_distro_guess() -> str | None:
    try:
        os_release = Path("/etc/os-release").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = re.search(r'^PRETTY_NAME="([^"]+)"', os_release, re.MULTILINE)
    if m:
        return m.group(1)
    m2 = re.search(r"^PRETTY_NAME=(.+)$", os_release, re.MULTILINE)
    return m2.group(1).strip('"') if m2 else None


def deployment_hint() -> str:
    sys = platform.system().lower()
    if sys == "darwin":
        return "macOS: Homebrew is common for Docker Desktop or Colima; see https://brew.sh/"
    if sys == "linux":
        if is_wsl():
            return "WSL2: use Docker Desktop WSL integration or Docker Engine inside the distro."
        d = linux_distro_guess()
        if d:
            return f"Linux ({d}): install Docker Engine or Podman per distro docs."
        return "Linux: install Docker Engine or Podman per distro docs."
    if sys == "windows":
        return "Windows: use WSL2 + Linux installer path, or Docker Desktop."
    return "Unknown platform: use a Linux VM or supported container host."


def has_command(name: str) -> bool:
    path = os.environ.get("PATH", "")
    for p in path.split(os.pathsep):
        exe = Path(p) / name
        if exe.is_file() and os.access(exe, os.X_OK):
            return True
    return False


def deployment_tier_gate_message(tier: str) -> str | None:
    """Non-blocking guidance when compose automation is not assumed for this tier."""
    if tier == "proxmox":
        return (
            "Proxmox: the installer does not configure hypervisors. Run Docker/Podman on a "
            "Linux VM or bare-metal guest, then use stack_bringup from that environment."
        )
    if tier == "lxc":
        return (
            "LXC: privilege and cgroup policies vary; prefer a VM with a supported Docker Engine "
            "install, then point MAISTRO_REPO_ROOT at your clone."
        )
    if tier == "vm":
        return (
            "VM: ensure Docker Engine or Podman is installed inside the VM; maistro-install "
            "detects repo root from the VM filesystem."
        )
    return None


def detect_container_runtime() -> tuple[str, str]:
    """Return (detected, hint) where detected is docker | podman | none."""
    d, p = has_command("docker"), has_command("podman")
    if d and p:
        return "both", "Both docker and podman are on PATH; pick one in answers."
    if d:
        return "docker", "docker is on PATH."
    if p:
        return "podman", "podman is on PATH (no docker)."
    return "none", "No docker/podman on PATH — install a container runtime first."
